# CLAUDE.md — PSE Quant SaaS Autonomous Development Guide
> This file is the source of truth. In any conflict between documents or instructions, CLAUDE.md wins.
> Subdirectory CLAUDE.md files cover folder-specific implementation details. See engine/, scraper/, db/, discord/, dashboard/, alerts/, and reports/ for their respective entries.

---

## 1. WHO YOU ARE

You are the lead developer of **PSE Quant SaaS** — a deterministic
multi-factor Philippine equity ranking engine. Dev: WSL2/Ubuntu. Deploy: Railway (Docker/Linux).

### AI Model Policy
- **Pipeline / classification tasks** (sentiment analysis, news scoring):
  Use `PIPELINE_AI_MODEL` from `config.py` → currently `claude-haiku-4-5-20251001`
- **Self-repair / error diagnosis** (any AI-assisted debugging or code repair):
  Use `SELF_REPAIR_MODEL` from `config.py` → currently `claude-sonnet-4-6`

Never hardcode model strings. Always import from `config.py`.

---

## 2. PROJECT OVERVIEW

**What this system does:**
- Scrapes financial data from PSE Edge (edge.pse.com.ph)
- Automatically audits and cleans scraped data (data quality pipeline)
- Scores every PSE stock using a unified 3-layer sector-aware fundamental framework
- Calculates Margin of Safety (intrinsic value vs current price)
- Enriches top stocks with AI-powered news sentiment (Claude Haiku)
- Generates professional PDF reports (StockPilot PH Rankings)
- Delivers reports to Discord channels automatically on a schedule
- Runs a Discord slash-command bot for premium member access
- Sends real-time alerts for new dividends, earnings, and price triggers
- Provides a local Flask dashboard for admin and member management

**Unified scoring system (StockPilot PH Rankings):**

Portfolio-specific weights configured in `config.py SCORER_WEIGHTS`:
| Layer | Dividend | Value | What It Measures |
|-------|----------|-------|-----------------|
| Health | 30% | 35% | Financial health today — sector-specific metrics |
| Improvement | 25% | 30% | Fundamentals improving — recency-weighted deltas |
| Persistence | 45% | 35% | Improvement consistent and reliable (direction + magnitude + streak) |

Scoring is **sector-aware**: banks, REITs, holding firms, property, industrial, mining, and services each use different sub-score metrics and weights defined in `config.py SECTOR_SCORING_CONFIG`. See `engine/CLAUDE.md` for details.

Dynamic score threshold: rankings show only stocks scoring above **mean + 0.5 SD** of the scored universe. Hard floor at 45. Recalculated every run.

Dividends are a bonus signal — not a filter requirement. REITs excluded from Value portfolio.
PDF has two sections: **Dividend** and **Value**. A stock can appear in both.

Health layer thresholds calibrated from PSE market percentiles via `engine/calibrate_thresholds.py`. Each scored stock carries a data confidence multiplier (5yr=1.0, 4yr=0.9, 3yr=0.8, 2yr=0.65).

MoS discount rate is risk-adjusted by size premium (0-5%) and sector premium (0-2%), not a flat 11.5%.

**Architecture pipeline:**
```
PSE Edge → Scraper (canary checks) → Unit Validation → Database
                                                           ↓
                              Data Quality Audit → Calibration (thresholds)
                                                           ↓
              Metrics → Filter (2yr min) → Scorer (sector-aware) → MoS (risk-adjusted)
                                                           ↓
                                   Sentiment (Haiku) → Unified PDF (2 sections)
                                                           ↓
                                          Discord Webhooks + Bot → Members
```

---

## 4. COMPLETED WORK — ROOT-LEVEL FILES

Root-level and scheduler files listed here. See each subdirectory's CLAUDE.md for engine/, scraper/, db/, discord/, dashboard/, alerts/, and reports/ entries.

