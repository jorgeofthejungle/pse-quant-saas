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
- Parses and stores data in a local SQLite database
- Scores every PSE stock using a unified 4-layer fundamental framework
- Calculates Margin of Safety (intrinsic value vs current price)
- Enriches top stocks with AI-powered news sentiment (Claude Haiku)
- Generates professional PDF reports (StockPilot PH Rankings)
- Delivers reports to a single Discord channel automatically on a schedule
- Sends real-time alerts for new dividends, earnings, and price triggers
- Provides a local Flask dashboard for admin and member management

**Unified scoring system (StockPilot PH Rankings):**
| Layer | Weight | What It Measures |
|-------|--------|-----------------|
| Health | 25% | Financial health today (ROE, margins, D/E, FCF, EPS stability) |
| Improvement | 30% | Fundamentals improving over 3 years (Revenue, EPS, OCF, ROE deltas) |
| Acceleration | 15% | Improvement getting stronger (2-year window delta-of-delta) |
| Persistence | 30% | Improvement consistent and reliable (consecutive positive YoY years) |

Dividends are a bonus signal within the score — not a filter requirement.
All 223 PSE stocks compete in one unified ranking.

**Architecture pipeline:**
```
PSE Edge → Scraper → Parser → Validator → Database
                                              ↓
                              Metrics → Filter → Scorer → MoS
                                                            ↓
                                    Sentiment (Haiku) → PDF Report
                                                            ↓
                                                   Discord → Members
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
│   │   └── scorer_momentum.py  ← Fundamental momentum composite ✅
│   ├── scorer_v2.py        ← Unified 4-layer scorer ✅
│   │   ├── scorer_health.py         ← Layer 1: Health
│   │   ├── scorer_improvement.py    ← Layer 2: Improvement
│   │   ├── scorer_acceleration.py   ← Layer 3: Acceleration
│   │   ├── scorer_persistence.py    ← Layer 4: Persistence
│   │   └── scorer_explanations_value.py
│   ├── sector_stats.py     ← Dynamic sector median computation ✅
│   ├── mos.py              ← Margin of Safety calculator ✅
│   ├── validator.py        ← Data validation layer ✅
│   └── sentiment_engine.py ← Claude Haiku news sentiment ✅
│
├── scraper/                ← PSE Edge data collection
│   ├── pse_edge_scraper.py ← Main scraper facade ✅
│   │   ├── pse_session.py
│   │   ├── pse_lookup.py
│   │   ├── pse_stock_data.py
│   │   └── pse_financial_reports.py
│   └── news_fetcher.py     ← Yahoo Finance + news RSS ✅
│
├── db/                     ← Database layer
│   ├── database.py         ← Facade (re-exports all DB functions) ✅
│   ├── db_connection.py    ← SQLite connection + DB_PATH ✅
│   ├── db_schema.py        ← Table creation (init_db) ✅
│   ├── db_prices.py        ← Price data CRUD ✅
│   ├── db_scores.py        ← Score storage + get_last_top5 ✅
│   ├── db_financials.py    ← Financial data CRUD ✅
│   └── db_sentiment.py     ← Sentiment cache CRUD ✅
│
├── reports/                ← PDF generation
│   ├── pdf_generator.py    ← Facade ✅
│   ├── pdf_styles.py
│   ├── pdf_cover_page.py
│   ├── pdf_rankings_table.py
│   ├── pdf_stock_detail_page.py
│   └── pdf_sentiment.py
│
├── discord/                ← Discord delivery
│   ├── publisher.py        ← Facade ✅
│   ├── discord_core.py
│   ├── discord_reports.py
│   └── discord_alerts.py
│
├── alerts/
│   └── alert_engine.py     ← Price, dividend, earnings alerts ✅
│
├── dashboard/              ← Local Flask admin dashboard ✅
│   ├── app.py              ← Flask app factory, runs on :8080
│   ├── background.py       ← Thread-based pipeline runner + scheduler process control
│   ├── db_members.py       ← Members/subscriptions DB operations
│   ├── routes_home.py      ← Overview page + /api/status (unified rankings)
│   ├── routes_pipeline.py  ← Pipeline controls + scheduler start/stop
│   ├── routes_members.py   ← Member CRUD + extend/cancel
│   ├── routes_analytics.py ← Chart data JSON endpoints
│   ├── routes_settings.py  ← Config display + webhook test (2 webhooks only)
│   ├── routes_paymongo.py  ← PayMongo payment link generation
│   ├── routes_stocks.py    ← Stock Lookup page + autocomplete API
│   ├── templates/          ← Jinja2 HTML templates (8 files, incl. stocks.html)
│   └── static/             ← CSS + JS (style.css, dashboard.js)
│
├── scheduler.py            ← APScheduler facade ✅
│   ├── scheduler_data.py   ← Ticker lists + run-date helpers
│   └── scheduler_jobs.py   ← daily_job, run_alert_check
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
Hard filters: min 3 years of EPS/Revenue/OCF data, 3Y normalized EPS > 0,
no persistent negative OCF (2+ consecutive years), D/E ≤ 2.5x (non-bank) or ≤ 10x (bank).

### engine/filters.py (archived — legacy 3-portfolio system)
Functions: `filter_dividend_portfolio(stock)`,
`filter_value_portfolio(stock)`, `filter_hybrid_portfolio(stock)`
Each returns: `(eligible: bool, reason: str)`. Kept for reference only.

### engine/scorer_v2.py (unified 4-layer scorer)
Function: `score_unified(stock, financials_history)` → returns `(score: float, breakdown: dict)`
Four layers: health (25%), improvement (30%), acceleration (15%), persistence (30%).

**Layer breakdown:**
| Layer | Weight | Key signals |
|-------|--------|-------------|
| Health | 25% | ROE, operating margin/OCF quality, D/E, FCF yield, EPS stability |
| Improvement | 30% | Revenue delta, EPS delta, OCF delta, ROE delta (3Y smoothed) |
| Acceleration | 15% | 2-year delta-of-delta for Revenue, EPS, OCF |
| Persistence | 30% | Consecutive positive YoY years for Revenue, EPS, OCF + direction consistency |

Breakdown dict format:
```python
{
  'layer_name': {
    'score':       float,   # 0-100 sub-score
    'weight':      float,   # e.g. 0.30
    'explanation': str,     # plain English specific to this stock
  }
}
```

**CRITICAL: Do not change weights or normalisation thresholds
without explicit instruction from the user. The scoring logic
is deterministic by design.**

### engine/scorer.py (archived — legacy 3-portfolio system)
Functions: `score_dividend(metrics)`, `score_value(metrics)`,
`score_hybrid(metrics)`. Kept for reference and backtester compatibility.

### engine/mos.py
Functions: `calc_ddm`, `calc_eps_pe`, `calc_dcf`,
`calc_mos_price`, `calc_mos_pct`, `calc_hybrid_intrinsic`
Risk-free rate = 6.5% (PH 10Y T-bond). Update periodically.
Max DDM growth rate capped at 7% to prevent model explosion.

### engine/sentiment_engine.py
Uses `PIPELINE_AI_MODEL` from `config.py` (Claude Haiku).
Entry: `enrich_with_sentiment(stocks)` — enriches list in-place.
Caches results in `sentiment` DB table for 24 hours.
Returns `None` silently if `ANTHROPIC_API_KEY` is missing.

### reports/pdf_generator.py (facade)
Function: `generate_report(portfolio_type, ranked_stocks,
output_path, total_stocks_screened)`
Includes sentiment panel per stock when `sentiment_data` is present.

### discord/publisher.py (facade)
Loads webhook URLs from `.env` via `python-dotenv`.
Functions: `send_report`, `send_dividend_alert`,
`send_price_alert`, `send_earnings_alert`,
`send_rescore_notice`, `send_opportunistic_alert`, `test_webhook`

### alerts/alert_engine.py
Three checks: price (DB-only), dividend (PSE Edge), earnings (PSE Edge).
First-run baseline: records existing disclosures without alerting.
Only checks top-15 ranked tickers to avoid PSE Edge rate limits.
CLI: `py alerts/alert_engine.py --dry-run`

### dashboard/app.py
Flask app — run with `py dashboard/app.py`, open `http://localhost:8080`.
6 pages: Overview, Pipeline, Stock Lookup, Members, Analytics, Settings.
PayMongo integration: generates payment links via API (manual confirmation).
New DB tables: `members`, `subscriptions`, `activity_log`.

