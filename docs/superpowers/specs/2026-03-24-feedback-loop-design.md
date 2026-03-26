# Feedback Loop & Monitoring System — Design Spec

**Date:** 2026-03-24
**Revision:** 5 (final)
**Status:** Approved
**Author:** Josh + Claude

---

## Golden Rule

> **The system must resist change unless change is undeniable.**
> The default posture is stability. The burden of proof is on the correction, not on the base model.
> Tier 3 (member-facing) NEVER influences Tier 2 (model corrections). Public perception and marketing pressure must never affect model adjustments.

---

## Conventions

- **All timestamps** are in PHT (UTC+8) unless explicitly noted otherwise
- **All return values** are stored as decimals (e.g., 0.05 = 5%, -0.12 = -12%). Display layer converts to percentage for human-facing output
- **All scheduled jobs** use PHT-aware cron triggers
- **Pure math only** — no AI calls anywhere in the feedback system

---

## Overview

A 3-tier layered feedback system that measures model effectiveness against reality, detects structural weaknesses, applies controlled auto-corrections, and surfaces a transparent track record to members.

| Tier | Purpose | Frequency | AI Calls | Modifies Model |
|------|---------|-----------|----------|----------------|
| 1 — Monthly Scorecard | Measure performance | 1st of month | None | No |
| 2 — Quarterly Deep Review | Diagnose + correct | After earnings | None | Yes (guarded) |
| 3 — Member Track Record | Build trust | After Tier 1 | None | Never |

**Data flow is strictly one-directional:**
```
Tier 1 (measurement) → Tier 2 (diagnosis + correction) → Tier 3 (presentation)
                                    ↓
                          settings table (overrides)
                                    ↓
                          scorer reads at runtime
```
Tier 3 has zero write paths back to Tier 2. No feedback loop from presentation to model.

---

## PSEi Index Data (prerequisite)

### New Table: `index_prices`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| index_name | TEXT | 'PSEi' (future-proof for sector indices) |
| date | DATE | Trading day |
| close | REAL | Closing value |
| created_at | TEXT | ISO timestamp (PHT) |

**UNIQUE constraint on (index_name, date)**

### New File: `scraper/pse_index.py`

- `fetch_psei_close(date)` — scrape daily PSEi closing value from PSE Edge
- `backfill_psei(start_date, end_date)` — historical backfill
- CLI: `py scraper/pse_index.py --backfill --start 2024-01-01`
- Daily scrape registered in scheduler alongside price scrape
- Fallback: if PSE Edge unavailable, skip (do not fabricate index data)

---

## Tier 1 — Monthly Scorecard

### Objective
Build a monthly feedback system that evaluates prior month stock scores vs actual performance using snapshot comparison. This is a measurement layer only (no model adjustments).

### 1.1 Snapshot Table: `feedback_snapshots`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| ticker | TEXT | |
| snapshot_date | DATE | Always 1st of month |
| portfolio_type | TEXT | 'dividend' or 'value' |
| score | REAL | |
| rank | INTEGER | |
| iv_estimate | REAL | NULL for holding firms with no meaningful IV |
| price_at_snapshot | REAL | |
| mos_pct | REAL | Decimal (0.25 = 25% margin of safety) |
| sector | TEXT | |
| is_top10 | BOOLEAN | Based on rank at snapshot time |
| price_source | TEXT | Must be consistent across all snapshots |

**Rules:**
- One row per ticker per portfolio_type per month
- Data must be captured AFTER daily scoring completes
- Use consistent closing price source for all snapshots
- UNIQUE constraint on (ticker, snapshot_date, portfolio_type)

### 1.2 Stock Returns Table: `feedback_stock_returns`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| ticker | TEXT | |
| month | TEXT | YYYY-MM |
| portfolio_type | TEXT | |
| score_at_start | REAL | Score from T-1 snapshot |
| price_start | REAL | |
| price_end | REAL | |
| return_pct | REAL | Decimal (0.05 = 5%) |
| rank_at_start | INTEGER | |
| was_top10 | BOOLEAN | |
| score_change_flag | BOOLEAN | TRUE if score shifted beyond threshold without new financial data |
| score_change_severity | TEXT | NULL, 'minor', or 'major' (see calibration section) |
| score_change_magnitude | REAL | Absolute point change (NULL if no flag) |
| consecutive_flag_months | INTEGER | Rolling count of consecutive months this ticker was flagged |
| created_at | TEXT | ISO timestamp (PHT) |

