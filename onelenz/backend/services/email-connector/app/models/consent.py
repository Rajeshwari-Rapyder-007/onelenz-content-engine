from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class ConsentManagement(Base):
    __tablename__ = "consent_management"

    cm_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cm_entity_id: Mapped[str] = mapped_column(String(50))
    cm_user_id: Mapped[str] = mapped_column(String(50))
    cm_consent_type: Mapped[str] = mapped_column(String(20))
    cm_domain_scope: Mapped[Optional[str]] = mapped_column(String(100))
    cm_is_granted: Mapped[bool] = mapped_column(Boolean, default=True)
    cm_granted_by: Mapped[Optional[str]] = mapped_column(String(50))
    cm_granted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cm_revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cm_created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    __table_args__ = (
        Index("idx_cm_entity_type", "cm_entity_id", "cm_consent_type"),
        Index("idx_cm_is_granted", "cm_is_granted"),
    )
