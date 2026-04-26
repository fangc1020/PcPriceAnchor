# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

E-commerce hardware price monitoring system. MVP scope: RAM sticks only, full pipeline from JD (京东) crawling → cleaning → storage → trend analysis. See `Architecture_Plan.md` for the full design document.

**Tech stack**: Python 3.12, PostgreSQL 16 + TimescaleDB, SQLAlchemy 2.x (async), Pydantic v2, APScheduler, httpx, pydantic-settings.

## Common Commands

```bash
# Install dependencies
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run a single test file
pytest tests/cleaners/test_ram_cleaner.py

# Run single crawl (dry-run, no DB needed)
python -m price_monitor.main once

# Run analysis + report (requires DB)
python -m price_monitor.main analyze

# Start scheduler (requires DB)
python -m price_monitor.main

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Run a single test file
pytest tests/crawlers/test_jd_search.py

# Run with coverage
pytest --cov=price_monitor --cov-report=term-missing

# Lint & type check
ruff check price_monitor/
mypy price_monitor/

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Start the scheduler (MVP entry point)
python -m price_monitor.main
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
| Crawlers | `crawlers/` | Per-platform scrapers. `BaseCrawler` defines `search()`, `fetch_detail()`, `fetch_price()`. JD uses `httpx` for search listings + price API (`p.3.cn/prices/mgets`), Playwright as fallback only. |
| Cleaners | `cleaners/` | Normalize raw data. `RamCleaner` parses capacity/frequency/timing/die from titles via regex. `Normalizer` handles brand aliases (loaded from `config/brand_aliases.yml`). Products with `parse_confidence < 0.8` are discarded. |
| Storage | `storage/` | Repository pattern. `ProductRepository.upsert_product()` is idempotent. `PriceRepository.record_price()` deduplicates by `raw_hash` (SHA-256). |
| Analysis | `analysis/` | `TrendAnalyzer` (moving average, all-time low), `ValueRanker` (price/spec/trend composite score 0-100), `ReportGenerator` (JSON/Markdown output). |

### Database

- `platforms` — platform catalog (jd, tmall, pdd)
- `products` — cross-platform product master, unique on `(platform_id, platform_sku_id)`
- `ram_specs` — 1:1 with products, stores parsed RAM specs (capacity, speed, timings, die type, DDR4/DDR5)
- `price_ticks` — TimescaleDB hypertable partitioned by day; has continuous aggregate `price_hourly`
- All prices in **fen** (分) to avoid floating-point errors

### Key Design Decisions

- **Brand resolution**: Static YAML (`config/brand_aliases.yml`), loaded once at startup — brands are stable business knowledge, no DB I/O needed.
- **Anti-scraping**: Anonymous requests for public prices; cookie-based auth (`pt_key`/`pt_pin`) only needed for promotional/coupon prices. Rate limit: < 30 req/min, random sleep 1-3s, User-Agent rotation.
- **Scheduler upgrade path**: APScheduler for MVP (≤ 3 platforms, < 100K items/day). Migrate to Celery + Redis when thresholds exceeded. `CrawlTask.run()` interface is designed idempotent so only the scheduler layer changes.
- **RAM spec parsing**: Regex + keyword matching from product titles. LLM annotation is for cold-start seed data only (one-time batch of ~500 samples to train regex patterns), not in the main pipeline.
- **Alerts**: Feishu (飞书) webhook — simple POST, rich text cards, no SDK dependency. Webhook URL in `.env`.

### MVP Implementation Phases

| Phase | Goal | Acceptance Criteria |
|---|---|---|
| P0 | DB schema + Alembic | `alembic upgrade head` succeeds, hypertable created |
| P1 | JD search crawl | Single run returns ≥50 RawProduct, no missing fields |
| P2 | RamCleaner parsing | 100-sample test set, confidence ≥0.8 on >85% |
| P3 | Storage write + dedup | Re-runs produce no duplicate ticks, upsert is idempotent |
| P4 | Trend query + report | Output 30-day price curve + buy signal for a given product_id |
