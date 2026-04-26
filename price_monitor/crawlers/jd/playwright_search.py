"""京东搜索 Playwright 爬虫 — 用真实浏览器绕过反爬风控。"""

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import AsyncIterator

from playwright.async_api import async_playwright, Page, Browser

from price_monitor.crawlers.base import BaseCrawler
from price_monitor.crawlers.jd.search import CRAWLER_VERSION, PRICE_API_URL
from price_monitor.crawlers.schemas import RawProduct

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

SEARCH_URL = "https://search.jd.com/Search"
MOBILE_SEARCH_URL = "https://so.m.jd.com/ware/search.action"


class JdSearchPlaywrightCrawler(BaseCrawler):
    platform_code = "jd"

    def __init__(self, headless: bool = False, slow_mo: int = 300) -> None:
        self._headless = headless
        self._slow_mo = slow_mo

    async def search(
        self,
        keyword: str,
        category: str,
        max_pages: int = 5,
    ) -> AsyncIterator[RawProduct]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self._headless,
                slow_mo=self._slow_mo,
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
            # 隐藏 Playwright 自动化特征
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                window.chrome = { runtime: {} };
            """)
            page = await context.new_page()

            try:
                for pg in range(1, max_pages + 1):
                    products = await self._fetch_search_page(page, keyword, pg)
                    if not products:
                        break

                    # 批量获取价格
                    sku_ids = [p["sku_id"] for p in products]
                    prices = await self._fetch_prices_via_api(page, sku_ids)

                    for p in products:
                        price_info = prices.get(p["sku_id"], {})
                        yield RawProduct(
                            platform_code=self.platform_code,
                            platform_sku_id=p["sku_id"],
                            title=p["title"],
                            price_fen=price_info.get("price_fen", 0),
                            original_fen=price_info.get("original_fen"),
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

    async def _require_login(self, page: Page) -> bool:
        """处理登录拦截：等待用户在浏览器中手动登录，返回是否成功。"""
        logger.info("=" * 60)
        logger.info("京东要求登录 — 请在浏览器窗口中扫码/输入账号登录")
        logger.info("登录后程序会自动继续...")
        logger.info("=" * 60)
        try:
            await page.wait_for_url(
                lambda u: "passport.jd.com" not in u,
                timeout=180000,
            )
            logger.info("登录成功，继续采集...")
            await asyncio.sleep(3.0)
            return True
        except Exception:
            logger.error("登录超时（3 分钟），放弃本次采集")
            return False

    async def _safe_goto(self, page: Page, url: str) -> bool:
        """安全导航：如果跳转到登录页则等待用户手动登录。返回 True 表示成功到达目标。"""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning("Navigation failed: %s", e)
            return False
        await asyncio.sleep(3.0)

        if "passport.jd.com" in page.url:
            if not await self._require_login(page):
                return False
            # 登录成功后页面会跳转到 jd.com，此时不要立刻跳转
            # 等一下，让 Cookie 充分写入
            await asyncio.sleep(5.0)
            logger.info("Login complete, current URL: %s", page.url[:120])
        return True

    async def _fetch_search_page(
        self, page: Page, keyword: str, page_num: int
    ) -> list[dict]:
        """模拟真实用户在 JD 搜索，返回商品列表。"""
        if page_num == 1:
            # 从 JD 首页通过搜索框搜索（最拟人，cookie 完整）
            if not await self._safe_goto(page, "https://www.jd.com/"):
                return []

            # 登录成功后用搜索框，不直接跳转搜索 URL
            await asyncio.sleep(2.0)
            search_input = page.locator("#key")
            try:
                await search_input.wait_for(state="visible", timeout=15000)
            except Exception:
                pass

            if await search_input.is_visible():
                await search_input.click()
                await asyncio.sleep(0.5)
                await search_input.fill(keyword)
                await asyncio.sleep(random.uniform(0.8, 1.5))
                await search_input.press("Enter")
                logger.info("Playwright: submitted search '%s' via homepage", keyword)
            else:
                # Fallback: URL + 已有 cookie
                logger.info("Playwright: search box not found, using URL with cookies")
                await page.goto(
                    f"{SEARCH_URL}?keyword={keyword}&enc=utf-8&page=1",
                    wait_until="domcontentloaded", timeout=30000,
                )
        else:
            jd_page = page_num * 2 - 1
            url = f"{SEARCH_URL}?keyword={keyword}&enc=utf-8&page={jd_page}"
            logger.info("Playwright: loading page %d: %s", page_num, url)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 等待搜索结果渲染
        await asyncio.sleep(random.uniform(3.0, 5.0))
        await self._scroll_page(page)

        current_url = page.url
        logger.info("Page URL: %s", current_url[:150])

        # 风控/登录检查
        if any(kw in current_url for kw in ("risk_handler", "cfe.m.jd.com")):
            logger.warning("JD risk page at: %s", current_url[:120])
            await page.screenshot(path="/tmp/jd_blocked.png")
            return []
        if "passport.jd.com" in current_url:
            if page_num > 1:
                logger.warning("Login required on page %d, giving up on pagination", page_num)
                return []
            logger.warning("Login required after search navigation")
            if await self._require_login(page):
                logger.info("Retrying search after login...")
                return await self._fetch_search_page(page, keyword, page_num)
            return []

        products = await self._extract_products(page)
        if not products:
            # 诊断：检查页面真实 DOM 结构
            html_snippet = await page.evaluate("""() => {
                const html = document.documentElement.outerHTML;
                return html.substring(0, 2000);
            }""")
            logger.info("  Page HTML preview:\n%s", html_snippet[:1000])
            await page.screenshot(path="/tmp/jd_search.png")
        return products

    async def _extract_products(self, page: Page) -> list[dict]:
        """从页面 DOM 提取商品卡片，尝试多种选择器。"""
        return await page.evaluate("""() => {
            // 尝试多种 JD 搜索页面结构
            const selectors = [
                '.gl-item[data-sku]',
                '[data-sku]',
                '.goods-list-v2 .gl-item',
                '.gl-warp .gl-item',
                'li[data-sku]',
                '.J_goodsList > li',
            ];
            let items = [];
            for (const sel of selectors) {
                items = document.querySelectorAll(sel);
                if (items.length > 0) break;
            }

            return Array.from(items).map(el => {
                const sku = el.getAttribute('data-sku') || '';
                // 寻找标题
                let title = '';
                const titleSelectors = [
                    '.p-name em', '.p-name a em', '.p-name-type-2 a',
                    '.p-name a', '[class*="title"] em', '[class*="name"] a',
                    'a[title]',
                ];
                for (const ts of titleSelectors) {
                    const t = el.querySelector(ts);
                    if (t) { title = (t.getAttribute('title') || t.textContent || '').trim(); break; }
                }
                // 寻找链接
                let detailUrl = '';
                const linkEl = el.querySelector('a[href*="item.jd.com"]') || el.querySelector('.p-name a') || el.querySelector('.p-img a');
                if (linkEl) {
                    const href = linkEl.getAttribute('href');
                    if (href) detailUrl = href.startsWith('//') ? 'https:' + href : href;
                }
                return { sku_id: sku, title: title, detail_url: detailUrl, price_text: '' };
            }).filter(p => p.sku_id && p.title.length > 0);
        }""")

    async def _fetch_prices_via_api(
        self, page: Page, sku_ids: list[str]
    ) -> dict[str, dict]:
        """通过页面 fetch 调用京东价格 API（利用浏览器 Cookie 上下文）。"""
        if not sku_ids:
            return {}
        ids_param = ",".join(f"J_{sid}" for sid in sku_ids)
        api_url = f"{PRICE_API_URL}?skuIds={ids_param}"
        try:
            result = await page.evaluate("""
                async (url) => {
                    const resp = await fetch(url, { credentials: 'include' });
                    return await resp.json();
                }
            """, api_url)
            if not isinstance(result, list):
                return {}
            prices: dict[str, dict] = {}
            for item in result:
                raw_id = item.get("id", "")
                sku = raw_id.replace("J_", "")
                p_str = item.get("p")
                op_str = item.get("op")
                price_fen = 0
                original_fen = None
                if p_str:
                    try:
                        price_fen = round(float(p_str) * 100)
                    except (ValueError, TypeError):
                        pass
                if op_str:
                    try:
                        original_fen = round(float(op_str) * 100)
                    except (ValueError, TypeError):
                        pass
                prices[sku] = {"price_fen": price_fen, "original_fen": original_fen}
            return prices
        except Exception as e:
            logger.warning("Price API via page.evaluate failed: %s", e)
            return {}

    @staticmethod
    def _yuan_to_fen(price_str: str | None) -> int:
        if not price_str:
            return 0
        try:
            # 去掉 ¥ 符号和逗号
            clean = re.sub(r"[^\d.]", "", price_str)
            return round(float(clean) * 100)
        except (ValueError, TypeError):
            return 0

    async def _scroll_page(self, page: Page) -> None:
        """渐进滚动触发京东懒加载。"""
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.6)

    async def fetch_detail(self, platform_sku_id: str) -> RawProduct | None:
        """抓取商品详情页。"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self._headless,
                slow_mo=self._slow_mo,
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
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                window.chrome = { runtime: {} };
            """)
            page = await context.new_page()
            try:
                url = f"https://item.jd.com/{platform_sku_id}.html"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2.0)
                title = await page.title()
                # 获取价格
                prices = await self._fetch_prices_via_api(page, [platform_sku_id])
                price_info = prices.get(platform_sku_id, {"price_fen": 0, "original_fen": None})
                return RawProduct(
                    platform_code=self.platform_code,
                    platform_sku_id=platform_sku_id,
                    title=title.strip() or platform_sku_id,
                    price_fen=price_info["price_fen"],
                    original_fen=price_info.get("original_fen"),
                    coupon_fen=0,
                    detail_url=url,
                    raw_payload={"html_title": title},
                    crawled_at=datetime.now(timezone.utc),
                    crawler_version=CRAWLER_VERSION,
                )
            except Exception as e:
                logger.warning("Playwright detail fetch failed for %s: %s", platform_sku_id, e)
                return None
            finally:
                await browser.close()

    async def fetch_price(self, platform_sku_id: str) -> dict | None:
        """轻量价格查询（复用价格 API）。"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await (await browser.new_context()).new_page()
            try:
                prices = await self._fetch_prices_via_api(page, [platform_sku_id])
                info = prices.get(platform_sku_id)
                if info:
                    return {
                        "price_fen": info["price_fen"],
                        "original_fen": info.get("original_fen"),
                        "crawler_version": CRAWLER_VERSION,
                    }
                return None
            finally:
                await browser.close()
