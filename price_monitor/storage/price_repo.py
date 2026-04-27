import logging
from datetime import datetime, timezone

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from price_monitor.models import PriceTick, Product, Platform

logger = logging.getLogger(__name__)


class PriceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def record_price(self, product_id: int, clean_product) -> bool:
        """写入价格 tick。raw_hash 已存在则跳过，返回 False；写入成功返回 True。"""
        existing = await self._session.execute(
            select(PriceTick.id).where(
                PriceTick.product_id == product_id,
                PriceTick.raw_hash == clean_product.raw_hash,
            ).limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            return False

        tick = PriceTick(
            product_id=product_id,
            price_fen=clean_product.price_fen,
            original_fen=clean_product.original_fen,
            coupon_fen=clean_product.coupon_fen,
            in_stock=clean_product.in_stock,
            promotion_tag=clean_product.promotion_tag,
            crawler_version=clean_product.crawler_version,
            raw_hash=clean_product.raw_hash,
        )
        self._session.add(tick)
        await self._session.commit()
        return True

    async def get_price_history(self, product_id: int, days: int = 30) -> list[dict]:
        """从 price_hourly 连续聚合视图查近 N 天价格历史。"""
        result = await self._session.execute(
            text("""
                SELECT bucket, min_final_fen, max_final_fen, avg_final_fen, tick_count
                FROM price_hourly
                WHERE product_id = :product_id
                  AND bucket >= NOW() - make_interval(days => :days)
                ORDER BY bucket DESC
            """),
            {"product_id": product_id, "days": days},
        )
        return [
            {
                "bucket": row[0].isoformat() if row[0] else None,
                "min_final_fen": row[1],
                "max_final_fen": row[2],
                "avg_final_fen": row[3],
                "tick_count": row[4],
            }
            for row in result
        ]

    async def get_current_lowest(
        self, category: str, filters: dict | None = None
    ) -> list[dict]:
        """查当前最低价商品列表。"""
        filters = filters or {}
        memory_type = filters.get("memory_type")
        min_capacity = filters.get("min_capacity_gb", 0)

        # Get latest price per product
        query = text("""
            WITH latest AS (
                SELECT DISTINCT ON (product_id)
                    product_id, price_fen, original_fen, coupon_fen,
                    (price_fen - coupon_fen) AS final_fen
                FROM price_ticks
                ORDER BY product_id, recorded_at DESC
            )
            SELECT
                p.id,
                p.brand,
                p.model,
                p.title,
                pl.code AS platform_code,
                rs.capacity_gb,
                rs.kit_count,
                rs.speed_mhz,
                rs.memory_type,
                rs.cl_latency,
                rs.form_factor,
                rs.die_type,
                l.price_fen,
                l.final_fen
            FROM latest l
            JOIN products p ON p.id = l.product_id
            JOIN platforms pl ON pl.id = p.platform_id
            JOIN ram_specs rs ON rs.product_id = p.id
            WHERE p.category = :category
              AND p.is_active = TRUE
              AND rs.capacity_gb >= :min_capacity
        """)

        params = {"category": category, "min_capacity": min_capacity}
        if memory_type:
            query = text(query.text + " AND rs.memory_type = :memory_type")
            params["memory_type"] = memory_type

        query = text(query.text + " ORDER BY l.final_fen ASC LIMIT 100")

        result = await self._session.execute(query, params)
        return [
            {
                "id": row[0],
                "brand": row[1],
                "model": row[2],
                "title": row[3],
                "platform_code": row[4],
                "capacity_gb": row[5],
                "kit_count": row[6],
                "speed_mhz": row[7],
                "memory_type": row[8],
                "cl_latency": row[9],
                "form_factor": row[10],
                "die_type": row[11],
                "price_fen": row[12],
                "final_fen": row[13],
            }
            for row in result
        ]
