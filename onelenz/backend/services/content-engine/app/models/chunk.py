from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from shared.db.base_model import Base


class ContentChunk(Base):
    __tablename__ = "content_chunk"

    ck_chunk_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    ck_asset_id: Mapped[UUID] = mapped_column(nullable=False)
    ck_entity_id: Mapped[UUID] = mapped_column(nullable=False)
    ck_category_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    ck_chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    ck_content_text: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    ck_section_heading: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    ck_source_page: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    ck_source_url: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True
    )
    ck_token_count: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    ck_data_origin: Mapped[str] = mapped_column(
        String(30), nullable=False, default="SUBSCRIBER_UPLOADED"
    )
    ck_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ck_embedding: Mapped[Optional[Any]] = mapped_column(
        Vector(1024), nullable=True
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
        Index("idx_ck_asset_id", "ck_asset_id"),
        Index("idx_ck_entity_id", "ck_entity_id"),
        Index(
            "idx_ck_embedding",
            "ck_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"ck_embedding": "vector_cosine_ops"},
        ),
    )
