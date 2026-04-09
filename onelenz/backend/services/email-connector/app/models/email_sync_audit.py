from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class EmailSyncAudit(Base):
    __tablename__ = "email_sync_audit"

    esa_sync_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    esa_entity_id: Mapped[str] = mapped_column(String(50))
    esa_config_id: Mapped[int] = mapped_column()
    esa_sync_type: Mapped[str] = mapped_column(String(20))
    esa_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    esa_ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    esa_emails_fetched: Mapped[int] = mapped_column(default=0)
    esa_emails_new: Mapped[int] = mapped_column(default=0)
    esa_emails_changed: Mapped[int] = mapped_column(default=0)
    esa_pages_fetched: Mapped[int] = mapped_column(default=0)
    esa_status: Mapped[str] = mapped_column(String(20), default="SUCCESS")
    esa_error_detail: Mapped[Optional[str]] = mapped_column(Text)
    esa_created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    __table_args__ = (
        Index("idx_esa_entity_id", "esa_entity_id"),
        Index("idx_esa_config_id", "esa_config_id"),
        Index("idx_esa_created_on", "esa_created_on"),
    )