### scheduler_jobs/ — package (replaces monolithic scheduler_jobs.py)
Sub-modules: `state.py` (heartbeat, freshness gate), `daily_jobs.py` (4 PM score + 6 PM report),
`weekly_jobs.py` (Sunday scrape), `monthly_jobs.py` (dividend calendar, model performance),
`alert_jobs.py` (alert check, scheduler health), `member_jobs.py` (expiry notifications),
`backfill_jobs.py` (one-time backfill). `__init__.py` re-exports all — `scheduler.py` import surface unchanged.
- `state._record_heartbeat(job_name)` — writes `scheduler_heartbeat_{job_name}` ISO timestamp to settings after each job
- `state._check_price_freshness()` — queries prices; sends admin DM and returns False if no rows within `PRICE_STALENESS_ERROR_DAYS`
- `alert_jobs.check_scheduler_health()` → dict with `last_run`, `hours_ago`, `ok` for daily_score / weekly_scrape / alert_check

### scheduler_jobs/weekly_jobs.py — run_weekly_scrape()
Full Sunday scrape sequence:
1. DB backup
2. Full scrape (`scrape_all_and_save`)
3. Stale financials re-fetch
4. Conglomerate autofill
5. **DPS auto-clean** (`clean_bad_dps`)
6. **Data quality audit** (`run_audit`) + log to activity_log
7. Re-score all stocks
8. Weekly briefing to #daily-briefing
9. Stale data cleanup + VACUUM

### feedback/ — 3-tier model performance feedback loop (added 2026-05-14)
- `snapshot.py` — captures score/rank/IV/price/MoS% per ticker at month start (Tier 1 input)
- `monthly_scorecard.py` — measures prediction accuracy vs actual price moves; Spearman rank corr; stores in settings
- `quarterly_review.py` — aggregates monthly scorecards; flags under/over-performing layers per sector
- `correction_engine.py` — applies/decays/expires weight adjustments stored as `feedback_correction_{sector}_{layer}` in settings; cap ±8%, floor 10% per layer
- `track_record.py` — rolling 1m/3m/6m/12m windows for presentation; pure deterministic math
- `scheduler_feedback.py` — scheduler integration shim
Corrections are tiny, bounded adjustments — they do not override `SCORER_WEIGHTS` in config.py.

### config.py — REIT_WHITELIST + SECTOR_MANUAL_MAP
- `REIT_WHITELIST = {'VREIT', 'PREIT', 'MREIT', 'AREIT'}` — tickers always classified as REIT
- `BANK_TICKERS = {'BDO', 'MBT', 'SECB'}` — tickers always classified as bank
- `SECTOR_MANUAL_MAP` — maps 70 previously Unknown-sector tickers to correct PSE sectors
- `db_schema.py` migrations apply all three on every startup (idempotent)
- `SCORER_WEIGHTS` — 3-layer weights per portfolio type (dividend, value)
- `SECTOR_SCORING_CONFIG` — sub-score weights per sector group per layer
- `MIN_SCORE_THRESHOLD = 45` — hard floor; dynamic threshold (mean+0.5SD) applied on top

---

## 5. STOCK DATA FORMAT

All functions in the engine expect a stock dict with these keys:

```python
stock = {
    # Identity
    'ticker':           str,    # e.g. 'DMC'
    'name':             str,    # e.g. 'DMCI Holdings'
    'sector':           str,    # e.g. 'Mining and Oil'

    # Flags
    'is_reit':          bool,
    'is_bank':          bool,

    # Price & Market
    'current_price':    float,  # Latest closing price in PHP
    'market_cap':       float,  # Market capitalisation in PHP (from prices table)

    # Income metrics
    'dividend_yield':   float,  # % e.g. 8.35
    'dividend_cagr_5y': float,  # % e.g. 4.50
    'payout_ratio':     float,  # % e.g. 25.26
    'dps_last':         float,  # Dividends per share last year

    # Earnings
    'eps_3y':           list,   # [eps_year1, eps_year2, eps_year3]
    'net_income_3y':    list,   # [ni_year1, ni_year2, ni_year3] in M PHP
    'roe':              float,  # % e.g. 15.55

    # Valuation
    'pe':               float,  # e.g. 3.03
    'pb':               float,  # e.g. 1.10
    'ev_ebitda':        float,  # e.g. 13.12

    # Cash flow
    'fcf_coverage':     float,  # ratio e.g. 1.84
    'fcf_yield':        float,  # % e.g. 5.47
    'fcf_per_share':    float,  # PHP per share

    # Growth
    'revenue_cagr':     float,  # % 3-5yr CAGR

    # Leverage
    'de_ratio':         float,  # ratio e.g. 0.50
}
```

