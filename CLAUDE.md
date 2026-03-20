# CLAUDE.md — PSE Quant SaaS Autonomous Development Guide
> Place this file in the root of the project: `C:\Users\Josh\Documents\pse-quant-saas\CLAUDE.md`
> Claude Code reads this file automatically at the start of every session.

---

## 1. WHO YOU ARE

You are the lead developer of **PSE Quant SaaS** — a deterministic
multi-factor Philippine equity ranking engine that runs locally on Windows.

You work autonomously. When given a task you:
1. Read the relevant files before writing any code
2. Write the code
3. Run it immediately to verify it works
4. Fix any errors yourself without asking the user
5. Only report back when the task is fully complete and tested

You never ask the user to paste code, run commands, or fix errors manually
unless the error requires something only they can provide
(e.g. a missing API key, a PSE Edge login, or a file only they have).

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
- Scores every PSE stock using a unified 4-layer fundamental framework
- Calculates Margin of Safety (intrinsic value vs current price)
- Enriches top stocks with AI-powered news sentiment (Claude Haiku)
- Generates professional PDF reports (StockPilot PH Rankings)
- Delivers reports to Discord channels automatically on a schedule
- Runs a Discord slash-command bot for premium member access
- Sends real-time alerts for new dividends, earnings, and price triggers
- Provides a local Flask dashboard for admin and member management

**Unified scoring system (StockPilot PH Rankings):**

Default unified weights (portfolio-specific weights configured in `config.py SCORER_WEIGHTS`):
| Layer | Unified | Pure Dividend | Div Growth | Value | What It Measures |
|-------|---------|---------------|------------|-------|-----------------|
| Health | 25% | 30% | 25% | 35% | Financial health today (ROE, margins, D/E, FCF, EPS stability) — sector-relative |
| Improvement | 30% | 20% | 35% | 25% | Fundamentals improving (Revenue, EPS, OCF, ROE deltas) — recency-weighted |
| Acceleration | 5% | 5% | 5% | 5% | Improvement getting stronger (2-year window delta-of-delta) |
| Persistence | 40% | 45% | 35% | 35% | Improvement consistent and reliable (direction + magnitude + streak) |

Dividends are a bonus signal within the score — not a filter requirement.
All PSE stocks compete in one unified ranking. The PDF contains three sections (Pure Dividend, Dividend Growth, Value) each scored with portfolio-specific weights. A stock can appear in multiple sections.

Health layer thresholds are calibrated from PSE market percentiles via `engine/calibrate_thresholds.py`. Each scored stock carries a data confidence multiplier (5yr=1.0, 4yr=0.9, 3yr=0.8, 2yr=0.65).

MoS discount rate is risk-adjusted by size premium (0-5%) and sector premium (0-2%), not a flat 11.5%.

**Architecture pipeline:**
```
PSE Edge → Scraper (canary checks) → Unit Validation → Database
                                                           ↓
                              Data Quality Audit → Calibration (thresholds)
                                                           ↓
                    Metrics → Filter (2yr min) → Scorer (per-portfolio) → MoS (risk-adjusted)
                                                           ↓
                                   Sentiment (Haiku) → Unified PDF (3 sections)
                                                           ↓
                                          Discord Webhooks + Bot → Members
```

---

## 3. PROJECT STRUCTURE

