# Data Quality Hardening & Scoring Recalibration — Design Spec

**Date:** 2026-03-17
**Author:** Claude (Lead Developer)
**Owner:** Josh
**Status:** Draft — Pending Review

---

## 1. Objective

Improve the reliability of data flowing into the scoring engine and recalibrate scoring thresholds to reflect Philippine Stock Exchange market reality. This is a two-phase effort:

- **Phase A (Sections 1-6):** Harden the data pipeline so bad data is caught earlier, failures are loud, and staleness is prevented.
- **Phase B (Sections 7-14):** Recalibrate the scoring engine using hybrid percentile-based thresholds, differentiate by portfolio type, and address data scarcity systemically.

**Out of scope:** Expanding the stock universe through new data sources (Phase A improvements and the backfill scraper will naturally increase pass rates). Dashboard UI changes beyond what's needed to surface scraper health. Discord bot command changes.

---

## 2. Context

### Current State

The PSE Quant SaaS system scrapes financial data from PSE Edge, scores 223 stocks using a deterministic 4-layer model, and delivers rankings via PDF reports and Discord. The system is production-ready (Phase 10 complete) but has two categories of issues:

**Data quality gaps:**
- PSE Edge HTML parsing uses regex with no change detection — structural changes cause silent failures
- Unit detection (millions vs thousands) defaults silently when the currency line is missing
- Dividend year attribution uses ex-date instead of fiscal year — can assign dividends to wrong year
- Current-year partial DPS enters scoring, distorting CAGR and payout ratios
- Write-time yield gate (40% non-REIT) is too loose — bad data reaches DB
- Market cap and price staleness are not cross-validated
- No alerting when scraper patterns break or scheduler process dies

**Scoring calibration issues:**
- Health layer thresholds are aspirational (30% OCF margin for full marks — most healthy PSE companies are 10-20%)
- All portfolio types use identical 4-layer weights (25/30/15/30)
- Acceleration layer requires 5 years of data — effectively dead weight for most stocks
- Persistence layer ignores magnitude (tiny improvements score same as strong ones)
- MoS uses fixed 11.5% discount rate regardless of size or sector risk
- Sector medians only cover PE/PB/EV-EBITDA — ROE, FCF yield, dividend yield have no sector context
- PE outlier filter (< 200) is too loose — micro-cap noise distorts sector medians
- Improvement layer hides recent deterioration behind 3-year average
- Improvement layer ROE delta has off-by-one risk with data gaps

### Evidence Base

All threshold proposals are backed by queries against the live database (48 stocks with valid PE, 223-stock universe). Key findings:

- Zero non-REIT stocks yield above 20% (max observed: 19.2%, a penny stock with partial-year data)
- Legitimate non-REIT yield ceiling is ~10%
- 4 REITs (VREIT, PREIT, MREIT, AREIT) are misclassified as non-REIT
- Only 4 stocks have PE > 100, all micro-cap artifacts (CSB at 1,490x, SRDC at 217x)
- 6 stocks have PE > 50, none are investable blue chips
- ROE < -50% hits only 7 genuinely distressed tickers
- P/B > 50 hits only 9 micro-cap shells
- Data completeness is bimodal: 135 tickers at ~0%, 104 tickers at ~40-60%, nothing in between
- 25% and 40% completeness thresholds block the same 135 tickers

---

## 3. Phase A — Data Quality Hardening

### Section 1: Scraper Change Detection

**Problem:** PSE Edge HTML parsing uses regex with no versioning. If PSE Edge redesigns a page, the scraper returns `None` silently — indistinguishable from "no data available."

**Solution:**

For each of the 4 scraper sub-modules (lookup, stock data, dividends, financial reports):

1. Define "canary fields" — fields that must always be present on a valid page:
   - `pse_lookup.py`: "cmpy_id" pattern in autocomplete response
   - `pse_stock_data.py`: "Last Traded Price" label in stock data page
   - `pse_stock_data.py` (dividends): table header with "Ex-Date" column
   - `pse_financial_reports.py`: "fiscal year ended" pattern in report page

2. On each scrape, check canaries before parsing. If a canary field is missing:
   - Log `ERROR` to `activity_log` with category `scraper_health` and detail identifying which module and which canary failed
   - Set `scraper_broken_{module}` flag in `settings` DB table (key-value)
   - On next scheduler run, send a one-time DM to admin (`ADMIN_DISCORD_ID=439376941393379328`) via `send_dm_text()`: "Scraper pattern broken for {module} — PSE Edge may have changed their page layout. Last successful parse: {timestamp}."
   - Do not re-alert until the flag is cleared (prevents spam)

3. Add `/api/scraper-health` endpoint to dashboard returning JSON:
   ```json
   {
     "lookup": {"last_success": "2026-03-16T22:15:00", "status": "ok"},
     "stock_data": {"last_success": "2026-03-16T17:30:00", "status": "ok"},
     "dividends": {"last_success": "2026-03-16T22:15:00", "status": "ok"},
     "financial_reports": {"last_success": "2026-03-16T22:15:00", "status": "broken"}
   }
   ```

