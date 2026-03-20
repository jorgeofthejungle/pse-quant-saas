# Data Quality Hardening & Scoring Recalibration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the PSE Quant data pipeline to catch bad data earlier and recalibrate the scoring engine to reflect Philippine market reality, expanding the qualifying stock universe from ~12 to 20+ stocks.

**Architecture:** Phase A fixes data quality (dividend attribution, write gates, staleness prevention). Phase B recalibrates scoring (percentile thresholds, portfolio-specific weights, confidence-weighted scoring, risk-adjusted MoS). Changes are ordered to front-load scoring accuracy and data expansion, deferring operational monitoring to last. Each task produces a working, testable change with a commit.

**Tech Stack:** Python 3.14, SQLite, ReportLab (PDF), Flask (dashboard), discord.py (bot), APScheduler

**Spec:** `docs/superpowers/specs/2026-03-17-data-quality-scoring-recalibration-design.md`

**Python command:** `py` (not `python`)

**Test pattern:** This project uses a simple test runner — `if __name__ == '__main__':` blocks, not pytest fixtures. All assertions use plain `assert`. Run with `py tests/test_*.py`.

---

## File Map

### Files to Create
| File | Responsibility |
|------|---------------|
| `engine/calibrate_thresholds.py` | Derives health thresholds from DB percentiles; writes to `settings` table |
| `reports/pdf_portfolio_sections.py` | Multi-section layout for unified PDF (3 portfolio sections) |
| `tests/test_phase11.py` | All Phase 11 unit tests (scoring fixes, confidence, MoS, etc.) |

### Files to Modify (by chunk)
| Chunk | Files |
|-------|-------|
| 1: Scoring fixes | `engine/scorer_improvement.py`, `engine/scorer_persistence.py`, `config.py` |
| 2: Data quality | `scraper/pse_stock_data.py`, `scraper/pse_stock_builder.py`, `scraper/pse_edge_scraper.py`, `db/db_schema.py`, `engine/validator.py`, `config.py` |
| 3: Data expansion | `scraper/pse_financial_reports.py`, `engine/validator.py`, `engine/scorer_v2.py`, `engine/filters_v2.py`, `engine/scorer_acceleration.py`, `db/db_schema.py`, `db/db_scores.py`, `config.py`, `scheduler.py`, `reports/pdf_stock_detail_page.py` |
| 4: Recalibration | `engine/sector_stats.py`, `engine/scorer_health.py`, `engine/mos.py`, `config.py`, `scraper/pse_stock_builder.py` |
| 5: Portfolio + PDF | `engine/scorer_v2.py`, `db/db_schema.py`, `db/db_scores.py`, `db/database.py`, `reports/pdf_generator.py`, `main.py`, `scheduler_jobs.py`, `discord/bot_commands.py`, `config.py` |
| 6: Monitoring | `scraper/pse_lookup.py`, `scraper/pse_stock_data.py`, `scraper/pse_financial_reports.py`, `scraper/pse_edge_scraper.py`, `engine/validator.py`, `scraper/pse_stock_builder.py`, `scheduler_jobs.py`, `scheduler.py`, `dashboard/routes_pipeline.py`, `dashboard/routes_home.py` |

---

## Chunk 1: Quick Scoring Fixes (Spec Sections 14, 13, 10)

Pure engine changes — no schema changes, no scraper changes. Three independent tasks that immediately improve scoring accuracy.

### Task 1: ROE Delta Year Validation (Spec Section 14)

**Problem:** `_roe_delta()` in `scorer_improvement.py:75` uses `financials_history[3]` (hardcoded index). If any year is missing from history, index 3 points to the wrong year.

**Files:**
- Modify: `engine/scorer_improvement.py:75-95`
- Test: `tests/test_phase11.py` (create)

- [ ] **Step 1: Create test file with ROE delta year validation tests**

Create `tests/test_phase11.py` with the test infrastructure and ROE delta tests:

```python
# tests/test_phase11.py — Phase 11 unit tests
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.scorer_improvement import _roe_delta

# ── Task 1: ROE delta year validation ─────────────────────

def test_roe_delta_correct_year_with_gap():
    """If year 2023 is missing, should still compare 2025 vs 2022."""
    history = [
        {'year': 2025, 'net_income': 1000, 'equity': 5000},  # ROE = 20%
        {'year': 2024, 'net_income': 900,  'equity': 5000},
        # 2023 missing
        {'year': 2022, 'net_income': 500,  'equity': 5000},  # ROE = 10%
        {'year': 2021, 'net_income': 400,  'equity': 5000},
    ]
    delta = _roe_delta(20.0, history)
    assert delta is not None, "Should find year 2022 despite gap"
    assert abs(delta - 10.0) < 0.01, f"Expected ~10.0, got {delta}"
    print('  roe_delta correct year with gap: PASS')


def test_roe_delta_returns_none_when_target_year_missing():
    """If the target year (current - 3) doesn't exist at all, return None."""
    history = [
        {'year': 2025, 'net_income': 1000, 'equity': 5000},
        {'year': 2024, 'net_income': 900,  'equity': 5000},
    ]
    delta = _roe_delta(20.0, history)
    assert delta is None, "Should return None when target year not found"
    print('  roe_delta None when target year missing: PASS')


def test_roe_delta_exact_3_year_gap():
    """Standard case: 4 consecutive years, compare index 0 vs 3."""
    history = [
        {'year': 2025, 'net_income': 1500, 'equity': 5000},  # ROE = 30%
        {'year': 2024, 'net_income': 1200, 'equity': 5000},
        {'year': 2023, 'net_income': 1000, 'equity': 5000},
        {'year': 2022, 'net_income': 750,  'equity': 5000},  # ROE = 15%
    ]
    delta = _roe_delta(30.0, history)
    assert delta is not None
    assert abs(delta - 15.0) < 0.01, f"Expected ~15.0, got {delta}"
    print('  roe_delta exact 3-year gap: PASS')


if __name__ == '__main__':
    tests = [
        test_roe_delta_correct_year_with_gap,
        test_roe_delta_returns_none_when_target_year_missing,
        test_roe_delta_exact_3_year_gap,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f'  FAIL {t.__name__}: {e}')
            failed += 1
        except Exception as e:
            print(f'  ERROR {t.__name__}: {e}')
            failed += 1
    print(f'\n{"="*50}')
    print(f'  {passed} passed, {failed} failed')
    print(f'{"="*50}')
    if failed:
        sys.exit(1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py tests/test_phase11.py`
Expected: FAIL — `_roe_delta` with a gap in years returns wrong value (uses index 3 which is year 2021, not target year 2022)

- [ ] **Step 3: Fix `_roe_delta` to index by fiscal year**

In `engine/scorer_improvement.py`, replace lines 75-95:

```python
def _roe_delta(roe_current: float | None,
               financials_history: list) -> float | None:
    """
    Computes ROE delta = current ROE - ROE 3 years ago.
    Uses financials_history (list of annual rows, newest first).
    Indexes by actual fiscal year, not array position, to handle gaps.
    Each row must have 'year', 'net_income', and 'equity' fields.
    """
    if roe_current is None:
        return None
    if not financials_history or len(financials_history) < 2:
        return None

    current_year = financials_history[0].get('year')
    if current_year is None:
        return None
    target_year = current_year - 3

    target_entry = next(
        (f for f in financials_history if f.get('year') == target_year), None
    )
    if target_entry is None:
        return None

    ni_3y = target_entry.get('net_income')
    eq_3y = target_entry.get('equity')
    if ni_3y is None or eq_3y is None or eq_3y <= 0:
        return None
    roe_3y = (ni_3y / eq_3y) * 100
    return roe_current - roe_3y
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py tests/test_phase11.py`
Expected: All 3 tests PASS

- [ ] **Step 5: Run existing scorer tests to verify no regression**

Run: `py tests/test_scorer_v2.py`
Expected: All 17 tests PASS

- [ ] **Step 6: Commit**

```bash
git add engine/scorer_improvement.py tests/test_phase11.py
git commit -m "fix: ROE delta indexes by fiscal year, not array position

Previously used hardcoded index [3] which gave wrong results when
years were missing from financials_history. Now searches for the
actual target year (current_year - 3).

Spec: Section 14
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Improvement Layer Recency Weighting (Spec Section 13)

**Problem:** `_smoothed_delta()` in `scorer_improvement.py:62` uses simple average. A stock with revenue [+20%, +15%, -8%] averages +9% — hiding the recent decline.

**Files:**
- Modify: `engine/scorer_improvement.py:62-72`
- Modify: `config.py` (add `IMPROVEMENT_RECENCY_WEIGHTS`)
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add recency weighting tests to test_phase11.py**

Append to `tests/test_phase11.py`:

```python
from engine.scorer_improvement import _smoothed_delta

# ── Task 2: Improvement recency weighting ─────────────────

def test_smoothed_delta_recency_negative_recent():
    """Recent decline should pull weighted average down vs simple average."""
    # Series newest-first: most recent year declined
    series = [92, 100, 85]  # changes: -8%, +17.6%
    delta = _smoothed_delta(series, 3)
    # Weighted: -8 * 0.50 + 17.6 * 0.30 = -4.0 + 5.3 = +1.3 (approx)
    # Simple average would be (-8 + 17.6) / 2 = +4.8
    assert delta is not None
    assert delta < 4.8, f"Recency weighting should be < simple avg 4.8, got {delta}"
    print(f'  smoothed_delta recency (negative recent): {delta:.1f} — PASS')


def test_smoothed_delta_recency_positive_recent():
    """Recent growth should pull weighted average up."""
    series = [120, 100, 110]  # changes: +20%, -9.1%
    delta = _smoothed_delta(series, 3)
    # Weighted: 20 * 0.50 + (-9.1) * 0.30 = 10.0 - 2.7 = +7.3 (approx)
    # Simple average: (20 + -9.1) / 2 = +5.45
    assert delta is not None
    assert delta > 5.5, f"Recency weighting should be > simple avg 5.45, got {delta}"
    print(f'  smoothed_delta recency (positive recent): {delta:.1f} — PASS')


def test_smoothed_delta_falls_back_with_fewer_changes():
    """With only 1 change, should still return a value (no weighting needed)."""
    series = [110, 100]  # one change: +10%
    delta = _smoothed_delta(series, 3)
    assert delta is not None
    assert abs(delta - 10.0) < 0.5
    print(f'  smoothed_delta single change: {delta:.1f} — PASS')