**UNIQUE constraint on (ticker, month, portfolio_type)**

**Score change detection logic:**
- Compare score at T-1 vs score at T
- Check if ticker received new financial data between T-1 and T (query `financials.updated_at`)
- If abs(score_delta) > `SCORE_CHANGE_MINOR_THRESHOLD` AND no new financials → flag = TRUE
- Severity: minor threshold to major threshold = 'minor', above major threshold = 'major'
- `consecutive_flag_months`: query previous months for same ticker, count consecutive TRUE flags backward from current month
- Thresholds are configurable (see Initial Rollout Calibration section)

### 1.3 Monthly Metrics Table: `feedback_monthly`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| month | TEXT | YYYY-MM, represents evaluation month |
| portfolio_type | TEXT | |
| top10_avg_return | REAL | Decimal |
| top10_vs_index | REAL | Decimal |
| hit_rate_positive | REAL | Decimal |
| match_rate_pct | REAL | Decimal — matched stocks / max(previous, current) |
| mos_direction_accuracy | REAL | Decimal (excludes holding firms with NULL IV) |
| iv_coverage_pct | REAL | Decimal — stocks with non-NULL IV / total scored stocks |
| spearman_correlation | REAL | |
| avg_score_of_gainers | REAL | |
| avg_score_of_losers | REAL | |
| score_separation_power | REAL | gainers avg - losers avg |
| total_previous | INTEGER | |
| total_current | INTEGER | |
| total_matched | INTEGER | |
| market_positive_rate | REAL | Decimal |
| score_change_flag_count | INTEGER | Stocks flagged for unexplained score shifts |
| score_change_minor_count | INTEGER | Flagged stocks with severity = 'minor' |
| score_change_major_count | INTEGER | Flagged stocks with severity = 'major' |
| confidence_level | TEXT | 'low', 'medium', 'high' |
| created_at | TEXT | ISO timestamp (PHT) |

**UNIQUE constraint on (month, portfolio_type)**

### 1.4 Monthly Job: `run_monthly_scorecard()`

**Schedule:** 1st of each month, after scoring completes (6 PM PHT)

**Step 1 — Load Data**
- Load previous month snapshot (T-1)
- Load current month snapshot (T)
- Match stocks by ticker + portfolio_type

**Step 2 — Data Integrity Checks**
- Only include stocks present in BOTH snapshots
- Track: total_previous, total_current, total_matched
- Compute match_rate_pct = total_matched / max(total_previous, total_current)

**Step 3 — Compute Returns**
- Return = (price_T - price_T-1) / price_T-1
- Store as decimal in `feedback_stock_returns`
- For each stock: detect unexplained score shifts (see 1.2 logic)
- Set score_change_flag, score_change_severity, score_change_magnitude
- Compute consecutive_flag_months by querying previous months

**Step 4 — Top 10 Performance**
- Use `is_top10` flag from previous snapshot (T-1) — do NOT recompute
- Compute average return of top 10
- Compare vs index return (same time window, from `index_prices`)

**Step 5 — Market Baseline**
- Compute % of all matched stocks with positive return

**Step 6 — Hit Rate (MoS-based)**
- MoS = (IV - Price) / Price
- Threshold: MoS > 0.15 = predicted upside
- Hit = stock return > 0
- Compute % of correct predictions
- **Exclude** holding firms with NULL IV from this calculation

**Step 7 — MoS Direction Accuracy**
- If MoS > 0 → expected up
- If MoS < 0 → expected down
- Accuracy = % where prediction matches actual direction
- **Exclude** holding firms with NULL IV — they have no meaningful intrinsic value estimate
- Track iv_coverage_pct = stocks with non-NULL IV / total scored stocks

**Step 8 — Score vs Return (Spearman)**
- Rank stocks by score (T-1)
- Rank stocks by return
- Compute Spearman rank correlation

**Step 9 — Score Separation**
- avg_score_of_gainers = avg score of stocks with positive return
- avg_score_of_losers = avg score of stocks with negative return
- separation = gainers avg - losers avg

**Step 10 — Score Stability Aggregation**
- Count total score_change_flag = TRUE stocks
- Count by severity (minor, major)
- Store in feedback_monthly

**Step 11 — Confidence Level**
- High: total_matched >= 30, strong outperformance vs index + high hit rate + positive correlation
- Medium: total_matched >= 15, mixed signals
- Low: total_matched < 15 or unstable/contradictory signals

