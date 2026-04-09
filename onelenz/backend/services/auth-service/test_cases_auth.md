# Auth Service — Test Documentation

**Project:** OneLenz
**Service:** auth-service
**Base URL:** `http://localhost:8000`
**Tool:** Postman

---

## 1. Signup

- **Endpoint:** `POST /auth/signup`
- **Auth Required:** No

### Request Body

```json
{
  "email": "user@company.com",
  "password": "password123",
  "first_name": "John",
  "last_name": "Doe",
  "company_name": "ABC Corp",
  "mobile": "9876543210"
}
```

### Validation Rules
|--------------|----------|-------------------------------------------------------------|
| Field        | Required | Constraints                                                 |
|--------------|----------|-------------------------------------------------------------|
| email        | Yes      | Valid email, must be company domain (no gmail, yahoo, etc.) |
| password     | Yes      | Min 8, max 255 characters                                   |
| first_name   | Yes      | Min 1, max 100 characters                                   |
| last_name    | Yes      | Min 1, max 100 characters                                   |
| company_name | No       | Max 200 characters. Required for first user of a new domain |
| mobile       | No       | Max 30 characters                                           |
|--------------|----------|-------------------------------------------------------------|
### TC-01: Valid Signup (First User — New Entity)

**Input:**
```json
{
  "email": "john@newcompany.com",
  "password": "password123",
  "first_name": "John",
  "last_name": "Doe",
  "company_name": "New Company",
  "mobile": "9876543210"
}
```

**Response:** `201 Created`
```json
{
  "user_id": "<uuid>",
  "entity_id": "<uuid>",
  "email": "john@newcompany.com",
  "display_name": "John Doe",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "access_token_expires_at": "2026-03-25T10:02:00Z",
  "refresh_token_expires_at": "2026-03-25T10:15:00Z"
}
```

### TC-02: Valid Signup (Existing Entity — company_name Not Required)

**Precondition:** Entity for `newcompany.com` already exists from TC-01.

**Input:**
```json
{
  "email": "jane@newcompany.com",
  "password": "password456",
  "first_name": "Jane",
  "last_name": "Smith"
}
```

**Response:** `201 Created` — same `entity_id` as TC-01.

### TC-03: Personal Email — Gmail

**Input:**
```json
{
  "email": "user@gmail.com",
  "password": "password123",
  "first_name": "John",
  "last_name": "Doe"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Please use your company email. Personal email addresses are not allowed."
  }
}
```

**Note:** All blocked domains — `gmail.com`, `googlemail.com`, `outlook.com`, `hotmail.com`, `live.com`, `msn.com`, `yahoo.com`, `yahoo.co.in`, `ymail.com`, `icloud.com`, `me.com`, `mac.com`, `aol.com`, `protonmail.com`, `proton.me`, `zoho.com`, `mail.com`, `gmx.com`, `tutanota.com`, `fastmail.com`, `yandex.com`, `rediffmail.com`

### TC-04: Password Less Than 8 Characters

**Input:**
```json
{
  "email": "user@company.com",
  "password": "pass",
  "first_name": "John",
  "last_name": "Doe"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "password: String should have at least 8 characters"
  }
}
```

### TC-05: Missing First Name

**Input:**
```json
{
  "email": "user@company.com",
  "password": "password123",
  "last_name": "Doe"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "first_name: Field required"
  }
}
```

### TC-06: Empty First Name

**Input:**
```json
{
  "email": "user@company.com",
  "password": "password123",
  "first_name": "",
  "last_name": "Doe"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "first_name: String should have at least 1 character"
  }
}
```

### TC-07: Missing Last Name

**Input:**
```json
{
  "email": "user@company.com",
  "password": "password123",
  "first_name": "John"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "last_name: Field required"
  }
}
```

### TC-08: Empty Last Name

**Input:**
```json
{
  "email": "user@company.com",
  "password": "password123",
  "first_name": "John",
  "last_name": ""
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "last_name: String should have at least 1 character"
  }
}
```

