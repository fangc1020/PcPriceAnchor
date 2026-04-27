"""分析层测试 — 趋势分析、性价比排名、报告生成。"""

import pytest

from price_monitor.analysis.trend import TrendAnalyzer, TrendResult
from price_monitor.analysis.value_rank import ValueRanker, ValueScore
from price_monitor.analysis.report import ReportGenerator


class TestTrendAnalyzer:
    def setup_method(self):
        self.analyzer = TrendAnalyzer()

    def test_empty_history(self):
        result = self.analyzer.analyze([])
        assert result.product_id == 0
        assert result.recommendation == "wait"

    def test_falling_trend(self):
        history = [
            {"product_id": 1, "avg_final_fen": 50000, "min_final_fen": 49000},
            {"product_id": 1, "avg_final_fen": 52000, "min_final_fen": 51000},
            {"product_id": 1, "avg_final_fen": 53000, "min_final_fen": 52000},
            {"product_id": 1, "avg_final_fen": 54000, "min_final_fen": 53000},
            {"product_id": 1, "avg_final_fen": 55000, "min_final_fen": 54000},
            {"product_id": 1, "avg_final_fen": 56000, "min_final_fen": 55000},
            {"product_id": 1, "avg_final_fen": 57000, "min_final_fen": 56000},
            {"product_id": 1, "avg_final_fen": 58000, "min_final_fen": 57000},
        ]
        result = self.analyzer.analyze(history)
        assert result.product_id == 1
        assert result.current_fen == 50000
        assert result.all_time_low_fen == 49000
        assert result.trend_signal in ("falling", "stable", "rising")

    def test_all_time_low_is_buy_now(self):
        """当前价格为历史最低时应推荐 buy_now。"""
        history = [
            {"product_id": 1, "avg_final_fen": 40000, "min_final_fen": 40000},
            {"product_id": 1, "avg_final_fen": 50000, "min_final_fen": 49000},
            {"product_id": 1, "avg_final_fen": 60000, "min_final_fen": 59000},
        ]
        result = self.analyzer.analyze(history)
        assert result.all_time_low_fen == 40000
        assert result.current_fen == result.all_time_low_fen
        assert result.recommendation == "buy_now"

    def test_rising_trend_should_wait(self):
        history = []
        # Simulate rising prices: recent prices are higher than older ones
        for i in range(30):
            history.append({
                "product_id": 1,
                "avg_final_fen": 55800 - i * 200,
                "min_final_fen": 54000 - i * 200,
            })
        result = self.analyzer.analyze(history)
        assert result.recommendation in ("wait", "watch")

    def test_trend_result_to_dict(self):
        result = TrendResult(
            product_id=1,
            current_fen=50000,
            all_time_low_fen=45000,
            avg_30d_fen=52000,
            drop_pct=-3.8,
            trend_signal="falling",
            recommendation="watch",
        )
        d = result.to_dict()
        assert d["product_id"] == 1
        assert d["recommendation"] == "watch"


