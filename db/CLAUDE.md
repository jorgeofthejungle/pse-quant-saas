# db/CLAUDE.md — Database Layer Implementation Details
> See root CLAUDE.md for system rules, stock data format, DB schema, and architecture.
> This file covers db-specific implementation details only.

Schema migrations run on every startup via `db/db_schema.py`. REIT whitelist, BANK_TICKERS, and SECTOR_MANUAL_MAP migrations are documented in root CLAUDE.md Section 4. See root CLAUDE.md Section 6 for the full table schema.

---

## db/db_financials.py — upsert_financials()
- `force=False` uses `COALESCE(new, existing)` so existing good data is not overwritten
- `force=True` overwrites ALL fields — use only when you are certain all fields are correct

## db/db_data_quality.py
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

## db/db_maintenance.py
- `clean_bad_dps(max_yield_non_reit=20.0, max_yield_reit=30.0, dry_run=False)` — NULLs DPS with implausible yield; returns `{nulled, tickers_affected}`
- `cleanup_stale_data(prices_keep_days=365, activity_keep_days=90, sentiment_keep_days=7, vacuum=True)` — prunes old rows and VACUUMs