```
pse-quant-saas/
├── CLAUDE.md               ← YOU ARE HERE
├── README.md               ← Public-facing system overview
├── config.py               ← Central config (models, URLs, thresholds)
├── .env                    ← API keys and secrets (never commit this)
├── main.py                 ← Entry point — runs the full pipeline
│
├── engine/                 ← Core calculation logic (DETERMINISTIC)
│   ├── metrics.py          ← Financial ratio calculators ✅
│   ├── filters.py          ← Legacy portfolio eligibility filters ✅ (archived)
│   ├── filters_v2.py       ← Unified health filter (pass/fail) ✅
│   ├── scorer.py           ← Legacy scoring engine ✅ (archived facade)
│   │   ├── scorer_utils.py
│   │   ├── scorer_explanations.py
│   │   └── scorer_momentum.py
│   ├── scorer_v2.py        ← Unified 4-layer scorer ✅
│   │   ├── scorer_health.py
│   │   ├── scorer_improvement.py
│   │   ├── scorer_acceleration.py
│   │   ├── scorer_persistence.py
│   │   └── scorer_explanations_value.py
│   ├── sector_stats.py     ← Dynamic sector median computation (8 metrics, market-cap weighted) ✅
│   ├── mos.py              ← Margin of Safety calculator (risk-adjusted discount rate) ✅
│   ├── validator.py        ← Data validation layer + confidence calculator ✅
│   ├── calibrate_thresholds.py ← Percentile-based threshold derivation from DB ✅
│   ├── sentiment_engine.py ← Claude Haiku news sentiment ✅
│   └── conglomerate_scorer.py ← Holding firm segment analysis ✅
│
├── scraper/                ← PSE Edge data collection
│   ├── pse_edge_scraper.py ← Main scraper facade ✅
│   │   ├── pse_session.py
│   │   ├── pse_lookup.py
│   │   ├── pse_stock_data.py   ← Dividend scraper (COMMON-only whitelist, deduped, fiscal year mapped) ✅
│   │   └── pse_financial_reports.py ← Financial report parser + backfill scraper ✅
│   ├── pse_stock_builder.py ← Builds stock dict from DB for scoring pipeline ✅
│   ├── scraper_canary.py   ← Canary field checks + admin DM on pattern failure ✅
│   └── news_fetcher.py     ← Yahoo Finance + news RSS ✅
│
├── db/                     ← Database layer
│   ├── database.py         ← Facade (re-exports all DB functions) ✅
│   ├── db_connection.py    ← SQLite connection + DB_PATH ✅
│   ├── db_schema.py        ← Table creation (init_db) ✅
│   ├── db_prices.py        ← Price data CRUD ✅
│   ├── db_scores.py        ← Score storage + get_last_scores_v2 ✅
│   ├── db_financials.py    ← Financial data CRUD ✅
│   ├── db_sentiment.py     ← Sentiment cache CRUD ✅
│   ├── db_conglomerates.py ← Conglomerate segment data CRUD ✅
│   ├── db_data_quality.py  ← Post-scrape data quality auditor ✅
│   └── db_maintenance.py   ← DPS auto-cleaner + stale data pruner ✅
│
├── reports/                ← PDF generation
│   ├── pdf_generator.py    ← Facade ✅
│   ├── pdf_styles.py
│   ├── pdf_cover_page.py
│   ├── pdf_rankings_table.py
│   ├── pdf_stock_detail_page.py
│   ├── pdf_portfolio_sections.py ← Multi-section layout for unified PDF ✅
│   └── pdf_sentiment.py
│
├── discord/                ← Discord delivery and bot
│   ├── publisher.py        ← Webhook sender facade ✅
│   ├── discord_core.py
│   ├── discord_reports.py
│   ├── discord_alerts.py
│   ├── discord_dm.py       ← Direct message via Discord REST API ✅
│   ├── bot.py              ← Slash command bot entry point ✅
│   ├── bot_commands.py     ← /stock, /top10, /help logic ✅
│   ├── bot_subscribe.py    ← /subscribe, /mystatus logic ✅
│   ├── bot_watchlist.py    ← /watchlist show/add/remove logic ✅
│   └── bot_admin.py        ← /admin commands (Josh only) ✅
│
├── alerts/
│   ├── alert_engine.py     ← Price, dividend, earnings alerts ✅
│   └── disclosure_monitor.py ← PSE Edge feed monitor (15-min polling) ✅
│
├── dashboard/              ← Local Flask admin dashboard ✅
│   ├── app.py              ← Flask app factory, runs on :8080
│   ├── background.py       ← Thread-based pipeline runner + scheduler process control
│   ├── access_control.py   ← Member tier checking (check_access, get_member_tier) ✅
│   ├── security.py         ← Security utilities ✅
│   ├── db_members.py       ← Members/subscriptions DB operations
│   ├── routes_home.py      ← Overview page + /api/status (unified rankings)
│   ├── routes_pipeline.py  ← Pipeline controls + scheduler start/stop
│   ├── routes_members.py   ← Member CRUD + extend/cancel
│   ├── routes_analytics.py ← Chart data JSON endpoints
│   ├── routes_settings.py  ← Config display + webhook test
│   ├── routes_paymongo.py  ← PayMongo payment link generation
│   ├── routes_stocks.py    ← Stock Lookup page + autocomplete API
│   ├── routes_portal.py    ← Public portal/landing page
│   ├── routes_conglomerates.py ← Conglomerates deep-dive page
│   ├── templates/          ← Jinja2 HTML templates
│   └── static/             ← CSS + JS (style.css, dashboard.js)
│
├── scheduler.py            ← APScheduler facade ✅
│   ├── scheduler_data.py   ← Ticker lists + run-date helpers
│   └── scheduler_jobs.py   ← All scheduled job functions
│
├── data/
│   ├── raw/                ← Raw scraped HTML/JSON
│   ├── parsed/             ← Cleaned JSON ready for DB
│   └── reports/            ← Generated PDF output files
│
└── tests/
    ├── test_metrics.py     ✅
    ├── test_filters.py     ✅
    ├── test_scorer.py      ✅
    ├── test_mos.py         ✅
    ├── test_pdf.py         ✅
    └── test_discord.py     ✅
```

