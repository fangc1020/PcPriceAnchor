"""采集任务编排 — CrawlTask 依赖注入 crawler, cleaner, repo 并执行流水线。"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from price_monitor.crawlers.base import BaseCrawler
from price_monitor.cleaners.base import BaseCleaner
from price_monitor.storage.product_repo import ProductRepository
from price_monitor.storage.price_repo import PriceRepository
from price_monitor.db.session import async_session

logger = logging.getLogger(__name__)


@dataclass
class CrawlTaskResult:
    total_fetched: int = 0
    total_cleaned: int = 0
    total_saved: int = 0
    total_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def merge(self, other: "CrawlTaskResult") -> None:
        self.total_fetched += other.total_fetched
        self.total_cleaned += other.total_cleaned
        self.total_saved += other.total_saved
        self.total_skipped += other.total_skipped
        self.errors.extend(other.errors)


class CrawlTask:
    """单次采集任务。依赖注入：crawler, cleaner, product_repo, price_repo。"""

    def __init__(
        self,
        crawler: BaseCrawler,
        cleaner: BaseCleaner,
    ):
        self._crawler = crawler
        self._cleaner = cleaner

    async def run(
        self,
        keyword: str,
        category: str,
        max_pages: int = 5,
    ) -> CrawlTaskResult:
        result = CrawlTaskResult()

        async with async_session() as session:
            product_repo = ProductRepository(session)
            price_repo = PriceRepository(session)

            try:
                async for raw in self._crawler.search(keyword, category, max_pages):
                    result.total_fetched += 1

                    clean = self._cleaner.clean(raw)
                    if clean is None or not self._cleaner.validate(clean):
                        result.total_skipped += 1
                        continue

                    result.total_cleaned += 1

                    try:
                        product_id = await product_repo.upsert_product(clean)
                        saved = await price_repo.record_price(product_id, clean)
                        if saved:
                            result.total_saved += 1
                        else:
                            result.total_skipped += 1
                    except Exception as e:
                        msg = f"Storage error for {clean.platform_sku_id}: {e}"
                        logger.error(msg)
                        result.errors.append(msg)

            except Exception as e:
                msg = f"Crawl error: {e}"
                logger.error(msg)
                result.errors.append(msg)

        return result

    async def run_dry(
        self,
        keyword: str,
        category: str,
        max_pages: int = 5,
    ) -> CrawlTaskResult:
        """Dry-run：只采集+清洗+打印，不写数据库。"""
        result = CrawlTaskResult()

        try:
            async for raw in self._crawler.search(keyword, category, max_pages):
                result.total_fetched += 1

                clean = self._cleaner.clean(raw)
                if clean is None or not self._cleaner.validate(clean):
                    result.total_skipped += 1
                    continue

                result.total_cleaned += 1

                # Print parsed result
                spec = clean.spec
                parts = [
                    f"[{clean.brand}] {clean.model}",
                    f"¥{clean.price_fen / 100:.2f}",
                    f"{spec.memory_type} {spec.speed_mhz}MHz",
                    f"{spec.capacity_gb}GB×{spec.kit_count}={spec.total_gb}GB",
                ]
                if spec.cl_latency:
                    parts.append(f"CL{spec.cl_latency}")
                if spec.timing_string:
                    parts.append(spec.timing_string)
                if spec.die_type:
                    parts.append(spec.die_type)
                if spec.has_rgb:
                    parts.append("RGB")
                if spec.form_factor != "DIMM":
                    parts.append(spec.form_factor)
                if spec.parse_confidence < 1.0:
                    parts.append(f"(conf={spec.parse_confidence:.0%})")

                logger.info("  %s", " | ".join(parts))

        except Exception as e:
            msg = f"Crawl error: {e}"
            logger.error(msg)
            result.errors.append(msg)

        return result

    async def run_price_update(
        self, sku_ids: list[str]
    ) -> dict[str, int | None]:
        """轻量价格更新：仅采集价格字段，不入库完整数据。"""
        updates: dict[str, int | None] = {}
        async with async_session() as session:
            price_repo = PriceRepository(session)
            for sku_id in sku_ids:
                price_data = await self._crawler.fetch_price(sku_id)
                if price_data:
                    updates[sku_id] = price_data.get("price_fen")
            # Price-only updates: create a minimal CleanProduct for recording
            # This is a lightweight path; full crawl uses the main pipeline.
        return updates