**Step 12 — Store Results**
- Insert row into feedback_monthly

**Step 13 — Notifications**
- Admin DM format:
  > "Monthly Scorecard — {Month}: Top-10: +X.X% vs PSEi +Y.Y%. Hit Rate: Z.Z%. MoS Accuracy: A.A%. Spearman: B.BB"
- If score_change_major_count > 0:
  > "⚠ {N} stocks had major unexplained score shifts. Review recommended."

**Step 14 — Consecutive Flag Alerts**
- After computing all stock returns, query for any ticker with consecutive_flag_months >= `SCORE_INSTABILITY_ALERT_MONTHS`
- For each such ticker: send immediate admin DM:
  > "Score Instability Alert — {TICKER} has triggered score_change_flag for {N} consecutive months (latest: {severity}). Immediate review recommended — do not wait for next monthly review."
- This fires immediately, not batched with the monthly summary

### 1.5 Critical Constraints
- DO NOT apply any weight adjustments in Tier 1
- Ensure consistent price source across months
- Avoid survivorship bias by matching only overlapping stocks
- Do not recompute Top 10 — rely on stored `is_top10` flag
- Keep logic deterministic and reproducible
- All returns stored as decimals, never percentages
- Holding firms with NULL IV excluded from MoS calculations

---

## Tier 2 — Quarterly Deep Review

### Objective
Evaluate model effectiveness over a 3-month window, detect structural weaknesses, and apply controlled, low-risk auto-corrections.

### 2.1 Trigger Conditions
- Runs quarterly after earnings season
- Trigger manually OR automatically when >30% of stocks have updated financial data since last review
- Must have at least 3 completed monthly scorecards

### 2.2 Table: `feedback_quarterly`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| quarter | TEXT | YYYY-Q# |
| portfolio_type | TEXT | |
| evaluation_window_start | DATE | |
| evaluation_window_end | DATE | |
| avg_monthly_top10_return | REAL | Decimal |
| avg_monthly_hit_rate | REAL | Decimal |
| avg_monthly_mos_accuracy | REAL | Decimal |
| avg_spearman | REAL | |
| blind_spot_count | INTEGER | |
| blind_spot_tickers | TEXT | JSON array |
| sector_bias_json | TEXT | JSON |
| sectors_flagged | TEXT | JSON array |
| sectors_skipped | TEXT | JSON array — sectors below minimum threshold |
| score_band_json | TEXT | JSON |
| band_inversion_flag | BOOLEAN | |
| consecutive_bias_quarters | TEXT | JSON: {sector: count} |
| total_stocks_evaluated | INTEGER | |
| confidence_level | TEXT | 'low', 'medium', 'high' |
| corrections_applied_json | TEXT | JSON or null |
| corrections_blocked_json | TEXT | JSON — corrections that failed gatekeeper with reasons |
| created_at | TEXT | ISO timestamp (PHT) |

**UNIQUE constraint on (quarter, portfolio_type)**

### 2.3 Diagnostic Log Table: `feedback_diagnostic_log`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| quarter | TEXT | YYYY-Q# |
| portfolio_type | TEXT | |
| sector | TEXT | |
| metric_name | TEXT | e.g. 'sector_bias', 'band_monotonicity' |
| metric_value | REAL | |
| z_score | REAL | |
| met_threshold | BOOLEAN | Whether this metric crossed the action threshold |
| stock_count | INTEGER | Stocks in this sector for this evaluation |
| notes | TEXT | |
| created_at | TEXT | ISO timestamp (PHT) |

Provides full audit trail of every diagnostic calculation per sector per quarter.

### 2.4 Step-by-Step Logic

**Step 1 — Aggregate Monthly Data**
- Load 3 monthly scorecards for the quarter
- Compute averages of key metrics

**Step 2 — Define Evaluation Window**
- T0 = first snapshot of quarter
- T1 = last snapshot of quarter
- Return = (price_T1 - price_T0) / price_T0

**Step 3 — Blind Spot Detection**
- Condition: score_T0 > `BLIND_SPOT_SCORE_THRESHOLD` AND return < -`BLIND_SPOT_RETURN_THRESHOLD`
- Count and store tickers
- Thresholds are configurable (see Initial Rollout Calibration section)

**Step 4 — Sector Bias Calculation**

Sector-specific minimum stock thresholds:

| Sector Group | Minimum Stocks |
|--------------|---------------|
| Banks | 3 |
| REITs | 4 |
| All others | 5 |

