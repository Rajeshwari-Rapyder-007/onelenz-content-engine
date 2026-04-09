# MS365 Connector — Email Connectivity Technical Specification

## 1. Overview

### Purpose
The MS365 connector service (email module) enables OneLenz users to connect their Microsoft 365 mailbox, automatically ingest the last 30 days of email, and maintain continuous incremental sync every 15 minutes — all self-serve with no IT admin intervention.

### Tech Stack
| Component | Technology |
|-----------|-----------|
| Backend | Python, FastAPI |
| Database | PostgreSQL 17.6+ (async via SQLAlchemy + asyncpg) |
| Cache / Broker | Redis 6.4 (auth sessions + Celery broker) |
| Object Storage | AWS S3 (email body + attachments) |
| Scheduler | Celery Beat + Celery Worker |
| Email API | Microsoft Graph API v1.0 |
| Auth Provider | Azure Entra ID (multi-tenant app, delegated permissions) |
| Encryption | AWS Secrets Manager / KMS (token encryption) |

### Architecture
```
User clicks "Connect Outlook"
  → email-connector API (OAuth flow)
    → Microsoft consent + token exchange
    → Store encrypted tokens in integration_config (Postgres)
    → Trigger initial full fetch (Celery task)

Every {sync_frequency} (Celery Beat):
  → Check consent gate
  → Ensure access token is fresh (refresh if expired/expiring)
  → Present delta token to Microsoft Graph API (delta endpoint with $filter for full fetch)
  → Fetch new/changed emails
  → Metadata → RAW_INGEST_LOG (Postgres, status=QUEUED)
  → Body + attachments → S3
  → Signal/ML pipeline polls QUEUED rows from RAW_INGEST_LOG
```

### Shared Modules Reused
| Module | Usage |
|--------|-------|
| `shared/db/` | DB adapter, base repository, base model |
| `shared/auth/middleware.py` | `get_current_user` — protects all email-connector APIs |
| `shared/logging/` | Structured logging with request context |
| `shared/redis/` | Redis client for OAuth state + sync locks |
| `shared/errors/` | Centralized `AppError` + error codes |

---

## 2. Azure App Registration

### Setup (one-time, done by OneLenz admin)

Register a multi-tenant app in Azure Portal → App Registrations:

| Setting | Value |
|---------|-------|
| Name | OneLenz |
| Supported account types | Accounts in any organizational directory (Multi-tenant) |
| Redirect URI (Web) | `https://{frontend-domain}/settings/integrations/callback` (redirects to UI, not backend) |

### Credentials
| Item | Where stored |
|------|-------------|
| Client ID (Application ID) | Env var: `MS_OAUTH_CLIENT_ID` |
| Client Secret | AWS Secrets Manager → env var: `MS_OAUTH_CLIENT_SECRET` |

### API Permissions (all Delegated, not Application)
| Permission | Type | Why |
|-----------|------|-----|
| `Mail.Read` | Delegated | Read user's mailbox |
| `User.Read` | Delegated | Read user profile (email, UPN) |
| `offline_access` | Delegated | Get refresh token for long-lived access |

**No admin consent required** — users approve for their own account.

---

## 3. OAuth 2.0 Connection Flow

### Step-by-Step

```
1. User clicks "Connect Microsoft 365" in OneLenz UI
2. UI calls POST /email/connect
3. Backend:
   a. Verify user has active OneLenz session (get_current_user middleware)
   b. Check EMAIL_SCAN consent exists and is valid
   c. Generate a random state token (UUID4)
   d. Store state in Redis: {env}:onelenz:email:oauth_state:{state} → { user_id, entity_id } (TTL 10 min)
   e. Build Microsoft authorization URL (redirect_uri = frontend callback URL)
   f. Return URL to UI
4. UI redirects user to Microsoft login page (same browser tab)
5. User logs into Microsoft 365, approves consent screen
6. Microsoft redirects browser to: {FRONTEND_URL}/settings/integrations/callback?code={auth_code}&state={state}
7. UI callback page:
   a. Reads code and state from URL query params
   b. Shows "Connecting..." spinner
   c. Calls POST /email/callback with { code, state }
8. Backend:
   a. Validate state exists in Redis (CSRF protection)
   b. Delete state from Redis
   c. Exchange auth_code for access_token + refresh_token via Microsoft token endpoint
   d. Fetch user profile (/me) to get UPN, tenant_id
   e. Encrypt tokens (AES-256)
   f. INSERT into integration_config (status=CONNECTED, sync_mode=full_fetch)
   g. Dispatch Celery task: initial_full_fetch(config_id)
   h. Return { status: "CONNECTED" } to UI
9. UI navigates to /settings/integrations, shows connected status
10. Celery worker runs full fetch in background (see Section 6)
```

### Microsoft Authorization URL
```
https://login.microsoftonline.com/common/oauth2/v2.0/authorize
  ?client_id={MS_OAUTH_CLIENT_ID}
  &response_type=code
  &redirect_uri={MS_OAUTH_REDIRECT_URI}
  &scope=Mail.Read User.Read offline_access
  &state={state_token}
  &response_mode=query
```