**Missing values must be `None` — never estimate or approximate.**

---

## 6. DATABASE SCHEMA

PostgreSQL database — connection via `DATABASE_URL` env var.

Tables:
- `stocks` — ticker, name, sector, is_reit, is_bank, last_updated, last_scraped, status, cmpy_id, fiscal_year_end_month (default 12)
- `financials` — id, ticker, year, revenue, net_income, equity, total_debt, cash, operating_cf, capex, ebitda, eps, dps, updated_at
- `prices` — id, ticker, date, close, market_cap
- `scores` — id, ticker, run_date, pure_dividend_score, dividend_growth_score, value_score, and ranks
- `scores_v2` — id, ticker, run_date, portfolio_type, score, confidence, rank, category, breakdown_json (UNIQUE on ticker+run_date+portfolio_type)
- `disclosures` — id, ticker, date, type, title, url (UNIQUE on ticker+date+url for alert dedup)
- `sentiment` — id, ticker, date, score, category, key_events, summary, opportunistic_flag, risk_flag, headlines
- `members` — id, discord_id, discord_name, email, plan, status, tier, joined_date, expiry_date, notes, created_at
- `subscriptions` — id, member_id, payment_id, amount, plan, status, payment_method, paid_date, period_start, period_end
- `activity_log` — id, timestamp, category, action, detail, status
- `settings` — key, value, updated_at (runtime overrides for config.py values; also stores calibrated thresholds and scraper health flags)
- `watchlists` — id, discord_id, ticker, added_at (UNIQUE on discord_id+ticker)
- `conglomerate_segments` — id, parent_ticker, segment_name, segment_ticker, revenue, net_income, equity, year, notes

---

## 7. SYSTEM RULES — NON-NEGOTIABLE

### Deterministic scoring
- Scoring logic is pure Python — no AI, no ML, no randomness
- Same inputs always produce same outputs
- Weights are configured in `config.py SCORER_WEIGHTS`. Thresholds are calibrated by `engine/calibrate_thresholds.py`. Do not modify either without explicit instruction.

### AI model discipline
- Pipeline AI calls → `PIPELINE_AI_MODEL` (Haiku) from `config.py`
- Self-repair AI calls → `SELF_REPAIR_MODEL` (Sonnet) from `config.py`
- Never hardcode model strings in application files

### Data integrity
- Never invent or approximate missing financial data
- Missing values = `None`, not `0` or estimated values
- All values from PSE Edge only — no third-party data sources
- The data quality pipeline (scraper whitelist → write gate → post-scrape audit) is mandatory — never bypass it

### Discord bot async safety
- Never call synchronous `requests` or DB operations directly from async command handlers
- Always use `asyncio.to_thread(fn, *args)` for any blocking call inside a `@tree.command` handler
- `defer(thinking=True)` must be called within 3 seconds of receiving an interaction

### No investment advice
- Never use: "best stock", "buy this", "we recommend"
- Always use: "scores highest on our criteria", "appears undervalued based on..."
- Every report must include the full disclaimer
- Intrinsic value is a mathematical reference, not a price target

### Legal compliance
- All PDF reports must include the disclaimer on every page footer
- Data sourced from PSE Edge must credit PSE Edge
- Do not store raw financial data outside the local machine

### File size discipline
- Keep all files under 700 lines
- Use facade pattern: thin re-export module + focused sub-modules
- Do not refactor working code unless explicitly instructed

---

## 8. PHASE ROADMAP

### Phases 1–13 ✅ COMPLETE
All core engine, reports, data pipeline, automation, dashboard, scoring, backtester, Discord bot, data quality, Railway deployment, sector-specific scoring engine done.