```

Add these to the `tests` list and `if __name__` block.

- [ ] **Step 2: Run tests to verify they fail**

Run: `py tests/test_phase11.py`
Expected: `test_smoothed_delta_recency_negative_recent` FAILS (simple average gives ~4.8, not < 4.8)

- [ ] **Step 3: Add IMPROVEMENT_RECENCY_WEIGHTS to config.py**

Append to `config.py` after line 108 (`MOMENTUM_MIN_YEARS = 4`):

```python
# ── Improvement Layer Recency Weighting ──────────────────
# Applied to 3-year smoothed deltas in scorer_improvement.py.
# Most recent YoY change gets 50% weight, then 30%, then 20%.
IMPROVEMENT_RECENCY_WEIGHTS = [0.50, 0.30, 0.20]  # newest first
```

- [ ] **Step 4: Update `_smoothed_delta` to use recency weighting**

In `engine/scorer_improvement.py`, replace lines 62-72:

```python
def _smoothed_delta(series: list, years: int = 3) -> float | None:
    """
    Computes the recency-weighted average of the most recent N YoY changes.
    Weights are loaded from config.IMPROVEMENT_RECENCY_WEIGHTS (newest first).
    Falls back to simple average if fewer changes than weights available.
    Returns None if fewer than 2 data points are available.
    """
    from config import IMPROVEMENT_RECENCY_WEIGHTS

    changes = _yoy_changes(series)
    if not changes:
        return None
    recent = changes[:years]  # newest changes first

    # Apply recency weights if we have enough changes
    weights = IMPROVEMENT_RECENCY_WEIGHTS[:len(recent)]
    if len(recent) >= len(weights) and len(weights) > 1:
        total_w = sum(weights)
        return sum(c * w for c, w in zip(recent, weights)) / total_w
    # Fallback: simple average for 1 change or missing config
    return sum(recent) / len(recent)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py tests/test_phase11.py`
Expected: All 6 tests PASS (3 from Task 1 + 3 from Task 2)

- [ ] **Step 6: Run existing scorer tests for regression**

Run: `py tests/test_scorer_v2.py`
Expected: All 17 tests PASS

- [ ] **Step 7: Commit**

```bash
git add engine/scorer_improvement.py config.py tests/test_phase11.py
git commit -m "feat: add recency weighting to improvement layer deltas

Most recent YoY change gets 50% weight (was equal weight).
Revenue [+20%, +15%, -8%] now scores +1.3% (was +9%), properly
reflecting the recent decline.

Weights configurable via IMPROVEMENT_RECENCY_WEIGHTS in config.py.

Spec: Section 13
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Persistence Layer Magnitude Awareness (Spec Section 10)

**Problem:** `_score_single_persistence()` in `scorer_persistence.py:80` counts direction only. Three consecutive years of +0.1% scores same as +20%.

**Files:**
- Modify: `engine/scorer_persistence.py:80-107`
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add persistence magnitude tests**

Append to `tests/test_phase11.py`:

```python
from engine.scorer_persistence import _score_single_persistence

# ── Task 3: Persistence magnitude awareness ───────────────

def test_persistence_strong_growth_beats_marginal():
    """Stock with +18%/+15%/+12% growth should outscore +0.5%/+0.3%/+0.1%."""
    # Strong grower: 3 positive years, large magnitude
    strong = [130, 110, 95, 82]  # newest first, all growing ~15%
    weak   = [103, 102.5, 102, 101.5]  # all growing ~0.5%

    strong_score = _score_single_persistence(strong)
    weak_score   = _score_single_persistence(weak)

    assert strong_score is not None and weak_score is not None
    assert strong_score > weak_score, \
        f"Strong growth ({strong_score}) should beat marginal ({weak_score})"
    print(f'  persistence: strong {strong_score} > marginal {weak_score} — PASS')


def test_persistence_magnitude_within_bounds():
    """Magnitude component should be 0-20 (not blow up the total)."""
    series = [200, 170, 145, 125, 110]  # ~15-18% growth each year
    score = _score_single_persistence(series)
    assert score is not None
    assert 0 <= score <= 100, f"Score must be 0-100, got {score}"
    print(f'  persistence magnitude within bounds: {score} — PASS')


def test_persistence_marginal_growth_gets_small_magnitude():
    """Very small growth should get minimal magnitude points."""
    series = [101, 100.5, 100.2, 100.1]  # <1% growth
    score = _score_single_persistence(series)
    assert score is not None
    # direction 60*(3/3)=60, magnitude ~2 (<1% avg), streak 15 → ~77
    assert 70 <= score <= 85, f"Expected 70-85 for marginal growth, got {score}"
    print(f'  persistence marginal growth: {score} — PASS')
```

Add these to the `tests` list.

- [ ] **Step 2: Run tests to verify they fail**

Run: `py tests/test_phase11.py`
Expected: `test_persistence_strong_growth_beats_marginal` FAILS — both score the same because current formula ignores magnitude.

- [ ] **Step 3: Update `_score_single_persistence` with magnitude formula**

In `engine/scorer_persistence.py`, replace lines 80-107:

```python
def _score_single_persistence(series: list | None,
                               min_years: int = 2) -> float | None:
    """
    Scores persistence for a single metric series (0-100).
    Blended formula: direction (60pts) + magnitude (20pts) + streak (20pts).

    Magnitude scoring (avg positive YoY change):
        >= 15%  →  20 pts
        10-15%  →  15 pts
         5-10%  →  10 pts
         1-5%   →   5 pts
         < 1%   →   2 pts
    """
    if not series:
        return None
    clean = [v for v in series if v is not None]
    if len(clean) < min_years + 1:
        return None

    ratio, pos, total = _persistence_ratio(series, years=5)
    streak = _consecutive_streak(series)

    # ── Direction score: 0-60 points ──
    direction = ratio * 60

    # ── Magnitude score: 0-20 points ──
    # Average of positive YoY % changes
    changes = []
    for i in range(len(clean) - 1):
        prior = clean[i + 1]
        curr = clean[i]
        if prior != 0:
            pct = (curr - prior) / abs(prior) * 100
            if pct > 0:
                changes.append(pct)
    if changes:
        avg_positive = sum(changes) / len(changes)
        if avg_positive >= 15:
            magnitude = 20
        elif avg_positive >= 10:
            magnitude = 15
        elif avg_positive >= 5:
            magnitude = 10
        elif avg_positive >= 1:
            magnitude = 5
        else:
            magnitude = 2
    else:
        magnitude = 0

    # ── Streak bonus: 0-20 points ──
    bonus = min(streak * 5, 20)

    raw_score = direction + magnitude + bonus

    # Penalty: if streak is 0 (most recent year declined), cap at 65
    if streak == 0 and raw_score > 65:
        raw_score = 65

    return round(min(raw_score, 100), 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py tests/test_phase11.py`
Expected: All 9 tests PASS

- [ ] **Step 5: Run existing persistence tests for regression**

Run: `py tests/test_scorer_v2.py`
Expected: All 17 tests PASS. Note: `test_persistence_strong` expects > 60 which should still pass with new formula since strong stock has consistent growth.

- [ ] **Step 6: Commit**

```bash
git add engine/scorer_persistence.py tests/test_phase11.py
git commit -m "feat: add magnitude awareness to persistence layer

New formula: direction (60pts) + magnitude (20pts) + streak (20pts).
Stocks with strong consistent growth now outscore marginal growers
with the same direction pattern.

Spec: Section 10
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Data Quality Fixes (Spec Sections 3, 4)

Scraper and validator changes. Includes a DB schema migration for `fiscal_year_end_month`.

### Task 4: Dividend Fiscal Year Attribution (Spec Section 3)

**Problem:** Dividends are attributed by ex-date year instead of fiscal year. A FY2024 dividend with Jan 2025 ex-date is counted as 2025 DPS. Also, current-year partial DPS enters scoring.

**Files:**
- Modify: `scraper/pse_stock_data.py:92-202` (add fiscal year mapping)
- Modify: `db/db_schema.py` (add `fiscal_year_end_month` column to `stocks`)
- Modify: `scraper/pse_stock_builder.py:31-231` (current-year DPS exclusion)
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add fiscal year mapping tests**

Append to `tests/test_phase11.py`:

```python
# ── Task 4: Dividend fiscal year attribution ──────────────

def test_fiscal_year_mapping_jan_exdate():
    """Jan 2025 ex-date for Dec year-end company → fiscal year 2024."""
    ex_month, ex_year, fy_end_month = 1, 2025, 12
    fiscal_year = ex_year if ex_month >= fy_end_month else ex_year - 1
    assert fiscal_year == 2024
    print('  fiscal year mapping Jan ex-date: PASS')


def test_fiscal_year_mapping_mar_exdate():
    """Mar 2025 ex-date for Dec year-end → fiscal year 2024."""
    ex_month, ex_year, fy_end_month = 3, 2025, 12
    fiscal_year = ex_year if ex_month >= fy_end_month else ex_year - 1
    assert fiscal_year == 2024
    print('  fiscal year mapping Mar ex-date: PASS')


def test_fiscal_year_mapping_jun_yearend():
    """Sep 2025 ex-date for Jun year-end company → fiscal year 2025."""
    ex_month, ex_year, fy_end_month = 9, 2025, 6
    fiscal_year = ex_year if ex_month >= fy_end_month else ex_year - 1
    assert fiscal_year == 2025
    print('  fiscal year mapping Jun year-end: PASS')


def test_fiscal_year_mapping_dec_exdate():
    """Dec 2025 ex-date for Dec year-end → fiscal year 2025."""
    ex_month, ex_year, fy_end_month = 12, 2025, 12
    fiscal_year = ex_year if ex_month >= fy_end_month else ex_year - 1
    assert fiscal_year == 2025, f"Got {fiscal_year}"
    print('  fiscal year mapping Dec ex-date: PASS')