### TC-09: All Fields Missing (Empty Body)

**Input:**
```json
{}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "email: Field required; password: Field required; first_name: Field required; last_name: Field required"
  }
}
```

### TC-10: Duplicate Email

**Precondition:** User with `john@newcompany.com` already exists.

**Input:**
```json
{
  "email": "john@newcompany.com",
  "password": "password123",
  "first_name": "John",
  "last_name": "Doe",
  "company_name": "New Company"
}
```

**Response:** `409 Conflict`
```json
{
  "error": {
    "code": "EMAIL_ALREADY_EXISTS",
    "message": "Email already registered"
  }
}
```

### TC-11: First User Without Company Name (New Domain)

**Precondition:** No entity exists for `brandnew.com`.

**Input:**
```json
{
  "email": "user@brandnew.com",
  "password": "password123",
  "first_name": "Test",
  "last_name": "User"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Company name required for first user"
  }
}
```

### TC-12: Invalid Email Format

**Input:**
```json
{
  "email": "not-an-email",
  "password": "password123",
  "first_name": "John",
  "last_name": "Doe"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "email: value is not a valid email address..."
  }
}
```

---

## 2. Login

- **Endpoint:** `POST /auth/login`
- **Auth Required:** No

### Request Body

```json
{
  "email": "user@company.com",
  "password": "password123"
}
```

### TC-13: Valid Login

**Input:**
```json
{
  "email": "john@newcompany.com",
  "password": "password123"
}
```

**Response:** `200 OK`
```json
{
  "user_id": "<uuid>",
  "entity_id": "<uuid>",
  "email": "john@newcompany.com",
  "display_name": "John Doe",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "access_token_expires_at": "2026-03-25T10:02:00Z",
  "refresh_token_expires_at": "2026-03-25T10:15:00Z"
}
```

### TC-14: Invalid Email (Not Registered)

**Input:**
```json
{
  "email": "unknown@company.com",
  "password": "password123"
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

### TC-15: Invalid Password

**Input:**
```json
{
  "email": "john@newcompany.com",
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

### TC-16: Account Locked (3 Failed Attempts)

**Precondition:** Enter wrong password 3 times for the same user.

**Input (4th attempt):**
```json
{
  "email": "john@newcompany.com",
  "password": "wrongpassword"
}
```

**Response:** `423 Locked`
```json
{
  "error": {
    "code": "ACCOUNT_LOCKED",
    "message": "Account locked due to too many failed attempts"
  }
}
```

**Note:** Account unlocks automatically after 30 minutes.

### TC-17: Missing Email or Password

**Input:**
```json
{
  "email": "john@newcompany.com"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "password: Field required"
  }
}
```

---

## 3. Refresh Token

- **Endpoint:** `POST /auth/refresh`
- **Auth Required:** No (token sent in body)

### Request Body

```json
{
  "refresh_token": "eyJ..."
}
```

### TC-18: Valid Refresh

**Input:**
```json
{
  "refresh_token": "<valid refresh token from login>"
}
```

**Response:** `200 OK`
```json
{
  "user_id": "<uuid>",
  "entity_id": "<uuid>",
  "email": "john@newcompany.com",
  "display_name": "John Doe",
  "access_token": "eyJ... (new)",
  "refresh_token": "eyJ... (new)",
  "token_type": "Bearer",
  "access_token_expires_at": "2026-03-25T10:02:00Z",
  "refresh_token_expires_at": "2026-03-25T10:15:00Z"
}
```

**Note:** Both access and refresh tokens are replaced. Old tokens become invalid.

### TC-19: Invalid Refresh Token

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

### TC-20: Expired Refresh Token

**Precondition:** Wait 15 minutes after login (refresh token TTL).

**Input:**
```json
{
  "refresh_token": "<expired refresh token>"
}
```

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "TOKEN_EXPIRED",
    "message": "Refresh token expired. Please login again."
  }
}
```

**Note:** Session is automatically deleted from Redis. User must login again.

### TC-21: Stale Refresh Token (Already Refreshed)

**Precondition:** Use a refresh token that was already used in a previous refresh call.

**Input:**
```json
{
  "refresh_token": "<old refresh token>"
}
```

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "STALE_TOKEN",
    "message": "Stale token"
  }
}
```

