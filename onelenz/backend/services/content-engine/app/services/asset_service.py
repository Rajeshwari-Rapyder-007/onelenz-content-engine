"""Asset lifecycle management."""
from __future__ import annotations

import io
import zipfile
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import AppError
from shared.errors.codes import (
    CONTENT_ASSET_NOT_FOUND,
    CONTENT_ASSET_PROCESSING,
    CONTENT_DAILY_LIMIT_REACHED,
    CONTENT_FILE_TOO_LARGE,
    CONTENT_INVALID_CATEGORY,
    CONTENT_INVALID_URL,
    CONTENT_TOO_MANY_FILES,
    CONTENT_UNSUPPORTED_FILE_TYPE,
    CONTENT_ZIP_INVALID,
)
from shared.logging import get_logger
from shared.s3.client import delete_object, upload_bytes

from ..config import settings
from ..models.asset import ContentAsset
from ..repositories.asset_repository import (
    AssetRepository,
)
from ..repositories.chunk_repository import (
    ChunkRepository,
)
from ..services.extraction_service import (
    check_url_reachable,
    detect_source_type_from_url,
)
from ..workers.ingestion_tasks import dispatch_ingestion

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = set(
    settings.allowed_file_types.split(",")
)
PROCESSING_STATUSES = {
    "EXTRACTING",
    "CHUNKING",
    "EMBEDDING",
    "REPLACING",
}
VALID_CATEGORIES = {
    "MARKETING_COLLATERAL",
    "SOW_PROJECT_DOC",
    "PRODUCT_WORKBOOK",
    "CASE_STUDY",
    "BLOG",
    "PRESS_RELEASE",
    "WEBSITE_PAGE",
    "SOCIAL_MEDIA",
}


def _get_file_extension(filename: str) -> str:
    """Extract extension from filename, lowercase, no dot."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower().strip(".")


def _asset_to_dict(asset: ContentAsset) -> dict[str, Any]:
    """Convert a ContentAsset model to a response dict."""
    return {
        "asset_id": str(asset.ca_asset_id),
        "entity_id": str(asset.ca_entity_id),
        "category_id": asset.ca_category_id,
        "source_type": asset.ca_source_type,
        "file_name": asset.ca_file_name,
        "file_type": asset.ca_file_type,
        "file_size_bytes": asset.ca_file_size_bytes,
        "page_count": asset.ca_page_count,
        "s3_key": asset.ca_s3_key,
        "status": asset.ca_status,
        "error_message": asset.ca_error_message,
        "chunk_count": asset.ca_chunk_count,
        "credits_consumed": (
            float(asset.ca_credits_consumed)
            if asset.ca_credits_consumed is not None
            else None
        ),
        "created_by": asset.created_by,
        "created_on": (
            asset.created_on.isoformat()
            if asset.created_on
            else None
        ),
        "modified_on": (
            asset.modified_on.isoformat()
            if asset.modified_on
            else None
        ),
    }


def _s3_key(
    entity_id: str, asset_id: str, filename: str
) -> str:
    """Build the S3 key for a raw asset file."""
    return (
        f"{entity_id}/content-engine/"
        f"{asset_id}/raw/{filename}"
    )


def _validate_category(category_id: str | None) -> None:
    """Raise if category_id is provided but invalid."""
    if (
        category_id is not None
        and category_id not in VALID_CATEGORIES
    ):
        raise AppError(
            CONTENT_INVALID_CATEGORY,
            f"Invalid category: {category_id}",
        )


async def _check_daily_limit(
    repo: AssetRepository,
    entity_id: str,
) -> None:
    """Raise if entity has reached daily asset limit."""
    count = await repo.count_today_by_entity(entity_id)
    if count >= settings.max_assets_per_day_per_entity:
        raise AppError(CONTENT_DAILY_LIMIT_REACHED)


async def _fetch_asset(
    repo: AssetRepository,
    asset_id: str,
    entity_id: str,
) -> ContentAsset:
    """Fetch asset and verify it belongs to entity."""
    asset = await repo.get_by_id(
        "ca_asset_id", asset_id
    )
    if asset is None or str(asset.ca_entity_id) != str(
        entity_id
    ):
        raise AppError(CONTENT_ASSET_NOT_FOUND)
    return asset


async def create_file_assets(
    files: list[UploadFile],
    entity_id: str,
    user_id: str,
    category_id: str | None,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Upload files (including ZIPs) and create assets."""
    if len(files) > settings.max_files_per_upload:
        raise AppError(
            CONTENT_TOO_MANY_FILES,
            f"Maximum {settings.max_files_per_upload}"
            f" files per upload",
        )

    _validate_category(category_id)

    repo = AssetRepository(session)
    await _check_daily_limit(repo, entity_id)

    # Collect (filename, content_bytes) pairs to process
    file_items: list[tuple[str, bytes]] = []

    for f in files:
        ext = _get_file_extension(f.filename or "")
        if ext not in ALLOWED_EXTENSIONS:
            raise AppError(
                CONTENT_UNSUPPORTED_FILE_TYPE,
                f"Unsupported file type: .{ext}",
            )

        content = await f.read()

        if len(content) > settings.max_file_size_bytes:
            raise AppError(
                CONTENT_FILE_TOO_LARGE,
                f"File {f.filename} exceeds "
                f"{settings.max_file_size_bytes} bytes",
            )

        if ext == "zip":
            # Handle ZIP extraction
            extracted = _extract_zip(content)
            file_items.extend(extracted)
        else:
            file_items.append(
                (f.filename or "unknown", content)
            )

    created: list[dict[str, Any]] = []

    for filename, content in file_items:
        ext = _get_file_extension(filename)
        asset = ContentAsset(
            ca_entity_id=entity_id,
            ca_category_id=category_id,
            ca_source_type="FILE",
            ca_file_name=filename,
            ca_file_type=ext,
            ca_file_size_bytes=len(content),
            ca_status="PENDING",
            created_by=user_id,
        )
        session.add(asset)
        await session.flush()

        asset_id = str(asset.ca_asset_id)
        key = _s3_key(entity_id, asset_id, filename)
        asset.ca_s3_key = key

        content_type = (
            "application/octet-stream"
        )
        await upload_bytes(
            settings.s3_bucket_content,
            key,
            content,
            content_type,
        )

        dispatch_ingestion(
            asset_id=asset_id,
            entity_id=entity_id,
            source_type="FILE",

        )

        created.append(_asset_to_dict(asset))

    await session.commit()
    return created


