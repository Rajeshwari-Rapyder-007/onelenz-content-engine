from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import CurrentUser, get_current_user, get_current_user_allow_expired
from shared.db import get_session

from ...schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
)
from ...services.auth_service import (
    change_password,
    forgot_password,
    login,
    logout,
    refresh,
    reset_password,
    signup,
)

router = APIRouter()


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For header or fallback to client host."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/signup", status_code=201)
async def signup_route(
    body: SignupRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user and auto-login."""
    return await signup(body, _get_client_ip(request), session)


@router.post("/login")
async def login_route(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Authenticate user with email and password."""
    return await login(body, _get_client_ip(request), session)


@router.post("/refresh")
async def refresh_route(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
):
    """Reissue access + refresh tokens using a valid refresh token."""
    return await refresh(body, session)


@router.post("/logout")
async def logout_route(
    user: CurrentUser = Depends(get_current_user_allow_expired),
    session: AsyncSession = Depends(get_session),
):
    """Invalidate the current session."""
    return await logout(user.user_id, user.session_id, user.entity_id, session)


@router.post("/forgot-password")
async def forgot_password_route(
    body: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """Send OTP to registered email for password reset."""
    return await forgot_password(body, session)


@router.post("/reset-password")
async def reset_password_route(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify OTP and set new password."""
    return await reset_password(body, session)


@router.post("/change-password")
async def change_password_route(
    body: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Change password for logged-in user."""
    return await change_password(body, user.user_id, user.entity_id, session)