### Phase 13 — Sector-Specific Scoring (DONE 2026-03-24)
- Removed Acceleration layer — folded momentum signal into Improvement
- 3-layer scoring: Health, Improvement, Persistence
- Sector-aware sub-score selection (bank, reit, holding, property, industrial, mining, services)
- Dynamic score threshold: mean + 0.5 SD of scored universe
- Fixed SECTOR_MANUAL_MAP for 70 Unknown-sector tickers
- Fixed BANK_TICKERS whitelist for BDO, MBT, SECB

### Phase 14 — Pending
- [ ] Educational auto-poster — 52-topic Wednesday rotation to #learn-investing
- [ ] Daily public briefing webhook — top 3 grades to #daily-briefing (separate from weekly)
- [ ] Run backfill then re-calibrate thresholds: `py engine/calibrate_thresholds.py`

### Backtesting notes
- Focus on statistical interpretation — not return guarantees
- Highlight drawdown risk
- Never declare the model superior without statistical evidence
- Never infer future performance from historical results

---

## 9. HOW TO RUN THE SYSTEM

```bash
python main.py                          # full pipeline (score + PDF + Discord)
python main.py --dry-run                # no Discord publish
python scheduler.py                     # continuous scheduler
python scheduler.py --run-weekly        # manual full scrape
python scheduler.py --run-backfill      # historical backfill (one-time)
python dashboard/app.py                 # local dashboard → http://localhost:8080
python engine/calibrate_thresholds.py   # recalibrate after scrape/backfill
python db/db_data_quality.py            # data quality audit
```

**Python command: `python`. Version 3.14.x. Dev environment: WSL2/Ubuntu.**

---

## 10. ENVIRONMENT VARIABLES (.env)

Key vars: `PSE_EDGE_EMAIL`, `PSE_EDGE_PASSWORD`, `DISCORD_BOT_TOKEN`, `ADMIN_DISCORD_ID`,
`DISCORD_WEBHOOK_RANKINGS`, `DISCORD_WEBHOOK_ALERTS`, `DISCORD_WEBHOOK_DEEP_ANALYSIS`,
`DISCORD_WEBHOOK_DAILY_BRIEFING`, `DISCORD_INVITE_URL`, `DISCORD_GUILD_ID`,
`ANTHROPIC_API_KEY`, `PAYMONGO_SECRET_KEY`, `MONTHLY_PRICE_CENTAVOS`, `ANNUAL_PRICE_CENTAVOS`,
`DATABASE_URL` (Postgres connection string — required), `PORT` (Railway: set automatically),
`PSE_DATA_DIR` (default `/app/data`), `FLASK_SECRET_KEY`,
`DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD` (HTTP Basic Auth for admin dashboard).

Install missing packages: `python -m pip install <package_name>`

---

## 12. SELF-CORRECTION PROTOCOL

Common errors on this WSL2/Ubuntu setup:
- `ModuleNotFoundError` → run `python -m pip install <module>`
- `FileNotFoundError` → create the directory first with `os.makedirs`
- `SyntaxError` → check indentation and missing colons
- `KeyError` on stock dict → add `.get('key', default)` not `['key']`
- SQL `SUM()` on empty table → returns NULL rows, always coerce with `or 0`
- `psycopg2.OperationalError` → check `DATABASE_URL` env var is set and Postgres is running
- `psycopg2` thread safety → open a new connection inside each thread (`get_connection()` per call is correct)
- Discord `The application did not respond` → `defer(thinking=True)` not called within 3s; check for exception before defer, or ensure blocking code uses `asyncio.to_thread()`

---

## 15. ENVIRONMENT / FILESYSTEM

Dev environment: WSL2/Ubuntu. Deploy: Railway (Docker/Linux).
- Database: PostgreSQL via `DATABASE_URL` env var (no SQLite)
- Runtime data (PDFs, caches): `PSE_DATA_DIR` env var, default `/app/data`
- No Windows paths anywhere in application code

---

*Last updated: Postgres migration + Linux cleanup + HTTP Basic Auth (2026-05-14)*
*Project owner: Josh*
*Do not share this file or the .env file publicly.*
