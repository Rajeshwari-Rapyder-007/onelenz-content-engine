from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class UserSecurityDetails(Base):
    __tablename__ = "user_security_details"

    usd_user_id: Mapped[UUID] = mapped_column(primary_key=True)
    usd_hashed_pwd: Mapped[Optional[str]] = mapped_column(String(255))
    usd_hashed_pin: Mapped[Optional[str]] = mapped_column(String(255))
    usd_2fa_option: Mapped[Optional[int]] = mapped_column(SmallInteger)
    usd_mobile_app_access: Mapped[int] = mapped_column(SmallInteger, default=0)
    usd_api_access: Mapped[int] = mapped_column(SmallInteger, default=0)

    # Audit columns
    usd_created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    usd_created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    usd_modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    usd_modified_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