```

- [ ] **Step 2: Run tests — these are pure formula tests, they pass immediately**

Run: `py tests/test_phase11.py`
Expected: Formula tests PASS (they test the mapping formula, not the scraper integration)

- [ ] **Step 3: Add `fiscal_year_end_month` column to db_schema.py**

In `db/db_schema.py`, in the migrations section (after existing ALTER TABLE blocks), add:

```python
# Migration: add fiscal_year_end_month to stocks
try:
    cur.execute("ALTER TABLE stocks ADD COLUMN fiscal_year_end_month INTEGER DEFAULT 12")
except Exception:
    pass
```

- [ ] **Step 4: Update `scrape_dividend_history` to add fiscal year mapping**

In `scraper/pse_stock_data.py`, modify `scrape_dividend_history()` to accept `fiscal_year_end_month` parameter and add fiscal year to each result:

After the existing ex-date parsing and DPS extraction, add fiscal year mapping:

```python
# In scrape_dividend_history(), after extracting ex_date and dps:
# Add parameter: fiscal_year_end_month=12
# For each dividend entry, compute fiscal_year:
#   fiscal_year = ex_year if ex_month > fiscal_year_end_month else ex_year - 1
# Return: [{year: int, dps: float, fiscal_year: int}]
```

The exact edit: add `fiscal_year_end_month=12` parameter to `scrape_dividend_history()` signature, and after computing `year` from ex-date, add:

```python
ex_month = ex_date.month
fiscal_year = year if ex_month >= fiscal_year_end_month else year - 1
```

Include `fiscal_year` in each returned dict alongside the existing `year` (which stays as ex-date year for dedup).

**Important storage clarification:** When DPS is stored via `upsert_financials()`, the `year` column should use `fiscal_year` (not ex-date year). This ensures the `financials` table consistently represents fiscal years. The ex-date year is only used for dedup within the scraper. `build_stock_dict_from_db` reads from `financials.year` which will now be fiscal year.

- [ ] **Step 5: Update `build_stock_dict_from_db` to exclude current-year DPS**

In `scraper/pse_stock_builder.py`, in `build_stock_dict_from_db()`, where DPS is loaded from financials, add current fiscal year exclusion:

```python
from datetime import date
current_fiscal_year = date.today().year
# When building dps_last, dividend_yield, dividend_cagr_5y, payout_ratio:
# Filter: only use DPS where year < current_fiscal_year
```

This ensures partial-year DPS doesn't enter scoring while remaining available for alerts/calendar.

- [ ] **Step 6: Run full test suite for regression**

Run: `py tests/test_phase11.py && py tests/test_scorer_v2.py && py tests/test_filters_v2.py`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add scraper/pse_stock_data.py scraper/pse_stock_builder.py db/db_schema.py tests/test_phase11.py
git commit -m "feat: dividend fiscal year attribution + current-year exclusion

Dividends now attributed to fiscal year (not ex-date year).
Jan-Mar ex-dates for Dec year-end companies map to prior fiscal year.
Current fiscal year DPS excluded from scoring (partial-year data).
Added fiscal_year_end_month column to stocks table (default 12).

Spec: Section 3
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Tighten Write-Time Gates + REIT Fix (Spec Section 4)

**Problem:** Yield gate at 40%/50% is too loose. 4 REITs misclassified. ROE < -50% only warned, not blocked. P/B > 100 too lenient.

**Files:**
- Modify: `scraper/pse_edge_scraper.py:166-171` (yield gate thresholds)
- Modify: `engine/validator.py:45-50,106` (block thresholds)
- Modify: `config.py` (REIT whitelist, yield gate constants)
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add write gate and validator tests**

Append to `tests/test_phase11.py`:

```python
from engine.validator import validate_stock

# ── Task 5: Tighten gates + validator ─────────────────────

def _make_complete_stock(**overrides):
    """Helper: stock with enough fields to pass the 40% completeness gate."""
    base = {
        'ticker': 'TEST', 'name': 'Test Corp', 'current_price': 10.0,
        'pe': 12.0, 'pb': 1.5, 'roe': 10.0, 'de_ratio': 0.5,
        'dividend_yield': 3.0, 'fcf_yield': 5.0, 'eps_3y': [1.0, 1.1, 0.9],
        'revenue_cagr': 5.0, 'fcf_coverage': 1.5, 'payout_ratio': 30.0,
    }
    base.update(overrides)
    return base


def test_validator_blocks_roe_below_negative_50():
    """ROE < -50% should be hard-blocked, not just warned."""
    stock = _make_complete_stock(ticker='BAD', name='Bad Corp', roe=-60.0)
    result = validate_stock(stock)
    assert not result['valid'], f"ROE -60% should be blocked. Errors: {result.get('errors')}"
    print('  validator blocks ROE < -50%: PASS')


def test_validator_blocks_pb_above_50():
    """P/B > 50 should be hard-blocked (tightened from 100)."""
    stock = _make_complete_stock(ticker='SHELL', name='Shell Corp', pb=55.0)
    result = validate_stock(stock)
    assert not result['valid'], f"P/B 55 should be blocked. Errors: {result.get('errors')}"
    print('  validator blocks P/B > 50: PASS')


def test_validator_passes_pb_at_50():
    """P/B exactly 50 should pass (boundary)."""
    stock = _make_complete_stock(ticker='OK', name='OK Corp', pb=50.0)
    result = validate_stock(stock)
    assert result['valid'], f"P/B 50 should not be blocked. Errors: {result.get('errors')}"
    print('  validator passes P/B = 50: PASS')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py tests/test_phase11.py`
Expected: `test_validator_blocks_roe_below_negative_50` FAILS (currently only warns). `test_validator_blocks_pb_above_50` FAILS (current threshold is 100).

- [ ] **Step 3: Update validator.py thresholds**

In `engine/validator.py`:
- Change `BLOCK_THRESHOLDS` (line ~45-50): add `'roe': ('<', -50.0, "ROE of {v:.1f}% below -50% — distressed or data error")`, change `'pb'` from `('>', 100.0, ...)` to `('>', 50.0, "P/B of {v:.1f}x above 50 — likely data error")`
- Change `MIN_COMPLETENESS` (line 106): from `0.25` to `0.40`

- [ ] **Step 4: Update yield gate in pse_edge_scraper.py**

In `scraper/pse_edge_scraper.py`, lines 166-171, change:
- `max_yield = 50` (REIT) → `max_yield = 35`
- `max_yield = 40` (non-REIT) → `max_yield = 25`

- [ ] **Step 5: Add REIT whitelist to config.py and one-time DB fix**

Append to `config.py`:

```python
# ── REIT Classification Whitelist ────────────────────────
# Tickers that must always be classified as REIT (is_reit=1).
# These were initially misclassified during scraping.
REIT_WHITELIST = {'VREIT', 'PREIT', 'MREIT', 'AREIT'}
```

Add a migration in `db/db_schema.py` to fix existing REIT flags:

```python
# Migration: fix REIT misclassification
for reit_ticker in ('VREIT', 'PREIT', 'MREIT', 'AREIT'):
    try:
        cur.execute("UPDATE stocks SET is_reit = 1 WHERE ticker = ?", (reit_ticker,))
    except Exception:
        pass
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py tests/test_phase11.py`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add scraper/pse_edge_scraper.py engine/validator.py config.py db/db_schema.py tests/test_phase11.py
git commit -m "feat: tighten write gates, fix REIT classification, harden validator

Yield gate: 25%/35% (was 40%/50%). P/B block: >50 (was >100).
ROE <-50%: hard block (was warn). Completeness: 40% (was 25%).
Fixed VREIT/PREIT/MREIT/AREIT REIT misclassification.
Added REIT_WHITELIST to config.py for future scrapes.

Spec: Section 4
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: Data Expansion (Spec Section 8)

Backfill scraper, confidence-weighted scoring, acceleration adjustment, and filter relaxation.

### Task 6: Historical Backfill Scraper (Spec Section 8, Part 1)

**Problem:** PSE Edge only shows 2 most recent years. Most stocks have 2-3 years. Need to fetch 2018-2023 from archive pages.

**Files:**
- Modify: `scraper/pse_financial_reports.py` (add `backfill_historical_financials()`)
- Modify: `scheduler.py` (add `--run-backfill` CLI flag)
- Test: Manual integration test (requires PSE Edge access)

- [ ] **Step 1: Add `backfill_historical_financials` function**

In `scraper/pse_financial_reports.py`, add a new function after existing functions:

```python
def backfill_historical_financials(session, cmpy_id: str, ticker: str,
                                    start_year: int = 2018,
                                    end_year: int = 2023) -> dict:
    """
    Fetch annual reports for historical years (2018-2023) individually.
    Uses upsert_financials(force=False) so existing data is never overwritten.
    Returns {'fetched': int, 'skipped': int, 'errors': int}.

    Rate-limited: 3s delay between requests, 30s timeout, 3 retries.
    Resumable: skips years where ticker already has data.
    """
    import time
    from db.database import upsert_financials, get_financials

    # Check which years already have data
    existing = get_financials(ticker, years=20)
    existing_years = {row['year'] for row in existing} if existing else set()

    stats = {'fetched': 0, 'skipped': 0, 'errors': 0}

    for year in range(start_year, end_year + 1):
        if year in existing_years:
            stats['skipped'] += 1
            continue

        for attempt in range(3):  # 3 retries
            try:
                time.sleep(SCRAPE_DELAY_SECS)
                # Fetch annual report page for specific year
                data = _fetch_year_financials(session, cmpy_id, year)
                if data:
                    upsert_financials(
                        ticker, year,
                        revenue=data.get('revenue'),
                        net_income=data.get('net_income'),
                        equity=data.get('equity'),
                        total_debt=data.get('total_debt'),
                        eps=data.get('eps'),
                        operating_cf=data.get('operating_cf'),
                        capex=data.get('capex'),
                        ebitda=data.get('ebitda'),
                        force=False,  # never overwrite existing
                    )
                    stats['fetched'] += 1
                break  # success or no data — don't retry
            except Exception as e:
                if attempt == 2:
                    stats['errors'] += 1
                else:
                    time.sleep(5 * (attempt + 1))  # exponential backoff

    return stats
