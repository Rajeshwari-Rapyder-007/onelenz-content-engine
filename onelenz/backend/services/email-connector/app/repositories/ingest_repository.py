from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_repository import BaseRepository
from shared.logging import get_logger

from ..models.raw_ingest_log import RawIngestLog

logger = get_logger(__name__)


class IngestRepository(BaseRepository[RawIngestLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(RawIngestLog, session)

    async def exists_by_ref(self, entity_id: str, source_ref_id: str) -> bool:
        """Check if an email already exists (dedup)."""
        stmt = select(RawIngestLog.ril_id).where(
            RawIngestLog.ril_entity_id == entity_id,
            RawIngestLog.ril_source_ref_id == source_ref_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def exists_by_refs_batch(
        self, entity_id: str, source_ref_ids: list[str],
    ) -> set[str]:
        """Batch dedup: return the subset of source_ref_ids that already exist."""
        if not source_ref_ids:
            return set()
        stmt = select(RawIngestLog.ril_source_ref_id).where(
            RawIngestLog.ril_entity_id == entity_id,
            RawIngestLog.ril_source_ref_id.in_(source_ref_ids),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def insert_email(
        self,
        entity_id: str,
        config_id: int,
        source_ref_id: str,
        conversation_id: Optional[str],
        raw_payload: dict[str, Any],
    ) -> RawIngestLog:
        """Insert a new email into raw_ingest_log."""
        now = datetime.now(timezone.utc)
        row = RawIngestLog(
            ril_entity_id=entity_id,
            ril_source_tag="EMAIL",
            ril_integration_cfg_id=config_id,
            ril_source_ref_id=source_ref_id,
            ril_conversation_id=conversation_id,
            ril_raw_payload=raw_payload,
            ril_ingest_status="QUEUED",
            ril_queued_at=now,
            ril_created_on=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def upsert_email(
        self,
        entity_id: str,
        source_ref_id: str,
        raw_payload: dict[str, Any],
    ) -> None:
        """Update an existing email record (changed email)."""
        stmt = (
            update(RawIngestLog)
            .where(
                RawIngestLog.ril_entity_id == entity_id,
                RawIngestLog.ril_source_ref_id == source_ref_id,
            )
            .values(
                ril_raw_payload=raw_payload,
                ril_ingest_status="UPDATED",
                ril_modified_on=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)

    async def batch_insert(
        self, rows: list[RawIngestLog]
    ) -> int:
        """Insert a batch of emails. Returns count inserted."""
        for row in rows:
            self.session.add(row)
        await self.session.flush()
        return len(rows)
