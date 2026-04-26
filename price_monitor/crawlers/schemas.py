from pydantic import BaseModel, HttpUrl
from datetime import datetime


class RawProduct(BaseModel):
    platform_code: str
    platform_sku_id: str
    title: str
    price_fen: int
    original_fen: int | None = None
    coupon_fen: int = 0
    in_stock: bool = True
    promotion_tag: str | None = None
    detail_url: str | None = None
    raw_payload: dict = {}
    crawled_at: datetime
    crawler_version: str
