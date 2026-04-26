from sqlalchemy import (
    BigInteger, SmallInteger, String, Boolean, DateTime, UniqueConstraint, Index, func,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from .base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("platforms.id"), nullable=False
    )
    platform_sku_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    brand: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ram_spec = relationship("RamSpec", back_populates="product", uselist=False, cascade="all, delete-orphan")
    price_ticks = relationship("PriceTick", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("platform_id", "platform_sku_id", name="uq_platform_sku"),
        Index("idx_products_category_brand", "category", "brand"),
    )
