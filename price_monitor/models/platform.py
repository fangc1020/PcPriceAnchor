from sqlalchemy import SmallInteger, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from .base import Base


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
