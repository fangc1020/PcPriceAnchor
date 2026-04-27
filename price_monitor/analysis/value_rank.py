"""性价比评分与排名 — 综合价格、规格、趋势三维度评分。"""

from dataclasses import dataclass, field
from typing import List

from price_monitor.analysis.trend import TrendResult


@dataclass
class ValueScore:
    product_id: int
    score: float  # 综合性价比分（0-100）
    price_score: float  # 价格维度
    spec_score: float  # 规格维度（频率/容量）
    trend_score: float  # 时机维度

    brand: str = ""
    model: str = ""
    title: str = ""
    capacity_gb: int = 0
    kit_count: int = 1
    speed_mhz: int = 0
    cl_latency: int | None = None
    die_type: str | None = None
    memory_type: str = ""
    form_factor: str = ""
    final_fen: int = 0
    recommendation: str = ""

    @property
    def total_capacity(self) -> int:
        return self.capacity_gb * self.kit_count

    @property
    def cl_tier(self) -> str:
        if self.cl_latency is None:
            return "CL未知"
        if self.cl_latency <= 30:
            return "CL28-30"
        if self.cl_latency <= 36:
            return "CL32-36"
        if self.cl_latency <= 40:
            return "CL38-40"
        return "CL42+"

    @property
    def group_key(self) -> str:
        return (
            f"{self.memory_type} {self.form_factor} "
            f"{self.total_capacity}GB {self.speed_mhz}MHz {self.cl_tier}"
        )

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "score": round(self.score, 1),
            "price_score": round(self.price_score, 1),
            "spec_score": round(self.spec_score, 1),
            "trend_score": round(self.trend_score, 1),
            "brand": self.brand,
            "model": self.model,
            "title": self.title,
            "capacity_gb": self.capacity_gb,
            "kit_count": self.kit_count,
            "speed_mhz": self.speed_mhz,
            "cl_latency": self.cl_latency,
            "die_type": self.die_type,
            "memory_type": self.memory_type,
            "form_factor": self.form_factor,
            "total_capacity": self.total_capacity,
            "cl_tier": self.cl_tier,
            "group_key": self.group_key,
            "final_fen": self.final_fen,
            "recommendation": self.recommendation,
        }


class ValueRanker:
    """综合评分排名引擎。

    评分维度：
    - 价格分 (0-40)：同等规格下，价格越低分越高
    - 规格分 (0-40)：频率越高、容量越大、时序越低分越高
    - 时机分 (0-20)：基于趋势信号加分
    """

    @staticmethod
    def rank(products: list[dict], trends: list[TrendResult]) -> list[ValueScore]:
        trend_map = {t.product_id: t for t in trends}

        # Build price-indexed data for relative scoring
        prices = [p.get("final_fen", 9999999) for p in products if p.get("final_fen")]
        min_price = min(prices) if prices else 1
        max_price = max(prices) if prices else 1
        price_range = max_price - min_price or 1

        speeds = [p.get("speed_mhz", 0) for p in products]
        min_speed = min(speeds) if speeds else 2000
        max_speed = max(speeds) if speeds else 8000
        speed_range = max_speed - min_speed or 1

        results = []
        for p in products:
            pid = p["id"]
            trend = trend_map.get(pid)
            price_score = ValueRanker._calc_price_score(
                p.get("final_fen", 0), min_price, price_range
            )
            spec_score = ValueRanker._calc_spec_score(p, min_speed, speed_range)
            trend_score = ValueRanker._calc_trend_score(trend)
            score = price_score + spec_score + trend_score

            results.append(ValueScore(
                product_id=pid,
                score=score,
                price_score=price_score,
                spec_score=spec_score,
                trend_score=trend_score,
                brand=p.get("brand", ""),
                model=p.get("model", ""),
                title=p.get("title", ""),
                capacity_gb=p.get("capacity_gb", 0),
                kit_count=p.get("kit_count", 1),
                speed_mhz=p.get("speed_mhz", 0),
                cl_latency=p.get("cl_latency"),
                die_type=p.get("die_type"),
                memory_type=p.get("memory_type", ""),
                form_factor=p.get("form_factor", ""),
                final_fen=p.get("final_fen", 0),
                recommendation=trend.recommendation if trend else "wait",
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    @staticmethod
    def group_rank(rankings: list[ValueScore], min_group_size: int = 3) -> dict[str, list[ValueScore]]:
        """按规格组合分组，组内按价格升序排名。

        分组维度：内存类型 + 外形 + 总容量 + 频率 + CL档位。
        只保留商品数 ≥ min_group_size 的组。
        """
        groups: dict[str, list[ValueScore]] = {}
        for r in rankings:
            groups.setdefault(r.group_key, []).append(r)

        # 组内按价格从低到高排序
        for key in groups:
            groups[key].sort(key=lambda x: x.final_fen if x.final_fen > 0 else 9999999)

        # 过滤小组，按组内平均价格排序
        filtered = {
            k: v for k, v in groups.items() if len(v) >= min_group_size
        }
        return dict(sorted(filtered.items()))

    @staticmethod
    def _calc_price_score(price_fen: int, min_price: int, price_range: int) -> float:
        """价格分：价格越低分越高 (0-40)。"""
        if price_fen <= 0:
            return 0
        relative = (price_fen - min_price) / price_range  # 0 = cheapest, 1 = most expensive
        return round(40 * (1 - relative), 1)

    @staticmethod
    def _calc_spec_score(product: dict, min_speed: int, speed_range: int) -> float:
        """规格分：综合频率和容量 (0-40)。"""
        speed = product.get("speed_mhz", 0)
        capacity = product.get("capacity_gb", 0)
        kit = product.get("kit_count", 1)
        total_gb = capacity * kit
        cl = product.get("cl_latency")

        # Speed score (0-25)
        if speed_range > 0:
            speed_ratio = (speed - min_speed) / speed_range
        else:
            speed_ratio = 0
        speed_score = 25 * speed_ratio

        # Capacity score (0-10)
        cap_score = min(10, total_gb / 6.4)  # 64GB = 10

        # Latency bonus (0-5): lower CL = higher score
        cl_score = 0
        if cl and cl > 0:
            if cl <= 16:
                cl_score = 5
            elif cl <= 30:
                cl_score = 3
            elif cl <= 40:
                cl_score = 1

        return round(speed_score + cap_score + cl_score, 1)

    @staticmethod
    def _calc_trend_score(trend: TrendResult | None) -> float:
        """时机分 (0-20)：基于趋势信号。"""
        if trend is None:
            return 10  # 默认中性
        if trend.recommendation == "buy_now":
            return 20
        if trend.recommendation == "watch":
            return 15
        return 5  # wait