def _extract_zip(
    zip_bytes: bytes,
) -> list[tuple[str, bytes]]:
    """Extract files from a ZIP archive.

    Rejects nested ZIPs, enforces size and count limits.
    Returns list of (filename, content_bytes).
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except (zipfile.BadZipFile, Exception) as exc:
        raise AppError(
            CONTENT_ZIP_INVALID,
            f"Cannot read ZIP: {exc}",
        )

    entries = [
        info
        for info in zf.infolist()
        if not info.is_dir()
    ]

    if len(entries) > settings.max_files_per_zip:
        raise AppError(
            CONTENT_TOO_MANY_FILES,
            f"ZIP contains {len(entries)} files, "
            f"max {settings.max_files_per_zip}",
        )

    total_size = sum(
        info.file_size for info in entries
    )
    if total_size > settings.max_zip_decompressed_bytes:
        raise AppError(
            CONTENT_FILE_TOO_LARGE,
            "ZIP decompressed size exceeds limit",
        )

    items: list[tuple[str, bytes]] = []
    for info in entries:
        name = info.filename.rsplit("/", 1)[-1]
        ext = _get_file_extension(name)

        if ext == "zip":
            raise AppError(
                CONTENT_ZIP_INVALID,
                "Nested ZIP files are not allowed",
            )

        if ext not in ALLOWED_EXTENSIONS:
            raise AppError(
                CONTENT_UNSUPPORTED_FILE_TYPE,
                f"Unsupported file in ZIP: .{ext}",
            )

        data = zf.read(info.filename)
        items.append((name, data))

    zf.close()
    return items


async def create_url_asset(
    url: str,
    entity_id: str,
    user_id: str,
    category_id: str | None,
    session: AsyncSession,
) -> dict[str, Any]:
    """Create an asset from a URL."""
    reachable = await check_url_reachable(url)
    if not reachable:
        raise AppError(
            CONTENT_INVALID_URL,
            f"URL is not reachable: {url}",
        )

    _validate_category(category_id)

    repo = AssetRepository(session)
    await _check_daily_limit(repo, entity_id)

    source_type = detect_source_type_from_url(url)

    asset = ContentAsset(
        ca_entity_id=entity_id,
        ca_category_id=category_id,
        ca_source_type=source_type,
        ca_file_name=url,
        ca_file_type=None,
        ca_file_size_bytes=None,
        ca_s3_key=None,
        ca_status="PENDING",
        created_by=user_id,
    )
    session.add(asset)
    await session.flush()

    asset_id = str(asset.ca_asset_id)

    dispatch_ingestion(
        asset_id=asset_id,
        entity_id=entity_id,
        source_type=source_type,
    )

    await session.commit()
    return _asset_to_dict(asset)


async def list_assets(
    entity_id: str,
    session: AsyncSession,
    category_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Return paginated asset list for an entity."""
    repo = AssetRepository(session)
    items, total = await repo.find_by_entity(
        entity_id=entity_id,
        category_id=category_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_asset_to_dict(a) for a in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_asset(
    asset_id: str,
    entity_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Fetch a single asset by ID."""
    repo = AssetRepository(session)
    asset = await _fetch_asset(
        repo, asset_id, entity_id
    )
    return _asset_to_dict(asset)


async def update_asset(
    asset_id: str,
    entity_id: str,
    updates: dict[str, Any],
    session: AsyncSession,
) -> dict[str, Any]:
    """Update mutable fields on an asset."""
    repo = AssetRepository(session)
    asset = await _fetch_asset(
        repo, asset_id, entity_id
    )

    new_category = updates.get("category_id")
    if new_category is not None:
        _validate_category(new_category)
        if new_category != asset.ca_category_id:
            asset.ca_category_id = new_category
            # Update category on all associated chunks
            from sqlalchemy import update as sql_update

            from ..models.chunk import ContentChunk

            stmt = (
                sql_update(ContentChunk)
                .where(
                    ContentChunk.ck_asset_id
                    == asset_id
                )
                .values(ck_category_id=new_category)
            )
            await session.execute(stmt)

    if "file_name" in updates:
        asset.ca_file_name = updates["file_name"]

    await session.commit()
    return _asset_to_dict(asset)


async def delete_asset(
    asset_id: str,
    entity_id: str,
    session: AsyncSession,
) -> None:
    """Delete an asset, its chunks, and S3 files."""
    repo = AssetRepository(session)
    asset = await _fetch_asset(
        repo, asset_id, entity_id
    )

    if asset.ca_status in PROCESSING_STATUSES:
        raise AppError(CONTENT_ASSET_PROCESSING)

    # Delete chunks
    chunk_repo = ChunkRepository(session)
    await chunk_repo.delete_by_asset_id(asset_id)

    # Delete S3 file if present
    if asset.ca_s3_key:
        try:
            await delete_object(
                settings.s3_bucket_content,
                asset.ca_s3_key,
            )
        except Exception:
            logger.warning(
                "Failed to delete S3 object %s",
                asset.ca_s3_key,
            )

    # Delete asset record
    await repo.delete_by_id("ca_asset_id", asset_id)
    await session.commit()


async def replace_asset(
    asset_id: str,
    entity_id: str,
    file: UploadFile,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Replace an INDEXED asset's file and re-ingest."""
    repo = AssetRepository(session)
    asset = await _fetch_asset(
        repo, asset_id, entity_id
    )

    if asset.ca_status != "INDEXED":
        raise AppError(
            CONTENT_ASSET_PROCESSING,
            "Asset must be INDEXED to replace",
        )

    content = await file.read()
    filename = file.filename or "unknown"
    ext = _get_file_extension(filename)

    if ext not in ALLOWED_EXTENSIONS:
        raise AppError(
            CONTENT_UNSUPPORTED_FILE_TYPE,
            f"Unsupported file type: .{ext}",
        )

    if len(content) > settings.max_file_size_bytes:
        raise AppError(CONTENT_FILE_TOO_LARGE)

    key = _s3_key(entity_id, asset_id, filename)
    await upload_bytes(
        settings.s3_bucket_content,
        key,
        content,
        "application/octet-stream",
    )

    asset.ca_s3_key = key
    asset.ca_file_name = filename
    asset.ca_file_type = ext
    asset.ca_file_size_bytes = len(content)
    asset.ca_status = "REPLACING"
    asset.modified_by = user_id

    await session.commit()

    dispatch_ingestion(
        asset_id=str(asset.ca_asset_id),
        entity_id=entity_id,
        source_type="FILE",
    )

    return _asset_to_dict(asset)


async def retry_asset(
    asset_id: str,
    entity_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Retry ingestion for a FAILED asset."""
    repo = AssetRepository(session)
    asset = await _fetch_asset(
        repo, asset_id, entity_id
    )

    if asset.ca_status != "FAILED":
        raise AppError(
            CONTENT_ASSET_PROCESSING,
            "Only FAILED assets can be retried",
        )

    asset.ca_status = "PENDING"
    asset.ca_error_message = None
    await session.commit()

    dispatch_ingestion(
        asset_id=str(asset.ca_asset_id),
        entity_id=entity_id,
        source_type=asset.ca_source_type,
    )

    return _asset_to_dict(asset)


async def rescrape_asset(
    asset_id: str,
    entity_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Re-scrape a WEBSITE_SCRAPE asset."""
    repo = AssetRepository(session)
    asset = await _fetch_asset(
        repo, asset_id, entity_id
    )

    if asset.ca_source_type != "WEBSITE_SCRAPE":
        raise AppError(
            CONTENT_ASSET_NOT_FOUND,
            "Only WEBSITE_SCRAPE assets can be rescraped",
        )

    if asset.ca_status != "INDEXED":
        raise AppError(
            CONTENT_ASSET_PROCESSING,
            "Asset must be INDEXED to rescrape",
        )

    asset.ca_status = "REPLACING"
    await session.commit()

    dispatch_ingestion(
        asset_id=str(asset.ca_asset_id),
        entity_id=entity_id,
        source_type="WEBSITE_SCRAPE",
    )

    return _asset_to_dict(asset)


async def get_stats(
    entity_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Return aggregated stats for an entity."""
    repo = AssetRepository(session)
    return await repo.get_stats_by_entity(entity_id)
