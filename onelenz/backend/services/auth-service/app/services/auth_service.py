import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from shared.email import send_otp_email
from shared.errors import AppError
from shared.errors.codes import (
    ACCOUNT_LOCKED,
    EMAIL_ALREADY_EXISTS,
    INVALID_CREDENTIALS,
    INVALID_OTP,
    INVALID_TOKEN,
    OTP_EXPIRED,
    SESSION_NOT_FOUND,
    STALE_TOKEN,
    WRONG_PASSWORD,
    TOKEN_EXPIRED,
    VALIDATION_ERROR,
)
from shared.logging import get_logger
from shared.utils import is_public_domain
from shared.redis.client import hdel, hget_json, hset_json

from ..config import settings
from ..models.auth_history import UserAuthenticationHistory
from ..models.entity import SubscriberEntity
from ..models.role_mapping import UserRoleMapping
from ..models.user import UserMaster
from ..models.user_security import UserSecurityDetails
from ..repositories.user_repository import UserRepository
from ..schemas.auth import (
    AuthTokenResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutResponse,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
)

logger = get_logger(__name__)


def _to_datetime(val) -> datetime:
    """Convert epoch int or datetime to timezone-aware datetime."""
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    return val


async def signup(
    request: SignupRequest,
    ip_address: str,
    session: AsyncSession,
) -> AuthTokenResponse:
    """Register a new user and auto-login by returning tokens."""
    repo = UserRepository(session)

    # 1. Check if email already exists
    existing = await repo.find_by_email(request.email)
    if existing:
        raise AppError(EMAIL_ALREADY_EXISTS)

    # 2. Extract domain and block public email providers
    domain = request.email.split("@")[1].lower() if "@" in request.email else None
    if not domain:
        raise AppError(VALIDATION_ERROR, detail="Invalid email format")
    if is_public_domain(domain):
        raise AppError(VALIDATION_ERROR, detail="Please use your company email. Personal email addresses are not allowed.")

    # 3. Hash password
    hashed_pwd = hash_password(request.password)

    # 4. Generate IDs
    user_id = uuid.uuid4()
    session_id = str(uuid.uuid4())
    display_name = f"{request.first_name} {request.last_name}"
    now = datetime.now(timezone.utc)

    # 5. Entity resolution — match by email domain
    existing_entity = await repo.find_entity_by_domain(domain)
    if existing_entity:
        entity_id = existing_entity.ent_entity_id
    else:
        if not request.company_name:
            raise AppError(VALIDATION_ERROR, detail="Company name required for first user")
        entity_id = uuid.uuid4()
        entity = SubscriberEntity(
            ent_entity_id=entity_id,
            ent_entity_name=request.company_name,
            ent_domain=domain,
            ent_is_active=1,
            ent_created_by=str(user_id),
            ent_created_on=now,
        )
        await repo.create_entity(entity)

    # 6. Create user_master + user_security_details
    entity_id_str = str(entity_id)
    user = UserMaster(
        usm_user_id=user_id,
        usm_user_email_id=request.email,
        usm_user_first_name=request.first_name,
        usm_user_last_name=request.last_name,
        usm_user_display_name=display_name,
        usm_user_mobile_no=request.mobile,
        usm_entity_id=entity_id_str,
        usm_user_status=1,
        usm_failed_login_count=0,
        usm_created_by=str(user_id),
        usm_created_on=now,
    )
    security = UserSecurityDetails(
        usd_user_id=user_id,
        usd_hashed_pwd=hashed_pwd,
        usd_mobile_app_access=0,
        usd_api_access=0,
        usd_created_by=str(user_id),
        usd_created_on=now,
    )
    await repo.create_user_with_security(user, security)

    # 7. Assign ADMIN role
    role_mapping = UserRoleMapping(
        urm_mapped_user_id=user_id,
        urm_role_id="ADMIN",
        urm_record_status=1,
        urm_created_by=str(user_id),
        urm_created_on=now,
    )
    await repo.create_role_mapping(role_mapping)

    # 8. Create auth history
    history = UserAuthenticationHistory(
        uah_user_id=user_id,
        uah_session_id=session_id,
        uah_ip_address=ip_address,
        uah_invalid_login_attempt_count=0,
        uah_login_time=now,
    )
    await repo.create_auth_history(history)

    # 8. Generate tokens
    user_id_str = str(user_id)
    access_token, access_exp = create_access_token(user_id_str, session_id)
    refresh_token, refresh_exp = create_refresh_token(user_id_str, session_id)
    access_exp = _to_datetime(access_exp)
    refresh_exp = _to_datetime(refresh_exp)

    # 9. Store session in Redis
    await hset_json("auth", "logged_in_users", user_id_str, {
        "accessToken": access_token,
        "accessTokenExpiry": access_exp.isoformat(),
        "refreshToken": refresh_token,
        "refreshTokenExpiry": refresh_exp.isoformat(),
        "userEmail": request.email,
        "userMobile": request.mobile or "",
        "userMappedEntityID": entity_id_str,
        "userMappedRoleID": "",
        "userDisplayName": display_name,
        "userLoggedInAt": now.isoformat(),
        "sessionID": session_id,
    })

    logger.info(
        "User signed up",
        extra={"x_user_id": user_id_str, "x_entity_id": entity_id_str},
    )

    # 10. Return response
    return AuthTokenResponse(
        user_id=user_id_str,
        entity_id=entity_id_str,
        email=request.email,
        display_name=display_name,
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_exp,
        refresh_token_expires_at=refresh_exp,
    )


