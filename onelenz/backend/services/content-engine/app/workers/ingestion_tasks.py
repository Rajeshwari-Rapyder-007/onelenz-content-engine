"""Celery tasks for the content ingestion pipeline.

Chain: task_extract -> task_chunk -> task_embed
Each task returns a JSON-serializable dict that Celery
passes as the first argument to the next task.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from celery import chain
from sqlalchemy import select, update

from shared.db.adapter import async_session_factory
from shared.logging import get_logger
from shared.s3.client import upload_json

from ..config import settings
from ..models.asset import ContentAsset
from ..models.chunk import ContentChunk
from ..repositories.asset_repository import AssetRepository
from ..repositories.chunk_repository import ChunkRepository
from ..services.chunking_service import (
    chunk_markdown,
)
from ..services.classification_service import (
    classify,
    classify_website_pages,
)
from ..services.embedding_service import embed_batch
from ..services.extraction_service import (
    extract_file,
    extract_url,
    extract_website,
    reclassify_if_listing,
)
from .celery_app import celery_app

logger = get_logger(__name__)


# ── helpers ──────────────────────────────────────


def run_async(coro: Any) -> Any:
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, coro
                ).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@asynccontextmanager
async def get_session_ctx():
    """Provide an async DB session as a context manager.

    Unlike the FastAPI dependency (which yields), this
    can be used directly in Celery tasks via run_async.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _s3_client():
    """Return a boto3 S3 client (sync)."""
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
    )


def _download_s3_bytes(s3_key: str) -> bytes:
    """Download an S3 object as bytes."""
    from io import BytesIO

    buf = BytesIO()
    _s3_client().download_fileobj(
        settings.s3_bucket_content, s3_key, buf
    )
    return buf.getvalue()


def _extracted_s3_key(
    entity_id: str, asset_id: str
) -> str:
    """S3 key for storing extracted JSON."""
    return (
        f"{entity_id}/content-engine/"
        f"{asset_id}/extracted/extracted.json"
    )


# ── task 1: extract ──────────────────────────────


@celery_app.task(
    bind=True,
    max_retries=settings.ingestion_task_retries,
    default_retry_delay=30,
)
def task_extract(
    self,
    asset_id: str,
    entity_id: str,
    source_type: str,
) -> dict:
    """Extract text from a file or URL.

    Returns a dict consumed by task_chunk.
    """

    async def _run() -> dict:
        # 1. Mark asset as EXTRACTING
        async with get_session_ctx() as session:
            repo = AssetRepository(session)
            await repo.update_status(
                asset_id, "EXTRACTING"
            )

        # 2. Fetch asset record for file name / s3 key
        async with get_session_ctx() as session:
            stmt = select(ContentAsset).where(
                ContentAsset.ca_asset_id == asset_id
            )
            result = await session.execute(stmt)
            asset = result.scalars().first()
            if asset is None:
                raise ValueError(
                    f"Asset {asset_id} not found"
                )
            file_name = asset.ca_file_name
            s3_key = asset.ca_s3_key
            file_type = asset.ca_file_type

        current_source = source_type
        extracted: dict = {}
        page_count = 0

        try:
            if current_source == "FILE":
                # 3. Download from S3, extract
                if not s3_key:
                    raise ValueError(
                        f"No S3 key for FILE asset "
                        f"{asset_id}"
                    )
                file_bytes = _download_s3_bytes(s3_key)
                result = await extract_file(
                    file_bytes=file_bytes,
                    file_name=file_name,
                    file_type=file_type or "PDF",
                )
                doc = result["document"]
                page_count = result["page_count"]
                # Serialize DoclingDocument to
                # markdown for inter-task transfer
                if hasattr(doc, "export_to_markdown"):
                    md_text = doc.export_to_markdown()
                else:
                    md_text = str(doc)
                extracted = {
                    "markdown": md_text,
                    "file_type": file_type,
                }

            elif current_source == "URL":
                # 4. Extract single URL
                result = await extract_url(file_name)
                page_count = result["page_count"]
                links = result.get("links", [])

                # 6. Reclassify if listing page
                new_type = reclassify_if_listing(
                    file_name, links
                )
                if new_type == "WEBSITE_SCRAPE":
                    current_source = "WEBSITE_SCRAPE"
                    async with get_session_ctx() as sess:
                        await sess.execute(
                            update(ContentAsset)
                            .where(
                                ContentAsset.ca_asset_id
                                == asset_id
                            )
                            .values(
                                ca_source_type=(
                                    "WEBSITE_SCRAPE"
                                )
                            )
                        )
                    ws_result = await extract_website(
                        file_name
                    )
                    extracted = {
                        "pages": ws_result["pages"],
                    }
                    page_count = ws_result["page_count"]
                else:
                    extracted = {
                        "pages": result["pages"],
                    }

            elif current_source == "WEBSITE_SCRAPE":
                # 5. Full website crawl
                ws_result = await extract_website(
                    file_name
                )
                extracted = {"pages": ws_result["pages"]}
                page_count = ws_result["page_count"]
            else:
                raise ValueError(
                    f"Unknown source_type: "
                    f"{current_source}"
                )

            # 7. Save extracted text to S3 as JSON
            s3_extract_key = _extracted_s3_key(
                entity_id, asset_id
            )
            await upload_json(
                settings.s3_bucket_content,
                s3_extract_key,
                extracted,
            )

            # 8. Update page count on asset
            async with get_session_ctx() as session:
                await session.execute(
                    update(ContentAsset)
                    .where(
                        ContentAsset.ca_asset_id
                        == asset_id
                    )
                    .values(ca_page_count=page_count)
                )

            # 9. Return result for next task
            return {
                "asset_id": asset_id,
                "entity_id": entity_id,
                "source_type": current_source,
                "extracted_s3_key": s3_extract_key,
                "page_count": page_count,
                "file_type": file_type,
            }

        except Exception as exc:
            async with get_session_ctx() as session:
                repo = AssetRepository(session)
                await repo.update_status(
                    asset_id,
                    "FAILED",
                    error_message=str(exc)[:500],
                )
            raise

    try:
        return run_async(_run())
    except Exception as exc:
        logger.exception(
            "task_extract failed for asset %s",
            asset_id,
        )
        raise self.retry(exc=exc)


