# Auth-Service Technical Specification

## 1. Overview

### Purpose
The auth-service handles user registration, authentication, session management, and token lifecycle for the OneLenz platform.

### Tech Stack
| Component | Technology |
|-----------|-----------|
| Backend | Python, FastAPI |
| Database | PostgreSQL 17.6+ (async via SQLAlchemy + asyncpg) |
| Cache | Redis |
| Password Hashing | Argon2id |
| Token Signing | RS256 (RSA-SHA256) |

### Architecture Flow
```
Client Request
  → FastAPI Route (api/routes/)
    → Service Layer (services/) — business logic, validation
      → Repository Layer (repositories/) — DB queries
      → Redis — token storage, session state
  → Response
```

### Base URL
All auth endpoints are mounted under `/auth`.

---

## 2. JWT Token Design

### Algorithm
RS256 (asymmetric RSA-SHA256). The auth-service signs tokens with a private key. All other services verify tokens using the corresponding public key.

### Claims

| Claim | Type | Description |
|-------|------|-------------|
| `iss` | string | Always `"onelenz"` |
| `sub` | string (UUID) | User ID from `user_master.usm_user_id` |
| `aud` | string | Always `"www.onelenz.ai"` |
| `exp` | integer (epoch) | Expiration timestamp |
| `iat` | integer (epoch) | Issued at (server time) |
| `jti` | string (UUID4) | Unique session ID — maps to `uah_session_id` in DB |

### Token Types

| Token | Default Expiry | Purpose |
|-------|---------------|---------|
| Access Token | 2 minutes | Sent with every API request in `Authorization: Bearer <token>` header |
| Refresh Token | 15 minutes | Used only to obtain new access + refresh tokens via `/auth/refresh` |

Both tokens share the same claims structure. They are distinguished by their `exp` values.

### Expiry Configuration
Token expiry values are configurable via environment variables:
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default: 2)
- `JWT_REFRESH_TOKEN_EXPIRE_MINUTES` (default: 15)

---

## 3. Redis Key Design

### Environment Prefix
All Redis keys are prefixed with the deployment environment:
```
{env}:onelenz:auth:...
```
Where `{env}` is one of: `dev`, `staging`, `prod`. Configured via `ENVIRONMENT` env var.

### Key: Logged-In Users

```
Key:        {env}:onelenz:auth:logged_in_users
Type:       Hash
Hash Field: {user_id} (UUID string)
Hash Value: JSON object
```

**Hash Value JSON Schema:**

| Field | Type | Description |
|-------|------|-------------|
| accessToken | string | Current access token |
| accessTokenExpiry | string (ISO 8601) | Access token expiry timestamp |
| refreshToken | string | Current refresh token |
| refreshTokenExpiry | string (ISO 8601) | Refresh token expiry timestamp |
| userEmail | string | User email from `user_master` |
| userMobile | string | User mobile from `user_master` |
| userMappedEntityID | string | Entity ID from `user_master` |
| userMappedRoleID | string | Role ID from `user_role_mapping` |
| userDisplayName | string | Display name from `user_master` |
| userLoggedInAt | string (ISO 8601) | Login timestamp |
| sessionID | string (UUID4) | JWT `jti` claim |

**Operations:**
- `HSET` on login and token refresh
- `HGET` on token validation (middleware)
- `HDEL` on logout and session expiry

### Key: Password Reset OTP

```
Key:        {env}:onelenz:auth:password_reset:{user_id}
Type:       Hash
Hash Field: data
Hash Value: JSON object
TTL:        OTP_EXPIRY_MINUTES (default 10 min)
```

**Hash Value JSON Schema:**

| Field | Type | Description |
|-------|------|-------------|
| otp_hash | string | Argon2id hash of the 6-digit OTP |
| email | string | User email (for verification) |
| created_at | string (ISO 8601) | OTP creation timestamp |

**Operations:**
- `HSET` + `EXPIRE` on forgot-password
- `HGET` on reset-password (verify OTP)
- `HDEL` on successful password reset