For each sector meeting its minimum threshold:
- avg_sector_score
- avg_sector_return
- Normalize: score_z = zscore(avg_sector_score), return_z = zscore(avg_sector_return)
- Bias = score_z - return_z
- Flag sector if abs(bias) > `SECTOR_BIAS_Z_THRESHOLD`
- Store: bias_direction, bias_magnitude
- Log each calculation to `feedback_diagnostic_log`

Sectors below their minimum → add to `sectors_skipped`, do NOT evaluate or correct.

**Step 5 — Score Band Analysis**
- Bands: 80-100, 65-79, 50-64, <50
- For each: compute avg return
- Check monotonicity: higher bands must outperform lower bands
- If violated: band_inversion_flag = TRUE

**Step 6 — Persistence Tracking**
- Load previous quarterly data
- Update consecutive_bias_quarters per sector

**Step 7 — Score Instability Review**
- Aggregate score_change_flag data from the quarter's 3 monthly stock returns
- Identify tickers with recurring instability (flagged in 2+ of 3 months)
- Include in quarterly summary as potential data quality or model issues

**Step 8 — Gatekeeper Logic (MANDATORY)**
Auto-correction allowed ONLY if ALL 5 conditions pass:
1. Sector flagged for >= 2 consecutive quarters
2. abs(bias) > `SECTOR_BIAS_Z_THRESHOLD`
3. sector_stock_count >= sector-specific minimum (see Step 4 table)
4. confidence_level != 'low'
5. At least one structural confirmation:
   - band_inversion_flag = TRUE
   - Blind spots present in sector
   - Sector underperforms index consistently

If any condition fails → log to `corrections_blocked_json` with the specific failing condition(s). Do NOT silently skip.

**Step 9 — Auto-Correction**
- Base formula: adjustment = bias_magnitude * 0.3
- Apply confidence weighting: high = 100%, medium = 50%, low = skip
- Cap at +/-3% per quarter
- Hard cap: +/-8% cumulative per sector
- All changes: logged, reversible, additive to base config

**Step 10 — Confidence Level**
- High: total_stocks_evaluated >= 50, stable metrics
- Medium: >= 30
- Low: < 30 or unstable signals
- If low: skip corrections

**Step 11 — Store & Notify**
- Insert into feedback_quarterly
- Log all diagnostic calculations to feedback_diagnostic_log
- Send admin summary with: performance metrics, flagged sectors, skipped sectors, corrections applied, corrections blocked

### 2.5 Critical Constraints
- No corrections in first 3 months of operation
- No corrections if confidence is low
- All logic must be deterministic
- All corrections must be logged and reversible
- Sectors below minimum threshold are skipped, not approximated
- Failed gatekeeper conditions are logged, not silently ignored

---

## Tier 3 — Member Track Record

### Objective
Generate rolling, member-facing performance summaries from Tier 1 data. This is a presentation layer with strict publishability controls to ensure credibility and avoid misleading outputs.

### 3.1 Table: `feedback_track_record`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| period_type | TEXT | '1m', '3m', '6m', '12m' |
| portfolio_type | TEXT | |
| evaluation_date | DATE | |
| top10_avg_return | REAL | Decimal |
| top10_cumulative_return | REAL | Compounded, not averaged. Decimal |
| index_cumulative_return | REAL | Decimal |
| top10_vs_index | REAL | Decimal |
| hit_rate | REAL | Decimal |
| mos_accuracy | REAL | Decimal |
| total_months_tracked | INTEGER | |
| consecutive_months_outperforming_index | INTEGER | |
| best_month_return | REAL | Decimal |
| worst_month_return | REAL | Decimal |
| avg_spearman | REAL | |
| positive_spearman_ratio | REAL | Decimal |
| data_completeness_pct | REAL | Decimal |
| publishable | BOOLEAN | |
| publish_reason | TEXT | Why not publishable, if false |
| created_at | TEXT | ISO timestamp (PHT) |

**UNIQUE constraint on (period_type, portfolio_type, evaluation_date)**

### 3.2 Rolling Window Computation
For each period (1m, 3m, 6m, 12m):
- Load N monthly rows
- Compute: averages (return, hit rate, MoS, Spearman), cumulative returns (compounded), best/worst month, positive Spearman ratio

### 3.3 Index Comparison
- Compute cumulative index return over same window (from `index_prices`)
- top10_vs_index = difference between cumulative returns