---

## 4. COMPLETED WORK — DO NOT MODIFY WITHOUT REASON

The following files are complete and tested. Read them before
building anything that depends on them. Do not change their
function signatures or return formats without updating all
dependents.

### engine/metrics.py
Calculates: `pe, pb, roe, de, dividend_yield, payout_ratio,
fcf, fcf_yield, fcf_coverage, cagr, ev_ebitda`
All functions return `float | None`. Never raise on bad input.

### engine/filters_v2.py
Function: `filter_unified(stock)` → returns `(eligible: bool, reason: str)`
Hard filters: min 2 years of EPS/Revenue data, min 2 years OCF, normalized EPS > 0,
no persistent negative OCF (2+ consecutive years), D/E ≤ 3.0x (non-bank) or ≤ 10x (bank) or ≤ 4.0x (REIT).
*(Phase 11: Relaxed from 3-year to 2-year minimum for EPS/Revenue. Confidence multiplier handles the penalty.)*

### engine/scorer_v2.py (unified 4-layer scorer)
Function: `score_unified(stock, financials_history, portfolio_type='unified')` → returns `(score: float, breakdown: dict)`
Four layers with portfolio-specific weights configured in `config.py SCORER_WEIGHTS`.
Default unified: health (25%), improvement (30%), acceleration (5%), persistence (40%).
Applies data confidence multiplier to final score.
**Weights and thresholds are configured in `config.py`. Do not change without explicit instruction.**
*(Phase 11: Portfolio-specific weights, confidence multiplier, acceleration reduced to 5%.)*

### engine/scorer_health.py
Health layer uses 70/30 blend of absolute (PSE percentile) and sector-relative scoring.
Thresholds calibrated by `engine/calibrate_thresholds.py`, stored in `settings` DB table with `config.py` fallbacks.

### engine/scorer_improvement.py
Uses recency-weighted smoothed deltas (50/30/20 newest-first).
ROE delta indexes by actual fiscal year, not array position.

### engine/scorer_persistence.py
Blended formula: direction (60pts) + magnitude (20pts) + streak bonus (20pts).

### engine/mos.py
Functions: `calc_ddm`, `calc_eps_pe`, `calc_dcf`, `calc_mos_price`, `calc_mos_pct`, `calc_hybrid_intrinsic`
Risk-free rate = 6.5% (PH 10Y T-bond). Max DDM growth rate capped at 7%.
Discount rate = risk-free + equity premium (5%) + size premium (0-5%) + sector premium (0-2%).
All constants imported from `config.py` — no local duplicates.
*(Phase 11: Risk-adjusted discount rate by size and sector.)*

### engine/sentiment_engine.py
Uses `PIPELINE_AI_MODEL` from `config.py` (Claude Haiku).
Entry: `enrich_with_sentiment(stocks)` — enriches list in-place.
Caches results in `sentiment` DB table for 24 hours.
Returns `None` silently if `ANTHROPIC_API_KEY` is missing.

### scraper/pse_stock_data.py — scrape_dividend_history()
Key quality controls (permanent — do not loosen):
- COMMON shares whitelist: `{'COMMON', 'ORDINARY', 'COMMON SHARES', 'ORDINARY SHARES', 'SHARES', ''}`
- Ex-date deduplication: first occurrence per ex-date wins (most recent amendment)
- Per-share rate: currency-prefixed regex `r'(?:P|PHP|Php)\s*([\d]+\.[\d]+)'`, cap ₱0.001–₱100
- Returns `[{year: int, dps: float, fiscal_year: int}]` newest-first, up to 6 years
- Fiscal year mapping: ex-dates in months ≤ fiscal_year_end_month → prior fiscal year
*(Phase 11: Added fiscal year mapping for correct year attribution.)*

### scraper/pse_edge_scraper.py — yield gate
- Write-time yield gate lives here (lines 166-171), NOT in `db_financials.py`
- DPS yielding > 25% (non-REIT) or > 35% (REIT) is blocked at scrape time
- Canary field checks on each scrape; admin DM on pattern failure
*(Phase 11: Tightened from 40%/50% to 25%/35%. Added scraper change detection.)*

