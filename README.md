# PSE Quant SaaS — StockPilot PH
### A Deterministic Multi-Factor Philippine Equity Ranking Engine

PSE Quant is a locally-run investment research tool for the Philippine Stock Exchange (PSE).
It automatically ranks every publicly listed PSE company using a unified 4-layer fundamental
scoring system, generates professional PDF research reports, delivers them to Discord,
and powers a premium Discord bot (StockPilot PH) — all on a hands-free schedule.

This is a **research and educational tool**. It does not provide investment advice.
All reports are for informational purposes only.

---

## What It Does

### 1. Scrapes & Validates Financial Data
The system connects to **PSE Edge** (the official PSE disclosure platform) and downloads:
- Stock prices and market capitalisation
- Annual financial statements (revenue, earnings, equity, debt, cash flow)
- Dividend history (per-share amounts, ex-dates)
- Corporate disclosures (quarterly earnings filings, dividend declarations)

After every scrape, an automated **data quality pipeline** runs:
- **Canary checks** — validates that PSE Edge page structure hasn't changed; alerts admin via DM if patterns break
- **Unit validation** — requires explicit currency line; cross-validates revenue/share and EPS/NI ratios
- **Write gate** — blocks dividend yields > 25% (non-REIT) or > 35% (REIT) at scrape time
- **DPS auto-cleaner** — nulls any dividend yield > 20% (non-REIT) or > 30% (REIT) post-scrape
- **Full audit** — checks payout ratios, EPS/NI mismatches, revenue anomalies, and implausible figures
- **Audit log** — issues recorded to the dashboard activity log for review
- **Scheduler heartbeat** — monitors scheduler health; alerts admin if process stops responding

Data is stored in a local SQLite database on your machine. Nothing is sent to external servers.

### 2. Scores Every PSE Stock
Every stock is scored using the **StockPilot PH Rankings** system — a unified 3-layer
sector-aware fundamental framework. The scoring is **deterministic** — the same data always produces
the same score, with no randomness or AI guessing.

**Portfolio-specific weights** (weights vary by investment objective):
| Layer | Dividend | Value | What It Measures |
|-------|----------|-------|-----------------|
| **Health** | 30% | 35% | Financial health today (ROE, NI margin, D/E, FCF, EPS stability) — sector-specific metrics |
| **Improvement** | 25% | 30% | Fundamentals improving (Revenue, EPS, ROE deltas) — recency-weighted (50/30/20) |
| **Persistence** | 45% | 35% | Improvement consistent and reliable (direction + magnitude + streak) |

