from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class UserRoleMapping(Base):
    __tablename__ = "user_role_mapping"

    urm_mapping_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    urm_mapped_user_id: Mapped[UUID] = mapped_column()
    urm_role_id: Mapped[str] = mapped_column(String(100))
    urm_record_status: Mapped[int] = mapped_column(SmallInteger, default=1)

    # Audit columns
    urm_created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    urm_created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    urm_modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    urm_modified_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        Index("idx_urm_user_id", "urm_mapped_user_id", "urm_record_status"),
    )
