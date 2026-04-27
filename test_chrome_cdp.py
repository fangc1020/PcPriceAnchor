"""
用真实 Chrome（已登录 JD）通过 CDP 抓内存条搜索结果 + 价格。

第一步：关闭所有 Chrome 窗口，然后运行：
    /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
        --remote-debugging-port=9222 \
        --user-data-dir=/tmp/chrome_jd_profile

第二步：在弹出的 Chrome 里手动登录京东（只需一次）

第三步：运行本脚本：
    python test_chrome_cdp.py
"""

import asyncio
import json
from playwright.async_api import async_playwright

KEYWORD = "DDR5 内存条"
MAX_PAGES = 2  # 先只测 2 页，验证通了再加


async def scroll_page(page) -> None:
    for _ in range(5):
        await page.evaluate("window.scrollBy(0, 600)")
        await asyncio.sleep(0.5)


async def extract_products(page) -> list[dict]:
    return await page.evaluate("""() => {
        const items = document.querySelectorAll('[data-sku]');
        return Array.from(items).map(el => {
            const sku = el.getAttribute('data-sku') || '';

            // 标题：新版用 span[class*="_text_"]，有 title 属性
            let title = '';
            const titleEl = el.querySelector('span[class*="_text_"][title], span[title]');
            if (titleEl) title = (titleEl.getAttribute('title') || titleEl.textContent || '').trim();

            // 链接：找 item.jd.com
            let detailUrl = `https://item.jd.com/${sku}.html`;

            // 价格：新版结构 span[class*="_price_"] > i + span
            let priceText = '';
            const priceWrap = el.querySelector('[class*="_price_"]');
            if (priceWrap) {
                const yuan = priceWrap.querySelector('span');
                const fen_el = priceWrap.querySelector('i[class*="_fen_"], i:last-child');
                const main = yuan ? yuan.textContent.trim() : '';
                const fen = fen_el ? fen_el.textContent.trim() : '';
                priceText = fen ? `${main}.${fen}` : main;
                // fallback：直接拼全文
                if (!priceText) priceText = priceWrap.textContent.replace(/¥/g, '').trim();
            }

            const num = priceText.replace(/[^0-9.]/g, '');
            const priceFen = num ? Math.round(parseFloat(num) * 100) : 0;

            return { sku_id: sku, title, detail_url: detailUrl, price_text: priceText, price_fen: priceFen };
        }).filter(p => p.sku_id && p.title.length > 0);
    }""")


async def main() -> None:
    async with async_playwright() as p:
        print("连接真实 Chrome（确保已用上面的命令启动）...")
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            print("请先运行：")
            print('  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\')
            print('      --remote-debugging-port=9222 \\')
            print('      --user-data-dir=/tmp/chrome_jd_profile')
            return

        print(f"✓ 连接成功，浏览器版本: {browser.version}")

        # 复用已有 context（保留登录态），或新建一个
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        page = await context.new_page()

        all_products: list[dict] = []

        for pg in range(1, MAX_PAGES + 1):
            jd_page = pg * 2 - 1
            url = f"https://search.jd.com/Search?keyword={KEYWORD}&enc=utf-8&page={jd_page}"
            print(f"\n第 {pg} 页: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            title = await page.title()
            current_url = page.url
            print(f"  页面标题: {title}")
            print(f"  当前 URL: {current_url[:80]}")

            if any(x in current_url for x in ("passport.jd.com", "risk_handler", "login")):
                print("  ⚠ 被跳转到登录/风控页，请在 Chrome 窗口里手动处理后按回车继续...")
                input()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

            await scroll_page(page)
            products = await extract_products(page)
            print(f"  提取到 {len(products)} 个商品")

            for prod in products[:3]:  # 只打印前 3 条预览
                price_str = f"¥{prod['price_fen']/100:.2f}" if prod['price_fen'] else "无价格"
                print(f"    [{prod['sku_id']}] {prod['title'][:40]}... {price_str}")

            all_products.extend(products)

            if pg < MAX_PAGES:
                await asyncio.sleep(2)

        # 保存结果
        output = "/tmp/jd_ram_products.json"
        with open(output, "w", encoding="utf-8") as f:
            json.dump(all_products, f, ensure_ascii=False, indent=2)

        has_price = sum(1 for p in all_products if p['price_fen'] > 0)
        print(f"\n{'='*60}")
        print(f"总计: {len(all_products)} 个商品，其中 {has_price} 个有价格")
        print(f"结果已保存到 {output}")

        await page.close()


if __name__ == "__main__":
    asyncio.run(main())
