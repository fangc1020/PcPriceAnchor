from pydantic import BaseModel, Field, field_validator


class RamSpec(BaseModel):
    capacity_gb: int
    kit_count: int = 1
    speed_mhz: int
    cl_latency: int | None = None
    timing_string: str | None = None
    die_type: str | None = None
    memory_type: str  # 'DDR4' | 'DDR5'
    form_factor: str = "DIMM"
    has_rgb: bool = False
    xmp_version: str | None = None
    expo_supported: bool = False
    parse_confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("speed_mhz")
    @classmethod
    def speed_in_range(cls, v: int) -> int:
        if v == 0:
            return v  # unknown speed, allowed with low confidence
        if not (800 <= v <= 12800):
            raise ValueError(f"speed_mhz {v} 超出合理范围")
        return v

    @property
    def total_gb(self) -> int:
        return self.capacity_gb * self.kit_count


class CleanProduct(BaseModel):
    platform_code: str
    platform_sku_id: str
    category: str
    brand: str
    model: str
    title: str
    canonical_url: str | None = None
    price_fen: int
    original_fen: int | None = None
    coupon_fen: int = 0
    in_stock: bool = True
    promotion_tag: str | None = None
    spec: RamSpec | None = None
    raw_hash: str
    crawled_at: str
    crawler_version: str