### scraper/scraper_canary.py
Shared canary helper for all PSE Edge scrapers.
- `fire_canary(scraper_name, canary_name, detail)` — logs failure to `settings` table under `scraper_health_{scraper_name}`; sends admin DM via `discord_dm.send_dm_text`; anti-spam: one DM per canary per 24 hours
- Canary checks added to: `pse_lookup.py` (JSON keys), `pse_stock_data.py` (price/dividend table), `pse_financial_reports.py` (report table + columns)
- All failures are non-fatal — scraper logs and continues

### engine/validator.py — check_price_staleness()
- `check_price_staleness(stock)` → `{price_date, days_stale, is_stale, is_critical, warning}`
- Warn threshold: `PRICE_STALENESS_WARN_DAYS = 5` days; critical: `PRICE_STALENESS_ERROR_DAYS = 30` days
- DB fallback: queries `SELECT MAX(date) FROM prices WHERE ticker = ?` if `price_date` not in stock dict
- Integrated into `validate_stock()` return dict as `'price_staleness'` key

### scheduler_jobs.py — heartbeat + freshness gate
- `_record_heartbeat(job_name)` — writes `scheduler_heartbeat_{job_name}` ISO timestamp to settings table after each job completes
- `_check_price_freshness()` — queries prices table; if no rows within `PRICE_STALENESS_ERROR_DAYS`, sends admin DM and returns False; `run_daily_score()` calls this at start and skips if stale
- `check_scheduler_health()` → dict with `last_run`, `hours_ago`, `ok` for daily_score / weekly_scrape / alert_check
- Re-exported via `scheduler.py` facade

### config.py — REIT_WHITELIST
- `REIT_WHITELIST = {'VREIT', 'PREIT', 'MREIT', 'AREIT'}` — tickers always classified as REIT
- db_schema.py migrations set `is_reit=1` for these tickers on every startup (idempotent)
*(Phase 11: Task 5 — fixes REIT misclassification introduced during initial scraping.)*

### engine/validator.py — hard-block thresholds
- `BLOCK_THRESHOLDS`: `'roe': ('<', -50.0, ...)` — ROE < -50% is a hard block (not warn)
- `BLOCK_THRESHOLDS`: `'pb': ('>', 50.0, ...)` — P/B > 50 is a hard block
- `MIN_COMPLETENESS = 0.40` — 40% of scored fields must be populated (tightened from 0.25)
*(Phase 11: Task 5 — tightened from ROE warn-only and P/B>100 to hard blocks.)*

### db/db_financials.py — upsert_financials()
- `force=False` uses `COALESCE(new, existing)` so existing good data is not overwritten
- `force=True` overwrites ALL fields — use only when you are certain all fields are correct

### db/db_data_quality.py
Post-scrape financial data auditor. Checks:
- Current-year DPS (likely partial/attribution error)
- Implausible yield > 15% (penny stock exception: price < ₱2 → WARN not ERROR)
- Payout ratio > 200% (holding co exception: yield < 5% → WARN)
- DPS jumped > 3× vs prior year
- DPS only — no other financials
- Negative revenue
- EPS > 500 (unit mismatch)
- Net margin > 500% (holding co or unit error)
- EPS vs NI mismatch > 100× (uses market_cap/close to derive shares)

Key functions:
- `run_audit(ticker_filter=None)` → `list[dict]` — each issue has ticker, year, check, severity, detail, suggested_action
- `get_dividend_quality_flags()` → `set[(ticker, year)]` — used by calendar query to exclude bad data
- `print_report(issues)` — formatted console output
- CLI: `py db/db_data_quality.py` or `py db/db_data_quality.py --ticker DMC`

### db/db_maintenance.py
- `clean_bad_dps(max_yield_non_reit=20.0, max_yield_reit=30.0, dry_run=False)` — NULLs DPS with implausible yield; returns `{nulled, tickers_affected}`
- `cleanup_stale_data(prices_keep_days=365, activity_keep_days=90, sentiment_keep_days=7, vacuum=True)` — prunes old rows and VACUUMs

### reports/pdf_generator.py (facade)
Function: `generate_report(portfolio_type, ranked_stocks, output_path, total_stocks_screened)`
Shows ALL qualifying stocks (no cap). Includes sentiment panel when data is present.

### discord/publisher.py (facade)
Loads webhook URLs from `.env`. 4 webhooks: `rankings`, `alerts`, `deep_analysis`, `daily_briefing`.
Functions: `send_report`, `send_dividend_alert`, `send_price_alert`, `send_earnings_alert`,
`send_rescore_notice`, `send_weekly_briefing`, `send_stock_of_week`,
`send_dividend_calendar`, `send_model_performance`

