# Email Connector — Test Documentation

**Project:** OneLenz
**Service:** email-connector
**Auth Service Base URL:** `http://localhost:8000`
**Email Connector Base URL:** `http://localhost:8001`
**Tool:** Postman

---

## Prerequisites

All email connector endpoints require a valid `access_token`. Run the Auth flow first (Signup → Login) to get one.

The full test flow follows this order:
1. Auth (Signup → Login → Refresh Token → Logout)
2. Consent (Grant → Status → Revoke)
3. Email Connector (Status → Connect → Callback → Status → Sync → Disconnect → Status → Reconnect)

---

## 1. Auth

### 1.1 Signup

- **Endpoint:** `POST /auth/signup`
- **Auth Required:** No

**Request Body:**
```json
{
  "email": "testuser@rapyder.com",
  "password": "password123",
  "first_name": "Test",
  "last_name": "User",
  "company_name": "Rapyder",
  "mobile": "9876543210"
}
```

#### TC-01: Valid Signup

**Input:** Body above

**Response:** `201 Created`
```json
{
  "user_id": "<uuid>",
  "entity_id": "<uuid>",
  "email": "testuser@rapyder.com",
  "display_name": "Test User",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "access_token_expires_at": "<datetime>",
  "refresh_token_expires_at": "<datetime>"
}
```

**Save:** `access_token`, `refresh_token`, `user_id`, `entity_id` for subsequent requests.

#### TC-02: Duplicate Email

**Precondition:** TC-01 already ran.

**Input:** Same body as TC-01.

**Response:** `409 Conflict`
```json
{
  "error": {
    "code": "EMAIL_ALREADY_EXISTS",
    "message": "Email already registered"
  }
}
```

---

### 1.2 Login

- **Endpoint:** `POST /auth/login`
- **Auth Required:** No

#### TC-03: Valid Login

**Input:**
```json
{
  "email": "testuser@rapyder.com",
  "password": "password123"
}
```

**Response:** `200 OK`
```json
{
  "user_id": "<uuid>",
  "entity_id": "<uuid>",
  "email": "testuser@rapyder.com",
  "display_name": "Test User",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "access_token_expires_at": "<datetime>",
  "refresh_token_expires_at": "<datetime>"
}
```

**Save:** `access_token`, `refresh_token` for subsequent requests.

#### TC-04: Wrong Password

**Input:**
```json
{
  "email": "testuser@rapyder.com",
  "password": "wrongpassword"
}
```

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid email or password"
  }
}
```

---

### 1.3 Refresh Token

- **Endpoint:** `POST /auth/refresh`
- **Auth Required:** No (token in body)

#### TC-05: Valid Refresh

**Input:**
```json
{
  "refresh_token": "<refresh_token from TC-03>"
}
```

**Response:** `200 OK`
```json
{
  "user_id": "<uuid>",
  "entity_id": "<uuid>",
  "email": "testuser@rapyder.com",
  "display_name": "Test User",
  "access_token": "eyJ... (new)",
  "refresh_token": "eyJ... (new)",
  "token_type": "Bearer",
  "access_token_expires_at": "<datetime>",
  "refresh_token_expires_at": "<datetime>"
}
```

**Save:** New `access_token` and `refresh_token`. Old tokens are now invalid.

#### TC-06: Invalid Refresh Token

**Input:**
```json
{
  "refresh_token": "invalid-token-string"
}
```

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "Invalid or expired token"
  }
}
```

---

### 1.4 Logout

- **Endpoint:** `POST /auth/logout`
- **Auth Required:** Yes — `Authorization: Bearer <access_token>`

#### TC-07: Valid Logout

**Headers:** `Authorization: Bearer <access_token from TC-05>`

**Response:** `200 OK`
```json
{
  "message": "Logged out successfully"
}
```

**Note:** Session is deleted from Redis. Login again before continuing to Section 2.

#### TC-08: No Token