### Microsoft Token Endpoint
```
POST https://login.microsoftonline.com/common/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id={MS_OAUTH_CLIENT_ID}
&client_secret={MS_OAUTH_CLIENT_SECRET}
&code={auth_code}
&redirect_uri={MS_OAUTH_REDIRECT_URI}
&grant_type=authorization_code
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "0.AT...",
  "expires_in": 3600,
  "token_type": "Bearer",
  "scope": "Mail.Read User.Read"
}
```

---

## 4. Integration Config Design

### Table: integration_config

One row per user per provider. Stores all OAuth state and sync metadata.

| Column | Type | Description |
|--------|------|-------------|
| inc_config_id | SERIAL | PK |
| inc_entity_id | VARCHAR(50) | Tenant isolation |
| inc_user_id | VARCHAR(50) | OneLenz user ID |
| inc_integration_type | VARCHAR(20) | `EMAIL` |
| inc_provider | VARCHAR(20) | `o365` |
| inc_auth_status | VARCHAR(20) | PENDING / CONNECTED / AUTH_FAILED / DISCONNECTED |
| inc_sync_frequency | VARCHAR(20) | `every_15min` |
| inc_last_sync_at | TIMESTAMPTZ | Last successful sync timestamp |
| inc_is_active | BOOLEAN | Active flag |
| inc_config_json | JSONB | Encrypted tokens + sync state (see below) |
| (audit columns) | | created_by, created_on, modified_by, modified_on |

### inc_config_json Structure (for EMAIL + o365)

| Field | Type | Description |
|-------|------|-------------|
| access_token | string | AES-256 encrypted Microsoft access token |
| access_token_expiry | string (ISO 8601) | When access token expires |
| refresh_token | string | AES-256 encrypted Microsoft refresh token |
| user_upn | string | Microsoft UPN (email), plaintext |
| tenant_id | string | Microsoft tenant ID, plaintext |
| sync_mode | string | `full_fetch` or `incremental` |
| days_to_fetch | int | Default 30, capped at 90 |
| inbox_delta_token | string | null until first incremental run; Microsoft-issued bookmark for inbox |
| sent_delta_token | string | null until first incremental run; Microsoft-issued bookmark for sent items |
| delta_token_updated_at | string (ISO 8601) | When delta tokens were last saved |
| initial_sync_complete | boolean | true after first full fetch |
| total_emails_synced | int | Running count |
| auth_failed_at | string (ISO 8601) | null unless AUTH_FAILED |
| auth_fail_reason | string | null unless AUTH_FAILED |

---

## 5. Consent Management

### Purpose
Before reading any email, the system must verify the user/entity has granted EMAIL_SCAN consent. This is a mandatory gate checked on every sync run.

### Table: consent_management

| Column | Type | Description |
|--------|------|-------------|
| cm_id | SERIAL | PK |
| cm_entity_id | VARCHAR(50) | Tenant |
| cm_user_id | VARCHAR(50) | User who granted consent |
| cm_consent_type | VARCHAR(20) | `EMAIL_SCAN` |
| cm_domain_scope | VARCHAR(100) | `ALL` or specific domain |
| cm_is_granted | BOOLEAN | Active consent flag |
| cm_granted_by | VARCHAR(50) | Who granted |
| cm_granted_at | TIMESTAMPTZ | When granted |
| cm_revoked_at | TIMESTAMPTZ | null if active |
| cm_created_on | TIMESTAMPTZ | |

### Consent Gate Logic (checked every sync run)
```
SELECT FROM consent_management
WHERE cm_entity_id = {entity_id}
  AND cm_consent_type = 'EMAIL_SCAN'
  AND cm_is_granted = true
  AND cm_revoked_at IS NULL
```
If no row found → sync halted, integration paused (not AUTH_FAILED).

### APIs

**POST /consent/grant**
- Auth: Protected (get_current_user)
- Body: `{ "consent_type": "EMAIL_SCAN", "domain_scope": "ALL" }`
- Logic: Insert into consent_management with is_granted=true, granted_at=now
- Response: 201 `{ "consent_id": 1, "consent_type": "EMAIL_SCAN", "granted_at": "..." }`

**POST /consent/revoke**
- Auth: Protected
- Body: `{ "consent_type": "EMAIL_SCAN" }`
- Logic: Update cm_revoked_at=now, cm_is_granted=false for entity + consent_type
- Response: 200 `{ "message": "Consent revoked" }`

**GET /consent/status**
- Auth: Protected
- Query: `?consent_type=EMAIL_SCAN`
- Response: 200 `{ "consent_type": "EMAIL_SCAN", "is_granted": true, "granted_at": "...", "revoked_at": null }`
- If no consent: 200 `{ "consent_type": "EMAIL_SCAN", "is_granted": false }`

---

## 6. Email Sync — Full Fetch (Initial)

### Trigger
Dispatched as a Celery task immediately after OAuth callback completes.

### Flow

