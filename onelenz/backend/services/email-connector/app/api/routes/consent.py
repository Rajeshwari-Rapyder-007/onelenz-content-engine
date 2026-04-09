from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import CurrentUser, get_current_user
from shared.db import get_session

from ...schemas.consent import ConsentGrantRequest, ConsentRevokeRequest
from ...services import consent_service

router = APIRouter()


@router.post("/grant", status_code=201)
async def grant_consent_route(
    body: ConsentGrantRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Grant consent for an entity."""
    return await consent_service.grant_consent(
        user, body.consent_type, body.domain_scope, session
    )


@router.post("/revoke")
async def revoke_consent_route(
    body: ConsentRevokeRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Revoke consent for an entity."""
    await consent_service.revoke_consent(user, body.consent_type, session)
    return {"message": "Consent revoked"}


@router.get("/status")
async def consent_status_route(
    consent_type: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get consent status for an entity."""
    return await consent_service.get_consent_status(user, consent_type, session)