---

## 4. Shared Auth Middleware

### Purpose
A FastAPI dependency (`get_current_user`) that protects routes by validating the JWT access token. This lives in `backend/shared/` since all services need it.

### Location
`backend/shared/auth/middleware.py`

### Flow

1. Extract `Authorization: Bearer <token>` header from the request
2. If header is missing or malformed → **401 Unauthorized**
3. Decode and verify the JWT using the RS256 public key
4. Validate claims:
   - `iss` must equal `"onelenz"`
   - `aud` must equal `"www.onelenz.ai"`
   - `exp` must not be in the past
5. Extract `sub` (user_id) from claims
6. `HGET` from Redis key `{env}:onelenz:auth:logged_in_users` using `user_id` as hash field
7. If no Redis entry found → **401 Unauthorized** (session invalidated)
8. Compare the token from the request with `accessToken` stored in Redis
9. If tokens don't match → **401 Unauthorized** (stale token)
10. Return user context object containing: `user_id`, `entity_id`, `role_id`, `email`, `session_id`

### Imports
```
from shared.auth import CurrentUser, get_current_user
from shared.errors import AppError
```

### Usage in Routes
```
@router.post("/some-protected-route")
async def handler(user: CurrentUser = Depends(get_current_user)):
    # user.user_id, user.entity_id, user.role_id, user.email, user.session_id
    ...
```

### Error Handling
The middleware raises `AppError` on failure. Protected routes must catch it and return the appropriate status:
```
try:
    ...
except AppError as e:
    return JSONResponse(
        status_code=e.status_code,
        content=ErrorResponse(
            error=ErrorDetail(code=e.code, message=e.message)
        ).model_dump(),
    )
```

### CurrentUser Fields
| Field | Type | Source |
|-------|------|--------|
| user_id | str (UUID) | JWT `sub` claim |
| entity_id | str | Redis session → userMappedEntityID |
| role_id | str | Redis session → userMappedRoleID |
| email | str | Redis session → userEmail |
| session_id | str (UUID) | JWT `jti` claim |

---

## 5. API Specifications

---

### 5.1 POST /auth/signup

**Auth:** Public (no token required)

**Description:** Register a new user and auto-login by returning tokens.

#### Request

**Headers:**
| Header | Value |
|--------|-------|
| Content-Type | application/json |

**Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| email | string | Yes | Valid email format, max 255 chars. Public domains (gmail.com, outlook.com) blocked. |
| password | string | Yes | Min 8 chars |
| first_name | string | Yes | Max 100 chars |
| last_name | string | Yes | Max 100 chars |
| company_name | string | Conditional | Max 200 chars. Required only if no entity exists for the email domain. Ignored if entity already exists. |
| mobile | string | No | Max 30 chars |

#### Business Logic

1. Validate request body fields
2. Check if email already exists in `user_master` where `usm_user_status = 1`
   - If exists → **409 Conflict**
3. Hash the password using Argon2id (salt auto-generated, stored in the hash string)
4. Extract domain from email (e.g. `user@acme.com` → `acme.com`)
   - Block public email domains (gmail.com, outlook.com, yahoo.com, etc.) → **400 Bad Request** "Please use your company email. Personal email addresses are not allowed."
   - Public domain list maintained in `shared/utils.py` → `is_public_domain()`
5. **Entity resolution — match by email domain:**
   - `SELECT * FROM subscriber_entity WHERE ent_domain = {domain} AND ent_is_active = 1`
   - **If entity found** → use existing `ent_entity_id` (user joins existing entity)
   - **If no entity found** → create new entity:
     - Require `company_name` in request (if missing → **400 Bad Request** "Company name required for first user")
     - Generate new entity UUID
     - **DB Insert — `subscriber_entity`:**
       - `ent_entity_id` = generated entity UUID
       - `ent_entity_name` = company_name
       - `ent_domain` = extracted domain
       - `ent_is_active` = 1
       - `ent_created_by` = generated user ID
       - `ent_created_on` = current server timestamp (UTC)