### dashboard/routes_stocks.py
Stock Lookup page at `/stocks`. Search by ticker OR company name with autocomplete.
`_get_stock_analysis(ticker)` — runs filter, score, MoS and returns full analysis dict.
`_resolve_ticker(query)` — resolves partial name/ticker to exact ticker via DB.
Autocomplete endpoint: `GET /api/stocks/search?q=` — returns `[{ticker, name}]`.
Individual stock API: `GET /api/stock/<ticker>` — returns full analysis as JSON.

### dashboard/background.py
Manages background pipeline threads AND the scheduler child process.
`start_scheduler()` — launches `py scheduler.py` via `subprocess.Popen`.
`stop_scheduler()` — terminates the child process.
`get_scheduler_status()` — returns `{running: bool, pid: int|None}`.

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

    # Price
    'current_price':    float,  # Latest closing price in PHP

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
The validator will flag nulls and the scorer handles them gracefully.

---

## 6. DATABASE SCHEMA

SQLite database at: `C:\Users\Josh\AppData\Local\pse_quant\pse_quant.db`

Tables:
- `stocks` — ticker, name, sector, is_reit, is_bank, last_updated
- `financials` — id, ticker, year, revenue, net_income, equity, total_debt, cash, operating_cf, capex, ebitda, eps, dps
- `prices` — id, ticker, date, close, market_cap
- `scores` — id, ticker, run_date, pure_dividend_score, dividend_growth_score, value_score, and ranks
- `disclosures` — id, ticker, date, type, title, url (used for alert dedup)
- `sentiment` — id, ticker, date, score, category, key_events, summary, opportunistic_flag, risk_flag, headlines
- `members` — id, discord_name, discord_id, email, plan, status, expiry_date, notes, created_at
- `subscriptions` — id, member_id, plan, amount, paid_at, expiry_date, notes
- `activity_log` — id, category, action, detail, status, timestamp