### 3.4 Streak Logic
- Count consecutive months (ending at evaluation_date) where top10_return > index_return
- Reset to 0 if latest month underperforms

### 3.5 Publishability Gate

**1m:** Always publish if data exists.

**3m, 6m, 12m:** Require:
- total_months_tracked >= required period
- AND (hit_rate > 0.40 OR top10_vs_index > 0)

**Additional flags:**
- If worst_month_return < -0.15 → mark as unstable (admin review)
- If data_completeness_pct < 1.0 → mark as incomplete

If not publishable: store row, set publish_reason.

### 3.6 Output Constraints
- Never fabricate or extrapolate — only use actual snapshot-based data
- All outputs must include disclaimer: "Past performance is not indicative of future results. These are model outputs, not investment returns."
- Language rules: use "model output", "score-based ranking". Avoid standalone "returns" or "performance."
- If no publishable data yet: "Track record building — first results available after [month]."

### 3.7 Storage & Schedule
- One row per period_type per portfolio_type per evaluation_date
- Overwrite existing row for same key
- Runs immediately after monthly scorecard
- Recompute all rolling windows each run

### 3.8 Tier 3 Isolation Rule
**Tier 3 NEVER influences Tier 2 decisions.** Never allow public perception or marketing pressure to affect model adjustments. This is a read-only presentation layer.

---

## Runtime Auto-Correction Engine

### Objective
Bridge corrections computed in Tier 2 into the live scoring engine safely, transparently, and reversibly.

### 4.1 Storage
Uses existing `settings` table.

**Key format:** `feedback_correction_{sector}_{layer}`

**Value:** JSON string:
```json
{
  "adjustment": -0.015,
  "quarter": "2026-Q1",
  "cumulative": -0.015,
  "version": 2,
  "previous_value": -0.01,
  "status": "active",
  "applied_at": "2026-04-01T18:00:00+08:00"
}
```

### 4.2 Weight Adjustment Logic
- Apply adjustment to target layer ONLY
- Redistribute remaining weight proportionally across other layers based on their base weights
- Do NOT globally re-normalize all layers

Example: If Health base weight = 30%, Improvement = 25%, Persistence = 45%, and Health is reduced by 2%:
- New Health = 28%
- Remaining 2% redistributed: Improvement gets 2% x (25/70) = 0.71%, Persistence gets 2% x (45/70) = 1.29%
- Final: Health 28%, Improvement 25.71%, Persistence 46.29%

### 4.3 Write-Time Validation (MANDATORY)
Before writing any correction:
- Ensure cumulative sector adjustment <= +/-8%
- Ensure no layer weight < 10% after adjustment
- If violated: reject write, log rejection reason, notify admin
- Distinguish between "no correction needed" (normal) and "correction rejected" (logged as blocked)

### 4.4 Read-Time Safety
New function in `engine/feedback_corrections.py`:
```python
def get_layer_weight_override(sector_group: str, layer: str) -> float:
```
- Returns cumulative weight adjustment, or 0.0 if none
- If override is invalid or would violate constraints → return 0.0 (fail-safe)
- Log at DEBUG level when returning 0.0 so silent failures are auditable

### 4.5 Scoring Run Logging
Each scoring run must log:
- Base weight per layer
- Override per layer (or "none")
- Effective weight per layer
- Log to `activity_log` table for audit trail

### 4.6 Cooldown Rule
After a correction is applied:
- Status transitions to `cooling_down` for the next quarter
- During cooldown: no further adjustment UNLESS bias worsens by >50% (measured by z-score increase)
- Prevents stacking corrections quarter-over-quarter

### 4.7 Expiry / Decay Logic
After 4 quarters without reconfirmation:
- If bias gone → expire correction (status = `expired`)
- If bias reduced → decay correction (reduce by 25% per quarter, status = `decaying`)
- If bias persists strongly → keep active

Decay is gradual (25% reduction), not binary expiry. A -0.02 correction decays to -0.015, then -0.01125, etc.

### 4.8 Correction Statuses
| Status | Meaning |
|--------|---------|
| active | Currently applied to scoring |
| cooling_down | Applied last quarter, waiting to observe |
| decaying | Being reduced by 25% per quarter |
| expired | Removed after bias resolved |
| admin_reset | Manually removed by admin |

### 4.9 Hard Constraints
- Max +/-3% per sector per quarter
- Max +/-8% cumulative per sector across all layers
- No layer weight below 10% after adjustment
- No corrections in first 3 months of operation
- All corrections logged, versioned, reversible
- Fail-safe: invalid override → return 0.0