**Files modified:** `scraper/pse_lookup.py`, `scraper/pse_stock_data.py`, `scraper/pse_financial_reports.py`, `dashboard/routes_pipeline.py`, `db/db_schema.py` (settings table already exists).

**Admin alert destination:** DM to `ADMIN_DISCORD_ID` via `discord/discord_dm.py:send_dm_text()`. Not sent to any public Discord channel.

---

### Section 2: Unit Detection Hardening

**Problem:** `pse_financial_reports.py` detects "thousands" vs "millions" via fuzzy regex on a currency line. If the line is missing, it defaults to dividing by 1,000,000 — potentially 1000x wrong. Fails silently.

**Solution:**

1. Make currency detection mandatory. If the regex doesn't find a currency/unit indicator:
   - Do NOT default to millions
   - Return `None` for that ticker's financials
   - Log `ERROR` to `activity_log`: "Unit detection failed for {ticker} — currency line not found on report page"
   - Include in scraper health DM to admin (Section 1 mechanism)

2. Add cross-validation for unit plausibility at parse-time (before DB write):
   - Revenue per share (revenue / derived shares): must be between 0.01 and 10,000. Outside range = likely unit error → reject
   - EPS vs Net Income / shares: if mismatch > 100x → reject (this check exists in `db_data_quality.py` post-scrape; move to parse-time as a gate)
   - Net margin (NI / Revenue): if > 500% → reject as likely unit mismatch

3. Add `unit_confidence` to parsing result:
   - `'detected'`: found explicit currency line (high confidence)
   - `'inferred'`: derived from cross-validation only (lower confidence)
   - Log to `activity_log` for audit trail

**Files modified:** `scraper/pse_financial_reports.py`, `scraper/pse_edge_scraper.py` (facade).

---

### Section 3: Dividend Attribution Fix

**Problem:** Two issues:
1. Year attribution uses ex-date, not fiscal year. A dividend declared for fiscal year 2024 with ex-date in January 2025 is attributed to 2025.
2. Current-year partial DPS enters scoring. Mid-year scrapes pick up Q1-Q2 dividends and store them as full-year DPS.

**Solution:**

**Fiscal year mapping:**
- Keep ex-date as storage key and dedup anchor (unchanged)
- Add fiscal year mapping: ex-dates in January-March are attributed to the prior fiscal year
- Default assumption: December fiscal year-end (covers ~95% of PSE companies)
- Add `fiscal_year_end_month` column to `stocks` table (default 12) for the ~5 stocks with non-December year-ends
- The scorer uses `fiscal_year` for CAGR, payout, and yield calculations — not the raw ex-date year

**Current-year exclusion:**
- `build_stock_dict_from_db()` excludes DPS for the current fiscal year from all scoring-related fields (`dps_last`, `dividend_yield`, `dividend_cagr_5y`, `payout_ratio`)
- Current-year DPS remains in the database — still available for dividend calendar and alerts
- The exclusion is date-based: if today is March 2026, most recent complete fiscal year is 2025

**Fiscal year mapping formula:**
```python
# Given: ex_date_month, ex_date_year, fiscal_year_end_month (from stocks table, default 12)
fiscal_year = ex_date_year if ex_date_month > fiscal_year_end_month else ex_date_year - 1
```
For a December year-end company (the default), a dividend with ex-date in March 2025 maps to fiscal year 2024. For a June year-end company, a dividend with ex-date in September 2025 maps to fiscal year 2025 (current year — correctly kept as current fiscal year).

**Files modified:** `scraper/pse_stock_data.py` (fiscal year mapping), `db/db_schema.py` (fiscal_year_end_month column), `scraper/pse_edge_scraper.py` (pass fiscal year to storage), `scraper/pse_stock_builder.py` (`build_stock_dict_from_db` — this is the function that constructs stock dicts for the scoring pipeline).

---

### Section 4: Tighten Write-Time Gates & Validator

**Problem:** Multiple validation thresholds are too lenient, allowing questionable data to enter the scoring pipeline.

**Solution:**

**Write-time gate changes (scraper → DB):**

| Gate | Current | New | Evidence |
|------|---------|-----|----------|
| Yield gate (non-REIT) | 40% | 25% | Max observed non-REIT yield: 19.2% (penny stock). Legitimate ceiling ~10%. |
| Yield gate (REIT) | 50% | 35% | Max observed REIT yield: 8.1%. |
| Negative revenue | Not checked | Block at write-time | Zero rows currently; safety net for future. |

**Validator changes (DB → scorer):**

| Check | Current | New | Evidence |
|-------|---------|-----|----------|
| Data completeness minimum | 25% | 40% | Bimodal distribution: 135 tickers at ~0%, 104 at ~40-60%. Both thresholds block the same 135 tickers; 40% is more defensible. |
| ROE hard block | Warning at < -50% | Hard block at < -50% | Only 7 tickers affected (all genuinely distressed: Lepanto -248%, GEO -201%, etc.). |
| P/B hard block | > 100 | > 50 | 9 micro-cap shells above P/B 50x. No legitimate blue chip approaches this. |

