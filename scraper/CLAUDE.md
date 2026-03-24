# scraper/CLAUDE.md — PSE Edge Scraper Implementation Details
> See root CLAUDE.md for system rules, stock data format, DB schema, and architecture.
> This file covers scraper-specific implementation details only.

All scrapers use PSE Edge (edge.pse.com.ph) exclusively — no third-party data sources. All scraper failures are non-fatal — log and continue. The yield gate and canary checks are permanent quality controls — never loosen or bypass.

---

## scraper/pse_stock_data.py — scrape_dividend_history()
Key quality controls (permanent — do not loosen):
- COMMON shares whitelist: `{'COMMON', 'ORDINARY', 'COMMON SHARES', 'ORDINARY SHARES', 'SHARES', ''}`
- Ex-date deduplication: first occurrence per ex-date wins (most recent amendment)
- Per-share rate: currency-prefixed regex `r'(?:P|PHP|Php)\s*([\d]+\.[\d]+)'`, cap ₱0.001–₱100
- Returns `[{year: int, dps: float, fiscal_year: int}]` newest-first, up to 6 years
- Fiscal year mapping: ex-dates in months ≤ fiscal_year_end_month → prior fiscal year
*(Phase 11: Added fiscal year mapping for correct year attribution.)*

## scraper/pse_edge_scraper.py — yield gate
- Write-time yield gate lives in `pse_edge_scraper.py`, NOT in `db_financials.py`
- DPS yielding > 25% (non-REIT) or > 35% (REIT) is blocked at scrape time
- Canary field checks on each scrape; admin DM on pattern failure
*(Phase 11: Tightened from 40%/50% to 25%/35%. Added scraper change detection.)*

## scraper/scraper_canary.py
Shared canary helper for all PSE Edge scrapers.
- `fire_canary(scraper_name, canary_name, detail)` — logs failure to `settings` table under `scraper_health_{scraper_name}`; sends admin DM via `discord_dm.send_dm_text`; anti-spam: one DM per canary per 24 hours
- Canary checks added to: `pse_lookup.py` (JSON keys), `pse_stock_data.py` (price/dividend table), `pse_financial_reports.py` (report table + columns)
- All failures are non-fatal — scraper logs and continues