---

## 7. SYSTEM RULES — NON-NEGOTIABLE

### Deterministic scoring
- Scoring logic is pure Python — no AI, no ML, no randomness
- Same inputs always produce same outputs
- Never modify weights or thresholds without explicit instruction

### AI model discipline
- Pipeline AI calls → `PIPELINE_AI_MODEL` (Haiku) from `config.py`
- Self-repair AI calls → `SELF_REPAIR_MODEL` (Sonnet) from `config.py`
- Never hardcode model strings in application files

### Data integrity
- Never invent or approximate missing financial data
- Missing values = `None`, not `0` or estimated values
- Flag suspicious values (negative equity, yield > 25%, etc.)
- All values from PSE Edge only — no third-party data sources

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

This system is deterministic in calculation, but educational in communication.
All PDF explanations, stock summaries, and breakdown text must follow this framework.

### Role when writing report text
Senior investment learning designer — not a salesperson, not a promoter.

### Writing style
1. Simple language. Short sentences.
2. Explain financial terms immediately in plain English.
3. Never assume prior investing knowledge.
4. Always explain both strengths and risks.
5. Never promise returns. Never imply a recommendation.
6. Always reinforce that intrinsic value is a mathematical estimate — not a price target.

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
news_fetcher.py, sentiment_engine.py.
223 PSE stocks scraped. DB live at AppData/Local/pse_quant/.

### Phase 4 — Automation ✅ COMPLETE
scheduler.py — daily scoring at 17:30 PHT, alert check at 09:00 PHT.
alert_engine.py — price, dividend, earnings alerts with first-run dedup.

### Phase 5 — Dashboard ✅ COMPLETE
Local Flask dashboard at http://localhost:8080.
Member management, PayMongo payment links, pipeline controls, analytics.

### Phase 6 — Scoring Enhancement ✅ COMPLETE
Fundamental Momentum layer added to all 3 portfolio scorers.
- `engine/scorer_momentum.py` — Split-Window CAGR Delta + OCF mean-comparison
- Signals: Revenue Momentum (40%), EPS Momentum (35%), Operating CF Momentum (25%)
- 10% weight in all portfolios; graceful None fallback via `_blend()`
- Requires: `revenue_5y`, `eps_5y`, `operating_cf_history` (newest-first lists, min 4 values)
- Config: `MOMENTUM_MIN_YEARS = 4` in `config.py`

