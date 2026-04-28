"""入口 — 启动 APScheduler 定时采集任务。"""

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from price_monitor.cleaners.ram import RamCleaner
from price_monitor.config.settings import settings
from price_monitor.crawlers.jd.cdp_crawler import JdCdpCrawler
from price_monitor.crawlers.jd.playwright_search import JdSearchPlaywrightCrawler
from price_monitor.crawlers.jd.search import JdSearchCrawler
from price_monitor.crawlers.jd.stealth_crawler import JdStealthCrawler
from price_monitor.scheduler.tasks import CrawlTask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_once(
    keyword: str = "DDR5 内存条",
    category: str = "ram",
    max_pages: int = 5,
    dry_run: bool = False,
    engine: str = "playwright",
) -> None:
    """单次采集（用于调试和一次性测试）。"""
    if engine == "cdp":
        crawler = JdCdpCrawler()
    elif engine == "stealth":
        crawler = JdStealthCrawler(headless=False)
    elif engine == "playwright":
        crawler = JdSearchPlaywrightCrawler(headless=False, slow_mo=300)
    else:
        crawler = JdSearchCrawler()
    cleaner = RamCleaner()
    task = CrawlTask(crawler=crawler, cleaner=cleaner)

    if dry_run:
        result = await task.run_dry(keyword=keyword, category=category, max_pages=max_pages)
        logger.info(
            "Dry-run complete: fetched=%d, cleaned=%d, skipped=%d, errors=%d",
            result.total_fetched,
            result.total_cleaned,
            result.total_skipped,
            len(result.errors),
        )
    else:
        result = await task.run(keyword=keyword, category=category, max_pages=max_pages)
        logger.info(
            "Crawl complete: fetched=%d, cleaned=%d, saved=%d, skipped=%d, errors=%d",
            result.total_fetched,
            result.total_cleaned,
            result.total_saved,
            result.total_skipped,
            len(result.errors),
        )

    if result.errors:
        for err in result.errors[:5]:
            logger.error("  %s", err)


async def run_analysis() -> None:
    """单次分析：查当前最低价商品 + 趋势 + 排名 + 输出报告。"""
    import webbrowser

    from price_monitor.analysis.report import ReportGenerator
    from price_monitor.analysis.trend import TrendAnalyzer
    from price_monitor.analysis.value_rank import ValueRanker
    from price_monitor.db.session import async_session
    from price_monitor.storage.price_repo import PriceRepository

    async with async_session() as session:
        price_repo = PriceRepository(session)

        products = await price_repo.get_current_lowest(category="ram")
        if not products:
            logger.info("No products found for analysis.")
            return

        # Batch-fetch price histories (avoids N+1 queries)
        pids = [p["id"] for p in products]
        price_histories = await price_repo.get_price_history_batch(pids)

        analyzer = TrendAnalyzer()
        trends = []
        for p in products:
            history = price_histories.get(p["id"], [])
            trend = analyzer.analyze(history)
            trend.product_id = p["id"]
            trends.append(trend)

        ranker = ValueRanker()
        rankings = ranker.rank(products, trends)
        grouped = ranker.group_rank(rankings)

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        json_str = ReportGenerator.to_json(grouped)
        md = ReportGenerator.to_markdown(grouped)

        # Print to terminal
        print(md)

        # Save to files
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        (reports_dir / f"report_{date_str}.md").write_text(md, encoding="utf-8")
        (reports_dir / f"report_{date_str}.json").write_text(json_str, encoding="utf-8")
        ReportGenerator.to_excel(grouped, reports_dir / f"report_{date_str}.xlsx")

        # HTML report with Plotly charts
        html = ReportGenerator.to_html(grouped, price_histories, trends)
        html_path = reports_dir / f"report_{date_str}.html"
        html_path.write_text(html, encoding="utf-8")
        logger.info("HTML report saved to %s", html_path)

        logger.info("Reports saved to reports/report_%s.{md,json,xlsx,html}", date_str)

        # Open in browser
        webbrowser.open(f"file://{html_path.resolve()}")

        # Optionally push to Feishu
        if settings.feishu_webhook_url:
            await _send_feishu(grouped)


async def _send_feishu(grouped) -> None:
    import httpx

    from price_monitor.analysis.report import ReportGenerator

    card = ReportGenerator.to_feishu_card(grouped)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(
                settings.feishu_webhook_url,
                content=card,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            logger.info("Feishu notification sent.")
    except Exception as e:
        logger.warning("Feishu notification failed: %s", e)


async def main() -> None:
    scheduler = AsyncIOScheduler()

    # 每 2 小时采集一次
    scheduler.add_job(
        lambda: asyncio.create_task(run_once()),
        "interval",
        minutes=settings.crawl_interval_minutes,
        id="crawl_job",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: JD crawl every %d minutes. Press Ctrl+C to stop.",
        settings.crawl_interval_minutes,
    )

    # 后台采集模式下，也可以按需分析
    await asyncio.Event().wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PC Price Monitor")
    sub = parser.add_subparsers(dest="command")

    once_p = sub.add_parser("once", help="Single crawl (writes to DB)")
    once_p.add_argument("--dry-run", action="store_true", help="Skip DB, just crawl + clean + print")
    once_p.add_argument("--keyword", default="DDR5 内存条", help="Search keyword")
    once_p.add_argument("--pages", type=int, default=3, help="Max pages to crawl")
    once_p.add_argument("--engine", choices=["cdp", "playwright", "httpx", "stealth"], default="cdp",
                        help="Crawl engine (default: cdp)")

    sub.add_parser("analyze", help="Run analysis + report (requires DB)")

    sub.add_parser("scheduler", help="Start the periodic scheduler (requires DB)")

    args = parser.parse_args()

    if args.command == "once":
        asyncio.run(run_once(
            keyword=args.keyword,
            max_pages=args.pages,
            dry_run=args.dry_run,
            engine=args.engine,
        ))
    elif args.command == "analyze":
        asyncio.run(run_analysis())
    elif args.command == "scheduler":
        asyncio.run(main())
    else:
        # Default: start scheduler (backwards compatible with no args)
        asyncio.run(main())
