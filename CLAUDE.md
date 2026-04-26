# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

E-commerce hardware price monitoring system. MVP scope: RAM sticks only, full pipeline from JD (京东) crawling → cleaning → storage → trend analysis. See `Architecture_Plan.md` for the full design document.

**Tech stack**: Python 3.12, PostgreSQL 16 + TimescaleDB, SQLAlchemy 2.x (async), Pydantic v2, APScheduler, httpx, pydantic-settings.

## Quick Start

```bash
source .venv/bin/activate

# Dry-run crawl (no DB needed) — default engine: stealth
python -m price_monitor.main once --dry-run --keyword "DDR5 内存条" --pages 1

# Choose engine
python -m price_monitor.main once --dry-run --engine httpx       # pure HTTP (blocked)
python -m price_monitor.main once --dry-run --engine playwright  # Playwright (blocked)
python -m price_monitor.main once --dry-run --engine stealth     # stealth + cookie persist

# Run tests (245 passing, no DB needed)
pytest

# With coverage
pytest --cov=price_monitor --cov-report=term-missing

# Lint & type check
ruff check price_monitor/
mypy price_monitor/

# DB-dependent (needs PostgreSQL + TimescaleDB first)
alembic upgrade head
python -m price_monitor.main analyze
python -m price_monitor.main scheduler
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
| Crawlers | `crawlers/` | Per-platform scrapers. `BaseCrawler` defines `search()`, `fetch_detail()`, `fetch_price()`. JD has 3 engines: `search.py` (httpx), `playwright_search.py` (Playwright), `stealth_crawler.py` (stealth + cookie persist). **⚠️ P1 blocked: JD anti-scraping** — see `docs/jd_anti_scraping_blocker.md`. |
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
- **Anti-scraping (current blocker)**: JD `search.jd.com` redirects to passport login for all automated browsers, including playwright-stealth. `p.3.cn` price API resolves to private IPs (RFC 1918). `api.m.jd.com` returns encrypted price data. `item.jd.com` accessible without login but shows ¥0. Full analysis in `docs/jd_anti_scraping_blocker.md`. Cookie persistence at `.jd_cookies.json` (gitignored).
- **Rate limiting**: < 30 req/min, random sleep 1-3s, User-Agent rotation.
- **Scheduler upgrade path**: APScheduler for MVP (≤ 3 platforms, < 100K items/day). Migrate to Celery + Redis when thresholds exceeded. `CrawlTask.run()` interface is designed idempotent so only the scheduler layer changes.
- **RAM spec parsing**: Regex + keyword matching from product titles. LLM annotation is for cold-start seed data only (one-time batch of ~500 samples to train regex patterns), not in the main pipeline.
- **Alerts**: Feishu (飞书) webhook — simple POST, rich text cards, no SDK dependency. Webhook URL in `.env`.

### Implementation Status

| Phase | Goal | Status |
|---|---|---|
| P0 | DB schema + Alembic | ✅ Code done. Needs PostgreSQL + TimescaleDB to verify |
| P1 | JD search crawl | ❌ **Blocked** — JD anti-scraping (`docs/jd_anti_scraping_blocker.md`) |
| P2 | RamCleaner parsing | ✅ 245 tests passing, 100% confidence ≥ 0.8 |
| P3 | Storage write + dedup | ✅ Code done. Needs DB to verify |
| P4 | Trend query + report | ✅ Code done. Needs DB + price data to verify |

**Next steps**: (1) Resolve JD anti-scraping to unblock P1. (2) Set up PostgreSQL + TimescaleDB (Docker recommended) to verify P0/P3/P4.