async def login(
    request: LoginRequest,
    ip_address: str,
    session: AsyncSession,
) -> AuthTokenResponse:
    """Authenticate user with email and password. Returns tokens on success."""
    repo = UserRepository(session)

    # 1. Find user by email
    user = await repo.find_by_email(request.email)
    if not user:
        raise AppError(INVALID_CREDENTIALS)

    # 2. Check lockout
    now = datetime.now(timezone.utc)
    locked_until = user.usm_locked_until
    if locked_until is not None and locked_until > now:
        raise AppError(
            ACCOUNT_LOCKED,
            detail=f"Account locked. Try again after {locked_until.isoformat()}",
        )
    # If lockout expired, reset it
    entity_id = user.usm_entity_id or ""
    if locked_until is not None and locked_until <= now:
        await repo.reset_failed_login(user.usm_user_id, entity_id)

    # 3. Verify password
    security = await repo.get_security_details(user.usm_user_id, entity_id)
    if not security or not security.usd_hashed_pwd or not verify_password(request.password, security.usd_hashed_pwd):
        await repo.increment_failed_login(
            user.usm_user_id,
            entity_id,
            settings.lockout_threshold,
            settings.lockout_duration_minutes,
        )
        raise AppError(INVALID_CREDENTIALS)

    # 4. Reset failed login count on success
    if user.usm_failed_login_count > 0:
        await repo.reset_failed_login(user.usm_user_id, entity_id)

    # 5. Get user role
    role_id = await repo.get_user_role(user.usm_user_id, entity_id) or ""

    # 6. Create session
    session_id = str(uuid.uuid4())
    history = UserAuthenticationHistory(
        uah_user_id=user.usm_user_id,
        uah_session_id=session_id,
        uah_ip_address=ip_address,
        uah_invalid_login_attempt_count=0,
        uah_login_time=now,
    )
    await repo.create_auth_history(history)

    # 7. Generate tokens
    user_id_str = str(user.usm_user_id)
    access_token, access_exp = create_access_token(user_id_str, session_id)
    refresh_token, refresh_exp = create_refresh_token(user_id_str, session_id)
    access_exp = _to_datetime(access_exp)
    refresh_exp = _to_datetime(refresh_exp)

    # 8. Store session in Redis
    await hset_json("auth", "logged_in_users", user_id_str, {
        "accessToken": access_token,
        "accessTokenExpiry": access_exp.isoformat(),
        "refreshToken": refresh_token,
        "refreshTokenExpiry": refresh_exp.isoformat(),
        "userEmail": user.usm_user_email_id,
        "userMobile": user.usm_user_mobile_no or "",
        "userMappedEntityID": user.usm_entity_id or "",
        "userMappedRoleID": role_id,
        "userDisplayName": user.usm_user_display_name or "",
        "userLoggedInAt": now.isoformat(),
        "sessionID": session_id,
    })

    logger.info(
        "User logged in",
        extra={"x_user_id": user_id_str, "x_email": user.usm_user_email_id},
    )

    # 9. Return response
    return AuthTokenResponse(
        user_id=user_id_str,
        entity_id=user.usm_entity_id or "",
        email=user.usm_user_email_id or "",
        display_name=user.usm_user_display_name or "",
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_exp,
        refresh_token_expires_at=refresh_exp,
    )