1. Load integration_config by config_id
2. **Consent gate check** — if consent invalid → abort, set status to paused
3. **Ensure token freshness** — if expired/expiring within 5 min, refresh first (see Section 8). If refresh fails → mark AUTH_FAILED, abort.
4. Decrypt access token from inc_config_json
5. Calculate date range: `receivedDateTime ge {now - 30 days}`
6. Cap to 90 days maximum
7. **Call Microsoft Graph API delta endpoint for both Inbox and Sent Items:**

   Both folders use the **delta endpoint** with `$filter` for the initial full fetch. This acquires a delta token on the last page, which is then used for subsequent incremental syncs — no separate delta token acquisition step is needed.

   **Inbox:**
   ```
   GET https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta
     ?$filter=receivedDateTime ge {start_date}
     &$orderby=receivedDateTime desc
     &$select=id,subject,from,toRecipients,ccRecipients,bccRecipients,
              receivedDateTime,sentDateTime,bodyPreview,body,hasAttachments,
              internetMessageId,isRead,isDraft,importance,inferenceClassification,
              conversationId,parentFolderId,flag
   Prefer: odata.maxpagesize=200
   ```

   **Sent Items:**
   ```
   GET https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages/delta
     ?$filter=receivedDateTime ge {start_date}
     &$orderby=receivedDateTime desc
     &$select=id,subject,from,toRecipients,ccRecipients,bccRecipients,
              receivedDateTime,sentDateTime,bodyPreview,body,hasAttachments,
              internetMessageId,isRead,isDraft,importance,inferenceClassification,
              conversationId,parentFolderId,flag
   Prefer: odata.maxpagesize=200
   ```

   Both folders use `receivedDateTime` for the filter (not `sentDateTime` for sent items). Page size is controlled via the `Prefer: odata.maxpagesize=200` header (not `$top`). Both folders are processed with the same pipeline. Dedup by `internetMessageId` prevents duplicates.

8. **INSERT into email_sync_audit** with status=IN_PROGRESS at the start of sync (before any Graph API calls).

9. **Concurrent processing pipeline (`_process_emails`) — 5 phases per page:**

   **Phase 1: Filter** — Remove drafts, emails with missing `internetMessageId`, and in-page duplicates.

   **Phase 2: Batch dedup** — One `IN` query against `raw_ingest_log` to check which `internetMessageId` values already exist for the entity (not N individual queries).

   **Phase 3: Batch attachment metadata** — For emails with `hasAttachments=true`, fetch attachment metadata (no content) via Graph `$batch` API in chunks of 20. Inline images (`isInline=true`) are skipped. Attachments >25MB are skipped with a warning logged.

   **Phase 4: Concurrent downloads + S3 uploads** — `asyncio.gather` with semaphores:
   - 10 concurrent Graph API calls for attachment `/$value` downloads
   - 20 concurrent S3 uploads for email bodies + attachments
   - Each attachment: download binary via `GET /me/messages/{id}/attachments/{attachmentId}/$value`, upload to S3
   - Each email body: build JSON payload, upload to S3

   **Phase 5: Sequential DB writes** — INSERT/UPSERT into `raw_ingest_log` with batch commit every 100 emails:
   - ril_entity_id = entity_id
   - ril_source_tag = `EMAIL`
   - ril_integration_cfg_id = config_id
   - ril_source_ref_id = internet_message_id (dedup key)
   - ril_conversation_id = conversationId (thread grouping)
   - ril_raw_payload = email metadata JSONB
   - ril_ingest_status = `QUEUED`

10. **Handle pagination:** Follow `@odata.nextLink` until no more pages. Delta token (`@odata.deltaLink`) appears on the last page of the response.

11. **On completion:**
   - Save delta token from last page: `@odata.deltaLink` (for both inbox and sent items)
   - Update integration_config: sync_mode=incremental, initial_sync_complete=true, total_emails_synced=count
   - Update inc_auth_status to `CONNECTED`
   - **Update email_sync_audit:** status=SUCCESS, emails_fetched/new/changed counts

12. **On error:** Log error
   - **Update email_sync_audit:** status=FAILED, error_detail
   - Celery task retry handles re-attempts

### Rate Limiting
Microsoft Graph: 10,000 requests per 10 min per app per tenant. If 429 received → respect `Retry-After` header, back off and retry.

### Large Mailbox Handling
For users with high email volume (e.g. 50,000 emails in 30 days):
- Full fetch processes pages of up to 200 emails each (via `Prefer: odata.maxpagesize=200`)
- Celery task timeout: 30 minutes. If exceeded, mark sync as PARTIAL in email_sync_audit and resume from last processed page on next run.
- Commit to DB in batches of 100 emails (not one giant transaction)
- Sync lock is extended after each batch commit to prevent lock expiration during long syncs

### Large Attachment Handling
- Graph API returns attachments up to **3MB inline** in the response
- Attachments **> 3MB** require a separate download: `GET /me/messages/{id}/attachments/{attachmentId}/$value`
- Max attachment size: **25MB** (Outlook limit). Skip attachments larger than this and log a warning.
- Store metadata for all attachments regardless of size

### Email Dedup
- Dedup key: `ril_source_ref_id` (internet_message_id) + `ril_entity_id`
- If User A and User B from the same entity both connect, the same email is stored once per entity (not per user)
- On INSERT, check if `ril_source_ref_id` already exists for the entity — if yes, skip

---

## 7. Email Sync — Incremental (Every 15 min)