**REIT misclassification fix:**
- Set `is_reit=1` for VREIT, PREIT, MREIT, AREIT in `stocks` table
- These 4 tickers currently appear as non-REIT in yield analysis, distorting thresholds
- One-time data fix + add these tickers to a REIT whitelist in `config.py` so future scrapes classify them correctly

**Yield gate alignment:** The write-time yield gate actually lives in `scraper/pse_edge_scraper.py` (lines 166-171), NOT `db/db_financials.py` as documented in CLAUDE.md. The post-scrape cleaner in `db/db_maintenance.py` uses separate thresholds (20%/30%). After this change:
- Write gate (`pse_edge_scraper.py`): 25% non-REIT, 35% REIT (blocks at scrape time)
- Post-scrape cleaner (`db_maintenance.py`): 20% non-REIT, 30% REIT (catches anything that slipped through)
- The cleaner remains stricter than the write gate intentionally — it's the last line of defense

**Files modified:** `scraper/pse_edge_scraper.py` (write-time yield gate thresholds), `db/db_maintenance.py` (align cleaner thresholds — keep at 20%/30%), `engine/validator.py` (threshold changes), `config.py` (REIT whitelist, yield gate thresholds), one-time DB migration for REIT flags. Note: CLAUDE.md incorrectly documents the yield gate as being in `db/db_financials.py` — this must be corrected.

---

### Section 5: Market Cap / Price Staleness Cross-Validation

**Problem:** Market cap and close price are fetched independently and can become misaligned. Derived share count (`market_cap / close`) inherits the error, propagating to EV/EBITDA, FCF per share, and P/B.

**Solution:**

1. Validate that market cap and price are from the same trading day. If `close` was updated today but `market_cap` is from a different date, flag the stock with `stale_market_cap` warning in validator.

2. Cross-validate derived shares: if derived share count changed > 10% vs the last known derivation (without a stock split announcement), flag as suspicious and log to `activity_log` with category `data_integrity`.

3. In the scorer, skip EV/EBITDA and FCF per share if market cap is > 3 days older than price. These metrics depend on accurate share count — better to score `None` (weight redistributes) than score on wrong data.

**Files modified:** `engine/validator.py`, `build_stock_dict_from_db()` function.

---

### Section 6: Staleness Prevention

**Problem:** Data can go stale when scheduled runs fail silently, the scheduler process dies, or a stock gets delisted/suspended.

**Solution: Three levels of defense.**

**Level 1 — Freshness enforcement in scorer:**
- Price older than 7 calendar days → exclude from scoring entirely (conservative; covers weekends + most holiday stretches like Holy Week)
- Financials older than 15 months → exclude from scoring
- Hard gate — stale stocks don't get ranked

**Level 2 — Automatic retry on failed scrapes:**
- Track consecutive scrape failures per ticker in `activity_log`
- After 3 consecutive daily failures → admin DM: "{ticker} hasn't updated in 3 days"
- On next scheduled run, retry failed tickers first
- After 7 consecutive failures → set `stocks.status = 'suspended'`, stop attempting
- Admin can manually un-suspend via dashboard

**Level 3 — Scheduler health heartbeat:**
- `settings` table entry `scheduler_heartbeat` updated every 15 minutes (aligned with disclosure monitor tick)
- Dashboard `/api/health` checks heartbeat age:
  - < 30 min: healthy
  - 30 min - 2 hours: show warning on dashboard
  - > 2 hours: send admin DM: "Scheduler hasn't reported in 2 hours — may need restart"
- Heartbeat check runs inside the dashboard's existing `/api/health` endpoint (polled by the overview page)

**Files modified:** `build_stock_dict_from_db()` (Level 1), `scheduler_jobs.py` (Level 2 retry logic), `scheduler.py` (Level 3 heartbeat write), `dashboard/routes_home.py` (Level 3 heartbeat check), `discord/discord_dm.py` (admin DM calls).

---

## 4. Phase B — Scoring Recalibration

### Section 7: Health Layer Threshold Recalibration

**Problem:** Health sub-scorer thresholds are aspirational, not grounded in PSE market reality. OCF margin needs 30% for full marks (most healthy PSE companies are 10-20%). FCF yield needs 12% for a high score (rare on PSE). ROE threshold isn't sector-adjusted.

**Solution: Percentile-based thresholds, hybrid-derived.**

After Phase A data cleaning completes, run a distribution analysis across all stocks with valid data. Set thresholds at meaningful percentiles:

| Sub-score | Current "excellent" | New approach |
|-----------|-------------------|--------------|
| ROE | >= 25% = 96pts | Top-10% of sector = 90+pts |
| OCF Margin | >= 30% = 100pts | Top-10% of PSE universe = 90+pts, median = 50pts |
| D/E | <= 0.3 = 100pts | Keep current (already sector-adjusted) |
| FCF Yield | >= 12% = 96pts | Top-10% of PSE = 90+pts |
| EPS Stability | CV <= 0.05 = 100pts | Top-25% of PSE = 90+pts |

