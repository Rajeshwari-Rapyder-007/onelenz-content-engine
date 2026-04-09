from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from shared.errors import AppError
from shared.errors.codes import INVALID_TOKEN, SESSION_NOT_FOUND, STALE_TOKEN, UNAUTHORIZED
from shared.logging import get_logger, request_context
from shared.redis.client import hget_json

from .jwt import decode_token

logger = get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """User context returned by the auth middleware."""

    user_id: str
    entity_id: str
    role_id: str
    email: str
    session_id: str
    display_name: str = ""


async def _validate_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    allow_expired: bool = False,
) -> CurrentUser:
    """Core validation logic. Used by both get_current_user and get_current_user_allow_expired."""
    # 1. Extract token from Authorization header
    if not credentials:
        raise AppError(UNAUTHORIZED, detail="Missing authorization header")

    token = credentials.credentials

    # 2. Decode and verify JWT
    claims = decode_token(token, verify_exp=not allow_expired)
    if not claims:
        # If expired and not allowed, try decoding without exp to get user_id for error context
        if not allow_expired:
            raise AppError(INVALID_TOKEN)
        # For allow_expired, decode without exp check
        claims = decode_token(token, verify_exp=False)
        if not claims:
            raise AppError(INVALID_TOKEN)

    user_id = claims.get("sub", "")
    session_id = claims.get("jti", "")

    # 3. Check Redis for active session
    session_data = await hget_json("auth", "logged_in_users", user_id)
    if not session_data:
        if allow_expired:
            # For logout, session might already be gone — still return user context
            return CurrentUser(
                user_id=user_id,
                entity_id="",
                role_id="",
                email="",
                session_id=session_id,
            )
        raise AppError(SESSION_NOT_FOUND)

    # 4. Compare token with stored access token (skip for expired tokens)
    if not allow_expired and session_data.get("accessToken") != token:
        raise AppError(STALE_TOKEN)

    # 5. Update logging context with user info
    ctx = request_context()
    ctx.user_id = user_id
    ctx.session_id = session_id

    # 6. Return user context
    return CurrentUser(
        user_id=user_id,
        entity_id=session_data.get("userMappedEntityID", ""),
        role_id=session_data.get("userMappedRoleID", ""),
        email=session_data.get("userEmail", ""),
        session_id=session_id,
        display_name=session_data.get("userDisplayName", ""),
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> CurrentUser:
    """FastAPI dependency that validates the JWT access token.

    Usage in routes:
        @router.post("/some-protected-route")
        async def handler(user: CurrentUser = Depends(get_current_user)):
            ...
    """
    return await _validate_user(credentials)


async def get_current_user_allow_expired(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> CurrentUser:
    """Same as get_current_user but allows expired tokens. Used for logout."""
    return await _validate_user(credentials, allow_expired=True)