# ── task 2: chunk ────────────────────────────────


@celery_app.task(
    bind=True,
    max_retries=settings.ingestion_task_retries,
    default_retry_delay=30,
)
def task_chunk(
    self,
    prev_result: dict,
) -> dict:
    """Chunk extracted text into ContentChunk rows.

    Returns a dict consumed by task_embed.
    """
    asset_id: str = prev_result["asset_id"]
    entity_id: str = prev_result["entity_id"]
    source_type: str = prev_result["source_type"]
    extracted_s3_key: str = prev_result[
        "extracted_s3_key"
    ]
    page_count: int = prev_result["page_count"]
    file_type: str | None = prev_result.get("file_type")

    async def _run() -> dict:
        # 2. Update status -> CHUNKING
        async with get_session_ctx() as session:
            repo = AssetRepository(session)
            await repo.update_status(
                asset_id, "CHUNKING"
            )

        try:
            # Load extracted data from S3
            from shared.s3.client import download_json

            extracted = await download_json(
                settings.s3_bucket_content,
                extracted_s3_key,
            )

            raw_chunks: list[dict] = []

            if source_type == "FILE":
                # 3. File: chunk via chunk_document
                # We stored markdown; use chunk_markdown
                # as the DoclingDocument is not preserved
                raw_chunks = chunk_markdown(
                    extracted["markdown"]
                )
                # Enrich metadata with file_type
                for c in raw_chunks:
                    c["metadata"]["file_type"] = (
                        file_type
                    )

            elif source_type == "URL":
                # 4. URL: chunk markdown text
                raw_chunks = chunk_markdown(
                    extracted["markdown"]
                )

            elif source_type == "WEBSITE_SCRAPE":
                # 5. Website: chunk each page separately
                for page in extracted.get("pages", []):
                    page_chunks = chunk_markdown(
                        page["markdown"],
                        source_url=page.get("url"),
                    )
                    raw_chunks.extend(page_chunks)
            else:
                raise ValueError(
                    f"Unknown source_type: "
                    f"{source_type}"
                )

            if not raw_chunks:
                raise ValueError(
                    "Extraction produced no chunks "
                    f"for asset {asset_id}"
                )

            # Re-index chunks sequentially
            for i, c in enumerate(raw_chunks):
                c["chunk_index"] = i

            # 6-7. Build ContentChunk model instances
            chunk_models: list[ContentChunk] = []
            for c in raw_chunks:
                chunk_model = ContentChunk(
                    ck_asset_id=asset_id,
                    ck_entity_id=entity_id,
                    ck_category_id=None,
                    ck_chunk_index=c["chunk_index"],
                    ck_content_text=c["content_text"],
                    ck_section_heading=c.get(
                        "section_heading"
                    ),
                    ck_token_count=c["token_count"],
                    ck_data_origin=(
                        "SUBSCRIBER_UPLOADED"
                    ),
                    ck_metadata=c.get("metadata", {}),
                    ck_source_url=c.get("source_url"),
                )
                chunk_models.append(chunk_model)

            # 8. Bulk insert chunks
            async with get_session_ctx() as session:
                chunk_repo = ChunkRepository(session)
                await chunk_repo.bulk_insert(
                    chunk_models
                )

            chunk_ids = [
                str(m.ck_chunk_id)
                for m in chunk_models
            ]

            # 9. Update chunk count on asset
            async with get_session_ctx() as session:
                await session.execute(
                    update(ContentAsset)
                    .where(
                        ContentAsset.ca_asset_id
                        == asset_id
                    )
                    .values(
                        ca_chunk_count=len(chunk_ids)
                    )
                )

            return {
                "asset_id": asset_id,
                "entity_id": entity_id,
                "source_type": source_type,
                "chunk_ids": chunk_ids,
                "page_count": page_count,
            }

        except Exception as exc:
            # Clean up partial chunks on failure
            async with get_session_ctx() as session:
                chunk_repo = ChunkRepository(session)
                await chunk_repo.delete_by_asset_id(
                    asset_id
                )
            async with get_session_ctx() as session:
                repo = AssetRepository(session)
                await repo.update_status(
                    asset_id,
                    "FAILED",
                    error_message=str(exc)[:500],
                )
            raise

    try:
        return run_async(_run())
    except Exception as exc:
        logger.exception(
            "task_chunk failed for asset %s", asset_id
        )
        raise self.retry(exc=exc)