6. Generate UUIDs: user_id + session_id
7. **DB Insert — `user_master`:**
   - `usm_user_id` = generated UUID
   - `usm_user_email_id` = email
   - `usm_user_first_name` = first_name
   - `usm_user_last_name` = last_name
   - `usm_user_display_name` = "{first_name} {last_name}"
   - `usm_user_mobile_no` = mobile (if provided)
   - `usm_entity_id` = entity UUID (existing or newly created)
   - `usm_user_status` = 1
   - `usm_failed_login_count` = 0
   - `usm_created_by` = generated user ID
   - `usm_created_on` = current server timestamp (UTC)
8. **DB Insert — `user_security_details`:**
   - `usd_user_id` = generated user ID
   - `usd_hashed_pwd` = Argon2id hashed password
   - `usd_mobile_app_access` = 0
   - `usd_api_access` = 0
   - `usd_created_by` = generated user ID
   - `usd_created_on` = current server timestamp (UTC)
9. **DB Insert — `user_role_mapping`:**
   - `urm_mapped_user_id` = generated user ID
   - `urm_role_id` = "ADMIN" (first user of an entity gets ADMIN)
   - `urm_record_status` = 1
   - `urm_created_by` = generated user ID
   - `urm_created_on` = current server timestamp (UTC)
10. Fetch IP address from `X-Forwarded-For` header (first IP in the list)
11. **DB Insert — `user_authentication_history`:**
    - `uah_user_id` = generated user ID
    - `uah_session_id` = session ID
    - `uah_ip_address` = client IP
    - `uah_invalid_login_attempt_count` = 0
    - `uah_login_time` = current server timestamp (UTC)
12. Build JWT claims and sign access token + refresh token
13. **Redis HSET** — `{env}:onelenz:auth:logged_in_users`, hash field = user ID, hash value = session JSON (see Section 3)
14. Return tokens in response

**Entity auto-join flow:**
```
User A (first from rapyder.com) signs up with company_name="Rapyder"
  → No entity with domain rapyder.com → creates Entity (Rapyder, rapyder.com)
  → User A assigned to Entity

User B (second from rapyder.com) signs up
  → Entity with domain rapyder.com found → uses existing Entity
  → User B assigned to same Entity
  → company_name field ignored (entity already exists)

User C (first from acme.com) signs up with company_name="Acme Corp"
  → No entity with domain acme.com → creates new Entity (Acme Corp, acme.com)
  → User C assigned to new Entity
```

**Limitation:** Users from the same email domain are assumed to be from the same company. This works for most B2B scenarios but won't handle shared domains (e.g. gmail.com). Public email domains should be blocked or handled specially in a future iteration.

**Note:** All DB inserts (steps 5-10) run in a single transaction. If any step fails, all are rolled back.

#### Response