class TestValueRanker:
    def test_rank_empty(self):
        assert ValueRanker.rank([], []) == []

    def test_rank_basic(self):
        products = [
            {"id": 1, "final_fen": 50000, "speed_mhz": 6000, "capacity_gb": 16, "kit_count": 2, "brand": "G.Skill", "model": "Trident", "memory_type": "DDR5", "title": "t1"},
            {"id": 2, "final_fen": 40000, "speed_mhz": 3200, "capacity_gb": 16, "kit_count": 2, "brand": "Kingston", "model": "Fury", "memory_type": "DDR4", "title": "t2"},
        ]
        trends = [
            TrendResult(product_id=1, current_fen=50000, all_time_low_fen=45000, avg_30d_fen=52000, drop_pct=-5.0, trend_signal="falling", recommendation="watch"),
            TrendResult(product_id=2, current_fen=40000, all_time_low_fen=40000, avg_30d_fen=42000, drop_pct=-3.0, trend_signal="stable", recommendation="buy_now"),
        ]
        results = ValueRanker.rank(products, trends)
        assert len(results) == 2
        assert results[0].score >= results[1].score  # sorted descending
        assert all(0 <= r.score <= 100 for r in results)

    def test_rank_missing_trend(self):
        products = [{"id": 1, "final_fen": 50000, "speed_mhz": 6000, "capacity_gb": 16, "kit_count": 2, "brand": "G.Skill", "model": "X", "memory_type": "DDR5", "title": "t1"}]
        results = ValueRanker.rank(products, [])
        assert len(results) == 1
        assert results[0].trend_score == 10  # neutral when no trend data

    def test_value_score_to_dict(self):
        s = ValueScore(
            product_id=1, score=85.0, price_score=35.0, spec_score=35.0, trend_score=15.0,
            brand="G.Skill", model="Trident", title="Test", capacity_gb=16, kit_count=2,
            speed_mhz=6000, cl_latency=30, memory_type="DDR5", form_factor="DIMM",
            final_fen=50000, recommendation="watch",
        )
        d = s.to_dict()
        assert d["score"] == 85.0
        assert d["brand"] == "G.Skill"
        assert d["form_factor"] == "DIMM"
        assert d["total_capacity"] == 32
        assert d["cl_tier"] == "CL28-30"
        assert "DDR5 DIMM 32GB 6000MHz CL28-30" in d["group_key"]

    def test_group_rank(self):
        products = [
            ValueScore(product_id=1, score=85.0, price_score=35.0, spec_score=35.0, trend_score=15.0,
                       brand="G.Skill", model="Trident", title="t1", capacity_gb=16, kit_count=2,
                       speed_mhz=6000, cl_latency=30, memory_type="DDR5", form_factor="DIMM",
                       final_fen=50000, recommendation="watch"),
            ValueScore(product_id=2, score=80.0, price_score=30.0, spec_score=35.0, trend_score=15.0,
                       brand="Corsair", model="Vengeance", title="t2", capacity_gb=16, kit_count=2,
                       speed_mhz=6000, cl_latency=28, memory_type="DDR5", form_factor="DIMM",
                       final_fen=45000, recommendation="watch"),
            # Different spec group
            ValueScore(product_id=3, score=75.0, price_score=25.0, spec_score=35.0, trend_score=15.0,
                       brand="Crucial", model="CT16G", title="t3", capacity_gb=16, kit_count=1,
                       speed_mhz=4800, cl_latency=42, memory_type="DDR5", form_factor="DIMM",
                       final_fen=30000, recommendation="wait"),
        ]
        grouped = ValueRanker.group_rank(products, min_group_size=2)
        # group of 2 (6000MHz CL28-30) should be present
        assert len(grouped) == 1
        group_key = "DDR5 DIMM 32GB 6000MHz CL28-30"
        assert group_key in grouped
        # Cheaper product (Corsair, 45000) should be first
        assert grouped[group_key][0].brand == "Corsair"
        assert grouped[group_key][1].brand == "G.Skill"
        # 1-product group (4800MHz CL42+) should be filtered out

    def test_group_rank_min_size(self):
        products = [
            ValueScore(product_id=1, score=85.0, price_score=35.0, spec_score=35.0, trend_score=15.0,
                       brand="G.Skill", model="Trident", title="t1", capacity_gb=16, kit_count=2,
                       speed_mhz=6000, cl_latency=30, memory_type="DDR5", form_factor="DIMM",
                       final_fen=50000, recommendation="watch"),
        ]
        grouped = ValueRanker.group_rank(products, min_group_size=3)
        assert len(grouped) == 0  # single product filtered out


def _make_test_group() -> dict:
    """Helper: create a single-group dict for report tests."""
    r = ValueScore(product_id=1, score=90.0, price_score=35.0, spec_score=35.0, trend_score=20.0,
                   brand="G.Skill", model="Trident", title="t1", capacity_gb=16, kit_count=2,
                   speed_mhz=6000, memory_type="DDR5", form_factor="DIMM", cl_latency=30,
                   final_fen=50000, recommendation="buy_now")
    return {r.group_key: [r]}


class TestReportGenerator:
    def test_to_json(self):
        grouped = _make_test_group()
        json_str = ReportGenerator.to_json(grouped)
        assert "buy_now" in json_str
        assert "G.Skill" in json_str
        assert "groups" in json_str

    def test_to_markdown(self):
        grouped = _make_test_group()
        md = ReportGenerator.to_markdown(grouped)
        assert "性价比排名" in md
        assert "G.Skill" in md
        assert "¥500.00" in md
        assert "CL30" in md

    def test_to_markdown_empty(self):
        md = ReportGenerator.to_markdown({})
        assert "暂无数据" in md

    def test_to_feishu_card(self):
        grouped = _make_test_group()
        card = ReportGenerator.to_feishu_card(grouped, top_n=3)
        assert "G.Skill" in card
        assert "建议购入" in card
