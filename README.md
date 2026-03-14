# PSE Quant SaaS
### A Deterministic Multi-Factor Philippine Equity Ranking Engine

PSE Quant is a locally-run investment research tool for the Philippine Stock Exchange (PSE).
It automatically ranks every publicly listed PSE company across three portfolio strategies,
generates professional PDF research reports, delivers them to Discord, and alerts you
when important financial events happen — all on a hands-free weekly schedule.

This is a **research and educational tool**. It does not provide investment advice.
All reports are for informational purposes only.

---

## What It Does

### 1. Scrapes Financial Data
The system connects to **PSE Edge** (the official PSE disclosure platform) and downloads:
- Stock prices and market capitalisation
- Annual financial statements (revenue, earnings, equity, debt, cash flow)
- Dividend history (per-share amounts, ex-dates)
- Corporate disclosures (quarterly earnings filings, dividend declarations)

Data is stored in a local SQLite database on your machine. Nothing is sent to external servers.

### 2. Scores Every PSE Stock
Each stock is evaluated against three portfolio strategies. The scoring is **deterministic** —
the same data always produces the same score, with no randomness or AI guessing.

| Portfolio | What It Looks For | Min Requirements |
|-----------|-------------------|-----------------|
| **Pure Dividend** | Stable, high-yield income stocks | Yield ≥ 3%, 4 of 5 dividend years paid, payout ≤ 90%, MoS ≥ 25% |
| **Dividend Growth** | Companies consistently growing dividends | CAGR > 0%, payout ≤ 75%, MoS ≥ 20% |
| **Value** | Underpriced businesses with strong fundamentals | P/E, P/B, ROE, CAGR screens, MoS ≥ 30% |

Stocks that do not meet the minimum requirements are **filtered out before scoring**.
Only qualifying stocks receive a 0–100 score.

### 3. Calculates Margin of Safety
For each stock, the system calculates an **intrinsic value** — a mathematical estimate
of what the business is worth based on earnings, cash flow, and dividends.

Three models are used:
- **DDM** (Dividend Discount Model) — for dividend stocks
- **DCF** (Discounted Cash Flow) — for cash-generating businesses
- **EPS × PE** — earnings-based fair value estimate

The **Margin of Safety** is the percentage discount between the intrinsic value and
the current market price. A larger margin means more cushion if our estimates are off.

> Intrinsic value is a mathematical reference point — not a price prediction or target.

### 4. Enriches with News Sentiment (Optional)
For all qualifying stocks per portfolio, the system fetches recent news headlines
from Yahoo Finance and Philippine business news sources, then uses **Claude Haiku**
(an AI model by Anthropic) to classify the tone as Positive, Neutral, or Negative.

Sentiment is **informational only** — it does not change any score.
It appears in the PDF report as context alongside the financial analysis.

To activate this feature, add your `ANTHROPIC_API_KEY` to the `.env` file.

### 5. Generates PDF Research Reports
Each portfolio run produces a professional A4 PDF report containing:
- Cover page with methodology overview
- Rankings table (all qualifying stocks, ranked by score)
- Individual detail page for **every qualifying stock** (not capped at 10):
  - Score breakdown by metric (with weights and plain-English explanations)
  - Intrinsic value calculation and Margin of Safety
  - News sentiment summary (if enabled)
- Full methodology and disclaimer page

Reports are written for **beginner investors**. Every financial term is explained
in plain language. No jargon is left undefined.

### 6. Delivers Reports to Discord
After generating a PDF, the system automatically sends it to your designated
Discord channels:
- `#pse-dividend` — Pure dividend portfolio
- `#pse-growth` — Dividend growth portfolio
- `#pse-value` — Value portfolio

It also sends a text summary with the top 5 ranked stocks per portfolio.

### 7. Sends Real-Time Alerts
The alert engine monitors PSE Edge continuously for:
- **New dividend declarations** — notifies when a company declares a dividend
- **New earnings filings** — notifies when a quarterly or annual result is filed
- **Price triggers** — notifies when a stock drops below its calculated buy price

Alerts are delivered to a `#pse-alerts` Discord channel.
The system prevents duplicate alerts — each event is only notified once, using
atomic database writes that prevent duplicates even if multiple scheduler
instances run simultaneously.