**Headers:** No `Authorization` header.

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Unauthorized"
  }
}
```

---

## 2. Consent

**Precondition:** Login again after TC-07 logout. Save the new `access_token`.

All consent endpoints require: `Authorization: Bearer <access_token>`

---

### 2.1 Grant EMAIL_SCAN Consent

- **Endpoint:** `POST /consent/grant`
- **Auth Required:** Yes

#### TC-09: Valid Grant

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "consent_type": "EMAIL_SCAN",
  "domain_scope": "ALL"
}
```

**Response:** `201 Created`
```json
{
  "consent_id": 1,
  "consent_type": "EMAIL_SCAN",
  "is_granted": true,
  "granted_at": "<datetime>"
}
```

#### TC-10: Grant Already Active Consent (Idempotent)

**Precondition:** TC-09 already ran.

**Input:** Same body as TC-09.

**Response:** `201 Created` — returns the existing consent row, no duplicate created.
```json
{
  "consent_id": 1,
  "consent_type": "EMAIL_SCAN",
  "is_granted": true,
  "granted_at": "<datetime>"
}
```

#### TC-11: Missing consent_type

**Input:**
```json
{
  "domain_scope": "ALL"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "consent_type: Field required"
  }
}
```

#### TC-12: No Auth Token

**Headers:** No `Authorization` header.

**Input:**
```json
{
  "consent_type": "EMAIL_SCAN",
  "domain_scope": "ALL"
}
```

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Unauthorized"
  }
}
```
#### TC-13: if Auth Token expires

**Headers:** `Authorization` header acess token expires.

**Input:**
```json
{
  "consent_type": "EMAIL_SCAN",
  "domain_scope": "ALL"
}
```

**Response:** `401 Unauthorized`
```json
{
    "error": {
        "code": "INVALID_TOKEN",
        "message": "Invalid or expired token"
    }
}
```

---

### 2.2 Get Consent Status

- **Endpoint:** `GET /consent/status?consent_type=EMAIL_SCAN`
- **Auth Required:** Yes

#### TC-13: Status After Grant

**Precondition:** TC-09 ran successfully.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "consent_type": "EMAIL_SCAN",
  "is_granted": true,
  "granted_at": "<datetime>",
  "revoked_at": null
}
```

#### TC-14: Status When No Consent Exists

**Precondition:** No consent has been granted yet for this entity.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "consent_type": "EMAIL_SCAN",
  "is_granted": false
}
```

#### TC-15: Missing consent_type Query Param

**Headers:** `Authorization: Bearer <access_token>`

**URL:** `GET /consent/status` (no query param)

**Response:** `422 Unprocessable Entity`

---

### 2.3 Revoke Consent

- **Endpoint:** `POST /consent/revoke`
- **Auth Required:** Yes

#### TC-16: Valid Revoke

**Precondition:** TC-09 ran successfully.

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "consent_type": "EMAIL_SCAN"
}
```

**Response:** `200 OK`
```json
{
  "message": "Consent revoked"
}
```

#### TC-17: Get Status After Revoke

**Precondition:** TC-16 ran successfully.

**Headers:** `Authorization: Bearer <access_token>`

**URL:** `GET /consent/status?consent_type=EMAIL_SCAN`

**Response:** `200 OK`
```json
{
  "consent_type": "EMAIL_SCAN",
  "is_granted": false,
  "granted_at": "<datetime>",
  "revoked_at": "<datetime>"
}
```

**Note:** Re-grant consent before continuing to Section 3. Run TC-09 again.

---

## 3. Email Connector

**Precondition:**
- User is logged in with a valid `access_token`
- `EMAIL_SCAN` consent is active (TC-09 ran)

All email connector endpoints require: `Authorization: Bearer <access_token>`

---

### 3.1 Get Email Status (Before Connect)

- **Endpoint:** `GET /email/status`
- **Auth Required:** Yes

