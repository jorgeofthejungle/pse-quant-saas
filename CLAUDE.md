# CLAUDE.md — PSE Quant SaaS
> Subdirectory CLAUDE.md files cover folder-specific details: engine/, scraper/, db/, discord/, dashboard/, alerts/, reports/

## Overview

Deterministic multi-factor Philippine equity ranking engine. Scrapes PSE Edge, scores every stock, generates PDF reports (StockPilot PH Rankings), delivers to Discord members.

```
PSE Edge → Scraper → Data Quality Audit → DB
                                          ↓
          Metrics → Scorer (sector-aware) → MoS → Sentiment (Haiku) → PDF → Discord
```

**Scoring:** 3-layer (Health / Improvement / Persistence), sector-aware. Weights in `config.py SCORER_WEIGHTS`. Two portfolios in PDF: Dividend and Value. A stock can appear in both.

## Tech Stack

- **Language:** Python 3.14 — WSL2/Ubuntu dev, Railway (Docker/Linux) deploy
- **Database:** PostgreSQL via `DATABASE_URL` (no SQLite)
- **AI:** Anthropic Claude — Haiku for pipeline, Sonnet for self-repair (import from `config.py`, never hardcode)
- **Bot/webhooks:** discord.py slash commands + webhooks
- **Dashboard:** Flask + HTTP Basic Auth → `http://localhost:8080`
- **Payments:** PayMongo
- **Runtime data:** `PSE_DATA_DIR` env var (default `/app/data`)

## Run Commands

```bash
python main.py                          # full pipeline (score + PDF + Discord)
python main.py --dry-run                # skip Discord publish
python scheduler.py                     # continuous scheduler
python scheduler.py --run-weekly        # manual full scrape
python scheduler.py --approve-pdf       # release a held PDF blocked by bad-PDF fail switch
python dashboard/app.py                 # local dashboard
python engine/calibrate_thresholds.py   # recalibrate after scrape/backfill
python db/db_data_quality.py            # data quality audit
```

## Non-Obvious Rules

### AI models — never hardcode
```python
from config import PIPELINE_AI_MODEL   # Haiku — sentiment, news scoring
from config import SELF_REPAIR_MODEL   # Sonnet — debugging, code repair
```

### Scoring nuances
- **Dynamic threshold:** only stocks above `mean + 0.5 SD` of the scored universe appear in rankings. Hard floor: 45. Recalculated every run — not a fixed cutoff.
- **Data confidence multiplier:** 5yr=1.0, 4yr=0.9, 3yr=0.8, 2yr=0.65. Minimum 2yr data required to score.
- **MoS discount rate** is risk-adjusted (size premium 0–5%, sector premium 0–2%) — not a flat rate.
- **REITs excluded from Value portfolio.** Dividends are a bonus signal, not a filter.
- `feedback/correction_engine.py` applies bounded weight tweaks (±8% cap, 10% floor per layer) stored in the `settings` table. These do NOT override `SCORER_WEIGHTS` in config.py.

### Key config constants
```python
REIT_WHITELIST    = {'VREIT', 'PREIT', 'MREIT', 'AREIT'}  # always REIT, overrides sector field
BANK_TICKERS      = {'BDO', 'MBT', 'SECB'}                # always bank
SECTOR_MANUAL_MAP  # maps 70 Unknown-sector tickers to correct PSE sectors
MIN_SCORE_THRESHOLD = 45
```
`db_schema.py` migrations apply all three on every startup (idempotent).

### Data integrity
- Missing values = `None` — never `0` or estimated. All data from PSE Edge only.
- Data quality pipeline (scraper whitelist → write gate → post-scrape audit) is mandatory — never bypass it.

### Discord async safety
- Never call sync `requests` or DB ops directly inside `@tree.command` handlers.
- Use `asyncio.to_thread(fn, *args)` for any blocking call.
- `defer(thinking=True)` must fire within 3 seconds of receiving an interaction.

### psycopg2 thread safety
Open a new connection per thread — `get_connection()` per call is correct. Never share a connection across threads.

### SQL NULL traps
`SUM()` on an empty table returns a NULL row — always coerce: `result or 0`.

### Output language
Never: "best stock", "buy this", "we recommend".  
Always: "scores highest on our criteria", "appears undervalued based on...".  
Every PDF page footer must include the full disclaimer. Intrinsic value is a mathematical reference, not a price target.

### File size
Keep files under 700 lines. Facade pattern: thin re-export module + focused sub-modules. Don't refactor working code without explicit instruction.

### Testing
- **Run with:** `.venv/bin/python tests/test_foo.py` — system `python3` lacks psycopg2/dotenv
- **Runner:** plain assert-based `if __name__ == '__main__':` block — no pytest
- **Patch deferred imports:** patch at source (`publisher.send_ops_alert`), not the caller's namespace

### Ops alerting
- `discord/discord_ops.py` — `send_ops_alert(stage, error)` posts a red embed to `DISCORD_WEBHOOK_OPS`, silently swallows all failures. Import from `publisher`.
- `scheduler_jobs/state.py` — manages two JSON hold files under `PSE_DATA_DIR/pse_quant/`:
  - `pending_pdf.json` — written by `run_daily_score()` to pass ranked results to `run_daily_report()`
  - `held_pdf.json` — written when bad-PDF fail switch triggers; released by `--approve-pdf`
- Bad-PDF fail switch: if portfolio scoring fails during `run_daily_report()`, the PDF is held (not sent) and `--approve-pdf` releases it.

---
*Owner: Josh — do not share this file or .env publicly.*

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues (`jorgeofthejungle/pse-quant-saas`). See `docs/agents/issue-tracker.md`.

### Triage labels

Using the five canonical label strings (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