### discord/bot.py
Slash command bot. Run with `py discord/bot.py`.
- `_premium_dm_gate(interaction)` — DM-only + premium member check (returns error string or None)
- `_dm_only_gate(interaction)` — DM-only, no premium check (for /subscribe, /mystatus)
- `_admin_gate(interaction)` — DM-only + ADMIN_DISCORD_ID check
- All admin handlers use `asyncio.to_thread()` to avoid blocking the event loop
- Guild sync: set `DISCORD_GUILD_ID` in `.env` for instant command propagation (testing)
- Global sync (no DISCORD_GUILD_ID): takes up to 1 hour to propagate

### discord/bot_admin.py
Josh-only commands via `/admin` group. All functions return embed dicts.
- `get_admin_list_embed()` — all active members
- `get_admin_pending_embed()` — pending members
- `confirm_member_embed(query)` — activates member + sends welcome DM (calls `send_welcome_dm` synchronously — bot.py wraps in asyncio.to_thread)
- `extend_member_embed(query, days)` — extends subscription
- `get_member_status_embed(query)` — full member detail
- `_find_member(query)` — finds by exact discord_id or partial name match

### discord/discord_dm.py
Sends embeds/text DMs via Discord REST API (bot token, not webhook).
- `send_dm_embed(discord_id, embed)` → `(bool, str)`
- `send_welcome_dm(discord_id, member_name, expiry_date)` → `(bool, str)`
- `send_dm_text(discord_id, content)` → `(bool, str)`
Uses synchronous `requests` — always call from a thread (not directly from async).

### dashboard/access_control.py
Member tier and access control for bot commands and portal.
- `check_access(discord_id, feature)` → `bool`
- `get_member_tier(discord_id)` → `'free' | 'paid'`
- `get_member_by_discord_id(discord_id)` → `dict | None`
Features: `'discord_bot'`, `'stock_lookup'`, `'watchlist'`, `'pdf_reports'`

### alerts/alert_engine.py
Three checks: price (DB-only), dividend (PSE Edge), earnings (PSE Edge).
First-run baseline: records existing disclosures without alerting.
Atomic dedup: `_claim_disclosure()` uses `INSERT OR IGNORE` + `rowcount`.
Only checks top-15 ranked tickers. CLI: `py alerts/alert_engine.py --dry-run`

### alerts/disclosure_monitor.py
15-minute polling of PSE Edge disclosure feed.
`run_disclosure_check(dry_run=False)` → count of disclosures sent.
Registered in scheduler as interval job (every 15 minutes, all day).

### dashboard/app.py
Flask app — run with `py dashboard/app.py`, open `http://localhost:8080`.
Pages: Overview, Pipeline, Stock Lookup, Members, Analytics, Settings, Portal, Conglomerates.

### dashboard/background.py
`start_scheduler()` — launches `py scheduler.py` via subprocess.Popen.
`stop_scheduler()` / `get_scheduler_status()` — process lifecycle management.

### scheduler_jobs.py — run_weekly_scrape()
Full Sunday scrape sequence:
1. DB backup
2. Full scrape (`scrape_all_and_save`)
3. Stale financials re-fetch
4. Conglomerate autofill
5. **DPS auto-clean** (`clean_bad_dps`) ← NEW
6. **Data quality audit** (`run_audit`) + log to activity_log ← NEW
7. Re-score all stocks
8. Weekly briefing to #daily-briefing
9. Stale data cleanup + VACUUM

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

SQLite database at: `C:\Users\Josh\AppData\Local\pse_quant\pse_quant.db`

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
- Keep all files under 500 lines
- Use facade pattern: thin re-export module + focused sub-modules
- Do not refactor working code unless explicitly instructed

---

## 7A. EDUCATIONAL COMMUNICATION LAYER — REPORT WRITING STANDARD

All PDF explanations, stock summaries, and breakdown text must follow this framework.

### Role when writing report text
Senior investment learning designer — not a salesperson, not a promoter.

### Writing style
1. Simple language. Short sentences.
2. Explain financial terms immediately in plain English.
3. Never assume prior investing knowledge.
4. Always explain both strengths and risks.
5. Never promise returns. Never imply a recommendation.

### Tone
Calm, analytical, neutral, beginner-friendly, rational, professional.

### Key term definitions
- P/E: "You are paying ₱X for every ₱1 the company earns per year."
- ROE: "This measures how efficiently management uses shareholders' money."
- D/E: "This shows how much the company relies on borrowed money."
- MoS: "Discount between intrinsic value and current price. Larger = more cushion."
- Intrinsic Value: "Mathematical estimate of fair business value. Not a price prediction."