---

## Observability & Edge Case Handling

### O1 — NULL IV Coverage Monitoring
- Track `iv_coverage_pct` in `feedback_monthly`
- If iv_coverage_pct < 0.70 → admin warning: "MoS accuracy metrics are based on {X}% of scored stocks — holding firms and stocks without IV estimates are excluded"
- Prevents MoS accuracy from appearing more reliable than it is

### O2 — Small Sector Monitoring
- Sectors below their minimum threshold (see Tier 2 Step 4) are skipped, not approximated
- `sectors_skipped` field in `feedback_quarterly` records which sectors were excluded and why
- If a sector is skipped for 3+ consecutive quarters → admin DM: "{Sector} has been below evaluation threshold for {N} quarters — consider manual review"

### O3 — Correction Cap Escalation
- If a sector hits the +/-8% cumulative cap AND bias persists → admin DM with recommendation
- Options presented: (a) raise cap for this sector (requires admin approval), (b) flag for manual model review, (c) accept current cap as sufficient
- System does NOT auto-raise caps. Admin decision only.

### O4 — Silent Override Rejection Auditing
- `get_layer_weight_override()` must log distinctly:
  - "No correction exists" (normal, DEBUG level)
  - "Correction exists but rejected due to constraint violation" (WARNING level)
- `corrections_blocked_json` in `feedback_quarterly` stores all blocked corrections with specific failure reasons
- Monthly audit: if >3 corrections are silently rejected in a quarter → admin DM

### O5 — Prolonged Unpublishability Detection
- If any portfolio_type + period_type combination remains unpublishable for >6 months → admin alert
- Suggests investigation: is the model consistently underperforming, or is data completeness the issue?

### O6 — Scoring Freshness Gate
- Before running monthly scorecard: verify that daily scoring ran within the last 48 hours
- If stale: skip scorecard, log reason, notify admin
- Prevents stale scores from contaminating feedback metrics

### O7 — Thin Month Detection
- If total_matched < `THIN_MONTH_THRESHOLD` for any portfolio_type in a monthly scorecard → mark confidence as 'low'
- Admin DM: "Thin month detected — only {N} stocks matched for {portfolio}. Scorecard computed but flagged low confidence."
- Tier 2 excludes thin months from quarterly aggregation

### O8 — Cumulative Adjustment Monitoring
- Dashboard widget showing total cumulative adjustment per sector per layer
- Color-coded: green (<3%), yellow (3-6%), red (>6%, approaching 8% cap)
- Historical chart showing adjustment trajectory over quarters

### O9 — Score Stability Monitoring

**Per-stock detection** (in `feedback_stock_returns`):
- `score_change_flag`: TRUE if score shifted beyond threshold without new financial data between snapshots
- `score_change_severity`: 'minor' or 'major' (thresholds configurable — see calibration section)
- `score_change_magnitude`: absolute point change for analysis

**Rolling historical trend** (per ticker):
- `consecutive_flag_months`: rolling count of consecutive months this ticker was flagged
- Computed by querying previous `feedback_stock_returns` rows for same ticker+portfolio_type
- Resets to 0 when a month passes without a flag

**Automated escalation**:
- If any ticker reaches consecutive_flag_months >= `SCORE_INSTABILITY_ALERT_MONTHS` → immediate admin DM (not batched with monthly summary):
  > "Score Instability Alert — {TICKER} has triggered score_change_flag for {N} consecutive months (latest: {severity}, magnitude: {X} pts). Immediate review recommended."
- This indicates a potential data quality issue, stale data, or model edge case that needs human investigation

**Monthly aggregation** (in `feedback_monthly`):
- `score_change_flag_count`: total stocks flagged this month
- `score_change_minor_count`: flagged with severity = 'minor'
- `score_change_major_count`: flagged with severity = 'major'
- If major_count > 0 → included in monthly admin DM summary

---

## Initial Rollout Calibration

Many threshold rules in this spec are based on reasonable assumptions, not empirical PSE market data. During the first 3 months of operation (the mandatory no-correction window), these thresholds must be validated and adjusted before Tier 2 activates.

### Configurable Thresholds

All thresholds below are stored in `config.py` with initial defaults. They are NOT hardcoded in logic files — always import from config.