### Trigger
Celery Beat schedules `incremental_sync` task every 15 minutes.

### Flow

1. Query all active integrations: `SELECT FROM integration_config WHERE inc_integration_type='EMAIL' AND inc_is_active=true AND inc_auth_status='CONNECTED'`
2. **For each integration:**
   a. **Consent gate check** — skip if consent invalid
   b. **Ensure token freshness** — if expired/expiring within 5 min, refresh first (see Section 8). If refresh fails → mark AUTH_FAILED, skip.
   c. Decrypt access token
   d. **Call delta endpoint for both Inbox and Sent Items:**

      **When delta tokens exist** (normal case):
      ```
      GET {saved_deltaLink_url}
      ```
      The saved `@odata.deltaLink` URL already contains all necessary parameters. Follow `@odata.nextLink` for pagination, save new `@odata.deltaLink` from the last page.

      **When delta tokens don't exist** (edge case / fallback):
      Use delta endpoint with date filter — same as full fetch but with a shorter window (`receivedDateTime ge {last_sync_at - 5min}`):
      ```
      GET https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta
        ?$filter=receivedDateTime ge {last_sync_at - 5min}
        &$orderby=receivedDateTime desc
        &$select=id,subject,from,toRecipients,ccRecipients,bccRecipients,...
      Prefer: odata.maxpagesize=200
      ```
      If no `last_sync_at` is available, falls back to 1 day lookback.

   d. **Process emails** through the same concurrent `_process_emails` pipeline as full fetch (5 phases: filter, batch dedup, batch attachment metadata, concurrent downloads/uploads, sequential DB writes with batch commit every 100).
   e. **Handle pagination** — follow `@odata.nextLink`
   f. **Save new delta token** from `@odata.deltaLink` on the last page
   g. Update integration_config: inc_last_sync_at=now, total_emails_synced+=count
   h. **Update email_sync_audit** (started as IN_PROGRESS at beginning): status=SUCCESS/FAILED, email counts, error detail if any

### Sync Lock
Before starting sync for a user, acquire Redis lock:
```
{env}:onelenz:email:sync_lock:{config_id}  (TTL = 10 min)
```
If lock exists → skip this user (previous sync still running). Prevents overlapping syncs.

---

## 8. Token Management

### Microsoft Token Lifecycle
| Token | Validity | Our action |
|-------|----------|-----------|
| Access token | ~60 min | Refreshed inline at start of each sync if expired/expiring |
| Refresh token | ~90 days (or until revoked) | Store encrypted, use to get new access token |

### Token Refresh (inline, at start of every sync)

No separate refresh task. Each sync job ensures token freshness before making Graph API calls:

1. Read `access_token_expiry` from integration_config
2. If token is **expired or expiring within 5 min**:
   a. Decrypt refresh token
   b. Call Microsoft token endpoint:
      ```
      POST https://login.microsoftonline.com/common/oauth2/v2.0/token
      client_id={MS_OAUTH_CLIENT_ID}
      &client_secret={MS_OAUTH_CLIENT_SECRET}
      &refresh_token={decrypted_refresh_token}
      &grant_type=refresh_token
      &scope=Mail.Read User.Read offline_access
      ```
   c. If success → encrypt new tokens, update integration_config, proceed with sync
   d. If failure (invalid_grant) → mark AUTH_FAILED (see Section 9), abort sync
3. If token is **still fresh** → proceed with sync directly

This approach:
- Works regardless of sync frequency (15 min, 2 hr, daily)
- No separate Celery task to manage
- Token is always fresh exactly when needed
- Between syncs, a dead token doesn't matter — nothing is using it

### Token Encryption
- Algorithm: AES-256-GCM
- Key source: AWS Secrets Manager (env var: `TOKEN_ENCRYPTION_KEY`)
- Encrypted before writing to inc_config_json
- Decrypted only when making Graph API calls
- **Never log tokens** — not in request logs, error messages, or debug output

---

## 9. Error Recovery

### Scenario A: Stale Delta Token
**Cause:** Microsoft no longer recognises the delta token (~30+ days without sync).
**Detection:** Graph API returns 410 Gone or delta query fails.
**Recovery:**
1. Discard stale delta token
2. Fall back to delta endpoint with date filter (`receivedDateTime ge {now - N days}`) — same pipeline as full fetch but re-acquires a fresh delta token
3. Save fresh delta token from last page
4. Resume incremental sync
5. No user action required

### Scenario B: Access Token Expired Mid-Sync
**Cause:** Token expired during a long sync operation.
**Detection:** Graph API returns 401.
**Recovery:**
1. Silently refresh using stored refresh token
2. Retry the failed request once
3. If retry succeeds → continue sync
4. If retry fails → mark as Scenario C

### Scenario C: Refresh Token Dead
**Cause:** User revoked OneLenz in Microsoft, or refresh token expired (~90 days idle).
**Detection:** Token refresh returns `invalid_grant`.
**Recovery:**
1. Mark integration: inc_auth_status = `AUTH_FAILED`
2. Set auth_failed_at and auth_fail_reason in inc_config_json
3. Stop all sync for this integration
4. Send notification email to user with re-auth link
5. On re-auth → new OAuth flow → full fetch (90-day cap) → resume incremental

