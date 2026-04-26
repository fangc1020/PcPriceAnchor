from sqlalchemy import (
    BigInteger, Integer, Boolean, String, DateTime, func, ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from .base import Base


class PriceTick(Base):
    __tablename__ = "price_ticks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), primary_key=True
    )
    price_fen: Mapped[int] = mapped_column(Integer, nullable=False)
    original_fen: Mapped[int | None] = mapped_column(Integer)
    coupon_fen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    promotion_tag: Mapped[str | None] = mapped_column(String(100))
    crawler_version: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_hash: Mapped[str | None] = mapped_column(String(64))

    product = relationship("Product", back_populates="price_ticks")

    @property
    def final_fen(self) -> int:
        return self.price_fen - self.coupon_fen
