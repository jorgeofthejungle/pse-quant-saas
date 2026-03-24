# alerts/CLAUDE.md — Alert Engine Implementation Details
> See root CLAUDE.md for system rules, stock data format, DB schema, and architecture.
> This file covers alerts-specific implementation details only.

Both alert files import from `scraper/pse_session.py` and `discord/publisher.py`. First-run baseline logic means no historical alerts fire on a fresh install — existing disclosures are recorded as seen without alerting.

---

## alerts/alert_engine.py
Three checks: price (DB-only), dividend (PSE Edge), earnings (PSE Edge).
First-run baseline: records existing disclosures without alerting.
Atomic dedup: `_claim_disclosure()` uses `INSERT OR IGNORE` + `rowcount`.
Only checks top-15 ranked tickers. CLI: `py alerts/alert_engine.py --dry-run`

## alerts/disclosure_monitor.py
15-minute polling of PSE Edge disclosure feed.
`run_disclosure_check(dry_run=False)` → count of disclosures sent.
Registered in scheduler as interval job (every 15 minutes, all day).