### Priority hierarchy
Clarity > Complexity | Education > Jargon | Risk > Optimism | Neutrality > Persuasion

---

## 8. PHASE ROADMAP

### Phase 1 — Engine Core ✅ COMPLETE
metrics.py, filters.py, scorer.py, mos.py, validator.py. All tested.

### Phase 2 — Reports & Delivery ✅ COMPLETE
pdf_generator.py, publisher.py, main.py.

### Phase 3 — Data Pipeline ✅ COMPLETE
database.py (+ sub-modules), pse_edge_scraper.py (+ sub-modules),
news_fetcher.py, sentiment_engine.py. DB live at AppData/Local/pse_quant/.

### Phase 4 — Automation ✅ COMPLETE
scheduler.py — daily scoring 17:30 PHT, alert check 09:00 PHT.
alert_engine.py — price, dividend, earnings alerts with atomic dedup.

### Phase 5 — Dashboard ✅ COMPLETE
Local Flask dashboard at http://localhost:8080.
Member management, PayMongo payment links, pipeline controls, analytics.

### Phase 6 — Scoring Enhancement ✅ COMPLETE
Unified 4-layer scorer (scorer_v2.py). Fundamental Momentum layer in legacy scorer.

### Phase 7 — Backtester ✅ COMPLETE
backtester.py — historical score simulation. CLI: `py backtester.py --portfolio pure_dividend`

### Phase 8 — Stability & Bug Fixes ✅ COMPLETE (2026-03-09)
- PDF shows ALL qualifying stocks (no cap)
- Atomic alert dedup via _claim_disclosure()
- Production readiness audit passed

### Phase 9 — Unified Scoring System ✅ COMPLETE (2026-03-14)
- Unified 4-layer scorer (scorer_v2.py + 4 sub-modules)
- Unified health filter (filters_v2.py)
- Stock Lookup dashboard page (routes_stocks.py)
- Scheduler start/stop from Pipeline page
- Overview page shows unified StockPilot PH Rankings
- Scheduler: alert 09:00 PHT, scoring 17:30 PHT

### Phase 10 — Discord Bot + Data Quality ✅ COMPLETE (2026-03-15)
- [x] Discord slash command bot (`discord/bot.py`)
  - /stock, /top10 — premium DM-only with tier gating
  - /subscribe, /mystatus — free DM-only
  - /watchlist show/add/remove — premium DM-only
  - /admin list/pending/confirm/extend/status — Josh-only DM
  - All blocking calls wrapped in asyncio.to_thread()
  - Guild sync via DISCORD_GUILD_ID for instant testing propagation
- [x] Member access control (`dashboard/access_control.py`)
- [x] Direct message delivery (`discord/discord_dm.py`)
- [x] Financial data quality auditor (`db/db_data_quality.py`)
  - Checks: yield, payout, EPS/NI mismatch, DPS jumps, negative revenue, net margin anomalies
  - Penny stock and holding company exceptions built in
  - `get_dividend_quality_flags()` used by calendar query
- [x] Database maintenance (`db/db_maintenance.py`)
  - `clean_bad_dps()` — auto-nulls implausible DPS
  - `cleanup_stale_data()` — prunes old rows + VACUUM
- [x] Weekly scrape now includes Steps 2c/2d: DPS auto-clean + full audit logged to activity_log
- [x] 4-webhook Discord structure: RANKINGS, ALERTS, DEEP_ANALYSIS, DAILY_BRIEFING
- [x] Disclosure monitor (15-min PSE Edge feed polling)

### Phase 11 — Data Quality & Scoring Recalibration ✅ COMPLETE (2026-03-20)
**Spec:** `docs/superpowers/specs/2026-03-17-data-quality-scoring-recalibration-design.md`

**Phase A — Data Quality Hardening:**
- [x] Scraper change detection (canary fields + admin DM alerts) ✅ Task 13 — `scraper/scraper_canary.py`
- [ ] Unit detection hardening (mandatory currency line, cross-validation) — deferred to Phase 12
- [x] Dividend fiscal year attribution (ex-date → fiscal year mapping) ✅ Task 4
- [x] Tighten write-time gates (25%/35% yield, 40% completeness, ROE/P/B hard blocks) ✅ Task 5
- [x] Fix REIT misclassification (VREIT, PREIT, MREIT, AREIT) ✅ Task 5
- [x] Market cap / price staleness cross-validation ✅ Task 14 — `check_price_staleness()` in `validator.py`
- [x] Staleness prevention (freshness gates, scheduler heartbeat) ✅ Task 15 — `_check_price_freshness()`, `_record_heartbeat()`, `check_scheduler_health()`

