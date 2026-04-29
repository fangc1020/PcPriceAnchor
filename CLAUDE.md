# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

E-commerce hardware price monitoring system. MVP scope: RAM sticks only, full pipeline from JD (京东) crawling → cleaning → storage → trend analysis. See `Architecture_Plan.md` for the full design document.

**Tech stack**: Python 3.12, PostgreSQL 16 + TimescaleDB, SQLAlchemy 2.x (async), Pydantic v2, APScheduler, httpx, pydantic-settings, Plotly (charts), Jinja2 (HTML templates).

## Quick Start

```bash
source .venv/bin/activate

# Dry-run crawl (no DB needed)
python -m price_monitor.main once --dry-run --engine cdp --keyword "DDR5 内存条" --pages 3
# CDP engine requires Chrome remote debugging on port 9222: bash scripts/start_chrome.sh

# Run tests (248 passing, no DB needed)
pytest
pytest --cov=price_monitor --cov-report=term-missing

# Lint & type check
ruff check price_monitor/
mypy price_monitor/

# DB-dependent (Docker runs PostgreSQL 16 + TimescaleDB on localhost:5432)
docker compose up -d
alembic upgrade head
python -m price_monitor.main once --engine cdp --keyword "DDR5 内存条" --pages 3
python -m price_monitor.main analyze     # → reports/*.{md,json,xlsx,html} + auto-open browser
python -m price_monitor.main scheduler   # periodic crawl (every 120 min)
```

## Architecture: Layered Pipeline

```
采集层 (crawlers/) → 清洗层 (cleaners/) → 存储层 (storage/) → 分析层 (analysis/)
```

**Discipline**:
- One-way dependency: upper layers never import lower layers.
- Cross-layer communication only via Pydantic schemas (`RawProduct` → `CleanProduct`).
- Only `storage/` touches SQLAlchemy sessions. Analysis layer reads via Repository interfaces, never writes raw SQL.

### Layer Responsibilities

| Layer | Dir | Role |
|---|---|---|
| Crawlers | `crawlers/` | Per-platform scrapers. `BaseCrawler` defines `search()`, `fetch_detail()`, `fetch_price()`. JD has 4 engines + 1 detail helper: `cdp_crawler.py` (**default, working** — connects real Chrome via CDP), `search.py` (httpx, blocked), `playwright_search.py` (blocked), `stealth_crawler.py` (blocked), `detail.py` (legacy detail fetcher). See `docs/cdp_crawler_solution.md`. |
| Cleaners | `cleaners/` | `RamCleaner`: regex parses capacity/frequency/timing/die from titles. Die: granular model-level (Samsung B-die, Hynix A-die/M-die) when detectable, manufacturer-only otherwise (Samsung, SK Hynix, Micron, Nanya, CXMT). `Normalizer`: brand aliases from `config/brand_aliases.yml`. Products with `parse_confidence < 0.8` discarded. |
| Storage | `storage/` | Repository pattern. `ProductRepository.upsert_product()` is idempotent. `PriceRepository.record_price()` deduplicates by `raw_hash` **within same day only** (cross-day same price still records a new tick). `get_price_history_batch()` for bulk queries. |
| Analysis | `analysis/` | `TrendAnalyzer` (moving average, all-time low), `ValueRanker` (price/spec/trend composite score 0-100, **grouped by spec**: memory_type → form_factor → capacity → speed → CL tier), `ReportGenerator` (JSON/Markdown/Excel/HTML+Plotly/Feishu card). HTML template: `templates/report.html`. |

### Database

- `platforms` — platform catalog (jd, tmall, pdd)
- `products` — cross-platform product master, unique on `(platform_id, platform_sku_id)`
- `ram_specs` — 1:1 with products, stores parsed RAM specs (capacity, speed, timings, die type: granular model-level e.g. Samsung B-die/Hynix A-die or manufacturer-only, DDR4/DDR5)
- `price_ticks` — TimescaleDB hypertable partitioned by day; has continuous aggregate `price_hourly` (timezone: Asia/Shanghai, auto-refresh every 30 min via policy)
- Migrations: `001_initial_schema.py`, `002_fix_timezone_and_refresh_policy.py`
- All prices in **fen** (分) to avoid floating-point errors

