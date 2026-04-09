from datetime import date, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_repository import BaseRepository
from shared.logging import get_logger

from ..models.asset import ContentAsset

logger = get_logger(__name__)


class AssetRepository(BaseRepository[ContentAsset]):
    def __init__(self, session: AsyncSession):
        super().__init__(ContentAsset, session)

    async def find_by_entity(
        self,
        entity_id: str,
        category_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ContentAsset], int]:
        """Paginated list with optional filters.

        Returns (items, total).
        """
        base = select(ContentAsset).where(
            ContentAsset.ca_entity_id == entity_id
        )
        count_base = select(func.count()).select_from(
            ContentAsset
        ).where(ContentAsset.ca_entity_id == entity_id)

        if category_id is not None:
            base = base.where(
                ContentAsset.ca_category_id == category_id
            )
            count_base = count_base.where(
                ContentAsset.ca_category_id == category_id
            )

        if status is not None:
            base = base.where(
                ContentAsset.ca_status == status
            )
            count_base = count_base.where(
                ContentAsset.ca_status == status
            )

        offset = (page - 1) * page_size
        items_stmt = (
            base
            .order_by(ContentAsset.created_on.desc())
            .offset(offset)
            .limit(page_size)
        )

        items_result = await self.session.execute(items_stmt)
        items = list(items_result.scalars().all())

        count_result = await self.session.execute(count_base)
        total = count_result.scalar() or 0

        return items, total

    async def count_today_by_entity(
        self, entity_id: str
    ) -> int:
        """Count assets created today for rate limiting."""
        today_start = datetime.combine(
            date.today(), datetime.min.time()
        ).replace(tzinfo=timezone.utc)

        stmt = (
            select(func.count())
            .select_from(ContentAsset)
            .where(
                ContentAsset.ca_entity_id == entity_id,
                ContentAsset.created_on >= today_start,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def update_status(
        self,
        asset_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Update asset status and optionally error message."""
        values: dict = {
            "ca_status": status,
            "modified_on": datetime.now(timezone.utc),
        }
        if error_message is not None:
            values["ca_error_message"] = error_message

        stmt = (
            update(ContentAsset)
            .where(ContentAsset.ca_asset_id == asset_id)
            .values(**values)
        )
        await self.session.execute(stmt)

    async def get_stats_by_entity(
        self, entity_id: str
    ) -> dict:
        """Aggregation query for stats endpoint.

        Returns: total_assets, total_chunks, total_storage_bytes,
                 by_category, by_status
        """
        # Total assets and storage
        totals_stmt = (
            select(
                func.count().label("total_assets"),
                func.coalesce(
                    func.sum(ContentAsset.ca_file_size_bytes), 0
                ).label("total_storage_bytes"),
            )
            .select_from(ContentAsset)
            .where(ContentAsset.ca_entity_id == entity_id)
        )
        totals_row = await self.session.execute(totals_stmt)
        totals = totals_row.one()

        # Total chunks
        chunks_stmt = (
            select(
                func.coalesce(
                    func.sum(ContentAsset.ca_chunk_count), 0
                ).label("total_chunks")
            )
            .select_from(ContentAsset)
            .where(ContentAsset.ca_entity_id == entity_id)
        )
        chunks_row = await self.session.execute(chunks_stmt)
        total_chunks = chunks_row.scalar() or 0

        # Group by category
        cat_stmt = (
            select(
                ContentAsset.ca_category_id,
                func.count().label("count"),
            )
            .where(ContentAsset.ca_entity_id == entity_id)
            .group_by(ContentAsset.ca_category_id)
        )
        cat_result = await self.session.execute(cat_stmt)
        by_category = {
            row.ca_category_id or "UNCATEGORIZED": row.count
            for row in cat_result
        }

        # Group by status
        status_stmt = (
            select(
                ContentAsset.ca_status,
                func.count().label("count"),
            )
            .where(ContentAsset.ca_entity_id == entity_id)
            .group_by(ContentAsset.ca_status)
        )
        status_result = await self.session.execute(status_stmt)
        by_status = {
            row.ca_status: row.count for row in status_result
        }

        return {
            "total_assets": totals.total_assets,
            "total_chunks": total_chunks,
            "total_storage_bytes": totals.total_storage_bytes,
            "by_category": by_category,
            "by_status": by_status,
        }