# ── task 3: embed ────────────────────────────────


@celery_app.task(
    bind=True,
    max_retries=settings.ingestion_task_retries,
    default_retry_delay=30,
)
def task_embed(
    self,
    prev_result: dict,
) -> dict:
    """Embed chunks, classify, and finalize asset.

    Category is always auto-classified.
    Returns a summary dict.
    """
    asset_id: str = prev_result["asset_id"]
    entity_id: str = prev_result["entity_id"]
    source_type: str = prev_result["source_type"]
    chunk_ids: list[str] = prev_result["chunk_ids"]
    page_count: int = prev_result["page_count"]

    async def _run() -> dict:
        batch_start = datetime.now(timezone.utc)

        # Check if this is a replacement flow BEFORE
        # updating status
        async with get_session_ctx() as session:
            stmt = select(ContentAsset).where(
                ContentAsset.ca_asset_id == asset_id
            )
            result = await session.execute(stmt)
            asset = result.scalars().first()
            is_replacing = (
                asset is not None
                and asset.ca_status == "REPLACING"
            )

        # 2. Update status -> EMBEDDING
        async with get_session_ctx() as session:
            repo = AssetRepository(session)
            await repo.update_status(
                asset_id, "EMBEDDING"
            )

        try:
            # 3. Fetch chunk texts from DB
            texts: list[str] = []
            async with get_session_ctx() as session:
                for cid in chunk_ids:
                    stmt = select(ContentChunk).where(
                        ContentChunk.ck_chunk_id == cid
                    )
                    result = await session.execute(stmt)
                    chunk = result.scalars().first()
                    if chunk:
                        texts.append(
                            chunk.ck_content_text
                        )

            if not texts:
                raise ValueError(
                    "No chunk texts found for asset "
                    f"{asset_id}"
                )

            # 4. Generate embeddings
            embeddings = await embed_batch(texts)

            # 5. Update chunks with embeddings
            chunk_updates = [
                {
                    "chunk_id": cid,
                    "embedding": emb,
                }
                for cid, emb in zip(
                    chunk_ids, embeddings
                )
            ]
            async with get_session_ctx() as session:
                chunk_repo = ChunkRepository(session)
                await chunk_repo.update_embeddings(
                    chunk_updates
                )

            # 6. Auto-classify content
            if (
                source_type == "WEBSITE_SCRAPE"
                and len(embeddings) > 1
            ):
                dominant, _ = (
                    await classify_website_pages(
                        embeddings
                    )
                )
                category_id = dominant
            else:
                category_id = await classify(
                    embeddings[0]
                )

            # 7. Update category on asset
            async with get_session_ctx() as session:
                await session.execute(
                    update(ContentAsset)
                    .where(
                        ContentAsset.ca_asset_id
                        == asset_id
                    )
                    .values(ca_category_id=category_id)
                )

            # Also update category on all chunks
            async with get_session_ctx() as session:
                await session.execute(
                    update(ContentChunk)
                    .where(
                        ContentChunk.ck_asset_id
                        == asset_id
                    )
                    .values(ck_category_id=category_id)
                )

            # 8. Calculate and store credits
            credits = Decimal(str(
                page_count * settings.credits_per_page
            ))
            async with get_session_ctx() as session:
                await session.execute(
                    update(ContentAsset)
                    .where(
                        ContentAsset.ca_asset_id
                        == asset_id
                    )
                    .values(
                        ca_credits_consumed=credits
                    )
                )

            # 10. Handle replacement flow cleanup
            if is_replacing:
                try:
                    async with (
                        get_session_ctx() as session
                    ):
                        chunk_repo = ChunkRepository(
                            session
                        )
                        await chunk_repo.delete_old_chunks(
                            asset_id, batch_start
                        )
                except Exception:
                    logger.exception(
                        "Failed to delete old chunks "
                        "during replacement for "
                        "asset %s, reverting to INDEXED",
                        asset_id,
                    )

            # 12. Mark as INDEXED
            async with get_session_ctx() as session:
                repo = AssetRepository(session)
                await repo.update_status(
                    asset_id, "INDEXED"
                )

            logger.info(
                "Ingestion complete for asset %s: "
                "%d chunks, category=%s, "
                "credits=%.2f",
                asset_id,
                len(chunk_ids),
                category_id,
                credits,
            )

            return {
                "asset_id": asset_id,
                "entity_id": entity_id,
                "category_id": category_id,
                "chunk_count": len(chunk_ids),
                "credits_consumed": float(credits),
                "status": "INDEXED",
            }

        except Exception as exc:
            # 11. On failure: clean up and set FAILED
            try:
                if is_replacing:
                    # Revert to INDEXED; keep old chunks
                    async with (
                        get_session_ctx() as session
                    ):
                        repo = AssetRepository(session)
                        await repo.update_status(
                            asset_id,
                            "INDEXED",
                            error_message=(
                                f"Replacement failed: "
                                f"{str(exc)[:400]}"
                            ),
                        )
                else:
                    # Delete all partial chunks
                    async with (
                        get_session_ctx() as session
                    ):
                        chunk_repo = ChunkRepository(
                            session
                        )
                        await (
                            chunk_repo.delete_by_asset_id(
                                asset_id
                            )
                        )
                    async with (
                        get_session_ctx() as session
                    ):
                        repo = AssetRepository(session)
                        await repo.update_status(
                            asset_id,
                            "FAILED",
                            error_message=(
                                str(exc)[:500]
                            ),
                        )
            except Exception:
                logger.exception(
                    "Failed to clean up after embed "
                    "failure for asset %s",
                    asset_id,
                )
            raise

    try:
        return run_async(_run())
    except Exception as exc:
        logger.exception(
            "task_embed failed for asset %s", asset_id
        )
        raise self.retry(exc=exc)


# ── helpers ──────────────────────────────────────


# ── dispatch ─────────────────────────────────────


def dispatch_ingestion(
    asset_id: str,
    entity_id: str,
    source_type: str,
) -> None:
    """Dispatch the 3-task ingestion chain.

    Called from the API layer after asset creation.
    Category is always auto-classified. User can
    update it later via PATCH /content/assets/{id}.
    """
    workflow = chain(
        task_extract.s(
            asset_id, entity_id, source_type
        ),
        task_chunk.s(),
        task_embed.s(),
    )
    workflow.apply_async()
    logger.info(
        "Dispatched ingestion chain for asset %s",
        asset_id,
    )
