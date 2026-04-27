"""京东 CDP 爬虫 — 连接用户真实 Chrome，复用登录态抓取搜索结果。

工作原理：
  用户用 --remote-debugging-port=9222 启动 Chrome 并手动登录京东一次，
  本爬虫通过 CDP 协议接管该浏览器，复用其完整登录态和浏览器指纹。
  对京东来说，访问来自真实用户 Chrome，无法与正常浏览区分。

前置条件：
  Chrome 必须以调试端口启动，见 scripts/start_chrome.sh。
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import AsyncIterator

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from price_monitor.crawlers.base import BaseCrawler
from price_monitor.crawlers.schemas import RawProduct

logger = logging.getLogger(__name__)

CRAWLER_VERSION = "jd-cdp-v1"
CDP_URL = "http://localhost:9222"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
]


class JdCdpCrawler(BaseCrawler):
    """通过 CDP 连接本地真实 Chrome 的京东爬虫。"""

    platform_code = "jd"

    def __init__(self, cdp_url: str = CDP_URL) -> None:
        self._cdp_url = cdp_url

    # ------------------------------------------------------------------
    # BaseCrawler 接口
    # ------------------------------------------------------------------

    async def search(
        self,
        keyword: str,
        category: str,
        max_pages: int = 3,
    ) -> AsyncIterator[RawProduct]:
        async with async_playwright() as p:
            browser, context = await self._connect(p)
            page = await context.new_page()
            try:
                for pg in range(1, max_pages + 1):
                    products = await self._fetch_search_page(page, keyword, pg)
                    if not products:
                        logger.warning("Page %d returned 0 products, stopping.", pg)
                        break

                    for prod in products:
                        yield RawProduct(
                            platform_code=self.platform_code,
                            platform_sku_id=prod["sku_id"],
                            title=prod["title"],
                            price_fen=prod["price_fen"],
                            original_fen=prod.get("original_fen"),
                            coupon_fen=0,
                            in_stock=True,
                            detail_url=prod["detail_url"],
                            raw_payload=prod,
                            crawled_at=datetime.now(timezone.utc),
                            crawler_version=CRAWLER_VERSION,
                        )

                    if pg < max_pages:
                        await asyncio.sleep(random.uniform(4.0, 8.0))
            finally:
                await page.close()

    async def fetch_detail(self, platform_sku_id: str) -> RawProduct | None:
        async with async_playwright() as p:
            browser, context = await self._connect(p)
            page = await context.new_page()
            try:
                url = f"https://item.jd.com/{platform_sku_id}.html"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                if "passport.jd.com" in page.url or "login" in page.url:
                    logger.warning("Detail page requires login for SKU %s", platform_sku_id)
                    return None

                title = await page.title()
                price_fen = await self._extract_detail_price(page)

                return RawProduct(
                    platform_code=self.platform_code,
                    platform_sku_id=platform_sku_id,
                    title=title.strip(),
                    price_fen=price_fen,
                    coupon_fen=0,
                    detail_url=url,
                    raw_payload={"html_title": title},
                    crawled_at=datetime.now(timezone.utc),
                    crawler_version=CRAWLER_VERSION,
                )
            except Exception as e:
                logger.warning("fetch_detail failed for %s: %s", platform_sku_id, e)
                return None
            finally:
                await page.close()

    async def fetch_price(self, platform_sku_id: str) -> dict | None:
        detail = await self.fetch_detail(platform_sku_id)
        if detail:
            return {
                "price_fen": detail.price_fen,
                "original_fen": detail.original_fen,
                "crawler_version": CRAWLER_VERSION,
            }
        return None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _connect(self, p) -> tuple[Browser, BrowserContext]:
        """连接 CDP，返回 browser 和第一个已有 context（保留登录态）。"""
        try:
            browser = await p.chromium.connect_over_cdp(self._cdp_url)
        except Exception as e:
            raise RuntimeError(
                f"无法连接 Chrome CDP ({self._cdp_url})。"
                f"请先运行 scripts/start_chrome.sh 并完成京东登录。\n原始错误: {e}"
            ) from e

        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        return browser, context

    async def _fetch_search_page(
        self, page: Page, keyword: str, page_num: int
    ) -> list[dict]:
        if page_num == 1:
            # 先访问首页预热（不带 Referer 直接访问 search.jd.com 会被重定向到首页）
            await page.goto(
                "https://www.jd.com/", wait_until="domcontentloaded", timeout=30000
            )
            await asyncio.sleep(1)

            url = f"https://search.jd.com/Search?keyword={keyword}&enc=utf-8"
            logger.info("Fetching page %d: %s", page_num, url)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        else:
            # 翻页：点击"下一页"按钮（URL page= 参数在 JD React SPA 无效）
            logger.info("Clicking next page button for page %d", page_num)
            next_btn = await page.query_selector('[class*="_pagination_next_"]')
            if next_btn is None:
                logger.warning("Next page button not found, stopping.")
                return []
            await next_btn.click()

        await asyncio.sleep(2)

        # --- 风控熔断 ---
        current = page.url
        if any(x in current for x in ("passport.jd.com", "risk_handler", "login")):
            logger.error(
                "被跳转到登录/风控页：%s。Chrome 登录态可能已失效。", current
            )
            return []
        if "search.jd.com" not in current:
            logger.error("不在搜索页（疑似风控重定向）：%s", current)
            return []

        # 检查页面是否包含验证码
        try:
            body_text = await page.evaluate("() => document.body.innerText")
            if "验证" in body_text:
                logger.warning("页面含「验证」关键词，疑似触发验证码，停止翻页。")
                return []
        except Exception:
            pass

        await self._scroll_page(page)
        return await self._extract_products(page)

    async def _extract_products(self, page: Page) -> list[dict]:
        """从京东新版 React 搜索页提取商品列表。

        JD 2025 页面使用 CSS Modules，class 名含哈希（如 _text_1k2fi_48）。
        用 [class*="xxx"] 匹配以应对哈希变化，但核心特征词（_text_, _price_）
        在 JD 组件命名规范下相对稳定。若提取到 0 条，参考故障排查文档。
        """
        return await page.evaluate("""() => {
            const items = document.querySelectorAll('[data-sku]');
            return Array.from(items).map(el => {
                const sku = el.getAttribute('data-sku') || '';

                // 标题：span[class*="_text_"] 有 title 属性
                let title = '';
                const titleEl = el.querySelector('span[class*="_text_"][title]');
                if (titleEl) {
                    title = (titleEl.getAttribute('title') || titleEl.textContent || '').trim();
                }

                // 商品链接
                const detailUrl = `https://item.jd.com/${sku}.html`;

                // 价格：新版结构 span[class*="_price_"] 内含 i(¥符号) + span(数字)
                let priceFen = 0;
                let originalFen = null;
                const priceWrap = el.querySelector('[class*="_price_"]');
                if (priceWrap) {
                    const numSpan = priceWrap.querySelector('span');
                    if (numSpan) {
                        const raw = numSpan.textContent.replace(/[^0-9.]/g, '');
                        if (raw) priceFen = Math.round(parseFloat(raw) * 100);
                    }
                }

                return {
                    sku_id: sku,
                    title,
                    detail_url: detailUrl,
                    price_fen: priceFen,
                    original_fen: originalFen,
                };
            }).filter(p => p.sku_id && p.title.length > 0);
        }""")

    async def _extract_detail_price(self, page: Page) -> int:
        """从商品详情页提取价格（fen）。"""
        try:
            await page.wait_for_selector('[class*="_price_"], .p-price', timeout=8000)
        except Exception:
            pass

        return await page.evaluate("""() => {
            const selectors = [
                '[class*="_price_"] span',
                '.p-price strong i',
                '#jd-price',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const raw = el.textContent.replace(/[^0-9.]/g, '');
                    if (raw && raw !== '0') return Math.round(parseFloat(raw) * 100);
                }
            }
            return 0;
        }""")

    async def _scroll_page(self, page: Page) -> None:
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(0.5)
