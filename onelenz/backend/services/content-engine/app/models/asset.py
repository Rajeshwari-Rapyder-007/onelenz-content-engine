from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class ContentAsset(Base):
    __tablename__ = "content_asset"

    ca_asset_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    ca_entity_id: Mapped[UUID] = mapped_column(nullable=False)
    ca_category_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    ca_source_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    ca_file_name: Mapped[str] = mapped_column(
        String(500), nullable=False
    )
    ca_file_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    ca_file_size_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    ca_page_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    ca_s3_key: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )
    ca_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )
    ca_error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    ca_chunk_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    ca_credits_consumed: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    # Audit columns
    created_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    modified_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    modified_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        Index("idx_ca_entity_id", "ca_entity_id"),
        Index("idx_ca_status", "ca_status"),
        Index(
            "idx_ca_entity_category",
            "ca_entity_id",
            "ca_category_id",
        ),
    )
