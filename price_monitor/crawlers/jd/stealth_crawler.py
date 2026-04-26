"""京东 Stealth 爬虫 — playwright-stealth + 手动登录 + 搜索结果提取。

核心思路：用 stealth 浏览器让用户手动登录一次，之后利用登录态
在搜索结果页上直接提取渲染好的价格 HTML（不调用 p.3.cn 或 api.m.jd.com）。
"""

import asyncio
import json
import logging
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from playwright_stealth import Stealth

from price_monitor.crawlers.base import BaseCrawler
from price_monitor.crawlers.jd.search import CRAWLER_VERSION
from price_monitor.crawlers.schemas import RawProduct

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

COOKIE_FILE = Path(__file__).resolve().parent.parent.parent.parent / ".jd_cookies.json"
SEARCH_URL = "https://search.jd.com/Search"


class JdStealthCrawler(BaseCrawler):
    """需要手动登录一次的京东爬虫。登录态保存到 .jd_cookies.json 复用。"""

    platform_code = "jd"

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless

    # ------------------------------------------------------------------
    # 登录管理
    # ------------------------------------------------------------------
    async def _load_cookies(self, context: BrowserContext) -> bool:
        """从文件加载 cookie 到 context。返回是否成功。"""
        if not COOKIE_FILE.exists():
            return False
        try:
            cookies = json.loads(COOKIE_FILE.read_text())
            if cookies:
                await context.add_cookies(cookies)
                logger.info("Loaded %d cookies from %s", len(cookies), COOKIE_FILE)
                return True
        except Exception as e:
            logger.warning("Failed to load cookies: %s", e)
        return False

    async def _save_cookies(self, context: BrowserContext) -> None:
        """保存 context 的 cookie 到文件。"""
        cookies = await context.cookies()
        COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
        logger.info("Saved %d cookies to %s", len(cookies), COOKIE_FILE)

    async def _ensure_logged_in(self, page: Page) -> bool:
        """确保京东已登录。先尝试 cookie 恢复，不行就等用户手动登录。"""
        # 先试 cookie
        await page.goto("https://www.jd.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        if "passport.jd.com" not in page.url:
            logger.info("Already logged in (via saved cookies)")
            return True

        # 需要手动登录
        logger.info("=" * 60)
        logger.info("需要登录京东 — 请在浏览器窗口中扫码/账号登录")
        logger.info("=" * 60)
        try:
            await page.wait_for_url(lambda u: "passport.jd.com" not in u, timeout=180000)
            await asyncio.sleep(3)
            logger.info("登录成功!")
            return True
        except Exception:
            logger.error("登录超时")
            return False

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    async def search(
        self,
        keyword: str,
        category: str,
        max_pages: int = 5,
    ) -> AsyncIterator[RawProduct]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self._headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
            )
            # Stealth 注入
            await Stealth().apply_stealth_async(context)

            page = await context.new_page()

            try:
                if not await self._ensure_logged_in(page):
                    return

                # 保存 cookie 供下次使用
                await self._save_cookies(context)

                for pg in range(1, max_pages + 1):
                    products = await self._fetch_search_page(page, keyword, pg)
                    if not products:
                        break

                    for p in products:
                        yield RawProduct(
                            platform_code=self.platform_code,
                            platform_sku_id=p["sku_id"],
                            title=p["title"],
                            price_fen=p.get("price_fen", 0),
                            original_fen=p.get("original_fen"),
                            coupon_fen=0,
                            in_stock=True,
                            detail_url=p.get("detail_url"),
                            raw_payload=p,
                            crawled_at=datetime.now(timezone.utc),
                            crawler_version=CRAWLER_VERSION,
                        )

                    if pg < max_pages:
                        await asyncio.sleep(random.uniform(2.0, 4.0))

            finally:
                await browser.close()

    async def _fetch_search_page(
        self, page: Page, keyword: str, page_num: int
    ) -> list[dict]:
        """加载搜索结果页，从 DOM 提取商品和价格。"""
        if page_num == 1:
            # 通过首页搜索框搜索
            if "jd.com" not in page.url:
                await page.goto("https://www.jd.com/", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

            # 用搜索框
            search_input = page.locator("#key")
            if await search_input.is_visible():
                await search_input.click()
                await asyncio.sleep(0.3)
                await search_input.fill(keyword)
                await asyncio.sleep(random.uniform(0.8, 1.5))
                await search_input.press("Enter")
                logger.info("Searched via homepage: %s", keyword)
            else:
                search_url = f"{SEARCH_URL}?keyword={keyword}&enc=utf-8&page=1"
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        else:
            jd_page = page_num * 2 - 1
            url = f"{SEARCH_URL}?keyword={keyword}&enc=utf-8&page={jd_page}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 等待搜索结果
        await asyncio.sleep(random.uniform(3.0, 5.0))
        await self._scroll_page(page)

        current = page.url
        if "passport.jd.com" in current:
            logger.warning("Login page detected during search (page %d)", page_num)
            return []

        # 从 DOM 提取
        return await self._extract_products(page)

    async def _extract_products(self, page: Page) -> list[dict]:
        """从搜索结果 DOM 提取商品信息，包括页面上渲染的价格。"""
        return await page.evaluate("""() => {
            const items = document.querySelectorAll('.gl-item[data-sku]');
            return Array.from(items).map(el => {
                const sku = el.getAttribute('data-sku') || '';

                // 标题
                let title = '';
                const titleEl = el.querySelector('.p-name em, .p-name a em, .p-name-type-2 a, [class*=title] em');
                if (titleEl) title = titleEl.textContent.trim();

                // 链接
                let detailUrl = '';
                const link = el.querySelector('a[href*="item.jd.com"]');
                if (link) {
                    const h = link.getAttribute('href');
                    detailUrl = h.startsWith('//') ? 'https:' + h : h;
                }

                // 价格 — 从页面上已渲染的 HTML 提取
                let priceText = '';
                const priceEl = el.querySelector('.p-price i, .p-price strong, .p-price span, [class*=price] i');
                if (priceEl) priceText = priceEl.textContent.trim();

                // 解析价格数字
                let priceFen = 0;
                if (priceText) {
                    const num = priceText.replace(/[^\\d.]/g, '');
                    if (num) priceFen = Math.round(parseFloat(num) * 100);
                }

                // original price
                let originalFen = null;
                const origEl = el.querySelector('.p-price .J_originPrice, .p-price del');
                if (origEl) {
                    const origNum = origEl.textContent.trim().replace(/[^\\d.]/g, '');
                    if (origNum) originalFen = Math.round(parseFloat(origNum) * 100);
                }

                return {
                    sku_id: sku,
                    title: title,
                    detail_url: detailUrl,
                    price_text: priceText,
                    price_fen: priceFen,
                    original_fen: originalFen,
                };
            }).filter(p => p.sku_id && p.title.length > 0);
        }""")

    async def _scroll_page(self, page: Page) -> None:
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.6)

    # ------------------------------------------------------------------
    # 单品详情 / 价格更新
    # ------------------------------------------------------------------
    async def fetch_detail(self, platform_sku_id: str) -> RawProduct | None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
            )
            await Stealth().apply_stealth_async(context)
            await self._load_cookies(context)
            page = await context.new_page()

            try:
                url = f"https://item.jd.com/{platform_sku_id}.html"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                title = await page.title()
                # 从详情页提取价格
                price_info = await page.evaluate("""() => {
                    const priceEl = document.querySelector('.p-price span, #jd-price .price, .summary-price .price, .spec-price');
                    let priceFen = 0;
                    if (priceEl) {
                        const num = priceEl.textContent.trim().replace(/[^\\d.]/g, '');
                        if (num) priceFen = Math.round(parseFloat(num) * 100);
                    }
                    return { price_fen: priceFen };
                }""")
                return RawProduct(
                    platform_code=self.platform_code,
                    platform_sku_id=platform_sku_id,
                    title=title.strip(),
                    price_fen=price_info.get("price_fen", 0),
                    coupon_fen=0,
                    detail_url=url,
                    raw_payload={"html_title": title},
                    crawled_at=datetime.now(timezone.utc),
                    crawler_version=CRAWLER_VERSION,
                )
            except Exception as e:
                logger.warning("Detail fetch failed: %s", e)
                return None
            finally:
                await browser.close()

    async def fetch_price(self, platform_sku_id: str) -> dict | None:
        """轻量价格查询。"""
        detail = await self.fetch_detail(platform_sku_id)
        if detail:
            return {
                "price_fen": detail.price_fen,
                "original_fen": detail.original_fen,
                "crawler_version": CRAWLER_VERSION,
            }
        return None