**Key principle:** "Excellent" = top-10% of the PSE, not top-10% globally. "Average" = PSE median. The scorer differentiates Philippine stocks against each other.

**Sector-relative ROE:** Compare against sector median ROE (Section 12 expands `sector_stats.py` to compute this). A bank at 12% ROE where the sector median is 8% scores higher than a consumer company at 12% where the median is 18%.

**Implementation:** Thresholds stored in `config.py` as a dictionary, not hardcoded in `scorer_health.py`. Updated when distribution analysis is re-run after future scrapes.

```python
# config.py
# Fallback thresholds used when calibration has not yet run.
# These are conservative estimates based on current DB analysis (2026-03-17).
# The calibration script (engine/calibrate_thresholds.py) overwrites these with
# actual percentile values derived from the live database.
HEALTH_THRESHOLDS = {
    'roe':              {'p90': 20.0, 'p75': 14.0, 'p50': 9.0,  'p25': 4.0},
    'ocf_margin':       {'p90': 22.0, 'p75': 15.0, 'p50': 9.0,  'p25': 3.0},
    'fcf_yield':        {'p90': 10.0, 'p75': 6.5,  'p50': 3.5,  'p25': 1.0},
    'eps_stability_cv': {'p90': 0.10, 'p75': 0.25, 'p50': 0.50, 'p25': 0.80},
}
# Note: For EPS stability CV, lower is better — p90 = the 10th percentile of CV values
# (i.e., the most stable 10% of stocks).
```

These fallback values are conservative initial estimates. The calibration script (`engine/calibrate_thresholds.py`) computes actual percentiles from the DB and writes them to the `settings` table. `scorer_health.py` reads from `settings` first, falling back to `config.py` if no calibrated values exist. The calibration script can be re-run after each weekly scrape to keep thresholds current.

**Files modified:** `engine/scorer_health.py` (threshold logic), `config.py` (threshold storage), new `engine/calibrate_thresholds.py` (distribution analysis script).

---

### Section 8: Data Scarcity Strategy

**Problem:** PSE Edge only publishes 2 most recent years per financial report page. Most stocks have 2-3 years of history. The 3-year filter requirement blocks ~80% of stocks. The acceleration layer requires 5 years (almost never available).

**Solution: Three strategies layered by effort and timeline.**

**Part 1 — Historical Backfill Scraper (one-time run):**
- New function `backfill_historical_financials()` in `scraper/pse_financial_reports.py`
- For each stock, request annual report pages for fiscal years 2018-2023 individually
- Extract same fields as current scraper (revenue, net income, EPS, equity, total debt, OCF, capex, EBITDA)
- Use `upsert_financials(force=False)` — existing data never overwritten
- Respects rate limiting (3s delay, 30s timeout, 3 retries)
- Run via CLI: `py scheduler.py --run-backfill`
- Estimated time: ~223 stocks x 6 years x 3s = ~67 minutes
- Logs progress to `activity_log`

**Part 2 — Confidence-Weighted Scoring:**
- New function `calc_data_confidence(stock)` in `engine/validator.py`
- Counts years of complete financial data (EPS + Revenue + OCF all present for a given year)
- Returns multiplier:

| Years of complete data | Confidence multiplier |
|-----------------------|----------------------|
| 5+ years | 1.00 |
| 4 years | 0.90 |
| 3 years | 0.80 |
| 2 years | 0.65 |
| 1 year | 0.00 (not scored) |

- `scorer_v2.py` applies multiplier to final score after all 4 layers compute
- `scores_v2` table gets `confidence` column (float, 0.0-1.0)
- PDF shows confidence badge: "High" (>= 0.9), "Medium" (0.8), "Limited" (0.65)
- Filter relaxed from 3-year hard minimum to 2-year minimum (confidence multiplier handles the penalty)
- **`engine/filters_v2.py` must be updated:** change `len(eps_vals) < 3` to `< 2`, `len(rev_vals) < 3` to `< 2`. OCF minimum stays at 2 (already correct).

**Part 3 — Acceleration Layer Adjustment:**
- Keep 5-year minimum for full acceleration scoring (math unchanged)
- Reduce weight to 5% across all portfolio types (from current 15%)
- Widen scoring bands to reduce sensitivity:
  - +10pp or more → 90pts (was ~85)
  - 0pp → 50pts (was 52)
  - -10pp or more → 15pts (was ~20)
- Config comment: "Increase acceleration weight to 15% once 80%+ of qualifying stocks have 5-year history"
- When acceleration returns `None`, only 5% redistributes — negligible impact

**Files modified:** `scraper/pse_financial_reports.py` (backfill), `engine/filters_v2.py` (relax 3-year to 2-year minimum for EPS and Revenue), `engine/validator.py` (confidence calc), `engine/scorer_v2.py` (apply confidence, acceleration weight), `db/db_schema.py` (confidence column), `config.py` (acceleration weight, confidence tiers), `reports/pdf_stock_detail_page.py` (confidence badge), `scheduler.py` (--run-backfill CLI).

**Backfill time estimate note:** The 67-minute estimate assumes no retries. With a 10% retry rate (3 retries per failure at exponential backoff), actual time could be 90-120 minutes. The backfill function should log progress every 10 stocks and support resuming from where it left off (skip tickers that already have data for a given year).