```

**Implementation of `_fetch_year_financials()`:** This helper uses `get_annual_report_edge_nos()` to get the list of all annual reports (each has edge_no + date). Filter by target year (report date falls in year or year+1 Q1). For each matching edge_no, call `scrape_financial_reports_page()` with that edge_no. The function already exists — it parses the financial report view page and returns `[{year, revenue, net_income, ...}]`. Extract the row matching the target year. If `get_annual_report_edge_nos` returns no match for a year, return `None`. Example skeleton:

```python
def _fetch_year_financials(session, cmpy_id: str, year: int) -> dict | None:
    """Fetch financials for a specific year from PSE Edge annual reports."""
    reports = get_annual_report_edge_nos(session, cmpy_id)
    for report in reports:
        report_year = int(report['date'][:4])
        # Annual report for fiscal year N is typically filed in year N or N+1
        if report_year in (year, year + 1):
            data_list = scrape_financial_reports_page(session, cmpy_id)
            for row in data_list:
                if row.get('year') == year:
                    return row
    return None
```

Note: If PSE Edge archive doesn't have historical reports for some years, this will return `None` gracefully — `backfill_historical_financials` counts it as a skip.

- [ ] **Step 2: Add `--run-backfill` CLI flag to scheduler.py**

In `scheduler.py`, in the `main()` CLI parser, add:

```python
parser.add_argument('--run-backfill', action='store_true',
                    help='One-time historical backfill (2018-2023)')
```

And in the handler section:

```python
if args.run_backfill:
    from scheduler_jobs import run_backfill
    run_backfill()
    return
```

- [ ] **Step 3: Add `run_backfill` to scheduler_jobs.py**

Add a new function to `scheduler_jobs.py`:

```python
def run_backfill():
    """One-time historical backfill: fetch 2018-2023 financials for all active tickers."""
    from scraper.pse_financial_reports import backfill_historical_financials
    from scraper.pse_session import create_session
    from db.database import get_all_tickers, get_all_cmpy_ids

    tickers = get_all_tickers(active_only=True)
    cmpy_ids = get_all_cmpy_ids()
    session = create_session()

    total = len(tickers)
    for i, ticker in enumerate(tickers):
        cmpy_id = cmpy_ids.get(ticker)
        if not cmpy_id:
            continue
        stats = backfill_historical_financials(session, cmpy_id, ticker)
        if (i + 1) % 10 == 0:
            print(f"  Backfill progress: {i+1}/{total} "
                  f"(fetched={stats['fetched']}, skipped={stats['skipped']})")

    print(f"  Backfill complete: {total} tickers processed")
```

- [ ] **Step 4: Test CLI flag parses**

Run: `py scheduler.py --help`
Expected: `--run-backfill` appears in help output

- [ ] **Step 5: Commit**

```bash
git add scraper/pse_financial_reports.py scheduler.py scheduler_jobs.py
git commit -m "feat: add historical backfill scraper (2018-2023)

New function backfill_historical_financials() fetches archive annual
reports for years 2018-2023. Resumable, rate-limited, uses
force=False to never overwrite existing data.

CLI: py scheduler.py --run-backfill

Spec: Section 8 Part 1
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Confidence-Weighted Scoring (Spec Section 8, Part 2)

**Problem:** All stocks scored equally regardless of data depth. 2-year stocks need penalty.

**Files:**
- Modify: `engine/validator.py` (add `calc_data_confidence()`)
- Modify: `engine/scorer_v2.py` (apply confidence multiplier)
- Modify: `engine/filters_v2.py` (relax 3yr → 2yr minimum)
- Modify: `db/db_schema.py` (add `confidence` column to `scores_v2`)
- Modify: `config.py` (confidence tiers)
- Modify: `reports/pdf_stock_detail_page.py` (confidence badge)
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add confidence calculation tests**

Append to `tests/test_phase11.py`:

```python
# ── Task 7: Confidence-weighted scoring ───────────────────

def test_confidence_5_years():
    """5+ years of complete data → confidence 1.0."""
    from engine.validator import calc_data_confidence
    stock = {
        'eps_5y': [3, 2.7, 2.4, 2.1, 1.8],
        'revenue_5y': [30000, 27000, 24000, 21000, 18000],
        'operating_cf_history': [7200, 6600, 6000, 5400, 4800],
    }
    conf = calc_data_confidence(stock)
    assert conf == 1.0, f"5yr data should be 1.0, got {conf}"
    print('  confidence 5yr = 1.0: PASS')


def test_confidence_3_years():
    """3 years of complete data → confidence 0.80."""
    from engine.validator import calc_data_confidence
    stock = {
        'eps_5y': [3, 2.7, 2.4],
        'revenue_5y': [30000, 27000, 24000],
        'operating_cf_history': [7200, 6600, 6000],
    }
    conf = calc_data_confidence(stock)
    assert conf == 0.80, f"3yr data should be 0.80, got {conf}"
    print('  confidence 3yr = 0.80: PASS')


def test_confidence_2_years():
    """2 years of complete data → confidence 0.65."""
    from engine.validator import calc_data_confidence
    stock = {
        'eps_5y': [3, 2.7],
        'revenue_5y': [30000, 27000],
        'operating_cf_history': [7200, 6600],
    }
    conf = calc_data_confidence(stock)
    assert conf == 0.65, f"2yr data should be 0.65, got {conf}"
    print('  confidence 2yr = 0.65: PASS')


def test_confidence_1_year():
    """1 year → confidence 0.0 (not scored)."""
    from engine.validator import calc_data_confidence
    stock = {
        'eps_5y': [3],
        'revenue_5y': [30000],
        'operating_cf_history': [7200],
    }
    conf = calc_data_confidence(stock)
    assert conf == 0.0, f"1yr data should be 0.0, got {conf}"
    print('  confidence 1yr = 0.0: PASS')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py tests/test_phase11.py`
Expected: FAIL — `calc_data_confidence` does not exist yet

- [ ] **Step 3: Add confidence tiers to config.py**

Append to `config.py`:

```python
# ── Data Confidence Tiers ────────────────────────────────
# Multiplier applied to final score based on years of complete data.
# Complete = EPS + Revenue + OCF all present for a given year.
CONFIDENCE_TIERS = {
    5: 1.00,  # 5+ years
    4: 0.90,
    3: 0.80,
    2: 0.65,
    1: 0.00,  # not scored
}
```

- [ ] **Step 4: Implement `calc_data_confidence` in validator.py**

Add to `engine/validator.py`:

```python
def calc_data_confidence(stock: dict) -> float:
    """
    Returns a confidence multiplier (0.0-1.0) based on years of complete data.
    Complete = EPS, Revenue, and OCF all present for a given year.
    """
    from config import CONFIDENCE_TIERS

    eps_vals = [v for v in (stock.get('eps_5y') or []) if v is not None]
    rev_vals = [v for v in (stock.get('revenue_5y') or []) if v is not None]
    ocf_vals = [v for v in (stock.get('operating_cf_history') or []) if v is not None]

    # Complete years = minimum length across all three series
    complete_years = min(len(eps_vals), len(rev_vals), len(ocf_vals))

    # Look up tier (5+ years all map to 1.0)
    for threshold in sorted(CONFIDENCE_TIERS.keys(), reverse=True):
        if complete_years >= threshold:
            return CONFIDENCE_TIERS[threshold]
    return 0.0
```

- [ ] **Step 5: Apply confidence multiplier in scorer_v2.py**

In `engine/scorer_v2.py`, in `score_unified()`, apply confidence multiplier **after** conglomerate scoring (line ~190) and **before** `get_category()`:

```python
from engine.validator import calc_data_confidence

confidence = calc_data_confidence(stock)
final_score = round(final_score * confidence, 1)
```

Note: Apply after conglomerate scoring so the confidence penalty stacks on top of the conglomerate discount. The order is: layer blend → conglomerate discount → confidence multiplier → category.

Also add `'confidence': confidence` to the `full_breakdown` dict.

In `rank_stocks_v2()`, add `'confidence': breakdown.get('confidence', 1.0)` to the enriched dict.

- [ ] **Step 6: Relax filter from 3yr to 2yr in filters_v2.py**

In `engine/filters_v2.py`, in `filter_unified()`:
- Change `len(eps_vals) < 3` to `len(eps_vals) < 2`
- Change `len(rev_vals) < 3` to `len(rev_vals) < 2`
- OCF minimum stays at 2 (already correct)

- [ ] **Step 7: Add `confidence` column to scores_v2 in db_schema.py**

In `db/db_schema.py`, add migration:

```python
# Migration: add confidence column to scores_v2
# Check if column exists before adding (avoids error on re-run)
cols = [row[1] for row in cur.execute("PRAGMA table_info(scores_v2)").fetchall()]
if 'confidence' not in cols:
    cur.execute("ALTER TABLE scores_v2 ADD COLUMN confidence REAL DEFAULT 1.0")
```

Note: This migration runs before the Task 13 schema recreation. If Task 13 runs first (which recreates the table with confidence column), this migration becomes a no-op. Either order is safe.

- [ ] **Step 7b: Update db_scores.py to write confidence**

In `db/db_scores.py`, in `save_scores_v2()`, add `confidence` to the INSERT statement. Read it from `stock.get('confidence', 1.0)` in the ranked_stocks list.

- [ ] **Step 8: Add confidence badge to PDF detail page**

In `reports/pdf_stock_detail_page.py`, in `build_stock_detail()`, after the score display, add:

```python
confidence = stock.get('confidence', 1.0)
if confidence >= 0.9:
    badge = 'High'
elif confidence >= 0.8:
    badge = 'Medium'
else:
    badge = 'Limited'
# Add badge text near the score display
```

- [ ] **Step 9: Update test_filters_v2.py for 2yr minimum**

The filter relaxation (3yr → 2yr) will break existing tests that expect 2 years to fail. Fix them first:

In `tests/test_filters_v2.py`, update `test_insufficient_eps_data`:
```python
def test_insufficient_eps_data():
    s = dict(PASS_STOCK, eps_3y=[1.5])  # Only 1 year (was 2)
    eligible, reason = filter_unified(s)
    assert not eligible, "Should fail: only 1 EPS year"
```

Similarly update `test_insufficient_revenue_data`:
```python
def test_insufficient_revenue_data():
    s = dict(PASS_STOCK, revenue_5y=[20000])  # Only 1 year (was 2)
    eligible, reason = filter_unified(s)
    assert not eligible, "Should fail: only 1 revenue year"
```

- [ ] **Step 10: Run all tests**