async def refresh(
    request: RefreshRequest,
    session: AsyncSession,
) -> AuthTokenResponse:
    """Validate refresh token and issue new access + refresh token pair."""
    repo = UserRepository(session)

    # 1. Decode refresh token (verify_exp=False so we can give a clear TOKEN_EXPIRED error)
    claims = decode_token(request.refresh_token, verify_exp=False)
    if not claims:
        raise AppError(INVALID_TOKEN)

    user_id = claims.get("sub", "")
    session_id = claims.get("jti", "")

    # 2. Check Redis session exists and refresh token matches
    session_data = await hget_json("auth", "logged_in_users", user_id)
    if not session_data:
        raise AppError(SESSION_NOT_FOUND)

    if session_data.get("refreshToken") != request.refresh_token:
        raise AppError(STALE_TOKEN)

    # 3. Check if refresh token is expired
    now = datetime.now(timezone.utc)
    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    if exp <= now:
        await hdel("auth", "logged_in_users", user_id)
        await repo.update_logout_time(
            uuid.UUID(user_id), session_id, session_data.get("userMappedEntityID", "")
        )
        raise AppError(TOKEN_EXPIRED)

    # 4. Issue new token pair (same session ID)
    access_token, access_exp = create_access_token(user_id, session_id)
    refresh_token, refresh_exp = create_refresh_token(user_id, session_id)
    access_exp = _to_datetime(access_exp)
    refresh_exp = _to_datetime(refresh_exp)

    # 5. Update Redis session
    session_data["accessToken"] = access_token
    session_data["accessTokenExpiry"] = access_exp.isoformat()
    session_data["refreshToken"] = refresh_token
    session_data["refreshTokenExpiry"] = refresh_exp.isoformat()
    await hset_json("auth", "logged_in_users", user_id, session_data)

    logger.info("Tokens refreshed", extra={"x_user_id": user_id})

    return AuthTokenResponse(
        user_id=user_id,
        entity_id=session_data.get("userMappedEntityID", ""),
        email=session_data.get("userEmail", ""),
        display_name=session_data.get("userDisplayName", ""),
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_exp,
        refresh_token_expires_at=refresh_exp,
    )


async def logout(
    user_id: str,
    session_id: str,
    entity_id: str,
    db_session: AsyncSession,
) -> LogoutResponse:
    """Invalidate session by removing from Redis and recording logout time."""
    repo = UserRepository(db_session)

    await hdel("auth", "logged_in_users", user_id)
    await repo.update_logout_time(uuid.UUID(user_id), session_id, entity_id)

    logger.info("User logged out", extra={"x_user_id": user_id})
    return LogoutResponse()


async def forgot_password(
    request: ForgotPasswordRequest,
    session: AsyncSession,
) -> MessageResponse:
    """Send OTP to user's email for password reset."""
    repo = UserRepository(session)
    user = await repo.find_by_email(request.email)

    # Always return 200 — don't reveal if email exists
    if not user:
        return MessageResponse(
            message="If the email is registered, an OTP has been sent"
        )

    # Generate 6-digit OTP
    otp = str(secrets.randbelow(900000) + 100000)
    otp_hash = hash_password(otp)

    # Store in Redis with TTL
    user_id_str = str(user.usm_user_id)
    otp_expiry = settings.otp_expiry_minutes
    await hset_json("auth", f"password_reset:{user_id_str}", "data", {
        "otp_hash": otp_hash,
        "email": request.email,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    from shared.redis.client import redis_client, ENVIRONMENT
    key = f"{ENVIRONMENT}:onelenz:auth:password_reset:{user_id_str}"
    await redis_client.expire(key, otp_expiry * 60)

    await send_otp_email(request.email, otp)

    logger.info("Password reset OTP sent", extra={"x_user_id": user_id_str})
    return MessageResponse(
        message="If the email is registered, an OTP has been sent"
    )


async def reset_password(
    request: ResetPasswordRequest,
    session: AsyncSession,
) -> MessageResponse:
    """Verify OTP and reset password."""
    repo = UserRepository(session)
    user = await repo.find_by_email(request.email)
    if not user:
        raise AppError(INVALID_OTP)

    user_id_str = str(user.usm_user_id)
    entity_id = user.usm_entity_id or ""

    # Get OTP from Redis
    otp_data = await hget_json("auth", f"password_reset:{user_id_str}", "data")
    if not otp_data:
        raise AppError(OTP_EXPIRED)

    # Verify OTP
    if not verify_password(request.otp, otp_data["otp_hash"]):
        raise AppError(INVALID_OTP)

    # Hash new password and update
    hashed_pwd = hash_password(request.new_password)
    await repo.update_password(user.usm_user_id, entity_id, hashed_pwd)

    # Delete OTP from Redis
    await hdel("auth", f"password_reset:{user_id_str}", "data")

    # Invalidate all sessions
    await hdel("auth", "logged_in_users", user_id_str)

    logger.info("Password reset successfully", extra={"x_user_id": user_id_str})
    return MessageResponse(
        message="Password reset successfully. Please login with your new password."
    )


async def change_password(
    request: ChangePasswordRequest,
    user_id: str,
    entity_id: str,
    session: AsyncSession,
) -> MessageResponse:
    """Change password for logged-in user."""
    repo = UserRepository(session)

    security = await repo.get_security_details(uuid.UUID(user_id), entity_id)
    if not security or not security.usd_hashed_pwd:
        raise AppError(WRONG_PASSWORD)
    if not verify_password(request.current_password, security.usd_hashed_pwd):
        raise AppError(WRONG_PASSWORD)

    hashed_pwd = hash_password(request.new_password)
    await repo.update_password(uuid.UUID(user_id), entity_id, hashed_pwd)

    logger.info("Password changed", extra={"x_user_id": user_id})
    return MessageResponse(message="Password changed successfully")
