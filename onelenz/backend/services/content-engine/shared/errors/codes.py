from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    """Immutable error code definition. Single source of truth for all errors."""

    code: str
    message: str
    status_code: int


# --- Auth ---
EMAIL_ALREADY_EXISTS = ErrorCode("EMAIL_ALREADY_EXISTS", "Email already registered", 409)
INVALID_CREDENTIALS = ErrorCode("INVALID_CREDENTIALS", "Invalid email or password", 401)
ACCOUNT_LOCKED = ErrorCode("ACCOUNT_LOCKED", "Account locked due to too many failed attempts", 423)
UNAUTHORIZED = ErrorCode("UNAUTHORIZED", "Unauthorized", 401)
SESSION_NOT_FOUND = ErrorCode("SESSION_NOT_FOUND", "Session not found", 401)
TOKEN_EXPIRED = ErrorCode("TOKEN_EXPIRED", "Refresh token expired. Please login again.", 401)
INVALID_TOKEN = ErrorCode("INVALID_TOKEN", "Invalid or expired token", 401)
STALE_TOKEN = ErrorCode("STALE_TOKEN", "Stale token", 401)

# --- Email Connector ---
MS365_CONSENT_REQUIRED = ErrorCode("MS365_CONSENT_REQUIRED", "EMAIL_SCAN consent not granted", 403)
MS365_INTEGRATION_EXISTS = ErrorCode("MS365_INTEGRATION_EXISTS", "Email integration already exists for this user", 400)
MS365_OAUTH_FAILED = ErrorCode("MS365_OAUTH_FAILED", "OAuth token exchange failed", 500)
MS365_OAUTH_DECLINED = ErrorCode("MS365_OAUTH_DECLINED", "User declined Microsoft consent", 400)
MS365_STATE_EXPIRED = ErrorCode("MS365_STATE_EXPIRED", "OAuth state expired or invalid", 400)
MS365_AUTH_FAILED = ErrorCode("MS365_AUTH_FAILED", "Microsoft authorization failed", 401)
MS365_NOT_CONNECTED = ErrorCode("MS365_NOT_CONNECTED", "No active email integration found", 404)
MS365_SYNC_FAILED = ErrorCode("MS365_SYNC_FAILED", "Email sync failed", 500)
MS365_RATE_LIMITED = ErrorCode("MS365_RATE_LIMITED", "Microsoft Graph API rate limit exceeded", 429)
MS365_DELTA_EXPIRED = ErrorCode("MS365_DELTA_EXPIRED", "Delta token expired, full fetch required", 500)

# --- Password Reset ---
INVALID_OTP = ErrorCode("INVALID_OTP", "Invalid or expired OTP", 400)
OTP_EXPIRED = ErrorCode("OTP_EXPIRED", "OTP has expired. Please request a new one.", 400)
WRONG_PASSWORD = ErrorCode("WRONG_PASSWORD", "Current password is incorrect", 401)

# --- Validation ---
VALIDATION_ERROR = ErrorCode("VALIDATION_ERROR", "Invalid or missing fields", 400)

# --- General ---
INTERNAL_ERROR = ErrorCode("INTERNAL_ERROR", "An unexpected error occurred", 500)

# ── Content Engine ──────────────────────────────────────
CONTENT_UNSUPPORTED_FILE_TYPE = ErrorCode("CONTENT_UNSUPPORTED_FILE_TYPE", "File type not supported. Accepted: PDF, DOCX, PPTX, XLSX, TXT, ZIP", 400)
CONTENT_FILE_TOO_LARGE = ErrorCode("CONTENT_FILE_TOO_LARGE", "File exceeds maximum size of 50MB", 400)
CONTENT_TOO_MANY_FILES = ErrorCode("CONTENT_TOO_MANY_FILES", "Too many files in single upload", 400)
CONTENT_INVALID_URL = ErrorCode("CONTENT_INVALID_URL", "URL is malformed or unreachable", 400)
CONTENT_INVALID_CATEGORY = ErrorCode("CONTENT_INVALID_CATEGORY", "Invalid content category", 400)
CONTENT_ASSET_NOT_FOUND = ErrorCode("CONTENT_ASSET_NOT_FOUND", "Asset not found", 404)
CONTENT_ASSET_PROCESSING = ErrorCode("CONTENT_ASSET_PROCESSING", "Asset is currently being processed", 409)
CONTENT_EXTRACTION_FAILED = ErrorCode("CONTENT_EXTRACTION_FAILED", "Document extraction failed", 500)
CONTENT_EMBEDDING_FAILED = ErrorCode("CONTENT_EMBEDDING_FAILED", "Embedding generation failed", 500)
CONTENT_CRAWL_BLOCKED = ErrorCode("CONTENT_CRAWL_BLOCKED", "Website crawling blocked by robots.txt", 400)
CONTENT_ZIP_INVALID = ErrorCode("CONTENT_ZIP_INVALID", "Invalid ZIP file", 400)
CONTENT_DAILY_LIMIT_REACHED = ErrorCode("CONTENT_DAILY_LIMIT_REACHED", "Daily asset upload limit reached", 429)
FORBIDDEN = ErrorCode("FORBIDDEN", "Insufficient permissions", 403)
