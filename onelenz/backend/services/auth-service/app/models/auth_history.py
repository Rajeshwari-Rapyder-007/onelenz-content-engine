from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class UserAuthenticationHistory(Base):
    __tablename__ = "user_authentication_history"

    uah_user_id: Mapped[UUID] = mapped_column(primary_key=True)
    uah_session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    uah_ip_address: Mapped[Optional[str]] = mapped_column(String(100))
    uah_invalid_login_attempt_count: Mapped[int] = mapped_column(
        SmallInteger, default=0
    )
    uah_login_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()"
    )
    uah_logout_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_uah_user_id", "uah_user_id"),
        Index("idx_uah_login_time", "uah_login_time"),
    )