---

### Section 9: Portfolio-Specific Weights & Unified PDF

**Problem:** All portfolio types use identical 4-layer weights (25/30/15/30). A dividend investor cares about different things than a value investor.

**Solution:**

**Differentiated weights:**

| Layer | Pure Dividend | Dividend Growth | Value | Unified (default) |
|-------|-------------|-----------------|-------|--------------------|
| Health | 30% | 25% | 35% | 25% |
| Improvement | 20% | 35% | 25% | 30% |
| Acceleration | 5% | 5% | 5% | 5% |
| Persistence | 45% | 35% | 35% | 40% |

Rationale:
- **Pure Dividend:** Persistence (45%) is king — consistent improvement predicts stable future dividends. Health (30%) matters for balance sheet strength to sustain payouts.
- **Dividend Growth:** Improvement (35%) is highest — growing earnings support future dividend increases.
- **Value:** Health (35%) is highest — current financial strength is the foundation of value investing. Persistence (35%) separates value traps from genuine bargains.

**Unified PDF with three sections:**
- One PDF report, one Discord upload, one scheduled run
- Cover page (unchanged)
- Section 1: Pure Dividend Rankings — stocks filtered for yield >= 3%, 4/5 dividend years, ranked by pure_dividend weights
- Section 2: Dividend Growth Rankings — stocks filtered for CAGR > 0%, ranked by dividend_growth weights
- Section 3: Value Rankings — no dividend requirement, ranked by value weights
- A stock can appear in multiple sections with different scores and ranks
- Stock detail pages show all applicable portfolio scores and breakdowns

**Implementation:**
- `scorer_v2.py` accepts `portfolio_type` parameter, loads weights from `config.py`
- `scores_v2` table gets `portfolio_type` column (TEXT, NOT NULL, default 'unified')
- **CRITICAL: The UNIQUE constraint on `scores_v2` must change from `(ticker, run_date)` to `(ticker, run_date, portfolio_type)`** — otherwise the second score insert for the same ticker on the same run date will collide. This requires a migration (SQLite: create new table, copy data, drop old, rename).
- Each stock scored up to 3 times (once per qualifying portfolio type)
- `pdf_generator.py` renders three ranked sections with section dividers. Given the 500-line file size limit, this may require a new sub-module `pdf_portfolio_sections.py` for the section-divider and multi-section layout logic.
- Discord bot `/stock` command shows all qualifying portfolio scores
- Discord bot `/top10` accepts optional portfolio type parameter

**CLAUDE.md update required:** After implementation, CLAUDE.md Section 2 (weight table showing 25/30/15/30) and Section 4 (`scorer_v2.py` documentation stating "Do not change weights") must be updated to reflect the new portfolio-specific weights. This spec constitutes the "explicit instruction" referenced by that rule.

```python
# config.py
SCORER_WEIGHTS = {
    'pure_dividend':   {'health': 30, 'improvement': 20, 'acceleration': 5, 'persistence': 45},
    'dividend_growth': {'health': 25, 'improvement': 35, 'acceleration': 5, 'persistence': 35},
    'value':           {'health': 35, 'improvement': 25, 'acceleration': 5, 'persistence': 35},
    'unified':         {'health': 25, 'improvement': 30, 'acceleration': 5, 'persistence': 40},
}
```

**Files modified:** `engine/scorer_v2.py`, `config.py`, `db/db_scores.py` (portfolio_type column), `reports/pdf_generator.py` + sub-modules (three sections), `discord/bot_commands.py` (/stock, /top10), `main.py`, `scheduler_jobs.py`.

---

### Section 10: Persistence Layer — Magnitude Awareness

**Problem:** Persistence counts direction only, ignoring magnitude. Three consecutive years of +0.1% revenue growth scores the same as three years of +20% growth.

**Solution: Blended formula with direction, magnitude, and streak.**

**Current formula:**
```
Base score = (positive_years / total_years) x 80
Streak bonus = consecutive_positive x 5 (max +20)
Total = Base + Streak (0-100)
```

**New formula:**
```
Direction score = (positive_years / total_years) x 60
Magnitude score = normalized avg positive YoY change (0-20)
Streak bonus    = consecutive_positive x 5 (max +20)
Total = Direction + Magnitude + Streak (0-100)
```

**Magnitude scoring:**

| Avg positive YoY change | Magnitude points |
|------------------------|-----------------|
| >= 15% | 20 |
| 10-15% | 15 |
| 5-10% | 10 |
| 1-5% | 5 |
| < 1% | 2 |

**Example comparison:**
- Stock A: 3/3 positive, changes [+0.5%, +0.3%, +0.1%] → Direction 60 + Magnitude 2 + Streak 15 = **77**
- Stock B: 3/3 positive, changes [+18%, +15%, +12%] → Direction 60 + Magnitude 20 + Streak 15 = **95**

Direction still dominates (60/100). Magnitude is a tiebreaker that separates strong performers from marginal ones.

