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

---

## 2. PROJECT OVERVIEW

**What this system does:**
- Scrapes financial data from PSE Edge (edge.pse.com.ph)
- Parses and stores data in a local SQLite database
- Scores every PSE stock across 3 portfolio strategies
- Calculates Margin of Safety (intrinsic value vs current price)
- Generates professional PDF reports
- Delivers reports to Discord automatically on a schedule

**Three portfolio strategies:**
| Portfolio | Focus | Key Metrics |
|-----------|-------|-------------|
| DIVIDEND  | Passive income | Yield, Payout Ratio, FCF Coverage, Dividend CAGR |
| VALUE     | Undervalued businesses | P/E, P/B, EV/EBITDA, ROE, Revenue CAGR |
| HYBRID    | Income + Value combined | Blend of both above |

**Architecture pipeline:**
```
PSE Edge → Scraper → Parser → Validator → Database
                                              ↓
                              Metrics → Filter → Scorer → MoS
                                                            ↓
                                              PDF Report → Discord
```

---

## 3. PROJECT STRUCTURE

```
pse-quant-saas/
├── CLAUDE.md               ← YOU ARE HERE
├── .env                    ← API keys and config (never commit this)
├── main.py                 ← Entry point — runs the full pipeline
│
├── engine/                 ← Core calculation logic (DETERMINISTIC)
│   ├── metrics.py          ← Financial ratio calculators ✅ DONE
│   ├── filters.py          ← Portfolio eligibility filters ✅ DONE
│   ├── scorer.py           ← 0-100 scoring engine ✅ DONE
│   ├── mos.py              ← Margin of Safety calculator ✅ DONE
│   └── validator.py        ← Data validation layer ⬜ TODO
│
├── scraper/                ← PSE Edge data collection
│   ├── pse_scraper.py      ← Main scraper ⬜ TODO
│   ├── pdf_parser.py       ← Parses PSE Edge PDF disclosures ⬜ TODO
│   └── session.py          ← HTTP session manager ⬜ TODO
│
├── db/                     ← Database layer
│   ├── database.py         ← SQLite connection and schema ⬜ TODO
│   ├── models.py           ← Table definitions ⬜ TODO
│   └── pse_quant.db        ← SQLite database file (auto-created)
│
├── reports/                ← PDF generation
│   └── pdf_generator.py    ← PDF report builder ✅ DONE
│
├── discord/                ← Discord delivery
│   └── publisher.py        ← Sends reports to Discord ✅ DONE
│
├── alerts/                 ← Real-time alerts
│   └── alert_engine.py     ← Disclosure and price alerts ⬜ TODO
│
├── data/
│   ├── raw/                ← Raw scraped HTML/JSON
│   ├── parsed/             ← Cleaned JSON ready for DB
│   └── reports/            ← Generated PDF output files
│
└── tests/
    ├── test_metrics.py     ✅ DONE
    ├── test_filters.py     ✅ DONE
    ├── test_scorer.py      ✅ DONE
    ├── test_mos.py         ✅ DONE
    ├── test_pdf.py         ✅ DONE
    └── test_discord.py     ✅ DONE
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

### engine/filters.py
Functions: `filter_dividend_portfolio(stock)`,
`filter_value_portfolio(stock)`, `filter_hybrid_portfolio(stock)`
Each returns: `(eligible: bool, reason: str)`
Bank and REIT sector exemptions are already implemented.

### engine/scorer.py
Functions: `score_dividend(metrics)`, `score_value(metrics)`,
`score_hybrid(metrics)`
Each returns: `(score: float, breakdown: dict)`

Breakdown dict format:
```python
{
  'metric_name': {
    'score':       float,   # 0-100 sub-score
    'weight':      float,   # e.g. 0.30
    'value':       float,   # actual stock value
    'explanation': str,     # plain English specific to this stock
  }
}
```
**CRITICAL: Do not change weights or normalisation thresholds
without explicit instruction from the user. The scoring logic
is deterministic by design.**

### engine/mos.py
Functions: `calc_ddm`, `calc_eps_pe`, `calc_dcf`,
`calc_mos_price`, `calc_mos_pct`, `calc_hybrid_intrinsic`
Risk-free rate = 6.5% (PH 10Y T-bond). Update periodically.
Max DDM growth rate capped at 7% to prevent model explosion.

### reports/pdf_generator.py
Function: `generate_report(portfolio_type, ranked_stocks,
output_path, total_stocks_screened)`
Generates A4 PDF with cover page, rankings table,
per-stock detail with score breakdowns and explanations,
and methodology/disclaimer page.

### discord/publisher.py
Loads webhook URLs from `.env` via `python-dotenv`.
Functions: `send_report`, `send_dividend_alert`,
`send_price_alert`, `send_earnings_alert`,
`send_rescore_notice`, `test_webhook`

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

Target SQLite schema (to be built in Phase 3):

```sql
CREATE TABLE stocks (
    ticker          TEXT PRIMARY KEY,
    name            TEXT,
    sector          TEXT,
    is_reit         INTEGER DEFAULT 0,
    is_bank         INTEGER DEFAULT 0,
    last_updated    TEXT
);