**Phase B — Scoring Recalibration:**
- [x] Historical backfill scraper (2018-2023 from PSE Edge) ✅ Task 8 — `pse_financial_reports.py`
- [x] Health threshold recalibration (PSE percentile-based, sector-relative) ✅ Task 9 — `calibrate_thresholds.py`
- [x] Confidence-weighted scoring (5yr=1.0 → 2yr=0.65) ✅ Task 10 — `calc_data_confidence()` in `validator.py`
- [x] Filter relaxed from 3-year to 2-year minimum ✅ Task 10 — `filters_v2.py`
- [x] Portfolio-specific weights (pure_dividend, dividend_growth, value) ✅ Task 12 — `SCORER_WEIGHTS` in `config.py`
- [x] Unified PDF with three ranked sections ✅ Task 12 — `pdf_portfolio_sections.py`, `pdf_generator.py`
- [x] Persistence magnitude awareness (direction + magnitude + streak) ✅ Task 2 — `scorer_persistence.py`
- [x] MoS risk-adjusted discount rate (size + sector premiums) ✅ Task 11 — `mos.py`
- [x] Sector medians expansion (8 metrics, market-cap weighted, PE<50 filter) ✅ Task 6 — `sector_stats.py`
- [x] Improvement recency weighting (50/30/20) ✅ Task 1 — `scorer_improvement.py`
- [x] ROE delta year validation (index by fiscal year, not array position) ✅ Task 1 — `scorer_improvement.py`
- [x] Acceleration weight reduced to 5%, wider scoring bands ✅ Task 3 — `scorer_acceleration.py`

### Phase 12 — Next (Backlog)
- [ ] Unit detection hardening (mandatory currency line, cross-validation) — deferred from Phase 11
- [ ] Manual data entry UI — for GSMI 2022, GLO 2022 (missing from PSE Edge)
- [ ] REIT FFO-based FCF coverage exemption
- [ ] Export rankings to CSV/Excel from dashboard
- [ ] Scheduler health page in dashboard (display `check_scheduler_health()` output)
- [ ] Educational auto-poster — 52-topic Wednesday rotation to #learn-investing
- [ ] Daily public briefing webhook — top 3 grades to #daily-briefing (separate from weekly)

---

## 9. HOW TO RUN THE SYSTEM

```bash
# Full unified pipeline (score + PDF + Discord)
py main.py

# Dry run (no Discord publish)
py main.py --dry-run

# Scheduler (continuous — runs on automatic schedule)
py scheduler.py

# Manual scheduler triggers
py scheduler.py --run-now           # full scoring cycle
py scheduler.py --run-alerts        # alert check
py scheduler.py --run-weekly        # full financial scrape (+ data quality)
py scheduler.py --run-backfill      # historical backfill 2018-2023 (one-time)
py scheduler.py --run-score         # 4 PM scoring phase only
py scheduler.py --run-report        # 6 PM report phase only
py scheduler.py --run-sotw          # Stock of the Week
py scheduler.py --run-digest        # Weekly Digest DMs
py scheduler.py --run-monthly       # Monthly reports (calendar + performance)
py scheduler.py --run-briefing      # Weekly public briefing
py scheduler.py --run-disclosure    # One disclosure feed check

# Discord bot (slash commands for members)
py discord/bot.py

# Local dashboard
py dashboard/app.py                 # open http://localhost:8080

# Data quality tools
py db/db_data_quality.py            # full audit report
py db/db_data_quality.py --ticker DMC  # audit one ticker

# Alerts only
py alerts/alert_engine.py --dry-run
py alerts/alert_engine.py --check price
py alerts/alert_engine.py --check dividend
py alerts/alert_engine.py --check earnings

# Sentiment test
py engine/sentiment_engine.py --ticker DMC

# Threshold calibration (run after weekly scrape or backfill)
py engine/calibrate_thresholds.py

# Tests
py tests/test_metrics.py
py tests/test_scorer.py
py tests/test_mos.py
```

**Python command on this machine: `py` (not `python`)**
Python version: 3.14.x
Location: `C:\Users\Josh\AppData\Local\Python\pythoncore-3.14-64\`

---

## 10. INSTALLED PACKAGES

```
requests, beautifulsoup4, pdfplumber, reportlab,
apscheduler, pydantic, pandas, pytest,
python-dotenv, lxml, anthropic, flask, discord.py
```

Install missing: `py -m pip install <package_name>`

---

## 11. ENVIRONMENT VARIABLES (.env)

```
# PSE Edge credentials
PSE_EDGE_EMAIL=your@email.com
PSE_EDGE_PASSWORD=yourpassword

