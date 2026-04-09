from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class RawIngestLog(Base):
    __tablename__ = "raw_ingest_log"

    ril_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ril_entity_id: Mapped[str] = mapped_column(String(50))
    ril_source_tag: Mapped[str] = mapped_column(String(20))
    ril_integration_cfg_id: Mapped[Optional[int]] = mapped_column()
    ril_source_ref_id: Mapped[Optional[str]] = mapped_column(String(500))
    ril_conversation_id: Mapped[Optional[str]] = mapped_column(String(255))
    ril_raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    ril_meeting_ref_id: Mapped[Optional[int]] = mapped_column()
    ril_source_id: Mapped[Optional[str]] = mapped_column(String(500))
    ril_dedup_hash: Mapped[Optional[str]] = mapped_column(String(64))
    ril_signals_generated: Mapped[Optional[int]] = mapped_column()
    ril_ingest_status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    ril_queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    ril_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ril_error_msg: Mapped[Optional[str]] = mapped_column(Text)
    ril_created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    ril_modified_on: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_ril_entity_id", "ril_entity_id"),
        Index("idx_ril_source_tag", "ril_source_tag"),
        Index("idx_ril_ingest_status", "ril_ingest_status"),
        Index("idx_ril_source_ref_id", "ril_source_ref_id"),
        Index("idx_ril_conversation_id", "ril_conversation_id"),
    )