CREATE TABLE financials (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT,
    year            INTEGER,
    revenue         REAL,
    net_income      REAL,
    equity          REAL,
    total_debt      REAL,
    cash            REAL,
    operating_cf    REAL,
    capex           REAL,
    ebitda          REAL,
    eps             REAL,
    dps             REAL,
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);

CREATE TABLE prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT,
    date            TEXT,
    close           REAL,
    market_cap      REAL,
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);

CREATE TABLE scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT,
    run_date        TEXT,
    dividend_score  REAL,
    value_score     REAL,
    hybrid_score    REAL,
    dividend_rank   INTEGER,
    value_rank      INTEGER,
    hybrid_rank     INTEGER,
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);

CREATE TABLE disclosures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT,
    date            TEXT,
    type            TEXT,
    title           TEXT,
    url             TEXT,
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);
```

---

## 7. SYSTEM RULES — NON-NEGOTIABLE

These come directly from the project's instruction manual:

### Deterministic scoring
- Scoring logic is pure Python — no AI, no ML, no randomness
- Same inputs always produce same outputs
- Never modify weights or thresholds without explicit instruction

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

---
## 7A. EDUCATIONAL COMMUNICATION LAYER — REPORT WRITING STANDARD

This system is deterministic in calculation,
but educational in communication.

All PDF explanations, stock summaries, and breakdown text
must follow this communication framework.

### ROLE WHEN WRITING REPORT TEXT

When generating any explanation text (PDF reports, score breakdown explanations, summaries):

You are a senior investment learning designer with 10+ years of experience
educating beginner Philippine retail investors.

You are not a salesperson.
You are not a hype promoter.
You are an educator.

---

### WRITING STYLE RULES

1. Use simple language.
2. Short sentences.
3. Explain financial terms immediately in plain English.
4. Never assume prior investing knowledge.
5. Always explain both strengths and risks.
6. Never promise returns.
7. Never imply a recommendation.
8. Always reinforce that intrinsic value is a mathematical estimate — not a price target.
9. Always reinforce that this is for research and educational purposes only.

---

### TONE

- Calm
- Analytical
- Neutral
- Beginner-friendly
- Rational
- Professional but understandable

Never:
- Use dramatic language
- Use urgency tactics
- Use phrases like “don’t miss out”
- Declare a stock “the best”
- Suggest guaranteed upside

---

### HOW TO EXPLAIN COMMON TERMS

When these terms appear in the report, explain them clearly:

P/E Ratio:
"You are paying ₱X for every ₱1 the company earns per year."

ROE:
"This measures how efficiently management uses shareholders’ money."

Debt/Equity:
"This shows how much the company relies on borrowed money."

Margin of Safety:
"The discount between our calculated intrinsic value and the current price.
A larger margin provides more cushion if our estimates are wrong."

Intrinsic Value:
"Our mathematical estimate of fair business value based on earnings,
cash flow, or dividends. It is not a price prediction."

---

### COMMUNICATION PRIORITY HIERARCHY

If any conflict occurs between depth and clarity:

1. Clarity > Complexity
2. Education > Technical jargon
3. Risk disclosure > Optimism
4. Neutrality > Persuasion

---

### OBJECTIVE OF REPORT TEXT

A beginner reading the PDF should feel:

- “I understand what this score means.”
- “I understand why this stock ranked where it did.”
- “I understand the risks.”
- “I am learning how value investing works.”

The goal is financial literacy — not stock promotion.

---

## 8. PHASE ROADMAP

### Phase 1 — Engine Core ✅ COMPLETE
All calculation and scoring logic. Tested with sample data.

### Phase 2 — Reports & Delivery ✅ COMPLETE
- [x] pdf_generator.py — professional PDF reports
- [x] publisher.py — Discord delivery via webhook
- [x] main.py — pipeline orchestrator (next task)

### Phase 3 — Data Pipeline ⬜ TODO
- [ ] database.py — SQLite schema and connection
- [ ] pse_scraper.py — scrape stock list and prices from PSE Edge
- [ ] pdf_parser.py — parse annual report PDFs with pdfplumber
- [ ] validator.py — validate and flag bad/missing data

### Phase 4 — Automation ⬜ TODO
- [ ] scheduler.py — APScheduler for weekly runs
- [ ] alert_engine.py — Discord alerts for new disclosures
- [ ] backtester.py — historical performance of scoring model

---

## 9. HOW TO RUN THE SYSTEM

```bash
# Run full pipeline (when complete)
py main.py

