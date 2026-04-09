"""Internal endpoints for service-to-service calls."""
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.errors import AppError
from shared.errors.codes import UNAUTHORIZED
from shared.logging import get_logger

from ...config import settings
from ...services import asset_service

logger = get_logger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


class AutoScrapeRequest(BaseModel):
    """Request body for the auto-scrape endpoint."""

    entity_id: str
    website_url: str


def _verify_service_key(
    x_service_key: str = Header(...),
) -> None:
    """Verify internal service-to-service auth."""
    if x_service_key != settings.internal_service_key:
        raise AppError(UNAUTHORIZED)


@router.post("/auto-scrape")
async def auto_scrape(
    body: AutoScrapeRequest,
    _auth: None = Depends(_verify_service_key),
    session: AsyncSession = Depends(get_session),
):
    """Called by auth-service on subscriber signup.

    Triggers automatic website scrape for the
    subscriber's company URL.
    """
    logger.info(
        "KH-0 auto-scrape: entity=%s url=%s",
        body.entity_id,
        body.website_url,
    )
    result = await asset_service.create_url_asset(
        url=body.website_url,
        entity_id=body.entity_id,
        user_id="system",
        session=session,
        category_id=None,
    )
    return {
        "asset_id": result["asset_id"],
        "status": result["status"],
    }