#### TC-18: Status When Not Connected

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
    "status": "DISCONNECTED",
    "provider": "o365",
    "user_email": "user@company.com",
    "total_emails_synced": 0,
    "last_sync_at": "datatime",
    "sync_frequency": "every_15min",
    "initial_sync_complete": true,
    "connected_at": "datatime"
}
```

#### TC-19: No Auth Token

**Headers:** No `Authorization` header.

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Unauthorized"
  }
}
```

---

### 3.2 Initiate OAuth Connect

- **Endpoint:** `POST /email/connect`
- **Auth Required:** Yes

#### TC-20: Valid Connect (Consent Active)

**Precondition:** `EMAIL_SCAN` consent is active.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...",
  "state": "<uuid>"
}
```

**Save:** `state` value for TC-22.

**Next step:** Open `auth_url` in a browser, log in with a Microsoft 365 account, approve consent. Microsoft will redirect to `{FRONTEND_URL}/settings/integrations/callback?code=xxx&state=yyy`. Copy the `code` and `state` from the URL.

#### TC-21: Connect Without Consent

**Precondition:** Revoke consent first (TC-16), then call connect.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `403 Forbidden`
```json
{
  "error": {
    "code": "MS365_CONSENT_REQUIRED",
    "message": "EMAIL_SCAN consent not granted"
  }
}
```

**Note:** Re-grant consent after this test.

#### TC-22: Connect When Already Connected

**Precondition:** TC-20 ran and OAuth callback completed (TC-23 succeeded). Integration is CONNECTED.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "MS365_INTEGRATION_EXISTS",
    "message": "Email integration already exists for this user"
  }
}
```

---

### 3.3 OAuth Callback

- **Endpoint:** `POST /email/callback`
- **Auth Required:** Yes

#### TC-23: Valid Callback

**Precondition:** TC-20 ran. `code` and `state` obtained from Microsoft redirect URL.

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "code": "<authorization_code from Microsoft redirect>",
  "state": "<state from TC-20 response>"
}
```

**Response:** `200 OK`
```json
{
  "status": "CONNECTED",
  "message": "Email integration connected successfully"
}
```

**Note:** This triggers the `initial_full_fetch` Celery task in the background. Check worker logs to confirm it started.

#### TC-24: Invalid State Token

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "code": "some-code",
  "state": "invalid-state-that-does-not-exist-in-redis"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "MS365_STATE_EXPIRED",
    "message": "OAuth state expired or invalid"
  }
}
```

#### TC-25: Expired State Token (After 10 Minutes)

**Precondition:** Call `POST /email/connect`, wait 10 minutes without completing the OAuth flow, then call callback with the old state.

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "code": "some-code",
  "state": "<state from 10+ minutes ago>"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "MS365_STATE_EXPIRED",
    "message": "OAuth state expired or invalid"
  }
}
```

#### TC-26: Missing code Field

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "state": "<valid state>"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "code: Field required"
  }
}
```

#### TC-27: Missing state Field

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "code": "<valid code>"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "state: Field required"
  }
}
```

---

### 3.4 Get Email Status (After Connect)

- **Endpoint:** `GET /email/status`
- **Auth Required:** Yes

#### TC-28: Status After Successful Connect

**Precondition:** TC-23 ran successfully.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "status": "CONNECTED",
  "provider": "o365",
  "user_email": "<microsoft_upn>",
  "total_emails_synced": 0,
  "last_sync_at": null,
  "sync_frequency": "every_15min",
  "initial_sync_complete": false,
  "connected_at": "<datetime>"
}
```

**Note:** `initial_sync_complete` will be `false` while the full fetch Celery task is still running. Poll this endpoint every few seconds until it becomes `true`.

#### TC-29: Status After Full Fetch Completes

