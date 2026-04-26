"""报告生成器 — JSON 和 Markdown 格式输出。"""

import json
from datetime import datetime
from typing import List

from price_monitor.analysis.value_rank import ValueScore


class ReportGenerator:
    @staticmethod
    def to_json(rankings: list[ValueScore]) -> str:
        data = {
            "generated_at": datetime.now().isoformat(),
            "total": len(rankings),
            "rankings": [r.to_dict() for r in rankings],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def to_markdown(rankings: list[ValueScore]) -> str:
        if not rankings:
            return "# 性价比排名\n\n暂无数据。\n"

        lines = [
            f"# 内存条性价比排名",
            f"",
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"> 共 {len(rankings)} 款",
            f"",
            f"| 排名 | 型号 | 规格 | 价格 | 综合分 | 建议 |",
            f"|------|------|------|------|--------|------|",
        ]

        for i, r in enumerate(rankings, 1):
            spec = f"{r.memory_type} {r.speed_mhz}MHz {r.capacity_gb * r.kit_count}GB"
            if r.kit_count > 1:
                spec += f" ({r.capacity_gb}G×{r.kit_count})"
            price_yuan = f"¥{r.final_fen / 100:.2f}"
            rec_emoji = {"buy_now": "🔥购入", "watch": "👀观望", "wait": "⏸等待"}.get(
                r.recommendation, "?"
            )
            lines.append(
                f"| {i} | {r.brand} {r.model[:30]} | {spec} | {price_yuan} | {r.score:.0f} | {rec_emoji} |"
            )

        return "\n".join(lines)

    @staticmethod
    def to_feishu_card(rankings: list[ValueScore], top_n: int = 5) -> str:
        """生成飞书富文本卡片 JSON。"""
        if not rankings:
            return json.dumps({"msg_type": "text", "content": {"text": "暂无性价比数据"}})

        top = rankings[:top_n]
        elements = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**🛒 内存条性价比速报**"},
            },
            {"tag": "hr"},
        ]

        for i, r in enumerate(top, 1):
            price_yuan = f"¥{r.final_fen / 100:.2f}"
            spec = f"{r.memory_type} {r.speed_mhz}MHz {r.capacity_gb * r.kit_count}GB"
            rec = {"buy_now": "🔥建议购入", "watch": "👀观望", "wait": "⏸等待"}.get(r.recommendation, "")
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{i}. {r.brand} {r.model}**\n{spec} | {price_yuan} | {rec}",
                },
            })

        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"共 {len(rankings)} 款商品，以上为 TOP {top_n}",
            },
        })

        return json.dumps(
            {"msg_type": "interactive", "card": {"elements": elements}},
            ensure_ascii=False,
        )
