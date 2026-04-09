from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class IntegrationConfig(Base):
    __tablename__ = "integration_config"

    inc_config_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inc_entity_id: Mapped[str] = mapped_column(String(50))
    inc_user_id: Mapped[str] = mapped_column(String(50))
    inc_integration_type: Mapped[str] = mapped_column(String(20))
    inc_provider: Mapped[str] = mapped_column(String(20))
    inc_auth_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    inc_sync_frequency: Mapped[Optional[str]] = mapped_column(String(20))
    inc_last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    inc_is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    inc_config_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    # Audit columns
    inc_created_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    inc_created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    inc_modified_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    inc_modified_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        Index("idx_inc_entity_id", "inc_entity_id"),
        Index("idx_inc_user_id", "inc_user_id"),
        Index("idx_inc_type_provider", "inc_integration_type", "inc_provider"),
        Index("idx_inc_is_active", "inc_is_active"),
    )