**Files modified:** `engine/scorer_persistence.py`.

---

### Section 11: MoS Discount Rate Differentiation

**Problem:** All stocks use a fixed 11.5% discount rate. A speculative micro-cap mining stock and SM Prime get the same required return.

**Solution: Tiered size + sector premium model.**

**Formula:**
```
required_return = risk_free (6.5%) + equity_premium (5.0%) + size_premium + sector_premium
```

**Size premium (by market cap):**

| Market Cap | Premium |
|-----------|---------|
| >= PHP 50B (large) | +0.0% |
| PHP 10B-50B (mid) | +1.5% |
| PHP 1B-10B (small) | +3.0% |
| < PHP 1B (micro) | +5.0% |

**Sector premium:**

| Sector | Premium |
|--------|---------|
| Banking, Utilities | +0.0% |
| Property, Consumer | +0.5% |
| Industrial, Services | +1.0% |
| Mining, Oil | +2.0% |
| Holding Firms | +1.0% |

**Examples:**
- SM Prime (Property, ~PHP 900B): 6.5% + 5% + 0% + 0.5% = **12.0%**
- DMC (Mining, ~PHP 30B): 6.5% + 5% + 1.5% + 2.0% = **15.0%**
- Micro-cap mining (PHP 500M): 6.5% + 5% + 5.0% + 2.0% = **18.5%**

All three MoS valuation methods (DDM, EPS-PE, DCF) use the same adjusted rate. The existing 20% conglomerate discount for Holding Firms remains on top of the sector premium.

**Implementation:** Premiums stored in `config.py` as dictionaries. `mos.py` imports and applies. PDF detail page shows applied discount rate per stock.

```python
# config.py
MOS_SIZE_PREMIUM = {
    'large':  0.0,   # >= 50B
    'mid':    1.5,   # 10B-50B
    'small':  3.0,   # 1B-10B
    'micro':  5.0,   # < 1B
}
# Sector premium mapping — keys must match ALL sector names found in the stocks table.
# Use get() with a default of 1.0% for any unmapped sector.
MOS_SECTOR_PREMIUM = {
    'Financials':     0.0,   # Banking sector
    'Banking':        0.0,   # Alias (some stocks use this)
    'Utilities':      0.0,   # Regulated, predictable cash flows
    'Property':       0.5,
    'Consumer':       0.5,
    'Industrial':     1.0,
    'Services':       1.0,
    'Mining and Oil': 2.0,
    'Holding Firms':  1.0,
    'Unknown':        1.5,   # Unclassified stocks get moderate premium
}
MOS_SECTOR_PREMIUM_DEFAULT = 1.0  # For any sector name not in the dict above
MOS_SIZE_THRESHOLDS = {
    'large': 50_000_000_000,
    'mid':   10_000_000_000,
    'small':  1_000_000_000,
}
```

`mos.py` uses `MOS_SECTOR_PREMIUM.get(stock['sector'], MOS_SECTOR_PREMIUM_DEFAULT)` to handle any sector name not explicitly mapped.

**Files modified:** `engine/mos.py`, `config.py`, `reports/pdf_stock_detail_page.py` (show discount rate).

---

### Section 12: Sector-Relative Scoring Expansion

**Problem:** `sector_stats.py` only computes medians for PE, PB, EV/EBITDA. ROE, FCF yield, dividend yield, OCF margin, and D/E have no sector context.

**Solution:**

**Expand sector medians to 8 metrics:**
- Existing: PE, PB, EV/EBITDA
- New: ROE, FCF Yield, Dividend Yield, OCF Margin, D/E Ratio

**Health layer blending:**
For each metric scored in the health layer, blend absolute and sector-relative:
- **Absolute score (70%):** How good is this metric against PSE-wide percentile thresholds (Section 7)
- **Sector-relative score (30%):** How does this metric compare to the sector median

Example:
- SECB ROE = 11%. Absolute score (PSE percentiles) = 55pts.
- Banking sector median ROE = 8%. SECB is 37% above median. Sector-relative = 78pts.
- Blended: (55 x 0.70) + (78 x 0.30) = **62pts**

**Outlier filtering tightened:**

| Metric | Current filter | New filter | Evidence |
|--------|---------------|------------|----------|
| PE | < 200 | < 50 | Only 6 stocks above PE 50, all micro-cap noise. No investable stock > 50. |
| PB | < 50 | < 20 | 17 stocks above PB 10, mostly shells. Conservative cut at 20. |
| EV/EBITDA | < 200 | < 50 | Aligned with PE cut. |

**Market-cap weighted medians:** Large caps count more than penny stocks in median calculation, preventing micro-cap contamination. This requires adding `market_cap` to the stock dict passed to `compute_sector_stats()`. The `market_cap` field is already available in the `prices` table — `build_stock_dict_from_db()` in `scraper/pse_stock_builder.py` must include it in the returned dict. Add `'market_cap': float | None` to the stock dict specification (CLAUDE.md Section 5).

**Minimum sector size for dynamic median:** Reduced from 5 to 3 stocks. More sectors get dynamic treatment instead of falling back to hardcoded benchmarks.

