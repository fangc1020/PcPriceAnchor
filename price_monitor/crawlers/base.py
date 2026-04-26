from abc import ABC, abstractmethod
from typing import AsyncIterator
from .schemas import RawProduct


class BaseCrawler(ABC):
    platform_code: str

    @abstractmethod
    async def search(
        self,
        keyword: str,
        category: str,
        max_pages: int = 5,
    ) -> AsyncIterator[RawProduct]:
        """搜索关键词，流式返回原始商品数据。"""

    @abstractmethod
    async def fetch_detail(self, platform_sku_id: str) -> RawProduct | None:
        """根据 SKU ID 抓取单品详情，失败返回 None。"""

    @abstractmethod
    async def fetch_price(self, platform_sku_id: str) -> dict | None:
        """仅抓取价格字段（轻量调用，用于定时价格更新）。"""