### TC-22: Session Not Found (User Logged Out)

**Precondition:** User has logged out, then tries to refresh.

**Input:**
```json
{
  "refresh_token": "<refresh token from before logout>"
}
```

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session not found"
  }
}
```

---

## 4. Forgot Password

- **Endpoint:** `POST /auth/forgot-password`
- **Auth Required:** No

### Request Body

```json
{
  "email": "user@company.com"
}
```

### TC-23: Valid — Registered Email

**Input:**
```json
{
  "email": "john@newcompany.com"
}
```

**Response:** `200 OK`
```json
{
  "message": "If the email is registered, an OTP has been sent"
}
```

**Note:** OTP is logged in Docker logs (mock mode). Run `docker-compose logs auth-service | findstr "OTP"` to get it. OTP expires in 10 minutes.

### TC-24: Inactive User (usm_user_status = 0)

**Precondition:** User exists in database but is deactivated (`usm_user_status = 0`).

**Input:**
```json
{
  "email": "deactivated@company.com"
}
```

**Response:** `200 OK`
```json
{
  "message": "If the email is registered, an OTP has been sent"
}
```

**Note:** Same generic response, but no OTP is generated or stored in Redis. The `find_by_email` query filters by `usm_user_status = 1`, so inactive users are treated as non-existent. No OTP will appear in Docker logs.

### TC-25: Unregistered Email

**Input:**
```json
{
  "email": "unknown@company.com"
}
```

**Response:** `200 OK`
```json
{
  "message": "If the email is registered, an OTP has been sent"
}
```

**Note:** Same response as registered email (security — prevents email enumeration). But no OTP is generated or stored in Redis.

### TC-26: Invalid Email Format

**Input:**
```json
{
  "email": "not-an-email"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "email: value is not a valid email address..."
  }
}
```

---

## 5. Reset Password

- **Endpoint:** `POST /auth/reset-password`
- **Auth Required:** No

### Request Body

```json
{
  "email": "user@company.com",
  "otp": "123456",
  "new_password": "newpassword123"
}
```

### Validation Rules

| Field        | Required | Constraints               |
|--------------|----------|---------------------------|
| email        | Yes      | Valid email format        |
| otp          | Yes      | Exactly 6 characters      |
| new_password | Yes      | Min 8, max 255 characters |

### TC-27: Valid Reset Password

**Precondition:** Called forgot-password and got OTP from Docker logs.

**Input:**
```json
{
  "email": "john@newcompany.com",
  "otp": "847291",
  "new_password": "newpassword123"
}
```

**Response:** `200 OK`
```json
{
  "message": "Password reset successfully. Please login with your new password."
}
```

**Note:** All active sessions are invalidated. User must login again with the new password.

### TC-28: Invalid OTP

**Input:**
```json
{
  "email": "john@newcompany.com",
  "otp": "000000",
  "new_password": "newpassword123"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "INVALID_OTP",
    "message": "Invalid or expired OTP"
  }
}
```

### TC-29: Expired OTP (After 10 Minutes)

**Precondition:** Wait 10 minutes after forgot-password request.

**Input:**
```json
{
  "email": "john@newcompany.com",
  "otp": "847291",
  "new_password": "newpassword123"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "OTP_EXPIRED",
    "message": "OTP has expired. Please request a new one."
  }
}
```

### TC-30: OTP Less Than 6 Characters

**Input:**
```json
{
  "email": "john@newcompany.com",
  "otp": "123",
  "new_password": "newpassword123"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "otp: String should have at least 6 characters"
  }
}
```

### TC-31: OTP More Than 6 Characters

**Input:**
```json
{
  "email": "john@newcompany.com",
  "otp": "1234567",
  "new_password": "newpassword123"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "otp: String should have at most 6 characters"
  }
}
```

### TC-32: New Password Too Short

**Input:**
```json
{
  "email": "john@newcompany.com",
  "otp": "847291",
  "new_password": "short"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "new_password: String should have at least 8 characters"
  }
}
```

### TC-33: Reusing Same OTP (Already Used)

**Precondition:** OTP was already used successfully in TC-27.

**Input:**
```json
{
  "email": "john@newcompany.com",
  "otp": "847291",
  "new_password": "anotherpassword"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "OTP_EXPIRED",
    "message": "OTP has expired. Please request a new one."
  }
}
```

**Note:** OTP is deleted from Redis after successful use — it's one-time only.

---

## 6. Change Password

- **Endpoint:** `POST /auth/change-password`
- **Auth Required:** Yes — `Authorization: Bearer <access_token>`

### Request Body

```json
{
  "current_password": "oldpassword",
  "new_password": "newpassword123"
}
```

### Validation Rules

| Field            | Required | Constraints                |
|------------------|----------|----------------------------|
| current_password | Yes      | Must match stored password |
| new_password     | Yes      | Min 8, max 255 characters  |

### TC-34: Valid Change Password

**Headers:** `Authorization: Bearer <valid access_token>`

**Input:**
```json
{
  "current_password": "password123",
  "new_password": "newpassword456"
}
```

**Response:** `200 OK`
```json
{
  "message": "Password changed successfully"
}
```

### TC-35: Wrong Current Password

**Headers:** `Authorization: Bearer <valid access_token>`

**Input:**
```json
{
  "current_password": "wrongpassword",
  "new_password": "newpassword456"
}
```

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "WRONG_PASSWORD",
    "message": "Current password is incorrect"
  }
}
```