**Success — 201 Created:**
```json
{
  "user_id": "uuid",
  "entity_id": "uuid",
  "email": "user@example.com",
  "display_name": "John Doe",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "access_token_expires_at": "2026-03-17T10:02:00Z",
  "refresh_token_expires_at": "2026-03-17T10:15:00Z"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| 400 Bad Request | Missing or invalid fields |
| 409 Conflict | Email already registered |
| 500 Internal Server Error | DB or Redis failure |

---

### 5.2 POST /auth/login

**Auth:** Public (no token required)

**Description:** Authenticate user with email and password. Returns access and refresh tokens on success. Implements account lockout after configurable failed attempts.

#### Request

**Headers:**
| Header | Value |
|--------|-------|
| Content-Type | application/json |

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| email | string | Yes | User email |
| password | string | Yes | User password |

#### Business Logic

1. Validate request body
2. **DB Query — `user_master`:**
   - `SELECT * FROM user_master WHERE usm_user_email_id = {email} AND usm_user_status = 1`
   - If no row found → **401 Unauthorized** ("Invalid email or password")
3. **Check lockout:**
   - If `usm_locked_until` is not null and is in the future → **423 Locked** ("Account locked. Try again after {usm_locked_until}")
   - If `usm_locked_until` is in the past → reset: set `usm_failed_login_count = 0`, `usm_locked_until = NULL`
4. **DB Query — `user_security_details`:**
   - `SELECT * FROM user_security_details WHERE usd_user_id = {user_id}`
5. **Verify password:**
   - Compare request password against `usd_hashed_pwd` using Argon2id verify
   - If mismatch:
     - Increment `usm_failed_login_count` in `user_master`
     - If `usm_failed_login_count >= LOCKOUT_THRESHOLD` (default 3):
       - Set `usm_locked_until = NOW() + LOCKOUT_DURATION_MINUTES` (default 30 min)
     - → **401 Unauthorized** ("Invalid email or password")
6. **On successful password match:**
   - Reset `usm_failed_login_count = 0`, `usm_locked_until = NULL`
7. **DB Query — `user_role_mapping`:**
   - `SELECT urm_role_id FROM user_role_mapping WHERE urm_mapped_user_id = {user_id} AND urm_record_status = 1 LIMIT 1`
8. Generate session ID (UUID4)
9. Fetch IP address from `X-Forwarded-For` header (first IP in the list)
10. **DB Insert — `user_authentication_history`:**
    - `uah_user_id` = user ID
    - `uah_session_id` = session ID
    - `uah_ip_address` = client IP
    - `uah_invalid_login_attempt_count` = 0
    - `uah_login_time` = current server timestamp (UTC)
11. Build JWT claims and sign access token + refresh token
12. **Redis HSET** — `{env}:onelenz:auth:logged_in_users`, hash field = user ID, hash value = session JSON (see Section 3)
13. Return tokens in response

#### Response

**Success — 200 OK:**
```json
{
  "user_id": "uuid",
  "entity_id": "uuid",
  "email": "user@example.com",
  "display_name": "John Doe",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "access_token_expires_at": "2026-03-17T10:02:00Z",
  "refresh_token_expires_at": "2026-03-17T10:15:00Z"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| 400 Bad Request | Missing or invalid fields |
| 401 Unauthorized | Invalid email or password |
| 423 Locked | Account locked due to too many failed attempts |
| 500 Internal Server Error | DB or Redis failure |

---

### 5.3 POST /auth/refresh

**Auth:** Public (requires refresh token in request body)

**Description:** Validate the refresh token and issue a new pair of access + refresh tokens. If the refresh token is expired, the session is terminated.

#### Request

**Headers:**
| Header | Value |
|--------|-------|
| Content-Type | application/json |

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| refresh_token | string | Yes | Current refresh token |

#### Business Logic

1. Decode the refresh token JWT (do NOT reject on `exp` yet — we need to check if it's expired to decide the flow)
2. Extract `sub` (user_id) and `jti` (session_id) from claims
3. Validate claims: `iss`, `aud` must match expected values
4. **Redis HGET** — `{env}:onelenz:auth:logged_in_users` using `user_id` as hash field
   - If no entry found → **401 Unauthorized** ("Session not found")
5. Compare the request refresh token with `refreshToken` stored in Redis
   - If tokens don't match → **401 Unauthorized** ("Invalid refresh token")
6. **Check if refresh token is expired** (`exp` claim vs current server time):
   - **If expired:**
     - **Redis HDEL** — remove user from `{env}:onelenz:auth:logged_in_users`
     - **DB Update — `user_authentication_history`:**
       - `UPDATE SET uah_logout_time = NOW() WHERE uah_user_id = {user_id} AND uah_session_id = {session_id}`
     - → **401 Unauthorized** ("Refresh token expired. Please login again.")
   - **If still valid:**
     - Generate new access token + refresh token (same `jti` / session ID)
     - **Redis HSET** — update `{env}:onelenz:auth:logged_in_users` with new tokens and expiries
     - Return new tokens

#### Response

**Success — 200 OK:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "access_token_expires_at": "2026-03-17T10:02:00Z",
  "refresh_token_expires_at": "2026-03-17T10:15:00Z"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| 400 Bad Request | Missing refresh token |
| 401 Unauthorized | Invalid, expired, or mismatched refresh token |
| 500 Internal Server Error | Redis or DB failure |

---

### 5.4 POST /auth/logout

**Auth:** Protected (requires valid access token via `get_current_user` middleware)

**Description:** Invalidate the current session by removing tokens from Redis and recording logout time in the database.

#### Request

**Headers:**
| Header | Value |
|--------|-------|
| Authorization | Bearer {access_token} |

**Body:** None

#### Business Logic

1. `get_current_user` middleware extracts and validates the access token (see Section 4)
2. From the middleware, obtain: `user_id`, `session_id` (jti)
3. **Redis HDEL** — remove hash field `user_id` from `{env}:onelenz:auth:logged_in_users`
4. **DB Update — `user_authentication_history`:**
   - `UPDATE SET uah_logout_time = NOW() WHERE uah_user_id = {user_id} AND uah_session_id = {session_id}`
5. Return success

#### Response

**Success — 200 OK:**
```json
{
  "message": "Logged out successfully"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| 401 Unauthorized | Missing, invalid, or expired access token |
| 500 Internal Server Error | Redis or DB failure |

---

### 5.5 POST /auth/forgot-password

**Auth:** Public (no token required)

**Description:** Send a 6-digit OTP to the user's registered email for password reset. Always returns 200 regardless of whether the email exists (prevents email enumeration).

#### Request

**Headers:**
| Header | Value |
|--------|-------|
| Content-Type | application/json |

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| email | string | Yes | User email |

#### Business Logic

1. Validate request body
2. **DB Query — `user_master`:**
   - `SELECT * FROM user_master WHERE usm_user_email_id = {email} AND usm_user_status = 1`
   - If no row found → return 200 with generic message (do NOT reveal email doesn't exist)
3. Generate 6-digit OTP using `secrets.randbelow(900000) + 100000`
4. Hash OTP using Argon2id
5. **Redis HSET** — `{env}:onelenz:auth:password_reset:{user_id}`, hash field = "data", value = `{otp_hash, email, created_at}`
6. **Redis EXPIRE** — set TTL of `OTP_EXPIRY_MINUTES` (default 10 min) on the key
7. Send OTP via email (mock in dev, SES in prod — see `shared/email/sender.py`)
8. Return generic success message

#### Response

**Success — 200 OK:**
```json
{
  "message": "If the email is registered, an OTP has been sent"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| 400 Bad Request | Missing or invalid email |
| 500 Internal Server Error | Redis, DB, or email send failure |

---

### 5.6 POST /auth/reset-password

**Auth:** Public (no token required)

**Description:** Verify the OTP and set a new password. Invalidates all existing sessions after reset.

#### Request

**Headers:**
| Header | Value |
|--------|-------|
| Content-Type | application/json |

**Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| email | string | Yes | Valid email format |
| otp | string | Yes | Exactly 6 digits |
| new_password | string | Yes | Min 8 chars, max 255 chars |

#### Business Logic

1. Validate request body
2. **DB Query — `user_master`:** find user by email
   - If not found → **400 INVALID_OTP**
3. **Redis HGET** — `{env}:onelenz:auth:password_reset:{user_id}` → get OTP data
   - If no data → **400 OTP_EXPIRED**
4. Verify OTP: compare request OTP against stored `otp_hash` using Argon2id verify
   - If mismatch → **400 INVALID_OTP**
5. Hash new password using Argon2id
6. **DB Update — `user_security_details`:** set `usd_hashed_pwd` = new hash
7. **Redis HDEL** — delete OTP key `password_reset:{user_id}`
8. **Redis HDEL** — remove user from `logged_in_users` (invalidate all sessions)
9. Return success message

#### Response

**Success — 200 OK:**
```json
{
  "message": "Password reset successfully. Please login with your new password."
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| 400 Bad Request | Invalid OTP, expired OTP, or missing fields |
| 500 Internal Server Error | Redis or DB failure |

---

### 5.7 POST /auth/change-password

**Auth:** Protected (requires valid access token via `get_current_user` middleware)

**Description:** Change password for the currently logged-in user. Requires the current password for verification.

#### Request

**Headers:**
| Header | Value |
|--------|-------|
| Authorization | Bearer {access_token} |
| Content-Type | application/json |

**Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| current_password | string | Yes | Current password |
| new_password | string | Yes | Min 8 chars, max 255 chars |

#### Business Logic

1. `get_current_user` middleware extracts and validates the access token
2. From the middleware, obtain: `user_id`, `entity_id`
3. **DB Query — `user_security_details`:** get current password hash
4. Verify `current_password` against stored hash using Argon2id verify
   - If mismatch → **400 WRONG_PASSWORD**
5. Hash new password using Argon2id
6. **DB Update — `user_security_details`:** set `usd_hashed_pwd` = new hash
7. Return success message

**Note:** Change password does NOT invalidate the current session. The user remains logged in with their existing tokens.

#### Response

**Success — 200 OK:**
```json
{
  "message": "Password changed successfully"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| 400 Bad Request | Wrong current password or missing fields |
| 401 Unauthorized | Missing, invalid, or expired access token |
| 500 Internal Server Error | DB failure |

---

## 6. Error Response Schema

All error responses follow a consistent format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error description"
  }
}
```

### Error Codes

All error codes are defined in `backend/shared/errors/codes.py`. Use `AppError` from `shared/errors` to raise errors in service code.

| HTTP Status | Error Code | Used In |
|-------------|-----------|---------|
| 400 | VALIDATION_ERROR | All endpoints — invalid or missing fields |
| 401 | INVALID_CREDENTIALS | login — wrong email or password |
| 401 | UNAUTHORIZED | middleware — missing authorization header |
| 401 | INVALID_TOKEN | middleware — JWT decode/verify failed |
| 401 | STALE_TOKEN | middleware — token doesn't match Redis |
| 401 | TOKEN_EXPIRED | refresh — refresh token expired |
| 401 | SESSION_NOT_FOUND | middleware, refresh — no Redis entry |
| 400 | INVALID_OTP | reset-password — OTP mismatch |
| 400 | OTP_EXPIRED | reset-password — OTP not found or TTL expired |
| 400 | WRONG_PASSWORD | change-password — current password mismatch |
| 409 | EMAIL_ALREADY_EXISTS | signup — duplicate email |
| 423 | ACCOUNT_LOCKED | login — too many failed attempts |
| 500 | INTERNAL_ERROR | Any — unexpected server error |

---

## 7. Database Tables Reference

### subscriber_entity
Tenant/organization. Created on signup. PK: `ent_entity_id` (UUID).

| Column | Type | Key/Notes |
|--------|------|-----------|
| ent_entity_id | UUID | PK, default uuid_generate_v4() |
| ent_entity_name | VARCHAR(200) | Company name from signup |
| ent_domain | VARCHAR(255) | Extracted from signup email |
| ent_is_active | SMALLINT | 1=active |
| ent_created_by | VARCHAR(100) | Audit |
| ent_created_on | TIMESTAMPTZ | Audit |
| ent_modified_by | VARCHAR(100) | Audit |
| ent_modified_on | TIMESTAMPTZ | Audit |

### user_master
Core user identity. PK: `usm_user_id` (UUID).

| Column | Type | Key/Notes |
|--------|------|-----------|
| usm_user_id | UUID | PK, default uuid_generate_v4() |
| usm_user_display_name | VARCHAR(200) | |
| usm_user_first_name | VARCHAR(100) | |
| usm_user_last_name | VARCHAR(100) | |
| usm_entity_id | VARCHAR(100) | Tenant isolation |
| usm_user_email_id | VARCHAR(255) | Indexed |
| usm_user_mobile_no | VARCHAR(30) | |
| usm_title_tag | VARCHAR(100) | |
| usm_department_tag | VARCHAR(100) | |
| usm_user_status | SMALLINT | 1=active, 0=inactive |
| usm_failed_login_count | SMALLINT | For lockout logic |
| usm_locked_until | TIMESTAMPTZ | Lockout expiry |
| usm_created_by | VARCHAR(100) | Audit |
| usm_created_on | TIMESTAMPTZ | Audit |
| usm_modified_by | VARCHAR(100) | Audit |
| usm_modified_on | TIMESTAMPTZ | Audit |

### user_security_details
Credentials and access flags. 1:1 with user_master.

| Column | Type | Key/Notes |
|--------|------|-----------|
| usd_user_id | UUID | PK (maps to user_master.usm_user_id) |
| usd_hashed_pwd | VARCHAR(255) | Argon2id |
| usd_hashed_pin | VARCHAR(255) | Argon2id (future 2FA) |
| usd_2fa_option | SMALLINT | NULL=disabled (future) |
| usd_mobile_app_access | SMALLINT | 0=denied, 1=permitted |
| usd_api_access | SMALLINT | 0=denied, 1=permitted |
| usd_created_by | VARCHAR(100) | Audit |
| usd_created_on | TIMESTAMPTZ | Audit |
| usd_modified_by | VARCHAR(100) | Audit |
| usd_modified_on | TIMESTAMPTZ | Audit |

### user_authentication_history
Audit log for login/logout events. Composite PK: (user_id, session_id).

| Column | Type | Key/Notes |
|--------|------|-----------|
| uah_user_id | UUID | PK (maps to user_master.usm_user_id) |
| uah_session_id | VARCHAR(255) | PK, UUID4 = JWT jti |
| uah_ip_address | VARCHAR(100) | From X-Forwarded-For |
| uah_invalid_login_attempt_count | SMALLINT | |
| uah_login_time | TIMESTAMPTZ | Set on login |
| uah_logout_time | TIMESTAMPTZ | Set on logout/expiry |

### user_role_mapping
User-to-role assignment.

| Column | Type | Key/Notes |
|--------|------|-----------|
| urm_mapping_id | SERIAL | PK |
| urm_mapped_user_id | UUID | Maps to user_master.usm_user_id |
| urm_role_id | VARCHAR(100) | Role identifier |
| urm_record_status | SMALLINT | 1=active |
| urm_created_by | VARCHAR(100) | Audit |
| urm_created_on | TIMESTAMPTZ | Audit |
| urm_modified_by | VARCHAR(100) | Audit |
| urm_modified_on | TIMESTAMPTZ | Audit |

---

## 8. Configuration

All environment variables are defined in `backend/.env.example`.

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | postgresql+asyncpg://postgres:postgres@localhost:5432/onelenz | PostgreSQL connection string |
| DB_POOL_SIZE | 10 | Connection pool size |
| DB_MAX_OVERFLOW | 20 | Max overflow connections |
| DB_POOL_TIMEOUT | 30 | Pool timeout (seconds) |
| DB_POOL_RECYCLE | 1800 | Connection recycle time (seconds) |
| DB_ECHO | false | Log SQL queries |
| REDIS_URL | redis://localhost:6379/0 | Redis connection string |
| ENVIRONMENT | dev | Deployment environment (dev/staging/prod) — used as Redis key prefix |
| JWT_PRIVATE_KEY | | RS256 private key PEM content (from AWS Secrets Manager) |
| JWT_PUBLIC_KEY | | RS256 public key PEM content (from AWS Secrets Manager) |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES | 2 | Access token TTL |
| JWT_REFRESH_TOKEN_EXPIRE_MINUTES | 15 | Refresh token TTL |
| LOCKOUT_THRESHOLD | 3 | Failed login attempts before lockout |
| LOCKOUT_DURATION_MINUTES | 30 | Lockout duration |
| EMAIL_PROVIDER | mock | Email provider: `mock` (dev, logs OTP) or `ses` (prod, AWS SES) |
| AWS_SES_FROM_EMAIL | noreply@onelenz.ai | SES sender email (prod only) |
| AWS_SES_REGION | ap-south-1 | AWS SES region (prod only) |
| OTP_EXPIRY_MINUTES | 10 | Password reset OTP time-to-live |

---

## 9. UI Integration Guide

### Token Storage
Store tokens in **memory** (React state/context), NOT in localStorage (vulnerable to XSS). On page refresh, the user will need to re-login — this is acceptable given the short session window (15 min).

### HTTP Client Setup (Axios)
The UI should configure a global Axios instance with an **interceptor** that handles token lifecycle automatically. All API calls go through this instance.

#### Request Interceptor
- Attach `Authorization: Bearer {access_token}` header to every request (except `/auth/signup`, `/auth/login`, `/auth/refresh`)

#### Response Interceptor (handles token refresh silently)
1. If any API returns **401**:
   - Check if a refresh token exists in memory
   - If yes → call `POST /auth/refresh` with the refresh token
   - If refresh succeeds → store new tokens, **retry the original failed request** automatically
   - If refresh also fails (401) → clear tokens, redirect to `/login`
2. If **423 Locked** → show lockout message with retry time
3. All other errors → pass through to the calling component

#### Request Queue During Refresh
When the interceptor is refreshing tokens, **queue all other in-flight requests** that get 401. Once refresh completes, replay them with the new access token. This prevents multiple simultaneous refresh calls.

### Auth Context (React)
A global auth context/provider that holds:

| State | Type | Description |
|-------|------|-------------|
| user | object or null | user_id, email, display_name from login/signup response |
| accessToken | string or null | Current access token |
| refreshToken | string or null | Current refresh token |
| isAuthenticated | boolean | Derived: `accessToken !== null` |

**Methods exposed by the context:**

| Method | Calls | Description |
|--------|-------|-------------|
| signup(email, password, first_name, last_name, mobile?) | POST /auth/signup | Stores tokens + user in state |
| login(email, password) | POST /auth/login | Stores tokens + user in state |
| logout() | POST /auth/logout | Clears state, redirects to /login |

### Route Protection
Wrap protected pages in a guard component that checks `isAuthenticated`:
- If `true` → render the page
- If `false` → redirect to `/login`

### Page Flows

#### Signup Page
1. User fills form: email, password, first name, last name, mobile (optional)
2. Client-side validation (email format, password min 8 chars)
3. Call `signup()` from auth context
4. On **201** → tokens stored, redirect to dashboard
5. On **409** → show "Email already registered"
6. On **400** → show field-level validation errors

#### Login Page
1. User enters email + password
2. Call `login()` from auth context
3. On **200** → tokens stored, redirect to dashboard
4. On **401** → show "Invalid email or password"
5. On **423** → show "Account locked. Try again after {time}"

#### Logout
1. User clicks logout button
2. Call `logout()` from auth context
3. Backend clears Redis + updates DB
4. Frontend clears state, redirects to `/login`

#### Session Expiry (automatic)
1. User is active, access token expires (2 min)
2. Next API call returns 401
3. Axios interceptor calls `POST /auth/refresh` silently
4. New tokens stored, original request retried — **user sees nothing**
5. If refresh token also expired (15 min idle) → redirect to `/login`

### UI File Structure (maps to existing scaffold)
```
ui/src/features/auth/
├── components/
│   ├── LoginForm.tsx        — email + password form
│   ├── SignupForm.tsx       — registration form
│   └── AuthGuard.tsx        — route protection wrapper
├── hooks/
│   └── useAuth.ts           — hook to access auth context
├── services/
│   └── authApi.ts           — Axios calls to /auth/* endpoints
└── types/
    └── auth.types.ts        — TypeScript interfaces for request/response
```