### Phase 7 — Backtester ✅ COMPLETE
`backtester.py` — fundamental score simulation across historical years.
- Re-runs scoring model for each year using only financials available at that time
- Measures rank consistency, Spearman correlation, portfolio turnover, score trajectories
- Uses current prices with historical fundamentals (no multi-year price archive)
- CLI: `py backtester.py --portfolio pure_dividend --years 2022 2023 2024 2025`
- Includes educational disclaimer per CLAUDE.md 7A

### Phase 8 — Stability & Bug Fixes ✅ COMPLETE (2026-03-09)
- [x] PDF report now shows ALL qualifying stocks (not capped at 10)
  - `reports/pdf_generator.py`: removed `[:10]` slice; heading shows "ALL N QUALIFYING STOCKS"
  - `main.py`: `_try_enrich_with_sentiment(ranked)` enriches full list (no slice)
- [x] Duplicate Discord alert fix — atomic dedup via `_claim_disclosure()`
  - `alerts/alert_engine.py`: `_claim_disclosure()` uses `INSERT OR IGNORE` + `rowcount`
    to atomically claim each alert slot BEFORE sending — prevents duplicates even
    when multiple `py scheduler.py` processes run simultaneously
- [x] Production readiness audit passed — all 50+ files present, all under 500 lines

### Phase 9 — Unified Scoring System ✅ COMPLETE (2026-03-14)
- [x] Unified 4-layer scoring engine (`engine/scorer_v2.py` + 4 sub-modules)
- [x] Unified health filter (`engine/filters_v2.py`)
- [x] Stock Lookup dashboard page (`dashboard/routes_stocks.py` + `templates/stocks.html`)
  - Search by ticker OR company name with live autocomplete
  - Shows score, letter grade, MoS, IV, 4-layer breakdown, key metrics, financial history
- [x] Scheduler start/stop from Pipeline page (`dashboard/background.py`)
- [x] Overview page shows unified StockPilot PH Rankings (single table)
- [x] Schedule times updated: alert 09:00 PHT, scoring 17:30 PHT
- [x] Discord webhooks simplified: `DISCORD_WEBHOOK_VALUE` (StockPilot Picks) + `DISCORD_WEBHOOK_ALERTS`
- [x] PDF cover page "About" section shortened to 3-line summary

### Phase 10 — Next (Backlog)
- [ ] Manual data entry UI — for GSMI 2022, GLO 2022 (missing from PSE Edge)
- [ ] REIT FFO-based FCF coverage exemption in dividend filters
- [ ] Export rankings to CSV/Excel from dashboard

---

## 9. HOW TO RUN THE SYSTEM

```bash
# Full unified pipeline
py main.py

# Dry run (no Discord publish)
py main.py --dry-run

# Scheduler (continuous — runs on schedule)
# Alert check: weekdays 09:00 PHT
# Scoring job: weekdays 17:30 PHT
py scheduler.py

# Run scoring job now
py scheduler.py --run-now

# Run alert check now
py scheduler.py --run-alerts

# You can also start/stop the scheduler from the Pipeline page in the dashboard

# Alerts only
py alerts/alert_engine.py --dry-run
py alerts/alert_engine.py --check price
py alerts/alert_engine.py --check dividend
py alerts/alert_engine.py --check earnings

# Local dashboard
py dashboard/app.py
# Open: http://localhost:8080

# Test sentiment for one ticker
py engine/sentiment_engine.py --ticker DMC

# Run individual tests
py tests/test_metrics.py
py tests/test_filters.py
py tests/test_scorer.py
py tests/test_mos.py
py tests/test_pdf.py
py tests/test_discord.py
```

