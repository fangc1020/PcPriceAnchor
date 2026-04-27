"""
测试 item.jd.com 单品页能否在无需登录的情况下等到价格加载。

用法：
    python test_item_price.py

结果说明：
    - 如果能拿到价格 → 说明 item.jd.com 路线可行，可以靠此爬价格
    - 如果价格仍为 0 / 超时 → 说明价格 Ajax 需要登录态
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

COOKIE_FILE = Path(__file__).parent / ".jd_cookies.json"

# 几个常见 DDR5 内存条 SKU（可自行替换）
TEST_SKUS = [
    "100012043978",  # 金士顿
    "100040061122",  # 芝奇
    "100036417590",  # 海力士
]

PRICE_SELECTORS = [
    "#jd-price",
    ".p-price strong i",
    ".p-price .price",
    "[class*='J_price'] i",
    ".summary-price-wrap [class*='price']",
]


async def fetch_price(sku_id: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 开着窗口方便观察
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
        )
        # 加载已保存的登录 cookie
        if COOKIE_FILE.exists():
            cookies = json.loads(COOKIE_FILE.read_text())
            await context.add_cookies(cookies)
            print(f"  已加载 {len(cookies)} 条 cookie")
        else:
            print("  ⚠ 未找到 .jd_cookies.json，将以未登录状态访问")

        page = await context.new_page()

        url = f"https://item.jd.com/{sku_id}.html"
        print(f"\n{'='*60}")
        print(f"SKU: {sku_id}  →  {url}")

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 等待价格元素出现且有非零内容（最多 10 秒）
        price_text = ""
        for sel in PRICE_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=10000)
                raw = await page.locator(sel).first.inner_text()
                raw = raw.strip().replace("¥", "").replace(",", "").strip()
                if raw and raw != "0" and raw != "0.00":
                    price_text = raw
                    print(f"  ✓ 价格找到 [{sel}]: ¥{price_text}")
                    break
                else:
                    print(f"  ✗ 选择器 [{sel}] 有值但为空/零: '{raw}'")
            except Exception:
                print(f"  ✗ 选择器 [{sel}] 超时或不存在")

        if not price_text:
            screenshot_path = f"/tmp/jd_item_{sku_id}.png"
            print(f"  ⚠ 所有选择器均未获取到有效价格，截图保存至 {screenshot_path}")
            await page.screenshot(path=screenshot_path, full_page=False)

        print(f"\n  [提示] 如果价格为 0，查看 /tmp/jd_item_{{sku_id}}.png 截图")
        print(f"  页面标题: {await page.title()}")

        await browser.close()


async def main() -> None:
    print("开始测试 item.jd.com 无登录态价格加载...")
    for sku in TEST_SKUS:
        await fetch_price(sku)
        await asyncio.sleep(2)
    print("\n测试完成。")


if __name__ == "__main__":
    asyncio.run(main())