| Threshold | Config Key | Initial Default | What It Controls |
|-----------|-----------|----------------|-----------------|
| Score change minor | `SCORE_CHANGE_MINOR_THRESHOLD` | 15 | Points shift to trigger 'minor' flag |
| Score change major | `SCORE_CHANGE_MAJOR_THRESHOLD` | 30 | Points shift to trigger 'major' flag |
| Blind spot score | `BLIND_SPOT_SCORE_THRESHOLD` | 70 | Min score for blind spot detection |
| Blind spot return | `BLIND_SPOT_RETURN_THRESHOLD` | 0.10 | Negative return threshold (decimal) |
| Sector bias z-score | `SECTOR_BIAS_Z_THRESHOLD` | 1.0 | Z-score for flagging sector bias |
| Thin month minimum | `THIN_MONTH_THRESHOLD` | 15 | Min matched stocks for valid month |
| MoS hit rate threshold | `MOS_HIT_THRESHOLD` | 0.15 | MoS cutoff for predicted upside |
| Instability alert months | `SCORE_INSTABILITY_ALERT_MONTHS` | 3 | Consecutive months before immediate DM |
| Sector min (banks) | `SECTOR_MIN_BANKS` | 3 | Min stocks for bank sector evaluation |
| Sector min (REITs) | `SECTOR_MIN_REITS` | 4 | Min stocks for REIT sector evaluation |
| Sector min (default) | `SECTOR_MIN_DEFAULT` | 5 | Min stocks for other sectors |

### Calibration Protocol (Months 1-3)

**Month 1 — Baseline Collection**
- Run Tier 1 as designed. No threshold adjustments.
- Observe: How many stocks trigger score_change_flag at 15-pt threshold? Is it 2% of the universe or 40%? Both extremes indicate a bad threshold.
- Record: actual distribution of score changes across the scored universe.

**Month 2 — Distribution Analysis**
- Compute percentile distribution of month-over-month score changes (all stocks, not just flagged)
- Target: score_change_flag should fire on ~5-10% of stocks (top tail of unexplained shifts)
- If >20% flagged: threshold too low → raise
- If <2% flagged: threshold too high → lower
- Same logic for blind spot thresholds: how many "high score + negative return" stocks exist? If zero blind spots every month, the threshold is too strict.

**Month 3 — Threshold Adjustment**
- Adjust thresholds based on observed distributions
- Log all changes to `activity_log` with category = 'feedback_calibration'
- Admin DM summarizing calibration decisions before Tier 2 activates

**Ongoing Recalibration**
- Every 6 months: review threshold hit rates. If a threshold fires on 0% or >30% of cases, it is not useful — flag for admin review.
- Thresholds are never auto-adjusted. Always admin-approved.
- All calibration changes are logged and reversible.

### What "Validated Empirically" Means
A threshold is considered validated when:
1. It has been observed across at least 3 monthly cycles
2. Its hit rate falls within a useful range (neither trivial nor overwhelming)
3. The flagged items, when manually reviewed, represent genuine anomalies (not noise)
4. Admin has explicitly approved the value (or approved keeping the default)

Until validated, the system runs in **observation mode** — it measures and reports, but does not act on the thresholds for correction purposes.

---

## Dashboard Integration

### New page: `/feedback` (admin-only)

**Tab 1: Monthly Scorecards**
- Table view of feedback_monthly — one row per month per portfolio
- Color-coded: green if top-10 beat index, red if not
- Sparkline trend for top-10 return over last 6 months
- Score stability summary: minor/major flag counts per month

**Tab 2: Quarterly Reviews**
- Expandable cards per quarter
- Summary: headline metrics, flagged sectors, skipped sectors, blind spot tickers
- Score band analysis visualization
- Corrections applied with status
- Corrections blocked with failure reasons

**Tab 3: Active Corrections**
- List of all active sector weight overrides
- Shows: sector, layer, adjustment, status, applied date, quarter, cumulative
- Performance impact: before vs after correction
- Cumulative adjustment gauge per sector (color-coded per O8)
- "Reset" button per correction
- "Reset All" with confirmation dialog

### Portal Track Record Section (public)
- Shows only `publishable = TRUE` stats from feedback_track_record
- Cards with headline numbers
- Mandatory disclaimer on every view
- If no publishable data: "Track record building — first results available after [month]."

---

## Discord Integration

### New file: `discord/discord_feedback.py`