### Scenario D: Consent Expired/Revoked
**Cause:** Admin revoked EMAIL_SCAN consent between sync cycles.
**Detection:** Consent gate check fails at start of sync.
**Recovery:**
1. Pause sync — do NOT mark AUTH_FAILED (different state)
2. Integration remains CONNECTED but sync skipped
3. On consent renewal → sync resumes automatically on next cycle

### Scenario E: Rate Limiting
**Cause:** Graph API returns 429 Too Many Requests.
**Recovery:**
1. Read `Retry-After` header (seconds)
2. Wait the specified duration
3. Retry the request
4. If repeated 429 → back off exponentially (max 5 min)
5. Log as warning, don't mark as failure

### Scenario F: 5xx Server Error from Graph
**Cause:** Graph API returns 500, 502, 503, or 504.
**Detection:** HTTP status code >= 500.
**Recovery:**
1. Read `Retry-After` header (default 5 seconds if not present)
2. Wait the specified duration
3. Retry the request once
4. If still fails → let the Celery task retry mechanism handle it (max 3 retries with exponential backoff)

---

## 10. API Specifications

### POST /email/connect

**Auth:** Protected (get_current_user)
**Description:** Initiate OAuth flow. Returns Microsoft authorization URL.

**Request:** None (user context from JWT)

**Business Logic:**
1. Verify EMAIL_SCAN consent exists and is valid
2. Check if user already has an active EMAIL integration → if yes, return error
3. Generate state token (UUID4)
4. Store state in Redis with TTL 10 min
5. Build Microsoft authorization URL
6. Return URL

**Response — 200 OK:**
```json
{
  "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...",
  "state": "uuid"
}
```

**Errors:**
| Status | Condition |
|--------|-----------|
| 400 | Integration already exists for this user |
| 403 | EMAIL_SCAN consent not granted |
| 401 | Not authenticated |

---

### POST /email/callback

**Auth:** Protected (get_current_user)
**Description:** Receives authorization code from UI after Microsoft redirect. Exchanges code for tokens.

**Body:**
```json
{
  "code": "M.C507_BAI.2.U.xxx",
  "state": "uuid"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | string | Yes | Authorization code from Microsoft (passed via UI from URL query param) |
| state | string | Yes | CSRF state token (passed via UI from URL query param) |

**Business Logic:**
1. Validate state exists in Redis
2. Delete state from Redis
3. Exchange code for tokens via Microsoft token endpoint (using client_secret, server-side)
4. Fetch user profile (/me) → get UPN, tenant_id
5. Encrypt tokens
6. Create integration_config row (status=CONNECTED, sync_mode=full_fetch)
7. Dispatch Celery task: initial_full_fetch
8. Return success to UI

**Response — 200 OK:**
```json
{
  "status": "CONNECTED",
  "message": "Email integration connected successfully"
}
```

**Errors:**
| Status | Condition |
|--------|-----------|
| 400 | Invalid or expired state token |
| 400 | Microsoft returned error (user declined consent) |
| 401 | Not authenticated |
| 500 | Token exchange failed |

---

### GET /email/status

**Auth:** Protected
**Description:** Get current integration status and sync stats.

**Response — 200 OK (connected):**
```json
{
  "status": "CONNECTED",
  "provider": "o365",
  "user_email": "admin@company.com",
  "total_emails_synced": 1247,
  "last_sync_at": "2026-03-18T10:15:00Z",
  "sync_frequency": "every_15min",
  "initial_sync_complete": true,
  "connected_at": "2026-03-15T09:00:00Z"
}
```

**Response — 200 OK (not connected):**
```json
{
  "status": "NOT_CONNECTED"
}
```

---

### POST /email/disconnect

**Auth:** Protected
**Description:** Stop syncing, mark integration as disconnected. Data is retained.

**Business Logic:**
1. Set inc_auth_status = `DISCONNECTED`
2. Set inc_is_active = false
3. Syncing stops (Celery skips inactive integrations)
4. Existing data in raw_ingest_log and S3 is retained

**Response — 200 OK:**
```json
{
  "message": "Disconnected. Synced data has been retained."
}
```

### Re-connect after disconnect
When a user clicks Connect again after disconnecting:
1. Check if a DISCONNECTED integration_config row exists for this user + entity + EMAIL + o365
2. If found → reactivate the existing row:
   - Set inc_is_active = true
   - Set inc_auth_status = PENDING
   - Clear old tokens from inc_config_json
   - Proceed with OAuth flow (new tokens will be stored on callback)
   - After OAuth → trigger full fetch (delta token was stale) → resume incremental
3. If not found → create new row (normal flow)

This preserves the config_id linkage to historical raw_ingest_log rows.

---

### POST /email/sync

**Auth:** Protected (admin only)
**Description:** Trigger a manual sync outside the 15-min schedule.

**Business Logic:**
1. Verify integration is CONNECTED
2. Check consent gate
3. Dispatch Celery task: incremental_sync(config_id)

**Response — 202 Accepted:**
```json
{
  "message": "Sync triggered",
  "config_id": 1
}
```

---

### POST /consent/grant

**Auth:** Protected
**Body:**
```json
{
  "consent_type": "EMAIL_SCAN",
  "domain_scope": "ALL"
}
```

**Business Logic:**
1. Check if consent already exists for entity + type
2. If exists and is_granted=true → return existing
3. If exists and revoked → update: is_granted=true, revoked_at=null, granted_at=now
4. If not exists → insert new row

**Response — 201 Created:**
```json
{
  "consent_id": 1,
  "consent_type": "EMAIL_SCAN",
  "is_granted": true,
  "granted_at": "2026-03-18T10:00:00Z"
}
```

---

### POST /consent/revoke

**Auth:** Protected
**Body:**
```json
{
  "consent_type": "EMAIL_SCAN"
}
```

**Business Logic:**
1. Find active consent for entity + type
2. Set cm_is_granted=false, cm_revoked_at=now
3. Active syncs will halt on next consent check

**Response — 200 OK:**
```json
{
  "message": "Consent revoked"
}
```

---

### GET /consent/status

**Auth:** Protected
**Query:** `?consent_type=EMAIL_SCAN`

**Response — 200 OK:**
```json
{
  "consent_type": "EMAIL_SCAN",
  "is_granted": true,
  "granted_at": "2026-03-18T10:00:00Z",
  "revoked_at": null
}
```

---

## 11. S3 Storage Design

### Bucket
`onelenz-emails` (one bucket for all entities, partitioned by entity_id)

### Structure
```
s3://onelenz-emails/
  {entity_id}/
    {internet_message_id}.json          ← full email body (HTML + text)
    attachments/
      {internet_message_id}/
        {attachment_id}_{filename}      ← binary attachment
