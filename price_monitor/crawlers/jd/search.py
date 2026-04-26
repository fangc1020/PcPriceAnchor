"""京东搜索列表页采集器。

使用 httpx 请求 search.jd.com，服务端渲染页面，
解析商品列表获取 SKU ID、标题、价格等基本信息。
价格通过独立 API p.3.cn/prices/mgets 批量获取。
"""

import asyncio
import logging
import re
import random
from datetime import datetime, timezone
from typing import AsyncIterator
from urllib.parse import urlencode

import httpx

from price_monitor.crawlers.base import BaseCrawler
from price_monitor.crawlers.schemas import RawProduct
from price_monitor.config.settings import settings

logger = logging.getLogger(__name__)

CRAWLER_VERSION = "jd-v1"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

SEARCH_URL = "https://search.jd.com/Search"
PRICE_API_URL = "https://p.3.cn/prices/mgets"
SKU_PATTERN = re.compile(r"data-sku=['\"](\d+)['\"]")
TITLE_PATTERN = re.compile(r'<a[^>]*title="([^"]*)"[^>]*>')



class JdSearchCrawler(BaseCrawler):
    platform_code = "jd"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        cookies = {}
        if settings.jd_pt_key and settings.jd_pt_pin:
            cookies["pt_key"] = settings.jd_pt_key
            cookies["pt_pin"] = settings.jd_pt_pin
        return httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            follow_redirects=True,
            cookies=cookies,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Referer": "https://www.jd.com/",
            },
        )

    async def search(
        self,
        keyword: str,
        category: str,
        max_pages: int = 5,
    ) -> AsyncIterator[RawProduct]:
        client = await self._get_client()
        for page in range(1, max_pages + 1):
            products = await self._fetch_search_page(client, keyword, page)
            if not products:
                break
            for p in products:
                p["category"] = category
                p["keyword"] = keyword
            sku_ids = [p["sku_id"] for p in products]
            prices = await self._fetch_prices_batch(client, sku_ids)
            for p in products:
                price_info = prices.get(p["sku_id"], {})
                yield RawProduct(
                    platform_code=self.platform_code,
                    platform_sku_id=p["sku_id"],
                    title=p["title"],
                    price_fen=price_info.get("price_fen") or self._extract_price_fen(p.get("price_text", "")),
                    original_fen=price_info.get("original_fen"),
                    coupon_fen=0,
                    in_stock=True,
                    promotion_tag=p.get("promotion_tag"),
                    detail_url=p.get("detail_url"),
                    raw_payload=p,
                    crawled_at=datetime.now(timezone.utc),
                    crawler_version=CRAWLER_VERSION,
                )
            if page < max_pages:
                await asyncio.sleep(random.uniform(1.0, 3.0))

    async def _fetch_search_page(
        self, client: httpx.AsyncClient, keyword: str, page: int
    ) -> list[dict]:
        params = {
            "keyword": keyword,
            "enc": "utf-8",
            "page": str(page * 2 - 1),  # JD 使用奇数页码
        }
        url = f"{SEARCH_URL}?{urlencode(params)}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return self._parse_search_html(resp.text)
        except httpx.HTTPError as e:
            logger.warning("JD search page %d fetch failed: %s", page, e)
            return []

    def _parse_search_html(self, html: str) -> list[dict]:
        """从搜索页 HTML 提取商品信息，使用正则匹配关键字段。"""
        if not SKU_PATTERN.findall(html):
            return []
        return self._extract_products_simple(html)

    def _extract_products_simple(self, html: str) -> list[dict]:
        """简化提取：用正则匹配商品卡片的关键字段。"""
        products = []
        # Find all SKU IDs
        for match in SKU_PATTERN.finditer(html):
            sku_id = match.group(1)
            products.append({"sku_id": sku_id})

        # Find titles near each SKU
        title_pattern = re.compile(r'data-sku="(\d+)".*?<a[^>]*title="([^"]*)"', re.DOTALL)
        title_map = {m.group(1): m.group(2).strip() for m in title_pattern.finditer(html)}

        # Find detail URLs
        url_pattern = re.compile(r'data-sku="(\d+)".*?href="(//item\.jd\.com/\d+\.html)"', re.DOTALL)
        url_map = {m.group(1): f"https:{m.group(2)}" for m in url_pattern.finditer(html)}

        # Merge
        result = []
        for p in products:
            sid = p["sku_id"]
            title = title_map.get(sid, "")
            if not title:
                continue  # skip items without parsable title
            result.append({
                "sku_id": sid,
                "title": title,
                "detail_url": url_map.get(sid),
            })
        return result

    async def _fetch_prices_batch(
        self, client: httpx.AsyncClient, sku_ids: list[str]
    ) -> dict[str, dict]:
        """批量获取价格，调用京东价格 API。"""
        if not sku_ids:
            return {}
        ids_param = ",".join(f"J_{sid}" for sid in sku_ids)
        url = f"{PRICE_API_URL}?skuIds={ids_param}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_price_response(data)
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("JD price API failed: %s", e)
            return {}

    def _parse_price_response(self, data: list[dict]) -> dict[str, dict]:
        """解析价格 API 响应。响应格式: [{'id': 'J_123456', 'p': '599.00', 'op': '699.00'}]"""
        result = {}
        for item in data:
            raw_id = item.get("id", "")
            sku_id = raw_id.replace("J_", "")
            price_fen = self._yuan_to_fen(item.get("p"))
            original_fen = self._yuan_to_fen(item.get("op")) if item.get("op") else None
            result[sku_id] = {
                "price_fen": price_fen,
                "original_fen": original_fen,
            }
        return result

    @staticmethod
    def _yuan_to_fen(price_str: str | None) -> int:
        """将元字符串转为分（整数）。"""
        if not price_str:
            return 0
        try:
            return round(float(price_str) * 100)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _extract_price_fen(text: str) -> int:
        """从 HTML 文本中提取价格并转为分。"""
        match = re.search(r"([\d,.]+)", text)
        if match:
            num_str = match.group(1).replace(",", "")
            try:
                return round(float(num_str) * 100)
            except ValueError:
                pass
        return 0

    async def fetch_detail(self, platform_sku_id: str) -> RawProduct | None:
        """抓取单品详情页，补全标题等信息。"""
        client = await self._get_client()
        url = f"https://item.jd.com/{platform_sku_id}.html"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
            title_match = re.search(r"<title>([^<]*)</title>", html)
            title = title_match.group(1).strip() if title_match else ""
            prices = await self._fetch_prices_batch(client, [platform_sku_id])
            price_info = prices.get(platform_sku_id, {})
            return RawProduct(
                platform_code=self.platform_code,
                platform_sku_id=platform_sku_id,
                title=title,
                price_fen=price_info.get("price_fen", 0),
                original_fen=price_info.get("original_fen"),
                coupon_fen=0,
                detail_url=url,
                raw_payload={"html_title": title},
                crawled_at=datetime.now(timezone.utc),
                crawler_version=CRAWLER_VERSION,
            )
        except httpx.HTTPError as e:
            logger.warning("JD detail fetch failed for %s: %s", platform_sku_id, e)
            return None

    async def fetch_price(self, platform_sku_id: str) -> dict | None:
        """仅抓取价格（轻量调用）。"""
        client = await self._get_client()
        prices = await self._fetch_prices_batch(client, [platform_sku_id])
        price_info = prices.get(platform_sku_id)
        if price_info:
            return {
                "price_fen": price_info["price_fen"],
                "original_fen": price_info.get("original_fen"),
                "crawler_version": CRAWLER_VERSION,
            }
        return None
