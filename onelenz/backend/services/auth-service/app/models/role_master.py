from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class RoleMaster(Base):
    __tablename__ = "role_master"

    rom_role_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    rom_role_name: Mapped[str] = mapped_column(String(200))
    rom_role_description: Mapped[Optional[str]] = mapped_column(Text)
    rom_is_active: Mapped[int] = mapped_column(SmallInteger, default=1)

    # Audit columns
    rom_created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rom_created_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    rom_modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rom_modified_on: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