Functions:
- `send_monthly_scorecard_dm(admin_id, scorecard_data)` — compact 1-embed summary
- `send_quarterly_review_dm(admin_id, review_data)` — detailed summary + corrections
- `send_correction_batch_dm(admin_id, corrections)` — batch multiple corrections into one message (avoid per-correction spam)
- `send_correction_expiry_dm(admin_id, expired_corrections)` — batch expiry notices
- `send_score_instability_alert(admin_id, ticker, consecutive_months, severity, magnitude)` — immediate DM for recurring instability (not batched)

Re-exported via `discord/publisher.py` facade.

### Weekly Briefing Integration
- Append track record one-liner to weekly briefing when 6m period is publishable
- Format: "Model track record (6mo): Top-10 avg +X.X% vs PSEi +Y.Y% | Hit rate Z.Z%"

---

## New File Structure

```
scraper/
  pse_index.py                — PSEi index scraper + backfill CLI

engine/
  feedback_corrections.py     — get_layer_weight_override(), validate_correction()

feedback/
  __init__.py
  CLAUDE.md                   — folder-specific implementation notes
  snapshot.py                 — take_monthly_snapshot()
  monthly_scorecard.py        — run_monthly_scorecard()
  quarterly_review.py         — run_quarterly_review()
  track_record.py             — compute_track_record()
  correction_engine.py        — apply_correction(), decay_corrections(), expire_corrections()
  scheduler_feedback.py       — thin wrapper for scheduler_jobs.py (keeps it under 500 lines)

dashboard/
  routes_feedback.py          — /feedback page + API endpoints
  templates/feedback.html     — 3-tab admin page

discord/
  discord_feedback.py         — DM functions for feedback events

tests/
  test_feedback.py            — Tier 1 unit tests
  test_quarterly_review.py    — Gatekeeper + Tier 2 tests
```

---

## Database Migrations (db/db_schema.py)

New tables (7 total):
- `index_prices`
- `feedback_snapshots`
- `feedback_stock_returns`
- `feedback_monthly`
- `feedback_quarterly`
- `feedback_diagnostic_log`
- `feedback_track_record`

All created via idempotent `CREATE TABLE IF NOT EXISTS` in the existing migration system.

---

## Scheduler Integration

All feedback jobs registered in `feedback/scheduler_feedback.py` (thin wrapper) to keep `scheduler_jobs.py` under 500 lines.

| Job | Schedule (PHT) | Trigger |
|-----|----------------|---------|
| `take_monthly_snapshot()` | 1st of month, 5 PM | CronTrigger(day=1, hour=17) |
| `run_monthly_scorecard()` | 1st of month, 6 PM | CronTrigger(day=1, hour=18) |
| `compute_track_record()` | 1st of month, 6:30 PM | CronTrigger(day=1, hour=18, minute=30) |
| `run_quarterly_review()` | Manual or auto-triggered | When >30% financials updated |
| PSEi daily scrape | Daily, with price scrape | Alongside existing price job |

---

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Sparse data in first 3 months | High | Low | No corrections allowed; measurement only |
| Small sector sample sizes | High | Medium | Sector-specific minimums; skip below threshold |
| Stale price data corrupting returns | Medium | High | O6 scoring freshness gate |
| Correction stacking across quarters | Medium | High | Cooldown rule; +/-8% cumulative cap |
| Silent override failures | Medium | Medium | O4 distinct logging; blocked corrections tracked |
| PSEi index unavailable | Low | Medium | Graceful skip; no fabricated index data |
| Unexplained score shifts | Medium | Medium | O9 per-stock detection + severity tiering + auto-escalation |
| Tier 3 influencing Tier 2 | Low | Critical | Strict isolation; zero write paths; Golden Rule |
| Holding firm IV bias | Medium | Medium | Excluded from MoS calculations; iv_coverage_pct tracked |
| Threshold rules based on assumptions | High | Medium | Initial rollout calibration protocol; 3-month observation before action |

---

*Revision history:*
- *Rev 1: Initial 3-tier structure + auto-correction engine*
- *Rev 2: PHT timezones, feedback_stock_returns table, decimal returns, holding firm IV exclusion*
- *Rev 3: Observability section (O1-O8), sectors_skipped, corrections_blocked_json, diagnostic_log table*
- *Rev 4: O9 score stability monitoring with score_change_flag*
- *Rev 5: Score change severity tiering (minor/major), rolling consecutive flag tracking, automated immediate DM for recurring instability, configurable thresholds with initial rollout calibration protocol, risk matrix*

*Last updated: 2026-03-24*