**Precondition:** Wait for the `initial_full_fetch` Celery task to complete (check worker logs for "Full fetch completed").

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "status": "CONNECTED",
  "provider": "o365",
  "user_email": "<microsoft_upn>",
  "total_emails_synced": <number>,
  "last_sync_at": "<datetime>",
  "sync_frequency": "every_15min",
  "initial_sync_complete": true,
  "connected_at": "<datetime>"
}
```

---

### 3.5 Trigger Manual Sync (Admin Only)

- **Endpoint:** `POST /email/sync`
- **Auth Required:** Yes (Admin role required)

#### TC-30: Valid Manual Sync Trigger

**Precondition:** Integration is CONNECTED. User has ADMIN role.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `202 Accepted`
```json
{
  "message": "Sync triggered",
  "config_id": <number>
}
```

**Note:** Check worker logs for `sync_single` task being received and completed.

#### TC-31: Trigger Sync Without Consent

**Precondition:** Revoke consent (TC-16), then call sync.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `403 Forbidden`
```json
{
  "error": {
    "code": "MS365_CONSENT_REQUIRED",
    "message": "EMAIL_SCAN consent not granted"
  }
}
```

**Note:** Re-grant consent after this test.

#### TC-32: Trigger Sync When Not Connected

**Precondition:** No active integration exists for this user.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `404 Not Found`
```json
{
  "error": {
    "code": "MS365_NOT_CONNECTED",
    "message": "No active email integration found"
  }
}
```

#### TC-33: No Auth Token

**Headers:** No `Authorization` header.

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Unauthorized"
  }
}
```

---

### 3.6 Disconnect

- **Endpoint:** `POST /email/disconnect`
- **Auth Required:** Yes

#### TC-34: Valid Disconnect

**Precondition:** Integration is CONNECTED.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "message": "Disconnected. Synced data has been retained."
}
```

**Note:** `inc_is_active` is set to `false`, `inc_auth_status` set to `DISCONNECTED`. Celery scheduler will skip this integration on next run. All data in `raw_ingest_log` and S3 is retained.

#### TC-35: Disconnect When Not Connected

**Precondition:** No active integration exists (either never connected or already disconnected).

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `404 Not Found`
```json
{
  "error": {
    "code": "MS365_NOT_CONNECTED",
    "message": "No active email integration found"
  }
}
```

---

### 3.7 Get Email Status (After Disconnect)

- **Endpoint:** `GET /email/status`
- **Auth Required:** Yes

#### TC-36: Status After Disconnect

**Precondition:** TC-34 ran successfully.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "status": "DISCONNECTED",
  "provider": "o365",
  "user_email": "<microsoft_upn>",
  "total_emails_synced": <number>,
  "last_sync_at": "<datetime>",
  "sync_frequency": "every_15min",
  "initial_sync_complete": true,
  "connected_at": "<datetime>"
}
```

**Note:** Status is `DISCONNECTED`, not `NOT_CONNECTED`. The integration row still exists with historical data.

---

### 3.8 Reconnect (After Disconnect)

- **Endpoint:** `POST /email/connect` then `POST /email/callback`
- **Auth Required:** Yes

#### TC-37: Reconnect Flow — Initiate

**Precondition:** TC-34 ran (integration is DISCONNECTED).

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...",
  "state": "<uuid>"
}
```

**Note:** The existing `DISCONNECTED` integration row is reactivated (same `config_id` preserved). Open `auth_url` in browser, complete Microsoft login, copy `code` and `state` from redirect URL.

#### TC-38: Reconnect Flow — Callback
C-38: Status During Reconnect (PENDING)

**Precondition:** TC-37 ran. Do NOT complete the Microsoft login yet — call this immediately after TC-37.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "status": "PENDING",
  "provider": "o365",
  "user_email": null,
  "total_emails_synced": null,
  "last_sync_at": null,
  "sync_frequency": "every_15min",
  "initial_sync_complete": null,
  "connected_at": "<original_connected_at datetime>"
}
```

**Note:** `PENDING` is only visible in the window between `POST /email/connect` and `POST /email/callback` — while the user is on the Microsoft login screen. The integration row exists (reactivated from DISCONNECTED) but tokens have been cleared. This is the state the UI uses to show a loading spinner.

#### TC-39: Reconnect Flow — Callback

