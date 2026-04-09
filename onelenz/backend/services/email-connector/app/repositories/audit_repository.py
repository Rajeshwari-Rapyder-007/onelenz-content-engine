from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.base_repository import BaseRepository

from ..models.email_sync_audit import EmailSyncAudit


class AuditRepository(BaseRepository[EmailSyncAudit]):
    def __init__(self, session: AsyncSession):
        super().__init__(EmailSyncAudit, session)

    async def start_audit(
        self, entity_id: str, config_id: int, sync_type: str
    ) -> EmailSyncAudit:
        """Create an audit row at the start of a sync run."""
        audit = EmailSyncAudit(
            esa_entity_id=entity_id,
            esa_config_id=config_id,
            esa_sync_type=sync_type,
            esa_started_at=datetime.now(timezone.utc),
            esa_status="IN_PROGRESS",
        )
        self.session.add(audit)
        await self.session.flush()
        return audit

    async def complete_audit(
        self,
        audit_id: int,
        status: str,
        emails_fetched: int = 0,
        emails_new: int = 0,
        emails_changed: int = 0,
        pages_fetched: int = 0,
        error_detail: Optional[str] = None,
    ) -> None:
        """Update audit row on sync completion."""
        await self.update_by_id("esa_sync_id", audit_id, {
            "esa_ended_at": datetime.now(timezone.utc),
            "esa_status": status,
            "esa_emails_fetched": emails_fetched,
            "esa_emails_new": emails_new,
            "esa_emails_changed": emails_changed,
            "esa_pages_fetched": pages_fetched,
            "esa_error_detail": error_detail,
        })