```

### Email Body JSON (stored in S3)
```json
{
  "id": "graph_message_id",
  "internetMessageId": "RFC2822_message_id",
  "subject": "...",
  "from": { "emailAddress": { "name": "...", "address": "..." } },
  "toRecipients": [...],
  "ccRecipients": [...],
  "body": { "contentType": "html", "content": "..." },
  "receivedDateTime": "...",
  "isRead": true,
  "importance": "normal",
  "hasAttachments": true,
  "attachments": [
    {
      "id": "attachment_id",
      "name": "report.pdf",
      "size": 45678,
      "contentType": "application/pdf",
      "s3_key": "s3://onelenz-emails/{entity_id}/attachments/{msg_id}/att_id_report.pdf"
    }
  ]
}
```

### RAW_INGEST_LOG Reference
`ril_raw_payload` (JSONB in Postgres) stores email **metadata only**:
```json
{
  "internetMessageId": "...",
  "subject": "...",
  "from": "sender@company.com",
  "to": ["a@b.com", "c@d.com"],
  "receivedDateTime": "...",
  "hasAttachments": true,
  "attachmentCount": 2,
  "s3_body_key": "s3://onelenz-emails/{entity_id}/{msg_id}.json",
  "isRead": true,
  "importance": "normal",
  "conversationId": "...",
  "parentFolderId": "..."
}
```

Body content is NOT in Postgres — only the S3 key to retrieve it.

### S3 Configuration
- **Encryption:** SSE-S3 (server-side encryption) enabled by default
- **Lifecycle:** Move to S3 Glacier after 90 days (configurable)
- **Access:** IAM role on EKS pods, no hardcoded credentials

---

## 12. Redis Key Design

| Key Pattern | Type | TTL | Purpose |
|------------|------|-----|---------|
| `{env}:onelenz:email:oauth_state:{state}` | String (JSON) | 10 min | CSRF state during OAuth flow |
| `{env}:onelenz:email:sync_lock:{config_id}` | String | 10 min | Prevent concurrent syncs for same user |

### OAuth State Value
```json
{
  "user_id": "uuid",
  "entity_id": "uuid",
  "config_id": null,
  "created_at": "2026-03-18T10:00:00Z"
}
```

---

## 13. Celery Beat Scheduler

### Periodic Tasks

| Task | Schedule | What it does |
|------|----------|-------------|
| `incremental_sync_all` | Configurable (default 15 min) | Loops through active integrations, ensures token freshness, runs delta sync for each |

**No separate token refresh task.** Token freshness is checked inline at the start of every sync (see Section 8). This simplifies scheduling and works regardless of sync frequency.

### Task Names
| Task Name | Description |
|-----------|-------------|
| `app.workers.sync_tasks.incremental_sync_all` | Scheduled: loops active integrations, dispatches sync_single for each |
| `app.workers.sync_tasks.sync_single` | Sub-task: sync one integration with lock protection |
| `app.workers.sync_tasks.initial_full_fetch` | One-time: full fetch after OAuth callback |

### Task Flow: incremental_sync_all
1. Query all active EMAIL integrations
2. For each, dispatch a sub-task: `sync_single(config_id)`
3. Sub-task:
   a. Acquires sync lock (Redis)
   b. Checks consent gate
   c. Ensures token freshness — refreshes if expired/expiring within 5 min
   d. Runs delta sync
   e. Releases lock

### Retry Policy
- Max retries: 3
- Retry backoff: 30s, 60s, 120s (exponential: `30 * (retry_count + 1)`)
- On final failure: log error, mark integration for review

### Celery Configuration
```
broker_url = redis://localhost:6379/1    ← separate Redis DB from auth sessions
result_backend = redis://localhost:6379/1
BEAT_ENABLED = true                      ← toggle via env var (default true)
beat_schedule = {
    "incremental_sync_all": {
        "task": "app.workers.sync_tasks.incremental_sync_all",
        "schedule": SYNC_FREQUENCY_MINUTES * 60,  ← seconds (not crontab)
    },
}
```

Worker uses **prefork** pool (not gevent). Each task creates a fresh event loop to run async code, resetting Redis and DB connections to avoid cross-fork issues.

---

## 14. Database Tables Reference

### integration_config
One row per user per provider. Stores OAuth tokens and sync state.

| Column | Type | Key/Notes |
|--------|------|-----------|
| inc_config_id | SERIAL | PK |
| inc_entity_id | VARCHAR(50) | Tenant isolation |
| inc_user_id | VARCHAR(50) | OneLenz user ID |
| inc_integration_type | VARCHAR(20) | EMAIL |
| inc_provider | VARCHAR(20) | o365 |
| inc_auth_status | VARCHAR(20) | PENDING / CONNECTED / AUTH_FAILED / DISCONNECTED |
| inc_sync_frequency | VARCHAR(20) | every_15min |
| inc_last_sync_at | TIMESTAMPTZ | Last successful sync |
| inc_is_active | BOOLEAN | Active flag |
| inc_config_json | JSONB | Encrypted tokens + sync state (see Section 4) |
| inc_created_by | VARCHAR(50) | Who created |
| inc_created_on | TIMESTAMPTZ | When created |
| inc_modified_by | VARCHAR(50) | Who last modified |
| inc_modified_on | TIMESTAMPTZ | When last modified |

### raw_ingest_log
One row per ingested email. Shared across all connectors.

| Column | Type | Key/Notes |
|--------|------|-----------|
| ril_id | BIGSERIAL | PK |
| ril_entity_id | VARCHAR(50) | Tenant isolation |
| ril_source_tag | VARCHAR(20) | EMAIL |
| ril_integration_cfg_id | INT | Maps to integration_config |
| ril_source_ref_id | VARCHAR(500) | internet_message_id (dedup key) |
| ril_conversation_id | VARCHAR(255) | Thread grouping key (conversationId from M365, threadId from Gmail). Indexed. |
| ril_raw_payload | JSONB | Email metadata + S3 reference keys |
| ril_ingest_status | VARCHAR(30) | QUEUED / PROCESSING / PROCESSED / UPDATED / FAILED |
| ril_queued_at | TIMESTAMPTZ | When queued |
| ril_processed_at | TIMESTAMPTZ | When signal engine processed it |
| ril_error_msg | TEXT | Error details on FAILED |
| ril_created_on | TIMESTAMPTZ | |
| ril_modified_on | TIMESTAMPTZ | |

### email_sync_audit
One row per sync run. Tracks every full fetch and incremental sync for debugging and monitoring.

| Column | Type | Key/Notes |
|--------|------|-----------|
| esa_sync_id | BIGSERIAL | PK |
| esa_entity_id | VARCHAR(50) | Tenant isolation |
| esa_config_id | INT | Maps to integration_config |
| esa_sync_type | VARCHAR(20) | FULL_FETCH / INCREMENTAL |
| esa_started_at | TIMESTAMPTZ | When sync started |
| esa_ended_at | TIMESTAMPTZ | When sync completed |
| esa_emails_fetched | INT | Total emails returned by Graph API |
| esa_emails_new | INT | New emails inserted |
| esa_emails_changed | INT | Changed emails upserted |
| esa_pages_fetched | INT | Graph API pages processed |
| esa_status | VARCHAR(20) | IN_PROGRESS / SUCCESS / PARTIAL / FAILED / AUTH_FAILED |
| esa_error_detail | TEXT | null on SUCCESS |
| esa_created_on | TIMESTAMPTZ | |

**Usage:**
- Created at the start of every sync run with status=IN_PROGRESS, updated to SUCCESS/FAILED on completion
- Powers admin sync dashboard (sync history, failure rate, email volume)
- Rows older than 90 days eligible for purge by maintenance job
- Query: `SELECT * FROM email_sync_audit WHERE esa_entity_id = X ORDER BY esa_started_at DESC`

### consent_management
Per-entity consent records.

| Column | Type | Key/Notes |
|--------|------|-----------|
| cm_id | SERIAL | PK |
| cm_entity_id | VARCHAR(50) | Tenant |
| cm_user_id | VARCHAR(50) | Who granted |
| cm_consent_type | VARCHAR(20) | EMAIL_SCAN |
| cm_domain_scope | VARCHAR(100) | ALL or specific domain |
| cm_is_granted | BOOLEAN | Active flag |
| cm_granted_by | VARCHAR(50) | |
| cm_granted_at | TIMESTAMPTZ | |
| cm_revoked_at | TIMESTAMPTZ | null if active |
| cm_created_on | TIMESTAMPTZ | |

---

## 15. Integration States

All 5 states must be implemented in the UI. The backend returns `status` field in GET /email/status.

| State | inc_auth_status | UI Display | User Action |
|-------|----------------|-----------|-------------|
| Not Connected | (no row exists) | "Connect" button | Click Connect |
| Pending | PENDING | OAuth in progress / loading spinner | Approve consent on Microsoft |
| Connected | CONNECTED | "Connected", last sync time, email count, "Disconnect" button | Disconnect |
| AUTH_FAILED | AUTH_FAILED | "Re-auth" button, error message | Click Re-auth |
| Disconnected | DISCONNECTED | "Connect" button, "Data retained" note | Reconnect |

---

## 16. Configuration

All environment variables for the email-connector service:

| Variable | Default | Description |
|----------|---------|-------------|
| MS_OAUTH_CLIENT_ID | | Azure app client ID |
| MS_OAUTH_CLIENT_SECRET | | Azure app client secret (from Secrets Manager) |
| MS_OAUTH_REDIRECT_URI | | OAuth redirect URI (actual env var, e.g. `https://{frontend-domain}/settings/integrations/callback`) |
| MS_GRAPH_BASE_URL | https://graph.microsoft.com/v1.0 | Graph API base URL |
| TOKEN_ENCRYPTION_KEY | | AES-256 key for encrypting tokens (from Secrets Manager) |
| S3_BUCKET_EMAILS | onelenz-emails | S3 bucket for email body + attachments |
| AWS_REGION | ap-south-1 | AWS region |
| CELERY_BROKER_URL | redis://localhost:6379/1 | Celery broker (separate Redis DB) |
| SYNC_FREQUENCY_MINUTES | 15 | How often to run incremental sync |
| TOKEN_REFRESH_BUFFER_MINUTES | 5 | Refresh token if expiring within this many minutes |
| BEAT_ENABLED | true | Toggle Celery Beat scheduler (set to false to disable periodic sync) |
| INITIAL_FETCH_DAYS | 30 | Days to look back on first connection (can be set to 2 for testing) |
| MAX_FETCH_DAYS | 90 | Absolute maximum lookback cap |
| FRONTEND_URL | http://localhost:3000 | For OAuth redirect back to UI |
| DATABASE_URL | (shared) | PostgreSQL connection |
| REDIS_URL | (shared) | Redis for auth sessions |
| ENVIRONMENT | dev | For Redis key prefix |