### Key Design Decisions

- **Brand resolution**: Static YAML (`config/brand_aliases.yml`), loaded once at startup — brands are stable business knowledge, no DB I/O needed.
- **Anti-scraping**: JD CDP crawler is working (2026-04-27 verified). Key findings and rate-limit thresholds documented in `docs/cdp_crawler_solution.md`. 3-page limit per session, 4-8s inter-page sleep, circuit-breaker on detection. **Always use `--dry-run --pages 1` for dev/debug.**
- **Scheduler upgrade path**: APScheduler for MVP (≤ 3 platforms, < 100K items/day). Migrate to Celery + Redis when thresholds exceeded. `CrawlTask.run()` interface is designed idempotent so only the scheduler layer changes.
- **RAM spec parsing**: Regex + keyword matching from product titles. LLM annotation is for cold-start seed data only (one-time batch of ~500 samples to train regex patterns), not in the main pipeline.
- **Alerts**: Feishu (飞书) webhook — simple POST, rich text cards, no SDK dependency. Webhook URL in `.env`.

### Status & Next Steps

MVP 全链路已于 2026-04-27 验证通过。249 tests passing。2026-04-29 完成报告系统大改。GitHub: https://github.com/fangc1020/PcPriceAnchor

**2026-04-29 更新**：
- 数据不足（<7天）降级为"📊积累中 X/7天"，不再误报买入
- CL 时序覆盖率 40% → 78%：正则同时匹配 `C30`/`CL30` 两种写法，回填 126 条
- 装机视角过滤：排除 OEM 裸条/笔记本内存/工控/服务器/拆机件，332 → 100 条有价值商品
- 首发延迟 FWL（CL×2000/频率 ns）+ 性能档位标签（旗舰/高性能/主流/入门）
- 表格新增列：类型(DIMM/SO-DIMM)、FWL、性能档位、¥/GB、品牌分档
- 总览图新增规格组筛选器 + Y 轴自适应按钮
- 品牌分档：`config/brand_tiers.yml`（一线/国产/其他）
- 笔记本关键词识别：`笔记本/笔电/notebook/laptop/天选/枪神` → SO-DIMM

**日常操作**：
- 爬取前确认 Chrome CDP 在 9222 端口、Docker PostgreSQL 在运行
- `python -m price_monitor.main once --engine cdp --keyword "DDR5 内存条" --pages 3` 爬取
- `python -m price_monitor.main analyze` 分析 + 生成 HTML 报告 + 自动打开浏览器
- 连续聚合 `price_hourly` 每 30 分钟自动刷新，如需立即看结果手动 `docker exec -e PGPASSWORD=password price_monitor_db psql -U user -d price_monitor -c "CALL refresh_continuous_aggregate('price_hourly', NULL, NULL);"`

**当前数据状态**：仅 2-3 天价格历史（75 款有效商品，9 个规格组），趋势分析全显示"积累中"。持续积累到 7 天以上才可靠。需定期 `python -m price_monitor.main once` 爬取积累数据。

**已知问题**：
- CPU 型号（如 9800X3D）可能被误识别为内存频率（威刚标题"适配9800X3D" → 9800MHz）
- 部分消费品牌的品牌名解析不干净（如"金百达16G/32GB/64G"应只取"金百达"）
- DB 时区已切为 Asia/Shanghai，但 `recorded_at` 默认值为 `func.now()` 依赖 session 时区
- 约 22% 商品 CL 仍未知（FURY 基础款等标题不标时序），需爬详情页参数表补全

**多平台扩展**：淘宝/天猫（需滑块）、拼多多（App 内嵌浏览器）。