# Run individual tests
py tests/test_metrics.py
py tests/test_filters.py
py tests/test_scorer.py
py tests/test_mos.py
py tests/test_pdf.py
py tests/test_discord.py

# Generate reports with sample data
py tests/test_pdf.py
# Output: Desktop\PSE_DIVIDEND_REPORT.pdf etc.
```

**Python command on this machine: `py` (not `python`)**
Python version: 3.14.x
Location: `C:\Users\Josh\AppData\Local\Python\pythoncore-3.14-64\`

---

## 10. INSTALLED PACKAGES

All required packages are already installed:
```
requests, beautifulsoup4, pdfplumber, reportlab,
apscheduler, pydantic, pandas, pytest,
python-dotenv, lxml
```

Install missing packages with:
```bash
py -m pip install <package_name>
```

---

## 11. ENVIRONMENT VARIABLES

Create a `.env` file in the project root for secrets:
```
DISCORD_WEBHOOK_DIVIDEND=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_VALUE=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_HYBRID=https://discord.com/api/webhooks/...
PSE_EDGE_EMAIL=your@email.com
PSE_EDGE_PASSWORD=yourpassword
```

Load with:
```python
from dotenv import load_dotenv
import os
load_dotenv()
webhook = os.getenv('DISCORD_WEBHOOK_DIVIDEND')
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

Common errors on this Windows setup:
- `ModuleNotFoundError` → run `py -m pip install <module>`
- `FileNotFoundError` → create the directory first with `os.makedirs`
- `SyntaxError` → check indentation and missing colons
- `KeyError` on stock dict → add `.get('key', default)` not `['key']`
- `return outside function` → check indentation of return statements

---

## 13. NEXT TASK QUEUE

Work through these in order. Complete and test each before moving on.

**IMMEDIATE — Phase 2 completion:**
1. Build `main.py`
   - Orchestrate: load data → filter → score → mos → report → publish
   - Accept `--portfolio` flag: `py main.py --portfolio dividend`
   - Accept `--dry-run` flag: generates report but does not send to Discord
   - Load webhook URLs from .env

**THEN — Phase 3 data pipeline:**
2. Build `db/database.py` — SQLite connection, schema creation
3. Build `scraper/pse_scraper.py` — PSE Edge stock list and prices
4. Build `scraper/pdf_parser.py` — annual report PDF parser
5. Build `engine/validator.py` — data quality checks

**THEN — Phase 4 automation:**
6. Build `scheduler.py` — weekly automated runs
7. Build `alerts/alert_engine.py` — disclosure alerts

---

## 14. DISCORD SETUP

Three Discord channels needed:
- `#pse-dividend` — Dividend portfolio reports
- `#pse-value` — Value portfolio reports
- `#pse-hybrid` — Hybrid portfolio reports

To get a webhook URL:
Discord → Channel Settings → Integrations → Webhooks → New Webhook → Copy URL

Paste webhook URLs into `.env` (not config.py).

---

## 15. BACKTESTING NOTES (Phase 4)

Per the project instruction manual:
- Focus on statistical interpretation — not return guarantees
- Highlight drawdown risk
- Compare against PSEi benchmark logically
- Identify factor instability across time periods
- Suggest sensitivity testing on weights
- Never declare the model superior without statistical evidence
- Never infer future performance from historical results

---

*Last updated: Phase 2 complete — publisher.py done*
*Project owner: Josh*
*Do not share this file or the .env file publicly.*