### 8. Runs on a Schedule
The scheduler runs two jobs automatically:
- **06:30 PHT (weekdays)** — Alert check: scans PSE Edge for new events
- **16:00 PHT (weekdays)** — Full scoring run: scrape → score → report → publish

You can also trigger any job manually via the dashboard or command line.

### 9. Local Admin Dashboard
A browser-based dashboard runs at `http://localhost:8080` and lets you:
- **Overview** — See system status, member counts, recent activity
- **Pipeline** — Trigger scoring runs or alert checks manually
- **Members** — Add, edit, extend, and manage Discord member subscriptions
- **Analytics** — Revenue charts, member growth, plan distribution
- **Settings** — View webhook status, DB table sizes, configuration

Member subscriptions use **PayMongo** for payment link generation.
The flow is manual: generate a link → send to the member → mark as paid when confirmed.

---

## How It Works (Technical)

```
PSE Edge (web scraper)
    ↓
SQLite Database (local)
    ↓
Filter engine (minimum thresholds)
    ↓
Scoring engine (0-100 weighted multi-factor score)
    ↓
Margin of Safety calculator (DDM / DCF / EPS×PE)
    ↓
News enrichment (Claude Haiku, all qualifying stocks)
    ↓
PDF report generator (ReportLab)
    ↓
Discord delivery (webhook)
    ↓
Alert engine (dividend, earnings, price triggers)
```

### Key Design Principles
- **Deterministic** — same data always produces the same output. No AI in the scoring.
- **Local-first** — all data stays on your machine. No cloud dependencies.
- **Fail-safe** — missing data is `None`, not estimated. Bad data is flagged, not hidden.
- **Educational** — every report is written to teach, not to sell.

---

## Scoring Methodology

### Pure Dividend Score (v4 — includes Fundamental Momentum)
| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Dividend Yield | 18% | Income return relative to price |
| FCF Yield | 14% | Free cash flow as % of market cap |
| Quality Composite | 18% | ROE (50%) + Cash Flow Quality (50%) |
| EPS Stability | 14% | Consistency of earnings over time |
| Leverage + Coverage | 14% | D/E, FCF coverage, interest coverage blend |
| Relative Valuation | 12% | P/E and EV/EBITDA blend |
| Fundamental Momentum | 10% | Revenue + EPS + Operating CF trend acceleration |

### Dividend Growth Score (v4 — includes Fundamental Momentum)
| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Growth Composite | 18% | EPS Growth (60%) + Growth Consistency (40%) |
| Dividend CAGR | 17% | How fast dividends are growing per year |
| Quality Composite | 14% | ROE (50%) + Cash Flow Quality (50%) |
| Dividend Yield | 14% | Current income yield |
| Payout Headroom | 14% | Room to raise dividends further |
| Leverage Stability | 13% | D/E and FCF coverage blend |
| Fundamental Momentum | 10% | Revenue + EPS + Operating CF trend acceleration |

### Value Score (v4 — includes Fundamental Momentum)
| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Valuation Composite | 27% | P/E + EV/EBITDA + FCF Yield + Earnings Yield vs Bonds (25% each) |
| Quality Composite | 27% | ROE (40%) + EPS Stability (30%) + Cash Flow Quality (30%) |
| Growth Composite | 17% | Revenue CAGR (60%) + Growth Consistency (40%) |
| Leverage Risk | 19% | D/E and interest coverage blend |
| Fundamental Momentum | 10% | Revenue + EPS + Operating CF trend acceleration |

**Fundamental Momentum** measures whether a company's key financial metrics are
accelerating or decelerating. It splits the historical data series into two halves
and compares the more recent half against the earlier half. Improving trends score
higher; deteriorating trends score lower. Missing data reduces its weight gracefully.

Cash Flow Quality = Operating CF / Net Income. Ratio ≥ 1.0 means earnings are backed by real cash.
Earnings Yield vs Bonds = stock earnings yield minus PH 10Y bond rate (6.5%). Positive spread means the stock out-earns risk-free bonds.
Growth Consistency penalizes erratic revenue/EPS patterns (high coefficient of variation).

> Weights and thresholds are fixed and deterministic. They are never modified
> without explicit instruction from the project owner.

---

## Intrinsic Value Models