---

## 17. UI Integration Guide

### OAuth Flow (from UI perspective)
1. User clicks "Connect Microsoft 365"
2. UI calls `POST /email/connect` → gets `auth_url`
3. UI redirects browser to `auth_url` (same tab — leaves OneLenz)
4. User logs into Microsoft, approves consent
5. Microsoft redirects browser to `{FRONTEND_URL}/settings/integrations/callback?code=xxx&state=yyy`
6. React router loads callback page component
7. Callback component:
   a. Reads `code` and `state` from `window.location.search`
   b. Shows "Connecting..." spinner
   c. Calls `POST /email/callback` with `{ code, state }`
   d. On success → navigates to `/settings/integrations`
   e. On error → shows error message with "Try again" button

### UI Callback Page (`/settings/integrations/callback`)
```
React component:
  1. On mount: read code + state from URL params
  2. If no code → show error ("OAuth failed, try again")
  3. Call POST /email/callback { code, state }
  4. On 200 → navigate to /settings/integrations
  5. On 400 (expired state) → show "Session expired, please try again"
  6. On 500 → show "Something went wrong, please try again"
```

### Polling Sync Status
After navigating to integrations page, UI should poll `GET /email/status` every 5 seconds:
```
NOT_CONNECTED → (user clicks connect) → (Microsoft login) → (callback) → CONNECTED → (sync runs in background)
```
Stop polling once CONNECTED or AUTH_FAILED.