**Python command on this machine: `py` (not `python`)**
Python version: 3.14.x
Location: `C:\Users\Josh\AppData\Local\Python\pythoncore-3.14-64\`

---

## 10. INSTALLED PACKAGES

```
requests, beautifulsoup4, pdfplumber, reportlab,
apscheduler, pydantic, pandas, pytest,
python-dotenv, lxml, anthropic, flask
```

Install missing: `py -m pip install <package_name>`

---

## 11. ENVIRONMENT VARIABLES (.env)

```
# Discord webhooks (only 2 needed now)
DISCORD_WEBHOOK_VALUE=https://discord.com/api/webhooks/...      # StockPilot Picks channel
DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/...     # Alerts channel

# PSE Edge login
PSE_EDGE_EMAIL=your@email.com
PSE_EDGE_PASSWORD=yourpassword

# AI sentiment (optional — dashboard works without this)
ANTHROPIC_API_KEY=sk-ant-...

# PayMongo (optional — dashboard works without this)
PAYMONGO_SECRET_KEY=sk_test_...
MONTHLY_PRICE_CENTAVOS=29900
ANNUAL_PRICE_CENTAVOS=299900
```

Load with:
```python
from dotenv import load_dotenv
import os
load_dotenv()
webhook = os.getenv('DISCORD_WEBHOOK_VALUE')
```

---

## 12. SELF-CORRECTION PROTOCOL

When you encounter an error:

1. **Read the full error message** — identify file, line, and type
2. **Read the relevant source file** — understand context before fixing
3. **Fix the minimal change needed** — do not refactor unrelated code
4. **Re-run immediately** — confirm the fix works
5. **If still failing after 3 attempts** — report the error to the user
   with: what you tried, what failed, and what you need from them

**If adding AI-assisted self-repair logic, use `SELF_REPAIR_MODEL` (Sonnet).**

Common errors on this Windows setup:
- `ModuleNotFoundError` → run `py -m pip install <module>`
- `FileNotFoundError` → create the directory first with `os.makedirs`
- `SyntaxError` → check indentation and missing colons
- `KeyError` on stock dict → add `.get('key', default)` not `['key']`
- `return outside function` → check indentation of return statements
- `UnicodeEncodeError` in print() → replace Unicode box chars with ASCII
- SQL `SUM()` on empty table → returns NULL rows, always coerce with `or 0`

---

## 13. NEXT TASK QUEUE

Work through these in order. Complete and test each before moving on.

1. Add `ANTHROPIC_API_KEY` to `.env` → activates news sentiment in PDF reports
2. Add `DISCORD_WEBHOOK_ALERTS` to `.env` → activates opportunistic alerts
3. Add `PAYMONGO_SECRET_KEY` to `.env` → activates payment link generation
4. Manual data entry for GSMI 2022 and GLO 2022 (missing from PSE Edge — enter from PSE Edge PDF disclosures directly)
5. Build `backtester.py` — historical model performance vs PSEi benchmark

---

## 14. DISCORD SETUP

Two channels needed:
- `#stockpilot-picks` (or any name) — Unified rankings PDF report, mapped to `DISCORD_WEBHOOK_VALUE`
- `#pse-alerts` — Price / dividend / earnings alerts + opportunistic flags, mapped to `DISCORD_WEBHOOK_ALERTS`

To get a webhook URL:
Discord → Channel Settings → Integrations → Webhooks → New Webhook → Copy URL

Paste webhook URLs into `.env` only (not config.py).

---

## 15. BACKTESTING NOTES (Phase 6)

Per the project instruction manual:
- Focus on statistical interpretation — not return guarantees
- Highlight drawdown risk
- Compare against PSEi benchmark logically
- Identify factor instability across time periods
- Suggest sensitivity testing on weights
- Never declare the model superior without statistical evidence
- Never infer future performance from historical results

---

## 16. IMPORTANT FILESYSTEM NOTE

Python (via Bash tool) **cannot write new files** to `C:\Users\Josh\Documents\`.
Use the **Write tool** directly to create new files — it bypasses this restriction.
PDFs are saved to Desktop (`C:\Users\Josh\Desktop\`) for this reason.
The SQLite DB lives at `C:\Users\Josh\AppData\Local\pse_quant\pse_quant.db`.

---

*Last updated: Phase 9 complete — unified scoring, stock lookup, scheduler control, simplified Discord (2026-03-14)*
*Project owner: Josh*
*Do not share this file or the .env file publicly.*