### TC-36: Expired Access Token

**Headers:** `Authorization: Bearer <expired access_token>`

**Input:**
```json
{
  "current_password": "password123",
  "new_password": "newpassword456"
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

### TC-37: No Access Token

**Headers:** No `Authorization` header.

**Input:**
```json
{
  "current_password": "password123",
  "new_password": "newpassword456"
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

### TC-38: New Password Too Short

**Headers:** `Authorization: Bearer <valid access_token>`

**Input:**
```json
{
  "current_password": "password123",
  "new_password": "short"
}
```

**Response:** `400 Bad Request`
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "new_password: String should have at least 8 characters"
  }
}
```

---

## 7. Logout

- **Endpoint:** `POST /auth/logout`
- **Auth Required:** Yes — `Authorization: Bearer <access_token>`
- **Note:** Accepts expired access tokens (user can logout even if token expired)

### TC-39: Valid Logout

**Headers:** `Authorization: Bearer <valid access_token>`

**Response:** `200 OK`
```json
{
  "message": "Logged out successfully"
}
```

**Note:** Session is deleted from Redis. Logout time is recorded in `user_authentication_history`.

### TC-40: Logout with Expired Access Token

**Headers:** `Authorization: Bearer <expired access_token>`

**Response:** `200 OK`
```json
{
  "message": "Logged out successfully"
}
```

**Note:** Logout accepts expired tokens — user should always be able to logout.

### TC-41: Invalid Token

**Headers:** `Authorization: Bearer invalid-token-string`

**Response:** `401 Unauthorized`
```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "Invalid or expired token"
  }
}
```

### TC-42: No Token

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

## Configuration Reference

| Setting                 | Value                         |
|-------------------------|-------------------------------|
| Access token expiry     | 2 minutes                     |
| Refresh token expiry    | 15 minutes                    |
| OTP expiry              | 10 minutes                    |
| Lockout threshold       | 3 failed attempts             |
| Lockout duration        | 30 minutes                    |
| Email provider          | mock (OTP logged to console)  |