**Precondition:** TC-37 ran. `code` and `state` obtained from Microsoft redirect.

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "code": "<authorization_code from Microsoft redirect>",
  "state": "<state from TC-37 response>"
}
```

**Response:** `200 OK`
```json
{
  "status": "CONNECTED",
  "message": "Email integration connected successfully"
}
```
#### TC-39: Reconnect Flow — Callback
**Precondition:** TC-37 ran. `code` and `state` obtained from Microsoft redirect.

**Headers:** `Authorization: Bearer <access_token>`

**Input:**
```json
{
  "code": "<authorization_code from Microsoft redirect>",
  "state": "<state from TC-37 response>"
}
```

**Response:** `200 OK`
```json
{
  "status": "CONNECTED",
  "message": "Email integration connected successfully"
}
```

**Note:** Same `config_id` is reused — historical `raw_ingest_log` rows are preserved. A new `initial_full_fetch` task is dispatched (delta tokens were stale after disconnect).

#### TC-39: Status After Reconnect

**Precondition:** TC-38 ran and full fetch completed.

**Headers:** `Authorization: Bearer <access_token>`

**Response:** `200 OK`
```json
{
  "status": "CONNECTED",
  "provider": "o365",
  "user_email": "<microsoft_upn>",
  "total_emails_synced": <number>,
  "last_sync_at": "<datetime>",
  "sync_frequency": "every_15min",
  "initial_sync_complete": true,
  "connected_at": "<original_connected_at datetime>"
}
```

---


## Test Execution Order

Run test cases in this exact sequence to ensure each one has the correct preconditions:

```
TC-01  Signup
TC-02  Duplicate Signup (negative)
TC-03  Login → save access_token, refresh_token
TC-04  Wrong Password (negative)
TC-05  Refresh Token → save new tokens
TC-06  Invalid Refresh (negative)
TC-07  Logout
TC-08  No Token Logout (negative)
       → Login again, save new access_token
TC-09  Grant Consent
TC-10  Grant Again (idempotent)
TC-11  Missing consent_type (negative)
TC-12  No Auth on Grant (negative)
TC-13  Get Consent Status (granted)
TC-14  Get Status No Consent (negative — use fresh entity)
TC-15  Missing query param (negative)
TC-16  Revoke Consent
TC-17  Status After Revoke
       → Re-grant consent (TC-09 again)
TC-18  Email Status Not Connected
TC-19  No Auth on Status (negative)
TC-20  Initiate Connect → save state, open auth_url in browser
TC-21  Connect Without Consent (negative) → re-grant after
TC-22  Connect When Already Connected (negative — run after TC-23)
TC-23  OAuth Callback → complete Microsoft login, paste code+state
TC-24  Invalid State (negative)
TC-25  Expired State (negative)
TC-26  Missing code (negative)
TC-27  Missing state (negative)
TC-28  Status After Connect (initial_sync_complete=false)
TC-29  Status After Full Fetch (initial_sync_complete=true)
TC-30  Manual Sync Trigger
TC-31  Sync Without Consent (negative) → re-grant after
TC-32  Sync Not Connected (negative — run before TC-23 or after TC-34)
TC-33  No Auth on Sync (negative)
TC-34  Disconnect
TC-35  Disconnect When Not Connected (negative)
TC-36  Status After Disconnect
TC-37  Reconnect — Initiate → open auth_url in browser
TC-38  Reconnect — Callback
TC-39  Status After Reconnect
```

---

## Configuration Reference

| Setting                  | Value                                      |
|--------------------------|--------------------------------------------|
| Auth service port        | 8000                                       |
| Email connector port     | 8001                                       |
| Access token expiry      | 2 minutes                                  |
| Refresh token expiry     | 15 minutes                                 |
| OAuth state TTL          | 10 minutes                                 |
| Sync lock TTL            | 35 minutes                                 |
| Sync frequency           | 15 minutes (Celery Beat)                   |
| Initial fetch days       | 30 (configurable via INITIAL_FETCH_DAYS)   |
| Max fetch days           | 90                                         |
| Token refresh buffer     | 5 minutes before expiry                    |
