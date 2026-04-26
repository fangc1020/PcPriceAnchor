from abc import ABC, abstractmethod


class AbstractProductRepository(ABC):

    @abstractmethod
    async def upsert_product(self, product) -> int:
        """插入或更新商品主表 + 规格表，返回 product.id。"""

    @abstractmethod
    async def get_by_platform_sku(
        self, platform_code: str, platform_sku_id: str
    ) -> dict | None:
        """按平台 SKU 查询商品，返回 None 表示不存在。"""


class AbstractPriceRepository(ABC):

    @abstractmethod
    async def record_price(self, product_id: int, product) -> bool:
        """写入价格 tick。若 raw_hash 已存在则跳过，返回 False；写入成功返回 True。"""

    @abstractmethod
    async def get_price_history(self, product_id: int, days: int = 30) -> list[dict]:
        """返回近 N 天每小时最低价列表（查 price_hourly 连续聚合）。"""

    @abstractmethod
    async def get_current_lowest(
        self, category: str, filters: dict
    ) -> list[dict]:
        """按过滤条件查当前最低价商品列表（用于性价比排名）。"""
