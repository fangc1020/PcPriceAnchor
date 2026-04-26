from abc import ABC, abstractmethod

from price_monitor.crawlers.schemas import RawProduct
from .schemas import CleanProduct


class BaseCleaner(ABC):
    category: str

    @abstractmethod
    def clean(self, raw: RawProduct) -> CleanProduct | None:
        """清洗单条原始数据。返回 None 表示数据质量不达标，应丢弃。"""

    @abstractmethod
    def validate(self, product: CleanProduct) -> bool:
        """业务规则二次校验。"""