Scoring is **sector-aware**: banks, REITs, holding firms, property, industrial, mining, and services
each use tailored sub-score metrics and weights. This prevents penalizing stocks for how their
industry naturally operates (e.g., banks don't need FCF yield; REITs use FFO not earnings).

The PDF shows two portfolio sections: **Dividend** and **Value**. A stock can qualify for both.
Each stock carries a **data confidence multiplier** (5yr=1.0, 4yr=0.9, 3yr=0.8, 2yr=0.65)
that reduces the final score for limited data.

**Dynamic score threshold**: Rankings show only stocks scoring above **mean + 0.5 SD** of the
scored universe, with a hard floor at 45. This threshold recalculates every run, ensuring
top-tier quality regardless of market conditions.

### 3. Calculates Margin of Safety
For each stock, the system calculates an **intrinsic value** — a mathematical estimate
of what the business is worth based on earnings, cash flow, and dividends.

Three models are used:
- **DDM** (Dividend Discount Model) — for dividend stocks
- **DCF** (Discounted Cash Flow) — for cash-generating businesses
- **EPS × PE** — earnings-based fair value estimate

The discount rate is **risk-adjusted** by company size (0-5% premium) and sector
(0-2% premium), so riskier companies get a more conservative valuation.

The **Margin of Safety** is the percentage discount between the intrinsic value and
the current market price. A larger margin means more cushion if our estimates are off.

> Intrinsic value is a mathematical reference point — not a price prediction or target.

### 4. Enriches with News Sentiment (Optional)
For qualifying stocks, the system fetches recent news headlines from Yahoo Finance
and Philippine business news sources, then uses **Claude Haiku** to classify the tone
as Positive, Neutral, or Negative.

Sentiment is **informational only** — it does not change any score.
To activate: add `ANTHROPIC_API_KEY` to `.env`.

### 5. Generates PDF Research Reports
Each run produces a professional A4 PDF report containing:
- Cover page with methodology overview
- Rankings table (all qualifying stocks, ranked by score)
- Individual detail page for every qualifying stock:
  - Score breakdown by layer (with weights and plain-English explanations)
  - Intrinsic value calculation and Margin of Safety
  - News sentiment summary (if enabled)
- Full methodology and disclaimer page

Reports are written for **beginner investors**. Every financial term is explained
in plain language.

### 6. Delivers Reports to Discord
After generating a PDF, the system sends it to designated Discord channels:
- `#rankings` — Full StockPilot PH Rankings PDF report (premium members)
- `#deep-analysis` — Stock of the Week, monthly performance (premium members)
- `#daily-briefing` — Top 3 grades only, no scores (public)
- `#alerts` — Price, dividend, and earnings alerts (public)

### 7. Discord Bot — StockPilot PH
A slash-command Discord bot gives premium members on-demand access to rankings data.

| Command | Access | Description |
|---------|--------|-------------|
| `/help` | Free, anywhere | Commands guide and glossary |
| `/subscribe` | Free, DM only | Pricing and payment link |
| `/mystatus` | Free, DM only | Subscription tier and expiry |
| `/top10` | Premium, DM only | Current top 10 with full scores |
| `/stock <ticker>` | Premium, DM only | Full analysis for any PSE stock |
| `/watchlist show/add/remove` | Premium, DM only | Personal stock watchlist (max 20) |
| `/admin list/pending/confirm/extend/status` | Josh only, DM | Member management |

Free users see grade only (A/B/C). Premium members see scores, MoS, IV, and 3-layer breakdown.

### 8. Sends Real-Time Alerts
The alert engine monitors PSE Edge for:
- **New dividend declarations** — notifies when a company declares a dividend
- **New earnings filings** — notifies when a quarterly or annual result is filed
- **Price triggers** — notifies when a stock drops below its calculated buy price

The system prevents duplicate alerts using atomic database writes.

### 9. Runs on a Schedule
| Job | When | What |
|-----|------|------|
| Disclosure monitor | Every 15 min | PSE Edge feed polling |
| Alert check | Weekdays 06:30 PHT | Price, dividend, earnings alerts |
| Scoring | Weekdays 17:30 PHT | Score all stocks, detect rank changes |
| Report | Weekdays 18:00 PHT | Send PDF if rankings changed |
| Full scrape | Sunday 22:00 PHT | Refresh all financials from PSE Edge |
| Stock of the Week | Monday 08:00 PHT | Biggest score mover → #deep-analysis |
| Weekly Digest DM | Friday 17:00 PHT | Personalised DM to premium members |
| Expiry reminders | Daily 09:00 PHT | 7d, 1d, 0d before subscription expiry |
| Monthly reports | 1st of month 09:00 PHT | Dividend calendar + model performance |

### 10. Local Admin Dashboard
A browser-based dashboard at `http://localhost:8080`:
- **Overview** — Unified StockPilot PH Rankings, member counts, recent activity
- **Pipeline** — Trigger scoring runs or alert checks manually; start/stop scheduler
- **Stock Lookup** — Search any PSE stock by ticker or company name
- **Members** — Add, edit, extend, and manage Discord member subscriptions
- **Analytics** — Revenue charts, member growth, plan distribution
- **Settings** — Webhook status, DB table sizes, configuration

---

## How It Works (Technical)

```
PSE Edge (web scraper)
    ↓
Data Quality Pipeline (DPS auto-clean + full audit)
    ↓
SQLite Database (local)
    ↓
Filter engine (minimum health thresholds)
    ↓
Scoring engine (0-100 weighted 4-layer score)
    ↓
Margin of Safety calculator (DDM / DCF / EPS×PE)
    ↓
News enrichment (Claude Haiku, optional)
    ↓
PDF report generator (ReportLab)
    ↓
Discord delivery (webhooks + bot)
    ↓
Alert engine (dividend, earnings, price triggers)
```

### Key Design Principles
- **Deterministic** — same data always produces the same output. No AI in the scoring.
- **Local-first** — all data stays on your machine. No cloud dependencies.
- **Fail-safe** — missing data is `None`, not estimated. Bad data is flagged, not hidden.
- **Data quality first** — every scrape is automatically audited and cleaned.
- **Educational** — every report is written to teach, not to sell.

---

## Scoring Methodology

### StockPilot PH Rankings — Sector-Aware 3-Layer Score

Each of the 3 layers (Health, Improvement, Persistence) uses **different sub-score metrics
depending on sector group** (bank, REIT, holding firm, property, industrial, mining, services/general):

| Layer | Dividend | Value | What It Measures |
|-------|----------|-------|-----------------|
| **Health** | 30% | 35% | ROE, NI margin, D/E, EPS stability, FCF yield, dividend yield — sub-scores chosen per sector |
| **Improvement** | 25% | 30% | Revenue, EPS, ROE deltas — recency-weighted (50/30/20 newest-first) |
| **Persistence** | 45% | 35% | Direction consistency + growth magnitude + streak bonus — no sector modification |

**Key principles:**
- **Sector-aware**: Banks exclude D/E (use 10× limit instead); REITs use FFO-equivalent metrics; holding firms skip FCF requirements
- **Missing factors handled dynamically**: If a factor is unavailable, weight redistributes to available factors (never forces zeros as penalties)
- **Data confidence multiplier**: 5yr data=1.0×, 4yr=0.9×, 3yr=0.8×, 2yr=0.65× — multiplied into final score
- **Dynamic threshold**: mean + 0.5 SD of scored universe; hard floor at 45

Health thresholds are calibrated from PSE market percentiles (top-10% = excellent, median = average).

**Health filter** (pass/fail before scoring):
- Minimum 2 years of EPS and Revenue data
- Normalized EPS must be positive
- No persistent negative earnings (3-year average)
- D/E ≤ 3.0× (non-financial), ≤ 10× (bank), or ≤ 4.0× (REIT)

---

## Setup

### Requirements
- Windows 10 or 11
- Python 3.11+ (`py` command)
- A PSE Edge account (free at edge.pse.com.ph)
- A Discord server with webhook URLs and a bot token

### Installation
```bash
py -m pip install requests beautifulsoup4 pdfplumber reportlab
py -m pip install apscheduler pydantic pandas pytest
py -m pip install python-dotenv lxml anthropic flask discord.py
```

### Configuration
Create a `.env` file in the project root:
```
# PSE Edge credentials
PSE_EDGE_EMAIL=your@email.com
PSE_EDGE_PASSWORD=yourpassword

# Discord webhooks (4 channels)
DISCORD_WEBHOOK_RANKINGS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_DEEP_ANALYSIS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_DAILY_BRIEFING=https://discord.com/api/webhooks/...

# Discord bot
DISCORD_BOT_TOKEN=your_bot_token_here
ADMIN_DISCORD_ID=your_discord_user_id
DISCORD_INVITE_URL=https://discord.gg/your_invite

# Optional: instant guild sync during bot testing
DISCORD_GUILD_ID=your_server_id

# Optional: AI news sentiment
ANTHROPIC_API_KEY=sk-ant-...

# Optional: PayMongo payment links
PAYMONGO_SECRET_KEY=sk_test_...
MONTHLY_PRICE_CENTAVOS=9900
ANNUAL_PRICE_CENTAVOS=99900
```

### Running the System
```bash
# Full unified pipeline (score + PDF + Discord)
py main.py

# Dry run (no Discord publish)
py main.py --dry-run

# Start the scheduler (runs on automatic schedule)
py scheduler.py

# Start the Discord bot
py discord/bot.py

# Open the admin dashboard
py dashboard/app.py        # then open http://localhost:8080

# Manual pipeline triggers
py scheduler.py --run-now           # trigger full scoring cycle
py scheduler.py --run-alerts        # trigger alert check
py scheduler.py --run-weekly        # trigger full financial scrape
py scheduler.py --run-score         # scoring phase only (4 PM job)
py scheduler.py --run-report        # report phase only (6 PM job)
py scheduler.py --run-sotw          # Stock of the Week
py scheduler.py --run-digest        # Weekly Digest DMs
py scheduler.py --run-monthly       # Monthly reports
py scheduler.py --run-backfill      # Historical data backfill (2018-2023)

# Threshold calibration
py engine/calibrate_thresholds.py   # Derive thresholds from DB percentiles

# Data quality
py db/db_data_quality.py            # full audit of all stocks
py db/db_data_quality.py --ticker DMC  # audit one ticker
```

---

## File Structure

```
pse-quant-saas/
├── config.py               Central configuration
├── main.py                 Pipeline entry point
├── scheduler.py            Automated job scheduler
│   ├── scheduler_data.py
│   └── scheduler_jobs.py
│
├── engine/                 Scoring and calculation logic
│   ├── metrics.py          Financial ratio calculations
│   ├── filters_v2.py       Health filter (pass/fail, 2yr min)
│   ├── scorer_v2.py        Unified 3-layer scorer (portfolio-specific weights)
│   ├── scorer_health.py    Health layer (sector-aware sub-scores)
│   ├── scorer_improvement.py  Improvement layer (recency-weighted deltas)
│   ├── scorer_persistence.py  Persistence layer (direction + magnitude + streak)
│   ├── scorer_utils.py     Blending and normalization utilities
│   ├── sector_groups.py    Sector classification + layer config lookup
│   ├── mos.py              Margin of Safety (risk-adjusted discount rate)
│   ├── validator.py        Pre-scoring data validation + confidence calc
│   ├── calibrate_thresholds.py  Percentile-based threshold derivation
│   └── sentiment_engine.py AI news sentiment (Claude Haiku, optional)
│
├── scraper/                Data collection from PSE Edge
│   ├── pse_edge_scraper.py Main scraper facade
│   │   ├── pse_session.py
│   │   ├── pse_lookup.py
│   │   ├── pse_stock_data.py   Dividend scraper (COMMON-only, deduped)
│   │   └── pse_financial_reports.py
│   └── news_fetcher.py     News headline fetcher
│
├── db/                     SQLite database layer
│   ├── database.py         Facade (all DB functions exported here)
│   ├── db_connection.py    SQLite connection + DB_PATH
│   ├── db_schema.py        Table creation (init_db)
│   ├── db_financials.py    Financial data CRUD (yield gate at write)
│   ├── db_data_quality.py  Post-scrape data quality auditor
│   └── db_maintenance.py   DPS auto-cleaner + stale data pruner
│
├── reports/                PDF report generation
│   └── pdf_generator.py    Report builder (ReportLab)
│
├── discord/                Discord delivery and bot
│   ├── publisher.py        Webhook sender facade
│   ├── bot.py              Slash command bot (run standalone)
│   ├── bot_commands.py     /stock, /top10, /help logic
│   ├── bot_subscribe.py    /subscribe, /mystatus logic
│   ├── bot_watchlist.py    /watchlist logic
│   ├── bot_admin.py        /admin commands (Josh only)
│   ├── discord_dm.py       Direct message via Discord REST API
│   ├── discord_core.py
│   ├── discord_reports.py
│   └── discord_alerts.py
│
├── alerts/                 Real-time alerts
│   ├── alert_engine.py     Dividend, earnings, price alerts
│   └── disclosure_monitor.py  PSE Edge feed monitor (15-min)
│
├── dashboard/              Local admin dashboard (Flask)
│   ├── app.py              Entry point — runs on localhost:8080
│   ├── background.py       Pipeline threads + scheduler process control
│   ├── access_control.py   Member tier checking (check_access)
│   ├── db_members.py       Member management DB operations
│   ├── routes_home.py      Overview page
│   ├── routes_pipeline.py  Pipeline controls + scheduler start/stop
│   ├── routes_stocks.py    Stock Lookup page + autocomplete API
│   ├── routes_portal.py    Public portal/landing page
│   ├── routes_paymongo.py  PayMongo payment link generation
│   ├── templates/          HTML templates
│   └── static/             CSS + JS
│
└── tests/                  Unit tests for engine components
```

---

## Data Quality System

Every weekly scrape automatically runs a 3-layer quality pipeline:

**Layer 1 — Scraper (prevents bad data entering the DB)**
- Canary field checks — validates PSE Edge page structure before parsing
- COMMON shares whitelist — preferred/warrant dividends excluded
- Ex-date deduplication — amended circulars don't double-count
- Per-share rate cap — ₱0.001–₱100 per declaration
- Mandatory unit detection — requires explicit currency line (no silent defaults)
- Fiscal year mapping — dividends attributed to correct fiscal year, not ex-date year

**Layer 2 — Write gate (catches anything the scraper misses)**
- Dividend yield > 25% (non-REIT) or > 35% (REIT) at write time → blocked
- Negative revenue → blocked
- Unit plausibility cross-validation (revenue/share, EPS/NI mismatch, net margin)

**Layer 3 — Post-scrape audit (auto-runs after every weekly scrape)**
- `clean_bad_dps()` — nulls DPS where yield > 20%/30%
- `run_audit()` — checks payout ratios, EPS/NI mismatches, revenue anomalies
- Results logged to dashboard activity log

**Layer 4 — Staleness prevention**
- Price older than 7 days → excluded from scoring
- Financials older than 15 months → excluded from scoring
- Consecutive scrape failures → escalated to admin; auto-suspended after 7 failures
- Scheduler heartbeat monitored every 15 minutes

Run manually: `py db/db_data_quality.py`

---

## Disclaimer

This tool is for **research and educational purposes only**.

- It does not constitute financial advice.
- It does not recommend buying or selling any security.
- Past performance of any ranking model does not guarantee future results.
- Intrinsic value calculations are mathematical estimates based on historical data,
  not predictions of future stock prices.
- All investment decisions are your own responsibility.
- Always do your own due diligence before investing.

Data sourced from PSE Edge (Philippine Stock Exchange).
Sentiment analysis powered by Claude (Anthropic), for informational purposes only.

---

*StockPilot PH — Built for the Philippine retail investor.*
*Version: Phase 13 complete (sector-aware 3-layer scoring) | Last updated: 2026-03-24*