**Fallback benchmarks:** Re-derived from historical data after backfill scraper runs (Section 8). Documented with derivation date in `config.py`.

**Files modified:** `engine/sector_stats.py`, `engine/scorer_health.py` (70/30 blending), `config.py` (fallback benchmarks), `scraper/pse_stock_builder.py` (add `market_cap` to stock dict).

---

### Section 13: Improvement Layer Recency Weighting

**Problem:** The 3-year smoothed delta treats all years equally. A stock with revenue growth [+20%, +15%, -8%] (newest first) averages to +9% — "moderate improvement." But the most recent year declined.

**Solution: Weighted average with recency bias.**

**Current:** Simple average of 3 most recent YoY changes.
```
delta = (change_1 + change_2 + change_3) / 3
```

**New:** Weighted average — most recent year has most influence.
```
delta = (change_1 x 0.50) + (change_2 x 0.30) + (change_3 x 0.20)
```

Where `change_1` is the most recent YoY change.

**Example:**
- Revenue growth: [+20%, +15%, -8%] (newest first)
- Current: (-8 + 15 + 20) / 3 = +9.0% → "moderate improvement"
- New: (-8 x 0.50) + (15 x 0.30) + (20 x 0.20) = +4.5% → properly reflects recent decline

**Weights stored in `config.py`:**
```python
IMPROVEMENT_RECENCY_WEIGHTS = [0.50, 0.30, 0.20]  # newest first
```

Applied to all 4 sub-components of the improvement layer: revenue delta, EPS delta, OCF delta, ROE delta.

**Files modified:** `engine/scorer_improvement.py`, `config.py`.

---

### Section 14: Improvement Layer ROE Delta Year Validation

**Problem:** `scorer_improvement.py` computes ROE delta by comparing `financials_history[3]` (hardcoded index) to current. If any year is missing from the history, index 3 may point to the wrong year — silently comparing ROE against a year that's 4 or 5 years ago instead of 3.

**Solution: Index by actual fiscal year, not array position.**

**Current:**
```python
roe_current = financials_history[0]['roe']
roe_3y_ago = financials_history[3]['roe']  # Assumes index 3 = 3 years ago
roe_delta = roe_current - roe_3y_ago
```

**New:**
```python
current_year = financials_history[0]['year']
target_year = current_year - 3

# Find the entry for the target year
target_entry = next((f for f in financials_history if f['year'] == target_year), None)

if target_entry is None or target_entry.get('roe') is None:
    roe_delta = None  # Cannot compute — missing data for target year
else:
    roe_delta = financials_history[0]['roe'] - target_entry['roe']
```

When `roe_delta` is `None`, the improvement layer scores the remaining 3 sub-components (revenue, EPS, OCF) and redistributes the ROE weight among them — same graceful degradation pattern used elsewhere.

**Files modified:** `engine/scorer_improvement.py`.

---

## 5. Dependencies & Ordering

Phase A must complete before Phase B begins (scoring recalibration depends on clean data).

Within Phase A, sections can be implemented in any order except:
- Section 1 (change detection) should be first — it provides the alerting mechanism used by Section 2

Within Phase B:
- Section 8 (backfill scraper) should run before Section 7 (threshold calibration) — calibration needs the expanded dataset
- Section 12 (sector medians expansion) should be done before or alongside Section 7 — health layer recalibration uses sector-relative scoring
- All other sections are independent

```
Phase A:
  Section 1 (change detection) → first
  Sections 2, 3, 4, 5, 6 → any order after Section 1

Phase B:
  Section 8 (backfill) → run first
  Section 12 (sector medians) → before or with Section 7
  Section 7 (calibration) → after 8 and 12
  Sections 9, 10, 11, 13, 14 → any order
```

**Recommended implementation order (optimized for impact):**

Front-load scoring accuracy fixes and data expansion; defer operational tooling; save highest-risk schema migration for after scoring logic is validated:

1. Section 14 (ROE delta bug fix — trivial, immediate impact)
2. Section 3 (Dividend attribution — highest ROI, fixes every dividend stock)
3. Section 4 (Tighten gates + REIT fix — quick wins)
4. Section 8 Part 1 (Backfill scraper — expands universe)
5. Section 10 (Persistence magnitude — clean scoring improvement)
6. Section 13 (Improvement recency — clean scoring improvement)
7. Section 8 Parts 2-3 (Confidence multiplier + acceleration adjustment)
8. Section 12 (Sector medians expansion — needed before calibration)
9. Section 7 (Health threshold calibration — depends on 8 and 12)
10. Section 11 (MoS discount rate differentiation)
11. Section 9 (Portfolio weights + unified PDF — highest risk, save for last)
12. Sections 1, 2, 5, 6 (Operational monitoring — important but doesn't affect scoring)

---

## 6. Testing Strategy

**Phase A testing:**
- Each section has isolated, testable behavior (canary check, unit validation, yield gate, etc.)
- Add test cases to existing `tests/` directory
- Run `db_data_quality.py` full audit before and after Phase A to compare issue counts
- Verify admin DM delivery with `--dry-run` flag

**Phase B testing:**
- Run full scoring pipeline before and after recalibration
- Compare score distributions: mean, median, std dev, min, max
- Verify no stock's score changes by more than 30 points (sanity check — if it does, investigate)
- **Required deliverable: before/after comparison table** — a CSV showing the top 20 stocks' scores (old vs new) saved for Josh's review before deploying to Discord. This is a gate: do not publish new scores until the comparison is reviewed.
- Run backtester across 2023-2025 to verify rank stability
- PDF visual inspection for three-section layout

**Integration testing:**
- Full pipeline dry run: `py main.py --dry-run`
- Verify scheduler runs all jobs without error
- Verify Discord bot commands return updated data

---

## 7. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Backfill scraper overwhelms PSE Edge | Medium | Temporary IP block | 3s delay already configured; can increase to 5s. Run during off-hours (midnight). |
| Threshold recalibration drastically changes rankings | Medium | Member confusion | Publish changelog with the report. Compare old vs new scores in transition period. |
| Confidence multiplier penalizes good stocks too heavily | Low | Missed opportunities | 0.65 for 2-year stocks means an 85-point stock still scores 55 — competitive if fundamentals are strong. |
| Fiscal year mapping wrong for non-December year-end | Low | DPS attributed to wrong year | Default covers 95% of PSE. `fiscal_year_end_month` column handles exceptions. |
| Sector medians unreliable for small sectors | Medium | Distorted sector-relative scores | Fallback benchmarks for sectors with < 3 stocks. Market-cap weighting reduces noise. |
| `scores_v2` migration loses historical scores | High | Score history lost | DB backup mandatory before migration; test on copy first; provide explicit SQL migration script |
| Confidence multiplier creates score cliffs (2.9yr vs 3.0yr) | Medium | Unfair rank jumps | Tier system is simpler to explain than linear interpolation; document the discrete steps in PDF |

---

## 8. Rollback Strategy

Each section can be independently reverted:

| Section | Rollback method |
|---------|----------------|
| 1 (Scraper change detection) | Remove canary checks; scraper returns to silent-failure mode |
| 2 (Unit detection) | Restore fallback divisor in `pse_financial_reports.py` |
| 3 (Dividend attribution) | Remove fiscal year mapping; revert to ex-date year attribution |
| 4 (Tighten gates) | Restore old thresholds in `pse_edge_scraper.py` and `validator.py` |
| 5 (Market cap staleness) | Remove staleness checks in validator |
| 6 (Staleness prevention) | Remove heartbeat writes and freshness gates |
| 7 (Health calibration) | Delete `settings` table entries with key prefix `health_threshold_`; falls back to `config.py` defaults |
| 8 (Backfill + confidence) | Backfilled data stays (no harm); remove confidence multiplier from `scorer_v2.py`; restore 3-year filter in `filters_v2.py` |
| 9 (Portfolio weights + PDF) | Restore `scores_v2` schema from backup; revert to unified weights |
| 10 (Persistence magnitude) | Restore old formula in `scorer_persistence.py` |
| 11 (MoS discount rate) | Restore fixed 11.5% in `mos.py` |
| 12 (Sector medians expansion) | Revert `sector_stats.py` to PE/PB/EV-EBITDA only |
| 13 (Improvement recency) | Restore simple average in `scorer_improvement.py` |
| 14 (ROE delta validation) | Restore index-based lookup (introduces old bug, but reverts behavior) |

**Global rollback:** Restore DB from the pre-implementation backup. Revert all code changes via git.

---

## 9. Housekeeping Notes

**`mos.py` constant cleanup:** `mos.py` lines 28-43 duplicate constants already defined in `config.py` (`PH_RISK_FREE_RATE`, `EQUITY_RISK_PREMIUM`, `DEFAULT_REQUIRED_RETURN`, `DDM_MAX_GROWTH_RATE`, `DEFAULT_TARGET_PE`, `CONGLOMERATE_DISCOUNT`). Section 11 implementation must remove these local duplicates and import from `config.py` only.

**`scorer_acceleration.py` comment cleanup:** Line 21 says "Weight in final score: 15%" — update to 5% after Section 8 Part 3.

**CLAUDE.md yield gate documentation fix:** CLAUDE.md Section 4 incorrectly states the yield gate lives in `db/db_financials.py`. It actually lives in `scraper/pse_edge_scraper.py` (lines 166-171). Correct this during CLAUDE.md update.

---

## 10. Success Criteria

After both phases are complete:

1. **Data quality:** Zero silent scraper failures — all parse errors trigger admin DM within 15 minutes
2. **Filter pass rate:** At least 20 stocks qualify (up from 5-12) due to backfill + 2-year minimum
3. **Score differentiation:** Top-10 and bottom-10 stocks are separated by at least 30 points (meaningful ranking)
4. **Confidence transparency:** Every ranked stock shows its data confidence level in the PDF
5. **Portfolio differentiation:** The same stock has visibly different scores across portfolio types (proving weights matter)
6. **Threshold grounding:** All health layer thresholds are derived from PSE data with documented percentiles
