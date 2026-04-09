from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import CurrentUser, get_current_user
from shared.db import get_session

from ...schemas.email import CallbackRequest
from ...services import oauth_service

router = APIRouter()


@router.post("/connect")
async def connect_route(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Initiate OAuth flow. Returns Microsoft authorization URL."""
    return await oauth_service.initiate_connect(user, session)


@router.post("/callback")
async def callback_route(
    body: CallbackRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Receive authorization code from UI, exchange for tokens."""
    return await oauth_service.handle_callback(body.code, body.state, session)


@router.get("/status")
async def status_route(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get current integration status and sync stats."""
    return await oauth_service.get_status(user, session)


@router.post("/disconnect")
async def disconnect_route(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Disconnect integration. Data is retained."""
    return await oauth_service.disconnect(user, session)


@router.post("/sync", status_code=202)
async def manual_sync_route(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Trigger a manual incremental sync outside the 15-min schedule (admin only)."""
    return await oauth_service.trigger_manual_sync(user, session)