# Discord webhooks (4 channels)
DISCORD_WEBHOOK_RANKINGS=https://discord.com/api/webhooks/...      # #rankings (premium PDF)
DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/...        # #alerts (public)
DISCORD_WEBHOOK_DEEP_ANALYSIS=https://discord.com/api/webhooks/... # #deep-analysis (premium)
DISCORD_WEBHOOK_DAILY_BRIEFING=https://discord.com/api/webhooks/.. # #daily-briefing (public)

# Discord bot
DISCORD_BOT_TOKEN=your_bot_token_here
ADMIN_DISCORD_ID=your_discord_user_id     # Right-click name → Copy User ID
DISCORD_INVITE_URL=https://discord.gg/... # Permanent server invite link
DISCORD_GUILD_ID=your_server_id           # Optional: instant guild sync for testing

# AI sentiment (optional)
ANTHROPIC_API_KEY=sk-ant-...

# PayMongo (optional)
PAYMONGO_SECRET_KEY=sk_test_...
MONTHLY_PRICE_CENTAVOS=9900
ANNUAL_PRICE_CENTAVOS=99900
```

---

## 12. SELF-CORRECTION PROTOCOL

When you encounter an error:

1. **Read the full error message** — identify file, line, and type
2. **Read the relevant source file** — understand context before fixing
3. **Fix the minimal change needed** — do not refactor unrelated code
4. **Re-run immediately** — confirm the fix works
5. **If still failing after 3 attempts** — report the error to the user

Common errors on this Windows setup:
- `ModuleNotFoundError` → run `py -m pip install <module>`
- `FileNotFoundError` → create the directory first with `os.makedirs`
- `SyntaxError` → check indentation and missing colons
- `KeyError` on stock dict → add `.get('key', default)` not `['key']`
- `UnicodeEncodeError` in print() → replace Unicode chars with ASCII in print() calls (Discord sends UTF-8 fine; only console output breaks on cp1252)
- SQL `SUM()` on empty table → returns NULL rows, always coerce with `or 0`
- `sqlite3.ProgrammingError: SQLite objects created in a thread` → open a new connection inside the thread (`get_connection()` per call is correct)
- Discord `The application did not respond` → `defer(thinking=True)` not called within 3s; check for exception before defer, or ensure blocking code uses `asyncio.to_thread()`

---

## 13. DISCORD SETUP

**4 channels needed:**

| Channel | Access | Webhook Env Var | Purpose |
|---------|--------|----------------|---------|
| `#rankings` | Premium only | `DISCORD_WEBHOOK_RANKINGS` | Full PDF rankings report |
| `#deep-analysis` | Premium only | `DISCORD_WEBHOOK_DEEP_ANALYSIS` | Stock of the Week, monthly reports |
| `#alerts` | Public | `DISCORD_WEBHOOK_ALERTS` | Price, dividend, earnings alerts |
| `#daily-briefing` | Public | `DISCORD_WEBHOOK_DAILY_BRIEFING` | Top 3 grades (no scores) |

**Bot setup:**
1. Create bot at discord.com/developers/applications
2. Bot → Reset Token → copy to `DISCORD_BOT_TOKEN` in `.env`
3. Invite bot with `bot` + `applications.commands` scopes
4. Set `ADMIN_DISCORD_ID` to your Discord user ID (right-click name → Copy User ID)
5. Set `DISCORD_GUILD_ID` to your server ID (right-click server → Copy Server ID) for instant sync
6. Run: `py discord/bot.py`

**Webhook URLs:**
Discord → Channel Settings → Integrations → Webhooks → New Webhook → Copy URL

---

## 14. BACKTESTING NOTES

Per the project instruction manual:
- Focus on statistical interpretation — not return guarantees
- Highlight drawdown risk
- Never declare the model superior without statistical evidence
- Never infer future performance from historical results

---

## 15. IMPORTANT FILESYSTEM NOTE

Python (via Bash tool) **cannot write new files** to `C:\Users\Josh\Documents\`.
Use the **Write tool** directly to create new files — it bypasses this restriction.
PDFs are saved to Desktop (`C:\Users\Josh\Desktop\`) for this reason.
The SQLite DB lives at `C:\Users\Josh\AppData\Local\pse_quant\pse_quant.db`.

---

*Last updated: Phase 11 complete — Data quality hardening & scoring recalibration (2026-03-20)*
*Project owner: Josh*
*Do not share this file or the .env file publicly.*
