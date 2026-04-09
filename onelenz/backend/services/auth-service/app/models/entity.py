from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Index, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class SubscriberEntity(Base):
    __tablename__ = "subscriber_entity"

    ent_entity_id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("uuid_generate_v4()")
    )
    ent_entity_name: Mapped[str] = mapped_column(String(200))
    ent_domain: Mapped[Optional[str]] = mapped_column(String(255))
    ent_is_active: Mapped[int] = mapped_column(SmallInteger, default=1)

    # Audit columns
    ent_created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ent_created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    ent_modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ent_modified_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        Index("idx_ent_domain", "ent_domain"),
        Index("idx_ent_is_active", "ent_is_active"),
    )
