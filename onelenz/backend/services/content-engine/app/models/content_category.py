from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base_model import Base


class ContentCategory(Base):
    __tablename__ = "content_category"

    cc_category_id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )
    cc_category_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    cc_description: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