### Handling Each State

| State | UI Behavior |
|-------|------------|
| Not Connected | Show "Connect Microsoft 365" button with description |
| PENDING | Show loading spinner ("Connecting...") |
| CONNECTED | Show connected status, email count, last sync time, "Disconnect" button |
| AUTH_FAILED | Show error alert with "Re-auth" button. Re-auth calls POST /email/connect again |
| DISCONNECTED | Show "Connect" button with note "Your synced data has been retained" |

### Consent Flow (before connecting)
Before showing the "Connect" button, UI should check `GET /consent/status?consent_type=EMAIL_SCAN`:
- If `is_granted=true` → show Connect button
- If `is_granted=false` → show consent prompt first, call `POST /consent/grant`, then show Connect button

---

## 18. Known Limitations (v1)

| Limitation | Notes |
|-----------|-------|
| Inbox + Sent only | Drafts, Junk, Deleted Items and other folders are not synced. |
| M365 only | Gmail support is future scope. Abstract provider interfaces should be built to support it. |
| No email deletion tracking | If user deletes an email in Outlook, we don't remove it from raw_ingest_log. |
| No real-time sync | Delta polling only (configurable frequency). Webhooks are future scope. |
| Fixed sync defaults | Frequency, date range not user-configurable in v1. |
| No per-user dedup | Same email stored once per entity, not per user. Per-user read/unread status not tracked. |
| No data purge API | Data retention/erasure API is future scope. S3 lifecycle handles archival only. |