Run: `py tests/test_phase11.py && py tests/test_scorer_v2.py && py tests/test_filters_v2.py`
Expected: All PASS

- [ ] **Step 12: Commit**

```bash
git add engine/validator.py engine/scorer_v2.py engine/filters_v2.py db/db_schema.py db/db_scores.py config.py reports/pdf_stock_detail_page.py tests/test_phase11.py tests/test_filters_v2.py
git commit -m "feat: confidence-weighted scoring + relax filter to 2yr minimum

Stocks scored with confidence multiplier: 5yr=1.0, 4yr=0.9,
3yr=0.8, 2yr=0.65. Filter relaxed from 3yr to 2yr minimum.
PDF shows confidence badge (High/Medium/Limited).
scores_v2 table gets confidence column.

Spec: Section 8 Part 2
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 8: Acceleration Layer Adjustment (Spec Section 8, Part 3)

**Problem:** Acceleration weight is 15% but requires 5yr data (rarely available). Reduce to 5%.

**Files:**
- Modify: `engine/scorer_v2.py:32-37` (weight change)
- Modify: `engine/scorer_acceleration.py:21` (comment update)
- Modify: `config.py` (add `SCORER_WEIGHTS` dict)
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add test for new weights**

Append to `tests/test_phase11.py`:

```python
# ── Task 8: Acceleration weight adjustment ────────────────

