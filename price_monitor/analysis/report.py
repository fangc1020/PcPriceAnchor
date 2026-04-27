"""报告生成器 — JSON、Markdown、Excel 格式输出，支持按规格分组。"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from price_monitor.analysis.value_rank import ValueScore


class ReportGenerator:
    @staticmethod
    def to_json(grouped: dict[str, list[ValueScore]]) -> str:
        data = {
            "generated_at": datetime.now().isoformat(),
            "groups": {
                key: [r.to_dict() for r in rankings]
                for key, rankings in grouped.items()
            },
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def to_markdown(grouped: dict[str, list[ValueScore]]) -> str:
        if not grouped:
            return "# 内存条性价比排名\n\n暂无数据。\n"

        lines = [
            f"# 内存条性价比排名（同规格对比）",
            f"",
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"> 共 {len(grouped)} 个规格组",
            f"",
        ]

        total_products = 0
        for group_key, rankings in grouped.items():
            total_products += len(rankings)
            lines.append(f"## {group_key}")
            lines.append(f"")
            lines.append(f"| 品牌 | 型号 | 颗粒 | 时序 | 到手价 | 建议 |")
            lines.append(f"|------|------|------|------|--------|------|")

            for r in rankings:
                price_yuan = f"¥{r.final_fen / 100:.2f}"
                cl_str = f"CL{r.cl_latency}" if r.cl_latency else "-"
                die_str = r.die_type or "-"
                rec_emoji = {"buy_now": "🔥购入", "watch": "👀观望", "wait": "⏸等待"}.get(
                    r.recommendation, "?"
                )
                lines.append(
                    f"| {r.brand} | {r.model[:30]} | {die_str} | {cl_str} | {price_yuan} | {rec_emoji} |"
                )
            lines.append(f"")

        lines.append(f"> 共 {total_products} 款商品，{len(grouped)} 个规格组")
        return "\n".join(lines)

    @staticmethod
    def to_excel(grouped: dict[str, list[ValueScore]], filepath: Path) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "内存性价比排名"

        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=11)
        group_fill = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"),
        )
        data_font = Font(name="微软雅黑", size=10)
        rec_labels = {"buy_now": "🔥建议购入", "watch": "👀观望", "wait": "⏸等待"}

        headers = ["规格", "品牌", "型号", "颗粒", "时序", "到手价(¥)", "建议"]
        col_widths = [32, 14, 36, 12, 10, 14, 14]

        # Write headers
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        # Flatten all groups into rows
        row = 2
        for group_key, rankings in grouped.items():
            for r in rankings:
                cl_str = f"CL{r.cl_latency}" if r.cl_latency else "-"
                die_str = r.die_type or "-"
                price_yuan = round(r.final_fen / 100, 2)
                values = [
                    group_key,
                    r.brand,
                    r.model[:60],
                    die_str,
                    cl_str,
                    price_yuan,
                    rec_labels.get(r.recommendation, "⏸等待"),
                ]

                for col, val in enumerate(values, 1):
                    cell = ws.cell(row=row, column=col, value=val)
                    cell.font = data_font
                    cell.border = thin_border
                    if col in (5, 6, 7):
                        cell.alignment = Alignment(horizontal="center", vertical="center")

                row += 1

        # Column widths
        for col, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(col)].width = w

        # Freeze header
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:G{row - 1}"

        wb.save(filepath)

    @staticmethod
    def to_feishu_card(grouped: dict[str, list[ValueScore]], top_n: int = 3) -> str:
        """生成飞书富文本卡片 JSON。每个规格组展示 TOP N。"""
        if not grouped:
            return json.dumps({"msg_type": "text", "content": {"text": "暂无性价比数据"}})

        elements = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**🛒 内存条性价比速报（同规格对比）**"},
            },
            {"tag": "hr"},
        ]

        for group_key, rankings in grouped.items():
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**▸ {group_key}**"},
            })

            for r in rankings[:top_n]:
                price_yuan = f"¥{r.final_fen / 100:.2f}"
                cl_str = f"CL{r.cl_latency}" if r.cl_latency else ""
                die_str = f" {r.die_type}" if r.die_type else ""
                rec = {"buy_now": "🔥建议购入", "watch": "👀观望", "wait": "⏸等待"}.get(
                    r.recommendation, ""
                )
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"{r.brand} {r.model}{die_str} | {cl_str} | {price_yuan} | {rec}",
                    },
                })

            elements.append({"tag": "hr"})

        total = sum(len(v) for v in grouped.values())
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"共 {len(grouped)} 个规格组、{total} 款商品",
            },
        })

        return json.dumps(
            {"msg_type": "interactive", "card": {"elements": elements}},
            ensure_ascii=False,
        )
