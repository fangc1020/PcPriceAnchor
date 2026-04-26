from sqlalchemy import (
    BigInteger, SmallInteger, Integer, String, Boolean, DateTime, Numeric, func,
    ForeignKey, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from .base import Base


class RamSpec(Base):
    __tablename__ = "ram_specs"

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    capacity_gb: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    kit_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    speed_mhz: Mapped[int] = mapped_column(Integer, nullable=False)
    cl_latency: Mapped[int | None] = mapped_column(SmallInteger)
    timing_string: Mapped[str | None] = mapped_column(String(30))
    die_type: Mapped[str | None] = mapped_column(String(20))
    memory_type: Mapped[str] = mapped_column(String(10), nullable=False)
    form_factor: Mapped[str] = mapped_column(String(10), nullable=False, default="DIMM")
    has_rgb: Mapped[bool] = mapped_column(Boolean, default=False)
    heatspreader: Mapped[bool] = mapped_column(Boolean, default=True)
    color: Mapped[str | None] = mapped_column(String(30))
    xmp_version: Mapped[str | None] = mapped_column(String(10))
    expo_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    parse_confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.0)

    product = relationship("Product", back_populates="ram_spec")

    __table_args__ = (
        Index("idx_ram_specs_type_speed", "memory_type", "speed_mhz"),
        Index("idx_ram_specs_capacity", "capacity_gb"),
    )

    @property
    def total_gb(self) -> int:
        return self.capacity_gb * self.kit_count