def test_acceleration_weight_is_5_percent():
    """Acceleration weight should be 5% (reduced from 15%)."""
    from engine.scorer_v2 import LAYER_WEIGHTS
    assert LAYER_WEIGHTS['acceleration'] == 0.05, \
        f"Acceleration should be 0.05, got {LAYER_WEIGHTS['acceleration']}"
    assert LAYER_WEIGHTS['persistence'] == 0.40, \
        f"Persistence should be 0.40, got {LAYER_WEIGHTS['persistence']}"
    total = sum(LAYER_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001, f"Weights must sum to 1.0, got {total}"
    print('  acceleration weight = 5%: PASS')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py tests/test_phase11.py`
Expected: FAIL — current acceleration weight is 0.15

- [ ] **Step 3: Add SCORER_WEIGHTS to config.py**

Append to `config.py`:

```python
# ── Scorer Layer Weights ─────────────────────────────────
# Portfolio-specific weights for the 4-layer scorer.
# Acceleration kept at 5% until 80%+ of stocks have 5yr history.
SCORER_WEIGHTS = {
    'unified':         {'health': 0.25, 'improvement': 0.30, 'acceleration': 0.05, 'persistence': 0.40},
    'pure_dividend':   {'health': 0.30, 'improvement': 0.20, 'acceleration': 0.05, 'persistence': 0.45},
    'dividend_growth': {'health': 0.25, 'improvement': 0.35, 'acceleration': 0.05, 'persistence': 0.35},
    'value':           {'health': 0.35, 'improvement': 0.25, 'acceleration': 0.05, 'persistence': 0.35},
}
```

- [ ] **Step 4: Update LAYER_WEIGHTS in scorer_v2.py**

In `engine/scorer_v2.py`, replace lines 31-37:

```python
# ── Layer weights ─────────────────────────────────────────────
from config import SCORER_WEIGHTS
LAYER_WEIGHTS = SCORER_WEIGHTS['unified']  # default; portfolio-specific in Task 12
```

- [ ] **Step 5: Update acceleration comment + widen scoring bands**

In `engine/scorer_acceleration.py`:
1. Update the weight comment (line 21 or nearby) from "15%" to "5%"
2. Update `_ACCEL_THRESHOLDS` (lines 91-95) to widen the scoring bands per spec:
   - `+10pp or more → 90pts` (was ~85)
   - `0pp → 50pts` (was ~52)
   - `-10pp or more → 15pts` (was ~20)

```python
_ACCEL_THRESHOLDS = {
    15: 100,   # strong positive acceleration
    10: 90,    # solid positive (was ~85)
    5:  75,
    2:  60,
    0:  50,    # neutral (was ~52)
    -2: 40,
    -5: 30,
    -10: 15,   # strong negative (was ~20)
    -15: 5,
}
```

- [ ] **Step 6: Run all tests**

Run: `py tests/test_phase11.py && py tests/test_scorer_v2.py`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add engine/scorer_v2.py engine/scorer_acceleration.py config.py tests/test_phase11.py
git commit -m "feat: reduce acceleration weight to 5%, add SCORER_WEIGHTS config

Acceleration reduced from 15% to 5% (rarely has 5yr data).
Persistence increased to 40%. Portfolio-specific weights defined
in config.py SCORER_WEIGHTS (unified used for now).

Spec: Section 8 Part 3
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: Scoring Recalibration (Spec Sections 12, 7, 11)

Expand sector medians, recalibrate health thresholds, and differentiate MoS discount rates.

### Task 9: Sector Medians Expansion (Spec Section 12)

**Problem:** `sector_stats.py` only covers PE, PB, EV/EBITDA. Need 8 metrics + market-cap weighting.

**Files:**
- Modify: `engine/sector_stats.py` (expand to 8 metrics, cap-weight, tighter outlier filters)
- Modify: `scraper/pse_stock_builder.py` (add `market_cap` to stock dict)
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add sector stats expansion tests**

Append to `tests/test_phase11.py`:

```python
from engine.sector_stats import compute_sector_stats

# ── Task 9: Sector medians expansion ─────────────────────

def test_sector_stats_includes_roe():
    """Expanded sector stats should include ROE median."""
    stocks = [
        {'sector': 'Property', 'pe': 10, 'pb': 1.5, 'ev_ebitda': 8,
         'roe': 15.0, 'fcf_yield': 5.0, 'dividend_yield': 3.0,
         'de_ratio': 0.5, 'market_cap': 50e9,
         'operating_cf': 1000, 'revenue_5y': [10000]},
        {'sector': 'Property', 'pe': 12, 'pb': 1.8, 'ev_ebitda': 10,
         'roe': 12.0, 'fcf_yield': 4.0, 'dividend_yield': 2.5,
         'de_ratio': 0.8, 'market_cap': 30e9,
         'operating_cf': 800, 'revenue_5y': [8000]},
        {'sector': 'Property', 'pe': 8,  'pb': 1.0, 'ev_ebitda': 6,
         'roe': 18.0, 'fcf_yield': 7.0, 'dividend_yield': 4.0,
         'de_ratio': 0.3, 'market_cap': 80e9,
         'operating_cf': 1500, 'revenue_5y': [15000]},
    ]
    stats = compute_sector_stats(stocks)
    prop = stats.get('Property', {})
    assert 'roe' in prop, f"Property stats missing ROE. Keys: {prop.keys()}"
    assert 'fcf_yield' in prop, f"Property stats missing fcf_yield"
    print(f'  sector stats includes ROE={prop["roe"]}: PASS')


def test_sector_stats_pe_filter_50():
    """Stocks with PE > 50 should be excluded from PE median."""
    stocks = [
        {'sector': 'Mining and Oil', 'pe': 8,   'pb': 1.0, 'ev_ebitda': 5,
         'roe': 20.0, 'market_cap': 30e9},
        {'sector': 'Mining and Oil', 'pe': 12,  'pb': 1.5, 'ev_ebitda': 7,
         'roe': 15.0, 'market_cap': 20e9},
        {'sector': 'Mining and Oil', 'pe': 200, 'pb': 0.5, 'ev_ebitda': 50,
         'roe': 1.0,  'market_cap': 0.5e9},  # micro-cap noise
    ]
    stats = compute_sector_stats(stocks)
    mining = stats.get('Mining and Oil', {})
    assert mining.get('pe', 999) < 50, f"PE median should exclude outlier, got {mining.get('pe')}"
    print(f'  sector stats PE filter <50: median={mining.get("pe")} — PASS')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py tests/test_phase11.py`
Expected: FAIL — current `compute_sector_stats` doesn't return `roe` key

- [ ] **Step 3: Update `build_stock_dict_from_db` to include `market_cap`**

In `scraper/pse_stock_builder.py`, ensure `market_cap` is included in the returned dict. It's derived from the `prices` table. Add:

```python
stock['market_cap'] = market_cap  # from latest price row
```

- [ ] **Step 4: Rewrite `compute_sector_stats` for 8 metrics + cap-weighting**

In `engine/sector_stats.py`, expand `compute_sector_stats()` to:
- Collect 8 metrics: PE, PB, EV/EBITDA, ROE, FCF Yield, Dividend Yield, OCF Margin (ocf/revenue), D/E
- Filter: PE < 50, PB < 20, EV/EBITDA < 50 (tightened outlier cuts)
- Market-cap weighted median (sort by metric, accumulate cap weight, median at 50% cumulative weight)
- Minimum sector size: 3 (reduced from 5)

- [ ] **Step 5: Run tests**

Run: `py tests/test_phase11.py`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add engine/sector_stats.py scraper/pse_stock_builder.py tests/test_phase11.py
git commit -m "feat: expand sector medians to 8 metrics with cap-weighting

Added ROE, FCF Yield, Dividend Yield, OCF Margin, D/E to sector
stats. Market-cap weighted medians. Outlier filters tightened:
PE<50, PB<20, EV/EBITDA<50. Min sector size reduced to 3.

Spec: Section 12
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 10: Health Threshold Calibration (Spec Section 7)

**Problem:** Health thresholds are aspirational (OCF margin 30% = full marks, but PSE top-10% is ~22%).

**Files:**
- Create: `engine/calibrate_thresholds.py`
- Modify: `engine/scorer_health.py` (read from settings, 70/30 blend)
- Modify: `config.py` (add `HEALTH_THRESHOLDS` fallbacks)
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add health calibration tests**

Append to `tests/test_phase11.py`:

```python
# ── Task 10: Health threshold calibration ─────────────────

def test_health_uses_percentile_thresholds():
    """Health scorer should use percentile-based thresholds, not hardcoded."""
    from engine.scorer_health import score_health
    # A stock with ROE at PSE median (~9%) should score ~50pts on ROE
    stock = {
        'ticker': 'MED', 'name': 'Median Corp', 'sector': 'Industrial',
        'is_reit': False, 'is_bank': False,
        'roe': 9.0, 'de_ratio': 1.0, 'fcf_yield': 3.5,
        'pe': 12.0, 'pb': 1.5, 'ev_ebitda': 8.0,
        'operating_cf': 900, 'eps_5y': [1.0, 1.1, 0.9, 1.0, 1.05],
    }
    # Also pass revenue for OCF margin calc
    stock['revenue_5y'] = [10000, 9500, 9000, 8500, 8000]
    sc, bd = score_health(stock)
    assert 30 <= sc <= 70, f"Median stock should score 30-70 on health, got {sc}"
    print(f'  health percentile-based: {sc:.1f}/100 — PASS')


def test_health_sector_relative_blend():
    """Health should blend absolute (70%) and sector-relative (30%) scores."""
    from engine.scorer_health import score_health
    # Bank with 11% ROE where sector median is 8%: above average for sector
    stock = {
        'ticker': 'BNK', 'name': 'Bank Corp', 'sector': 'Banking',
        'is_reit': False, 'is_bank': True,
        'roe': 11.0, 'de_ratio': 8.0, 'fcf_yield': 3.0,
        'pe': 10.0, 'pb': 1.2, 'ev_ebitda': None,
        'operating_cf': 500, 'eps_5y': [2.0, 1.8, 1.7, 1.6, 1.5],
        'revenue_5y': [5000, 4800, 4600, 4400, 4200],
    }
    sc, bd = score_health(stock, sector_median_pe=10.0,
                           sector_medians={'roe': 8.0, 'fcf_yield': 2.5})
    assert sc > 0
    print(f'  health sector-relative blend: {sc:.1f}/100 — PASS')
```

- [ ] **Step 2: Add HEALTH_THRESHOLDS to config.py**

Append to `config.py`:

```python
# ── Health Layer Thresholds (PSE percentile-based) ───────
# Fallback values used when calibration has not yet run.
# calibrate_thresholds.py overwrites these in the settings table.
HEALTH_THRESHOLDS = {
    'roe':              {'p90': 20.0, 'p75': 14.0, 'p50': 9.0,  'p25': 4.0},
    'ocf_margin':       {'p90': 22.0, 'p75': 15.0, 'p50': 9.0,  'p25': 3.0},
    'fcf_yield':        {'p90': 10.0, 'p75': 6.5,  'p50': 3.5,  'p25': 1.0},
    'eps_stability_cv': {'p90': 0.10, 'p75': 0.25, 'p50': 0.50, 'p25': 0.80},
}
# Note: For EPS stability CV, lower is better.
# p90 = the 10th percentile of CV values (most stable 10%).
```

- [ ] **Step 3: Create `engine/calibrate_thresholds.py`**

New file that queries the DB, computes percentiles, and writes to `settings` table:

```python
"""
Derives health layer thresholds from actual PSE database percentiles.
Run after weekly scrape or backfill: py engine/calibrate_thresholds.py

Reads all valid financial data, computes p25/p50/p75/p90 for each metric,
and writes results to the settings table. scorer_health.py reads from
settings first, falling back to config.py HEALTH_THRESHOLDS.
"""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from db.database import get_connection
from db.db_settings import set_setting


def _percentile(sorted_vals: list, pct: float) -> float:
    """Simple percentile calculation (nearest-rank method)."""
    if not sorted_vals:
        return 0.0
    idx = int(len(sorted_vals) * pct / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return round(sorted_vals[idx], 2)


def calibrate():
    """Compute and store health thresholds from current DB data."""
    conn = get_connection()
    # ... query financials + prices, compute ROE, OCF margin, FCF yield, EPS CV
    # ... write to settings table as JSON
    # Key: 'health_threshold_{metric}', Value: JSON of {p90, p75, p50, p25}
    print("  Calibration complete — thresholds written to settings table")


if __name__ == '__main__':
    from db.database import init_db
    init_db()
    calibrate()
```

Full implementation queries `financials` joined with `prices` to compute each metric across all active stocks, then stores percentiles.

- [ ] **Step 4: Update `scorer_health.py` to use percentile thresholds + 70/30 blend**

Modify `score_health()` to:
1. Load thresholds from `settings` table (via `get_setting()`), falling back to `config.HEALTH_THRESHOLDS`
2. Accept optional `sector_medians` parameter (dict with sector median values)
3. For each sub-score (ROE, OCF margin, FCF yield, EPS stability):
   - Compute absolute score using PSE percentile thresholds
   - Compute sector-relative score (how far above/below sector median)
   - Blend: `final = absolute * 0.70 + sector_relative * 0.30`

**CRITICAL wiring:** `scorer_v2.py` must pass sector medians to `score_health()`. In `score_unified()`, after getting `sector_pe` via `get_sector_pe()`, also pass the full sector medians dict:

```python
sector = stock.get('sector', '')
sector_median_pe = get_sector_pe(sector, sector_stats)
sector_medians = sector_stats.get(sector, {})  # full dict with roe, fcf_yield, etc.
health_score, health_bd = score_health(stock, sector_median_pe, sector_medians=sector_medians)
```

- [ ] **Step 5: Run tests**

Run: `py tests/test_phase11.py && py tests/test_scorer_v2.py`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add engine/calibrate_thresholds.py engine/scorer_health.py config.py tests/test_phase11.py
git commit -m "feat: percentile-based health thresholds + 70/30 sector-relative blend

Health layer now uses PSE percentile thresholds (p90=excellent,
p50=average). 70% absolute + 30% sector-relative blend.
calibrate_thresholds.py derives from DB; config.py has fallbacks.

Spec: Section 7
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 11: MoS Discount Rate Differentiation (Spec Section 11)

**Problem:** Fixed 11.5% discount rate for all stocks. SM Prime and a micro-cap mining stock get same required return.

**Files:**
- Modify: `engine/mos.py` (remove local constant duplicates, add size+sector premium)
- Modify: `config.py` (add `MOS_SIZE_PREMIUM`, `MOS_SECTOR_PREMIUM`, `MOS_SIZE_THRESHOLDS`)
- Test: `tests/test_phase11.py` (append)

- [ ] **Step 1: Add MoS discount rate tests**

Append to `tests/test_phase11.py`:

```python
# ── Task 11: MoS discount rate differentiation ───────────

def test_mos_large_cap_property():
    """Large property stock should get 12.0% rate (6.5 + 5.0 + 0.0 + 0.5)."""
    from engine.mos import _get_required_return
    rate = _get_required_return(sector='Property', market_cap=900e9)
    assert abs(rate - 0.120) < 0.001, f"Expected 0.120, got {rate}"
    print(f'  MoS large property: {rate:.3f} — PASS')


def test_mos_mid_cap_mining():
    """Mid-cap mining stock should get 15.0% (6.5 + 5.0 + 1.5 + 2.0)."""
    from engine.mos import _get_required_return
    rate = _get_required_return(sector='Mining and Oil', market_cap=30e9)
    assert abs(rate - 0.150) < 0.001, f"Expected 0.150, got {rate}"
    print(f'  MoS mid mining: {rate:.3f} — PASS')


def test_mos_micro_cap():
    """Micro-cap stock gets max premium: 18.5% (6.5 + 5.0 + 5.0 + 2.0)."""
    from engine.mos import _get_required_return
    rate = _get_required_return(sector='Mining and Oil', market_cap=500e6)
    assert abs(rate - 0.185) < 0.001, f"Expected 0.185, got {rate}"
    print(f'  MoS micro mining: {rate:.3f} — PASS')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py tests/test_phase11.py`
Expected: FAIL — `_get_required_return` does not exist

- [ ] **Step 3: Add MoS config constants**

Append to `config.py`:

```python
# ── MoS Discount Rate Premiums ───────────────────────────
MOS_SIZE_PREMIUM = {
    'large':  0.0,   # >= 50B PHP
    'mid':    1.5,   # 10B-50B
    'small':  3.0,   # 1B-10B
    'micro':  5.0,   # < 1B
}
MOS_SIZE_THRESHOLDS = {
    'large': 50_000_000_000,
    'mid':   10_000_000_000,
    'small':  1_000_000_000,
}
MOS_SECTOR_PREMIUM = {
    'Financials':     0.0,
    'Banking':        0.0,
    'Utilities':      0.0,
    'Property':       0.5,
    'Consumer':       0.5,
    'Industrial':     1.0,
    'Services':       1.0,
    'Mining and Oil': 2.0,
    'Holding Firms':  1.0,
    'Unknown':        1.5,
}
MOS_SECTOR_PREMIUM_DEFAULT = 1.0
```

- [ ] **Step 4: Update mos.py — remove local duplicates, add risk-adjusted rate**

In `engine/mos.py`:
1. Remove lines 28-43 (local constant definitions: `PH_RISK_FREE_RATE`, `EQUITY_RISK_PREMIUM`, `DEFAULT_REQUIRED_RETURN`, `DDM_MAX_GROWTH_RATE`, `DEFAULT_TARGET_PE`, `CONGLOMERATE_DISCOUNT`, `MOS_TARGET`)
2. Replace with imports from config.py. **CRITICAL: These constants must exist in config.py before removing from mos.py. If they're not already there, add them first:**

```python
from config import (
    PH_RISK_FREE_RATE, EQUITY_RISK_PREMIUM, DDM_MAX_GROWTH_RATE,
    DEFAULT_TARGET_PE, CONGLOMERATE_DISCOUNT, MOS_TARGET,
    MOS_SIZE_PREMIUM, MOS_SECTOR_PREMIUM, MOS_SECTOR_PREMIUM_DEFAULT,
    MOS_SIZE_THRESHOLDS,
)
```

Ensure these constants are in config.py (move, don't just delete):
```python
# ── MoS Constants (moved from mos.py) ─────────────────
PH_RISK_FREE_RATE = 0.065       # PH 10-year T-bond
EQUITY_RISK_PREMIUM = 0.05      # Market equity premium
DDM_MAX_GROWTH_RATE = 0.07      # Max DDM growth cap
DEFAULT_TARGET_PE = 15.0
CONGLOMERATE_DISCOUNT = 0.20    # 20% holding company discount
MOS_TARGET = {'pure_dividend': 25, 'dividend_growth': 20, 'value': 30}
```
3. Add new function:

```python
def _get_required_return(sector: str = '', market_cap: float = 0) -> float:
    """
    Risk-adjusted required return = risk_free + equity_premium + size + sector.
    """
    # Size premium
    if market_cap >= MOS_SIZE_THRESHOLDS['large']:
        size_prem = MOS_SIZE_PREMIUM['large']
    elif market_cap >= MOS_SIZE_THRESHOLDS['mid']:
        size_prem = MOS_SIZE_PREMIUM['mid']
    elif market_cap >= MOS_SIZE_THRESHOLDS['small']:
        size_prem = MOS_SIZE_PREMIUM['small']
    else:
        size_prem = MOS_SIZE_PREMIUM['micro']

    sector_prem = MOS_SECTOR_PREMIUM.get(sector, MOS_SECTOR_PREMIUM_DEFAULT)

    return PH_RISK_FREE_RATE + EQUITY_RISK_PREMIUM + (size_prem / 100) + (sector_prem / 100)
```

4. Update `calc_ddm`, `calc_dcf` to accept optional `sector`/`market_cap` and use `_get_required_return()` when `required_return` is not explicitly provided.

- [ ] **Step 5: Run tests**

Run: `py tests/test_phase11.py && py tests/test_mos.py`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add engine/mos.py config.py tests/test_phase11.py
git commit -m "feat: risk-adjusted MoS discount rate by size + sector

Required return now varies: SM Prime 12.0%, mid-cap mining 15.0%,
micro-cap mining 18.5%. Removed duplicate constants from mos.py
(now imports from config.py only).

Spec: Section 11
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 5: Portfolio Weights + Unified PDF (Spec Section 9)

Highest-risk chunk. Includes DB schema migration, multi-score pipeline, and 3-section PDF.

### Task 12: Portfolio-Specific Scoring in scorer_v2.py (Spec Section 9, Part 1)

**Files:**
- Modify: `engine/scorer_v2.py` (accept `portfolio_type` parameter, load weights from config)

- [ ] **Step 1: Add portfolio weight tests**

Append to `tests/test_phase11.py`:

```python
# ── Task 12: Portfolio-specific scoring ───────────────────

def test_score_unified_accepts_portfolio_type():
    """score_unified should accept portfolio_type and use different weights."""
    from engine.scorer_v2 import score_unified
    from tests.test_scorer_v2 import STRONG_STOCK

    sc_unified, _ = score_unified(STRONG_STOCK, portfolio_type='unified')
    sc_value, _   = score_unified(STRONG_STOCK, portfolio_type='value')
    sc_div, _     = score_unified(STRONG_STOCK, portfolio_type='pure_dividend')

    # Different weights should produce different scores
    assert sc_unified != sc_value or sc_unified != sc_div, \
        "Different portfolio types should produce different scores"
    print(f'  portfolio types: unified={sc_unified}, value={sc_value}, div={sc_div} — PASS')
```

- [ ] **Step 2: Update `score_unified()` to accept `portfolio_type`**

In `engine/scorer_v2.py`, modify `score_unified()`:

```python
def score_unified(stock: dict,
                  sector_stats: dict | None = None,
                  financials_history: list | None = None,
                  portfolio_type: str = 'unified'
                  ) -> tuple[float, dict]:
```

And replace the `LAYER_WEIGHTS` references with:

```python
from config import SCORER_WEIGHTS
weights = SCORER_WEIGHTS.get(portfolio_type, SCORER_WEIGHTS['unified'])
```

Use `weights['health']`, `weights['improvement']`, etc. in `_blend_layers()`.

Also update `rank_stocks_v2()` to accept and pass `portfolio_type`.

- [ ] **Step 3: Run tests**

Run: `py tests/test_phase11.py && py tests/test_scorer_v2.py`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add engine/scorer_v2.py tests/test_phase11.py
git commit -m "feat: scorer_v2 accepts portfolio_type for per-portfolio weights

score_unified() and rank_stocks_v2() now accept portfolio_type
parameter. Loads weights from config.SCORER_WEIGHTS.

Spec: Section 9 Part 1
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 13: scores_v2 Schema Migration (Spec Section 9, Part 2)

**Files:**
- Modify: `db/db_schema.py` (UNIQUE constraint migration)
- Modify: `db/db_scores.py` (add `portfolio_type` to save/get functions)
- Modify: `db/database.py` (re-export updated functions)

- [ ] **Step 1: Add migration to db_schema.py**

In `db/db_schema.py`, add a migration that recreates `scores_v2` with the new UNIQUE constraint:

```python
# Migration: add portfolio_type to scores_v2 + new UNIQUE constraint
# SQLite doesn't support ALTER UNIQUE, so we recreate the table.
try:
    cur.execute("SELECT portfolio_type FROM scores_v2 LIMIT 1")
except Exception:
    # Column doesn't exist — need migration
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scores_v2_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            run_date TEXT NOT NULL,
            portfolio_type TEXT NOT NULL DEFAULT 'unified',
            score REAL,
            confidence REAL DEFAULT 1.0,
            rank INTEGER,
            category TEXT,
            breakdown_json TEXT,
            UNIQUE(ticker, run_date, portfolio_type)
        )
    """)
    cur.execute("""
        INSERT OR IGNORE INTO scores_v2_new
            (ticker, run_date, portfolio_type, score, confidence, rank, category, breakdown_json)
        SELECT ticker, run_date, 'unified', score,
               COALESCE(confidence, 1.0), rank, category, breakdown_json
        FROM scores_v2
    """)
    cur.execute("DROP TABLE scores_v2")
    cur.execute("ALTER TABLE scores_v2_new RENAME TO scores_v2")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_v2_run_date ON scores_v2(run_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_v2_ticker ON scores_v2(ticker)")
```

**CRITICAL:** This is destructive. DB backup mandatory before running. Test on a copy first.

- [ ] **Step 2: Update `save_scores_v2()` in db_scores.py**

Modify to accept `portfolio_type` parameter and include it in INSERT:

```python
def save_scores_v2(run_date, ranked_stocks, portfolio_type='unified'):
    # INSERT OR REPLACE INTO scores_v2 (ticker, run_date, portfolio_type, ...)
```

Also update `get_last_scores_v2()` to accept `portfolio_type` filter.

- [ ] **Step 3: Update database.py facade**

Re-export the updated functions (no signature changes needed for re-export).

- [ ] **Step 4: Test migration on a copy**

```bash
# Backup first
copy "%LOCALAPPDATA%\pse_quant\pse_quant.db" "%LOCALAPPDATA%\pse_quant\pse_quant_backup_phase11.db"
```

Run: `py -c "from db.database import init_db; init_db()"`
Expected: No errors. Verify with: `py -c "from db.database import get_connection; c=get_connection(); print([r for r in c.execute('PRAGMA table_info(scores_v2)')])"` — should show `portfolio_type` column.

- [ ] **Step 5: Commit**

```bash
git add db/db_schema.py db/db_scores.py db/database.py
git commit -m "feat: scores_v2 schema migration for portfolio_type

Recreated scores_v2 table with UNIQUE(ticker, run_date, portfolio_type).
Added portfolio_type column (default 'unified'). Existing data migrated.
save_scores_v2() and get_last_scores_v2() accept portfolio_type.

Spec: Section 9 Part 2
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 14: Unified PDF with 3 Sections (Spec Section 9, Part 3)

**Files:**
- Create: `reports/pdf_portfolio_sections.py`
- Modify: `reports/pdf_generator.py` (orchestrate 3 sections)

- [ ] **Step 1: Create `pdf_portfolio_sections.py`**

New file handling section dividers and multi-portfolio layout:

```python
"""
Multi-section PDF layout for unified StockPilot PH Rankings report.
Renders three sections: Pure Dividend, Dividend Growth, Value.
Each section has its own rankings table and stock detail pages.
"""
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, PageBreak, HRFlowable
from reports.pdf_styles import NAVY, GOLD, CONTENT_WIDTH
from reports.pdf_rankings_table import build_rankings_table
from reports.pdf_stock_detail_page import build_stock_detail


SECTION_CONFIG = [
    {
        'portfolio_type': 'pure_dividend',
        'title': 'Pure Dividend Rankings',
        'subtitle': 'Stocks scored for consistent dividend income',
    },
    {
        'portfolio_type': 'dividend_growth',
        'title': 'Dividend Growth Rankings',
        'subtitle': 'Stocks scored for growing dividend potential',
    },
    {
        'portfolio_type': 'value',
        'title': 'Value Rankings',
        'subtitle': 'Stocks scored for fundamental value',
    },
]


def build_section_divider(title: str, subtitle: str) -> list:
    """Returns flowables for a section title page."""
    # ... section header with title, subtitle, accent line
    pass


def build_portfolio_section(ranked_stocks: list, portfolio_type: str,
                             total_screened: int) -> list:
    """Returns all flowables for one portfolio section."""
    config = next(s for s in SECTION_CONFIG if s['portfolio_type'] == portfolio_type)
    elements = []
    elements.extend(build_section_divider(config['title'], config['subtitle']))
    elements.extend(build_rankings_table(ranked_stocks, portfolio_type, total_screened))
    for stock in ranked_stocks:
        elements.extend(build_stock_detail(stock, portfolio_type))
    return elements
```

- [ ] **Step 2: Update `generate_report()` in pdf_generator.py**

Modify to accept a dict of `{portfolio_type: ranked_stocks}` instead of a single list:

```python
def generate_report(portfolio_sections: dict, output_path: str,
                    total_stocks_screened: int):
    """
    Generate unified PDF with 3 portfolio sections.
    portfolio_sections: {'pure_dividend': [...], 'dividend_growth': [...], 'value': [...]}
    """
```

**CRITICAL:** This is a breaking signature change. All callers (`main.py`, `scheduler_jobs.py`) must be updated atomically in the same commit or in the immediately following Task 15. Do NOT commit this alone — commit together with Task 15, or add a backward-compatible wrapper:

```python
def generate_report(portfolio_sections_or_stocks, output_path, total_stocks_screened,
                    portfolio_type=None):
    # Backward compat: if called with a list, wrap it
    if isinstance(portfolio_sections_or_stocks, list):
        portfolio_sections_or_stocks = {portfolio_type or 'unified': portfolio_sections_or_stocks}
    # ... rest of implementation
```

- [ ] **Step 3: Visual inspection**

Run: `py main.py --dry-run`
Open generated PDF and verify 3 sections render correctly.

- [ ] **Step 4: Commit**

```bash
git add reports/pdf_portfolio_sections.py reports/pdf_generator.py
git commit -m "feat: unified PDF with 3 portfolio sections

Single PDF now contains Pure Dividend, Dividend Growth, and Value
sections. Each section has its own rankings table and detail pages.
A stock can appear in multiple sections with different scores.

Spec: Section 9 Part 3
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 15: Pipeline Integration (Spec Section 9, Part 4)

**Files:**
- Modify: `main.py` (score each portfolio type, pass to PDF)
- Modify: `scheduler_jobs.py` (score each portfolio type, save per-portfolio)
- Modify: `discord/bot_commands.py` (show all portfolio scores in /stock)

- [ ] **Step 1: Update main.py pipeline**

In `run_pipeline()`, after filtering, score each portfolio type:

```python
portfolio_sections = {}
for ptype in ['pure_dividend', 'dividend_growth', 'value']:
    ranked = rank_stocks_v2(eligible_stocks, sector_stats, financials_map,
                             portfolio_type=ptype)
    portfolio_sections[ptype] = ranked
```

Pass `portfolio_sections` to `generate_report()`.

- [ ] **Step 2: Update scheduler_jobs.py**

In `_run_score_pipeline()`, score and save for each portfolio type:

```python
for ptype in ['pure_dividend', 'dividend_growth', 'value']:
    ranked = rank_stocks_v2(eligible, sector_stats, fins_map, portfolio_type=ptype)
    save_scores_v2(run_date, ranked, portfolio_type=ptype)
```

- [ ] **Step 3: Update bot_commands.py `/stock` embed**

In `get_stock_embed()`, show all portfolio scores the stock qualifies for.

- [ ] **Step 4: Run full dry-run pipeline**

Run: `py main.py --dry-run`
Expected: PDF generated with 3 sections, no errors

- [ ] **Step 5: Commit**

```bash
git add main.py scheduler_jobs.py discord/bot_commands.py
git commit -m "feat: pipeline scores 3 portfolio types, unified PDF delivery

main.py and scheduler score each stock for pure_dividend,
dividend_growth, and value. Scores saved per portfolio_type.
/stock command shows all qualifying portfolio scores.

Spec: Section 9 Part 4
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 6: Operational Monitoring (Spec Sections 1, 2, 5, 6)

Scraper health detection, unit hardening, staleness prevention. These don't affect scoring but make the system more resilient.

### Task 16: Scraper Change Detection (Spec Section 1)

**Files:**
- Modify: `scraper/pse_lookup.py` (canary check for autocomplete response)
- Modify: `scraper/pse_stock_data.py` (canary check for stock data + dividends pages)
- Modify: `scraper/pse_financial_reports.py` (canary check for report page)
- Modify: `scraper/pse_edge_scraper.py` (log canary failures, set health flags)
- Modify: `dashboard/routes_pipeline.py` (add `/api/scraper-health` endpoint)

- [ ] **Step 1: Define canary check functions in each scraper module**

In each module, add a `_check_canary(html)` function that verifies expected HTML landmarks exist. Return `True` if canary passes, `False` if structure changed.

Example for `pse_stock_data.py`:
```python
def _check_canary(html: str) -> bool:
    """Verify PSE Edge stock data page structure hasn't changed."""
    return 'Last Traded Price' in html
```

For dividends: check "Ex-Date" column header exists.
For financial reports: check "fiscal year ended" pattern.
For lookup: check cmpy_id pattern in autocomplete response.

- [ ] **Step 2: Add canary check calls before parsing**

At the top of each scrape function, call `_check_canary()`. On failure:
1. Log ERROR to `activity_log` with category `scraper_health`
2. Set `scraper_broken_{module}` in `settings` table
3. Return `None` (same as "no data") — don't attempt to parse broken HTML

- [ ] **Step 3: Add admin DM alert on canary failure**

In `scraper/pse_edge_scraper.py`, after any canary failure during a scrape, check if the `scraper_broken_{module}` flag was just set (not already set). If newly broken, queue an admin DM via `send_dm_text()`.

- [ ] **Step 4: Add `/api/scraper-health` endpoint**

In `dashboard/routes_pipeline.py`, add:

```python
@pipeline_bp.route('/api/scraper-health')
def scraper_health():
    from db.db_settings import get_setting
    modules = ['lookup', 'stock_data', 'dividends', 'financial_reports']
    health = {}
    for mod in modules:
        broken = get_setting(f'scraper_broken_{mod}')
        last_ok = get_setting(f'scraper_last_success_{mod}')
        health[mod] = {
            'status': 'broken' if broken else 'ok',
            'last_success': last_ok,
        }
    return jsonify(health)
```

- [ ] **Step 5: Commit**

```bash
git add scraper/pse_lookup.py scraper/pse_stock_data.py scraper/pse_financial_reports.py scraper/pse_edge_scraper.py dashboard/routes_pipeline.py
git commit -m "feat: scraper change detection with canary checks + admin DM alerts

Each scraper module validates expected HTML landmarks before parsing.
On failure: logs to activity_log, sets scraper_broken flag, sends
one-time admin DM. Dashboard /api/scraper-health shows status.

Spec: Section 1
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 17: Unit Detection Hardening (Spec Section 2)

**Files:**
- Modify: `scraper/pse_financial_reports.py` (mandatory currency detection, cross-validation)

- [ ] **Step 1: Make currency detection mandatory**

In `scraper/pse_financial_reports.py`, in `scrape_financial_reports_page()`, change the unit detection fallback from `divisor = 1_000_000` to `return None` with an activity log entry.

- [ ] **Step 2: Add cross-validation checks**

After extracting financials, before returning:
- Revenue per share: if outside 0.01-10,000 → reject
- EPS vs NI/shares: if mismatch > 100x → reject
- Net margin > 500% → reject

- [ ] **Step 3: Add `unit_confidence` to return dict**

```python
result['unit_confidence'] = 'detected' if found_currency_line else 'inferred'
```

- [ ] **Step 4: Commit**

```bash
git add scraper/pse_financial_reports.py
git commit -m "feat: mandatory unit detection + cross-validation at parse time

Currency line detection now mandatory (no silent default to millions).
Added revenue/share, EPS/NI, and net margin cross-validation gates.
Returns unit_confidence: 'detected' or 'inferred'.

Spec: Section 2
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 18: Market Cap / Price Staleness Cross-Validation (Spec Section 5)

**Files:**
- Modify: `engine/validator.py` (staleness checks)
- Modify: `scraper/pse_stock_builder.py` (include price_date, market_cap_date)

- [ ] **Step 1: Add price_date and market_cap_date to stock dict**

In `build_stock_dict_from_db()`, include the dates when price and market_cap were last updated:

```python
stock['price_date'] = price_row['date'] if price_row else None
```

- [ ] **Step 2: Add staleness validation in validator.py**

In `validate_stock()`, add checks:
- Price older than 7 days → add `stale_price` to blocks (exclude from scoring)
- Financials older than 15 months → add `stale_financials` to blocks
- Market cap date vs price date mismatch > 3 days → skip EV/EBITDA and FCF per share

- [ ] **Step 3: Commit**

```bash
git add engine/validator.py scraper/pse_stock_builder.py
git commit -m "feat: market cap / price staleness cross-validation

Price >7 days old excluded from scoring. Financials >15 months excluded.
Market cap/price date mismatch >3 days skips EV/EBITDA and FCF/share.

Spec: Section 5
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 19: Staleness Prevention (Spec Section 6)

**Files:**
- Modify: `scheduler_jobs.py` (retry failed tickers, auto-suspend after 7 failures)
- Modify: `scheduler.py` (heartbeat write every 15 min)
- Modify: `dashboard/routes_home.py` (heartbeat check in `/api/health`)

- [ ] **Step 1: Add scheduler heartbeat**

In `scheduler.py`, in `start_scheduler()`, add an interval job that writes `scheduler_heartbeat` to the `settings` table every 15 minutes:

```python
scheduler.add_job(
    _write_heartbeat, IntervalTrigger(minutes=15),
    id='heartbeat', replace_existing=True
)

def _write_heartbeat():
    from db.db_settings import set_setting
    from datetime import datetime
    set_setting('scheduler_heartbeat', datetime.now().isoformat())
```

- [ ] **Step 2: Add heartbeat check to dashboard**

In `dashboard/routes_home.py`, in `api_health()`, add:

```python
heartbeat = get_setting('scheduler_heartbeat')
if heartbeat:
    from datetime import datetime, timedelta
    last_beat = datetime.fromisoformat(heartbeat)
    age = datetime.now() - last_beat
    if age > timedelta(hours=2):
        health['scheduler_status'] = 'stale'
        # Trigger admin DM (one-time)
```

- [ ] **Step 3: Add retry logic for failed scrapes**

In `scheduler_jobs.py`, in the daily score job, track consecutive failures per ticker in `activity_log`. After 3 failures → admin DM. After 7 → auto-suspend.

- [ ] **Step 4: Commit**

```bash
git add scheduler.py scheduler_jobs.py dashboard/routes_home.py
git commit -m "feat: staleness prevention with heartbeat + retry + auto-suspend

Scheduler writes heartbeat every 15 min. Dashboard alerts if >2hr stale.
Failed scrapes tracked: 3 failures → admin DM, 7 → auto-suspend ticker.

Spec: Section 6
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Post-Implementation: Before/After Comparison

After all chunks are complete:

- [ ] **Step 1: Run full scoring pipeline before deploying**

```bash
py main.py --dry-run
```

- [ ] **Step 2: Generate before/after comparison CSV**

Save top-20 stocks' scores (old vs new) for Josh's review. This is a gate — do not publish new scores to Discord until the comparison is reviewed.

- [ ] **Step 3: Run existing test suite**

```bash
py tests/test_phase11.py
py tests/test_scorer_v2.py
py tests/test_filters_v2.py
py tests/test_mos.py
```

- [ ] **Step 4: Visual PDF inspection**

Open the generated PDF and verify:
- Three sections render correctly
- Confidence badges show
- Discount rates vary per stock
- Section dividers are clean

- [ ] **Step 5: Run backtester for rank stability**

```bash
py backtester.py --portfolio pure_dividend --years 2023 2024 2025
py backtester.py --portfolio value --years 2023 2024 2025
```
