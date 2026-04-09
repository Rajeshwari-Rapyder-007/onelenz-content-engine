from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Index, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class UserMaster(Base):
    __tablename__ = "user_master"

    usm_user_id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("uuid_generate_v4()")
    )
    usm_user_display_name: Mapped[Optional[str]] = mapped_column(String(200))
    usm_user_first_name: Mapped[Optional[str]] = mapped_column(String(100))
    usm_user_last_name: Mapped[Optional[str]] = mapped_column(String(100))
    usm_entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    usm_user_email_id: Mapped[Optional[str]] = mapped_column(String(255))
    usm_user_mobile_no: Mapped[Optional[str]] = mapped_column(String(30))
    usm_title_tag: Mapped[Optional[str]] = mapped_column(String(100))
    usm_department_tag: Mapped[Optional[str]] = mapped_column(String(100))
    usm_user_status: Mapped[int] = mapped_column(SmallInteger, default=1)
    usm_failed_login_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    usm_locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Audit columns
    usm_created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    usm_created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    usm_modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    usm_modified_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        Index("idx_usm_entity_id", "usm_entity_id"),
        Index("idx_usm_email", "usm_user_email_id"),
        Index("idx_usm_status", "usm_user_status"),
    )
