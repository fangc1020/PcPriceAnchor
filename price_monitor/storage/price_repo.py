import logging

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from price_monitor.models import PriceTick

logger = logging.getLogger(__name__)


class PriceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def record_price(self, product_id: int, clean_product) -> bool:
        """写入价格 tick。同日同 raw_hash 跳过，跨日重新记录以积累趋势数据。"""
        existing = await self._session.execute(
            select(PriceTick.id).where(
                PriceTick.product_id == product_id,
                PriceTick.raw_hash == clean_product.raw_hash,
                func.date(PriceTick.recorded_at) == func.current_date(),
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

    async def get_price_history_batch(
        self, product_ids: list[int], days: int = 14
    ) -> dict[int, list[dict]]:
        """批量查询价格历史，返回 {product_id: [records]} 映射。"""
        if not product_ids:
            return {}
        result = await self._session.execute(
            text("""
                SELECT product_id, bucket, min_final_fen, max_final_fen, avg_final_fen, tick_count
                FROM price_hourly
                WHERE product_id = ANY(:pids)
                  AND bucket >= NOW() - make_interval(days => :days)
                ORDER BY product_id, bucket DESC
            """),
            {"pids": product_ids, "days": days},
        )
        history: dict[int, list[dict]] = {}
        for row in result:
            pid = row[0]
            history.setdefault(pid, []).append({
                "bucket": row[1].isoformat() if row[1] else None,
                "min_final_fen": float(row[2]) if row[2] is not None else 0,
                "max_final_fen": float(row[3]) if row[3] is not None else 0,
                "avg_final_fen": float(row[4]) if row[4] is not None else 0,
                "tick_count": row[5],
            })
        return history

    # 装机视角：OEM 裸条 / 工控 / 服务器 / 拆机件 无参考价值，标题级过滤
    _OEM_TITLE_RE = (
        r'(三星|samsung|海力士|hynix|镁光|micron)\s*[内存条]'
        r'|工控|工业|服务器|工作站|ECC|REG|RECC'
        r'|原装|拆机|备件|oem'
        r'|天迪工控|戴尔|dell|惠普|hp|联想原装'
    )

    async def get_current_lowest(
        self, category: str, filters: dict | None = None
    ) -> list[dict]:
        """查当前最低价商品列表。"""
        filters = filters or {}
        memory_type = filters.get("memory_type")
        min_capacity = filters.get("min_capacity_gb", 0)
        exclude_form_factor = filters.get("exclude_form_factor", "SO-DIMM")

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
              AND rs.form_factor != :exclude_form_factor
              AND NOT (p.title ~* :oem_title_re)
              AND NOT (p.title ~* '(笔记本|笔电|notebook|laptop|天选|枪神)')
        """)

        params = {
            "category": category,
            "min_capacity": min_capacity,
            "exclude_form_factor": exclude_form_factor,
            "oem_title_re": self._OEM_TITLE_RE,
        }
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
