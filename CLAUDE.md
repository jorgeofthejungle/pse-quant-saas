# CLAUDE.md — PSE Quant SaaS Autonomous Development Guide
> This file is the source of truth. In any conflict between documents or instructions, CLAUDE.md wins.

---

## 1. WHO YOU ARE

You are the lead developer of **PSE Quant SaaS** — a deterministic
multi-factor Philippine equity ranking engine that runs locally on Windows.

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

Portfolio-specific weights configured in `config.py SCORER_WEIGHTS`:
| Layer | Unified | Dividend | Value | What It Measures |
|-------|---------|----------|-------|-----------------|
| Health | 25% | 27% | 35% | Financial health today (ROE, margins, D/E, FCF, EPS stability) — sector-relative |
| Improvement | 30% | 27% | 25% | Fundamentals improving (Revenue, EPS, OCF, ROE deltas) — recency-weighted |
| Acceleration | 5% | 5% | 5% | Improvement getting stronger (2-year window delta-of-delta) |
| Persistence | 40% | 41% | 35% | Improvement consistent and reliable (direction + magnitude + streak) |

Dividends are a bonus signal — not a filter requirement. REITs excluded from Value portfolio.
PDF has two sections: **Dividend** and **Value**. A stock can appear in both.

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
Function: `score_unified(stock, sector_stats, financials_history, portfolio_type='unified')` → returns `(score: float, breakdown: dict)`
Four layers with portfolio-specific weights configured in `config.py SCORER_WEIGHTS`.
Default unified: health (25%), improvement (30%), acceleration (5%), persistence (40%).
Applies data confidence multiplier to final score.
Passes full `sector_medians` dict to `score_health()` — activates the 70/30 absolute/sector-relative blend.
**Weights and thresholds are configured in `config.py`. Do not change without explicit instruction.**
*(Phase 11: Portfolio-specific weights, confidence multiplier, acceleration reduced to 5%. Phase 12: sector_medians now passed correctly.)*

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
All constants imported from `config.py` — no local duplicates (removed in Phase 12 audit fix).
*(Phase 11: Risk-adjusted discount rate by size and sector. Phase 12: Removed local constant copies.)*

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

### Phases 1–12 ✅ COMPLETE
All core engine, reports, data pipeline, automation, dashboard, scoring, backtester, Discord bot, data quality, Railway deployment done. See Section 4 for key function signatures.

### Phase 12 — Pending
- [ ] Educational auto-poster — 52-topic Wednesday rotation to #learn-investing
- [ ] Daily public briefing webhook — top 3 grades to #daily-briefing (separate from weekly)
- [ ] Run backfill then re-calibrate thresholds: `py engine/calibrate_thresholds.py`

---

## 9. HOW TO RUN THE SYSTEM

```bash
py main.py                          # full pipeline (score + PDF + Discord)
py main.py --dry-run                # no Discord publish
py scheduler.py                     # continuous scheduler
py scheduler.py --run-weekly        # manual full scrape
py scheduler.py --run-backfill      # historical backfill (one-time)
py dashboard/app.py                 # local dashboard → http://localhost:8080
py engine/calibrate_thresholds.py   # recalibrate after scrape/backfill
py db/db_data_quality.py            # data quality audit
```

**Python command: `py` (not `python`). Version 3.14.x.**

---

## 10. ENVIRONMENT VARIABLES (.env)

Key vars: `PSE_EDGE_EMAIL`, `PSE_EDGE_PASSWORD`, `DISCORD_BOT_TOKEN`, `ADMIN_DISCORD_ID`,
`DISCORD_WEBHOOK_RANKINGS`, `DISCORD_WEBHOOK_ALERTS`, `DISCORD_WEBHOOK_DEEP_ANALYSIS`,
`DISCORD_WEBHOOK_DAILY_BRIEFING`, `DISCORD_INVITE_URL`, `DISCORD_GUILD_ID`,
`ANTHROPIC_API_KEY`, `PAYMONGO_SECRET_KEY`, `MONTHLY_PRICE_CENTAVOS`, `ANNUAL_PRICE_CENTAVOS`,
`PSE_DB_PATH` (Railway: `/app/data/pse_quant.db`), `PORT` (Railway: set automatically).

Install missing packages: `py -m pip install <package_name>`

---

## 12. SELF-CORRECTION PROTOCOL

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

## 13. DISCORD CHANNELS

| Channel | Access | Webhook Env Var | Purpose |
|---------|--------|----------------|---------|
| `#rankings` | Premium | `DISCORD_WEBHOOK_RANKINGS` | Full PDF rankings report |
| `#deep-analysis` | Premium | `DISCORD_WEBHOOK_DEEP_ANALYSIS` | Stock of the Week, monthly reports |
| `#alerts` | Public | `DISCORD_WEBHOOK_ALERTS` | Price, dividend, earnings alerts |
| `#daily-briefing` | Public | `DISCORD_WEBHOOK_DAILY_BRIEFING` | Top 3 grades (no scores) |

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

*Last updated: Phase 12 audit fixes + house cleaning complete (2026-03-21)*
*Project owner: Josh*
*Do not share this file or the .env file publicly.*