### Dividend Discount Model (DDM)
Used for pure dividend stocks. Projects future dividends and discounts them
to present value using the risk-free rate (PH 10-year T-bond: 6.5%) plus
an equity risk premium (5.0%).

Growth rate is capped at 7% to prevent unrealistic valuations.

### Discounted Cash Flow (DCF)
Used for value stocks. Projects free cash flow forward and discounts at the
company's estimated cost of equity.

### EPS × Target PE
Simple earnings-based model: multiply current EPS by the market's fair PE multiple (15×).
Used as a cross-check on the other models.

### Combined Intrinsic Value
The final intrinsic value is a weighted average of whichever models have sufficient data.
Margin of Safety = (Intrinsic Value − Current Price) / Intrinsic Value × 100%.

---

## Data Sources

**Primary source: PSE Edge (edge.pse.com.ph)**
- Official PSE disclosure platform
- All financial data, prices, and corporate announcements
- Requires a free PSE Edge account

**News sources (for sentiment only):**
- Yahoo Finance RSS (Philippine stocks, `.PS` suffix)
- BusinessWorld Online
- Inquirer Business

All data is sourced from publicly available information.
No premium data subscriptions required.

---

## Setup

### Requirements
- Windows 10 or 11
- Python 3.11+ (installed at `C:\Users\Josh\AppData\Local\Python\`)
- A PSE Edge account (free registration at edge.pse.com.ph)
- A Discord server with webhook URLs configured

### Installation
```bash
# Install Python packages
py -m pip install requests beautifulsoup4 pdfplumber reportlab
py -m pip install apscheduler pydantic pandas pytest
py -m pip install python-dotenv lxml anthropic flask
```

### Configuration
Create a `.env` file in the project root:
```
PSE_EDGE_EMAIL=your@email.com
PSE_EDGE_PASSWORD=yourpassword

DISCORD_WEBHOOK_PURE_DIVIDEND=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_DIVIDEND_GROWTH=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_VALUE=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/...

# Optional — enables AI news sentiment
ANTHROPIC_API_KEY=sk-ant-...

# Optional — enables PayMongo payment links in dashboard
PAYMONGO_SECRET_KEY=sk_test_...
MONTHLY_PRICE_CENTAVOS=29900
ANNUAL_PRICE_CENTAVOS=299900
```

### Running the System
```bash
# Run the full pipeline once
py main.py

# Start the scheduler (runs on schedule automatically)
py scheduler.py

# Open the admin dashboard
py dashboard/app.py
# Then open http://localhost:8080 in your browser

# Manual pipeline controls
py main.py --portfolio pure_dividend
py main.py --dry-run                  # generates report but skips Discord
py scheduler.py --run-now             # trigger scoring immediately
py scheduler.py --run-alerts          # trigger alert check immediately
```

---

## File Structure

```
pse-quant-saas/
├── config.py           Central configuration (models, thresholds, URLs)
├── main.py             Pipeline entry point
├── scheduler.py        Automated job scheduler
│
├── engine/             Scoring and calculation logic
│   ├── metrics.py      Financial ratio calculations
│   ├── filters.py      Portfolio eligibility filters
│   ├── scorer.py       0-100 scoring engine
│   ├── mos.py          Margin of Safety calculator
│   ├── validator.py    Data quality checks
│   └── sentiment_engine.py  AI news sentiment (Claude Haiku)
│
├── scraper/            Data collection from PSE Edge
│   ├── pse_edge_scraper.py  Main scraper
│   └── news_fetcher.py      News headline fetcher
│
├── db/                 SQLite database layer
│   └── database.py     Facade (all DB functions exported here)
│
├── reports/            PDF report generation
│   └── pdf_generator.py     Report builder (ReportLab)
│
├── discord/            Discord delivery
│   └── publisher.py    Webhook sender
│
├── alerts/             Real-time alerts
│   └── alert_engine.py      Dividend, earnings, price alerts
│
├── dashboard/          Local admin dashboard (Flask)
│   ├── app.py          Entry point — runs on localhost:8080
│   ├── db_members.py   Member management DB operations
│   └── templates/      HTML templates for dashboard pages
│
└── tests/              Unit tests for all engine components
```

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

*PSE Quant SaaS — Built for the Philippine retail investor.*
*Version: Phase 8 (production) | Last updated: 2026-03-09*
