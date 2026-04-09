"""Asset management API routes."""
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import CurrentUser, get_current_user
from shared.db import get_session
from shared.errors import AppError
from shared.errors.codes import FORBIDDEN
from shared.logging import get_logger

from ...schemas.asset import (
    AssetDetailResponse,
    AssetListResponse,
    AssetResponse,
    AssetUpdateRequest,
    StatsResponse,
    UrlCreateResponse,
    UrlSubmitRequest,
)
from ...services.asset_service import (
    create_file_assets,
    create_url_asset,
    delete_asset,
    get_asset,
    get_stats,
    list_assets,
    replace_asset,
    rescrape_asset,
    retry_asset,
    update_asset,
)

logger = get_logger(__name__)

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────


def _require_admin(user: CurrentUser) -> None:
    """Raise 403 if user is not SUB_ADMIN."""
    if user.role_id not in ("SUB_ADMIN", "ADMIN"):
        raise AppError(FORBIDDEN)


def _require_read_access(user: CurrentUser) -> None:
    """Raise 403 if user is not SUB_ADMIN, ADMIN, or SELLER."""
    if user.role_id not in (
        "SUB_ADMIN",
        "ADMIN",
        "SELLER",
    ):
        raise AppError(FORBIDDEN)


def _to_asset_response(data: dict) -> AssetResponse:
    """Map service dict to AssetResponse schema."""
    return AssetResponse(
        asset_id=data["asset_id"],
        file_name=data["file_name"],
        category_id=data.get("category_id"),
        source_type=data["source_type"],
        status=data["status"],
        chunk_count=data.get("chunk_count"),
        page_count=data.get("page_count"),
        credits_consumed=data.get("credits_consumed"),
        created_on=data["created_on"],
    )


def _to_detail_response(
    data: dict,
) -> AssetDetailResponse:
    """Map service dict to AssetDetailResponse schema."""
    return AssetDetailResponse(
        asset_id=data["asset_id"],
        file_name=data["file_name"],
        category_id=data.get("category_id"),
        source_type=data["source_type"],
        status=data["status"],
        file_size_bytes=data.get("file_size_bytes"),
        page_count=data.get("page_count"),
        chunk_count=data.get("chunk_count"),
        credits_consumed=data.get("credits_consumed"),
        error_message=data.get("error_message"),
        created_on=data["created_on"],
        modified_on=data.get("modified_on"),
    )


# ── Routes ─────────────────────────────────────────────────────────


@router.post("/assets/upload", status_code=202)
async def upload_assets(
    files: list[UploadFile] = File(...),
    category_id: str | None = Form(None),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Upload one or more files as assets."""
    _require_admin(user)
    result = await create_file_assets(
        files=files,
        entity_id=user.entity_id,
        user_id=user.user_id,
        category_id=category_id,
        session=session,
    )
    return {
        "assets": [_to_asset_response(r) for r in result],
    }


@router.post("/assets/url", status_code=202)
async def submit_url(
    body: UrlSubmitRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Submit a URL for scraping."""
    _require_admin(user)
    result = await create_url_asset(
        url=str(body.url),
        entity_id=user.entity_id,
        user_id=user.user_id,
        category_id=body.category_id,
        session=session,
    )
    return UrlCreateResponse(
        asset_id=result["asset_id"],
        url=result["file_name"],
        source_type=result["source_type"],
        status=result["status"],
    )


@router.get("/assets")
async def list_assets_route(
    category_id: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List assets with optional filters."""
    _require_read_access(user)
    result = await list_assets(
        entity_id=user.entity_id,
        session=session,
        category_id=category_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return AssetListResponse(
        items=[
            _to_asset_response(i)
            for i in result["items"]
        ],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/assets/{asset_id}")
async def get_asset_route(
    asset_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get asset detail by ID."""
    _require_read_access(user)
    result = await get_asset(
        asset_id=str(asset_id),
        entity_id=user.entity_id,
        session=session,
    )
    return _to_detail_response(result)


@router.patch("/assets/{asset_id}")
async def update_asset_route(
    asset_id: UUID,
    body: AssetUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update asset metadata."""
    _require_admin(user)
    updates = body.model_dump(exclude_none=True)
    result = await update_asset(
        asset_id=str(asset_id),
        entity_id=user.entity_id,
        updates=updates,
        session=session,
    )
    return _to_detail_response(result)


@router.put(
    "/assets/{asset_id}/replace", status_code=202
)
async def replace_asset_route(
    asset_id: UUID,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Replace an existing asset's file."""
    _require_admin(user)
    result = await replace_asset(
        asset_id=str(asset_id),
        entity_id=user.entity_id,
        file=file,
        user_id=user.user_id,
        session=session,
    )
    return _to_detail_response(result)


@router.post(
    "/assets/{asset_id}/retry", status_code=202
)
async def retry_asset_route(
    asset_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retry ingestion for a failed asset."""
    _require_admin(user)
    result = await retry_asset(
        asset_id=str(asset_id),
        entity_id=user.entity_id,
        session=session,
    )
    return _to_asset_response(result)


@router.post(
    "/assets/{asset_id}/rescrape", status_code=202
)
async def rescrape_asset_route(
    asset_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Re-scrape a website asset."""
    _require_admin(user)
    result = await rescrape_asset(
        asset_id=str(asset_id),
        entity_id=user.entity_id,
        session=session,
    )
    return _to_asset_response(result)


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset_route(
    asset_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete an asset and its chunks."""
    _require_admin(user)
    await delete_asset(
        asset_id=str(asset_id),
        entity_id=user.entity_id,
        session=session,
    )


@router.get("/stats")
async def get_stats_route(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get aggregated asset stats for the entity."""
    _require_read_access(user)
    result = await get_stats(
        entity_id=user.entity_id,
        session=session,
    )
    return StatsResponse(**result)
