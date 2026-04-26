"""京东商品详情页采集器 — 使用 httpx 为主，Playwright 为降级方案。"""

import logging
from datetime import datetime, timezone

import httpx

from price_monitor.crawlers.base import BaseCrawler
from price_monitor.crawlers.schemas import RawProduct

logger = logging.getLogger(__name__)

CRAWLER_VERSION = "jd-detail-v1"


class JdDetailCrawler(BaseCrawler):
    platform_code = "jd"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def search(self, keyword: str, category: str, max_pages: int = 5):
        """详情爬虫不支持搜索，由 JdSearchCrawler 负责。"""
        return
        yield  # make it an async generator

    async def fetch_detail(self, platform_sku_id: str) -> RawProduct | None:
        """获取商品详情页信息，补全搜索采集不到的字段。"""
        # Delegate to the search crawler's detail method
        from price_monitor.crawlers.jd.search import JdSearchCrawler

        search_crawler = JdSearchCrawler(client=self._client)
        return await search_crawler.fetch_detail(platform_sku_id)

    async def fetch_price(self, platform_sku_id: str) -> dict | None:
        from price_monitor.crawlers.jd.search import JdSearchCrawler

        search_crawler = JdSearchCrawler(client=self._client)
        return await search_crawler.fetch_price(platform_sku_id)
