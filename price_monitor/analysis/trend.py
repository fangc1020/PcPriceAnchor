"""价格趋势分析器 — 移动均值、历史低点、推荐信号。"""

from dataclasses import dataclass


@dataclass
class TrendResult:
    product_id: int
    current_fen: int
    all_time_low_fen: int
    avg_30d_fen: int
    drop_pct: float  # 相比 30 天均价的降幅百分比（负值表示低于均价）
    trend_signal: str  # 'falling' | 'stable' | 'rising'
    recommendation: str  # 'buy_now' | 'wait' | 'watch' | 'accumulating'
    data_days: int = 0  # 实际数据跨度的天数

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "current_fen": self.current_fen,
            "all_time_low_fen": self.all_time_low_fen,
            "avg_30d_fen": self.avg_30d_fen,
            "drop_pct": round(self.drop_pct, 1),
            "trend_signal": self.trend_signal,
            "recommendation": self.recommendation,
            "data_days": self.data_days,
        }


class TrendAnalyzer:
    """分析价格趋势，生成推荐信号。"""

    WINDOW_RECENT_DAYS = 7
    WINDOW_OLDER_DAYS = 21

    TREND_THRESHOLD_PCT = 5.0  # 降幅超过 5% 视为下降趋势

    def analyze(self, price_history: list[dict]) -> TrendResult:
        """分析价格历史数据，输出趋势结果。

        Args:
            price_history: price_hourly 记录列表，需含 product_id, avg_final_fen, min_final_fen, bucket 字段。
        """
        if not price_history:
            return self._empty_result(0)

        product_id = price_history[0].get("product_id", 0)

        # Count distinct days from bucket dates
        distinct_dates = set()
        for p in price_history:
            bucket = p.get("bucket", "")
            if bucket:
                distinct_dates.add(bucket[:10])
        data_days = len(distinct_dates)

        # Use avg_final_fen for trend, min_final_fen for all-time low
        avg_prices = [
            p.get("avg_final_fen", 0) for p in price_history if p.get("avg_final_fen")
        ]
        min_prices = [
            p.get("min_final_fen", 99999999) for p in price_history if p.get("min_final_fen") is not None
        ]
        if not avg_prices:
            return self._empty_result(product_id)

        current_fen = avg_prices[0]  # 最新价格（按时间降序排列的第一个）
        all_time_low_fen = min(min_prices) if min_prices else min(avg_prices)
        avg_30d_fen = sum(avg_prices) // len(avg_prices)

        # 趋势判断：近 7 天 vs 前 21 天
        recent = avg_prices[:min(self.WINDOW_RECENT_DAYS, len(avg_prices))]
        older = avg_prices[self.WINDOW_RECENT_DAYS:min(self.WINDOW_RECENT_DAYS + self.WINDOW_OLDER_DAYS, len(avg_prices))]

        if older and recent:
            recent_avg = sum(recent) // len(recent)
            older_avg = sum(older) // len(older)
            if older_avg > 0:
                drop_pct = float((recent_avg - older_avg) / older_avg * 100)
            else:
                drop_pct = 0.0
        else:
            drop_pct = 0.0

        trend_signal = self._classify_trend(drop_pct)
        recommendation = self._make_recommendation(
            current_fen, all_time_low_fen, avg_30d_fen, trend_signal, data_days
        )

        return TrendResult(
            product_id=product_id,
            current_fen=current_fen,
            all_time_low_fen=all_time_low_fen,
            avg_30d_fen=avg_30d_fen,
            drop_pct=drop_pct,
            trend_signal=trend_signal,
            recommendation=recommendation,
            data_days=data_days,
        )

    def _classify_trend(self, drop_pct: float) -> str:
        if drop_pct < -self.TREND_THRESHOLD_PCT:
            return "falling"
        elif drop_pct > self.TREND_THRESHOLD_PCT:
            return "rising"
        return "stable"

    def _make_recommendation(
        self,
        current_fen: int,
        all_time_low_fen: int,
        avg_30d_fen: int,
        trend_signal: str,
        data_days: int = 0,
    ) -> str:
        if current_fen <= all_time_low_fen:
            if data_days < self.MIN_DATA_DAYS:
                return "accumulating"
            return "buy_now"
        if trend_signal == "falling":
            return "watch"
        if current_fen < avg_30d_fen:
            return "watch"
        return "wait"

    MIN_DATA_DAYS = 7  # 数据不足时降级建议

    @staticmethod
    def _empty_result(product_id: int) -> TrendResult:
        return TrendResult(
            product_id=product_id,
            current_fen=0,
            all_time_low_fen=0,
            avg_30d_fen=0,
            drop_pct=0.0,
            trend_signal="stable",
            recommendation="wait",
            data_days=0,
        )
