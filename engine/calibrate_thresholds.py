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
    n = len(sorted_vals)
    idx = max(0, min(int(pct * n / 100), n - 1))
    return sorted_vals[idx]


def calibrate_health_thresholds() -> dict:
    """
    Query DB for ROE, OCF margin, FCF yield, EPS stability CV.
    Compute percentiles and write to settings table.
    Returns the computed thresholds dict.
    """
    conn = get_connection()
    cur = conn.cursor()

    thresholds = {}

    # ── ROE ──────────────────────────────────────────────
    rows = cur.execute("""
        SELECT f.net_income / f.equity * 100 as roe
        FROM financials f
        WHERE f.net_income IS NOT NULL
          AND f.equity IS NOT NULL
          AND f.equity > 0
          AND f.year >= 2018
        ORDER BY roe
    """).fetchall()
    roe_vals = sorted([r[0] for r in rows if r[0] is not None])
    if len(roe_vals) >= 20:
        thresholds['roe'] = {
            'p90': _percentile(roe_vals, 90),
            'p75': _percentile(roe_vals, 75),
            'p50': _percentile(roe_vals, 50),
            'p25': _percentile(roe_vals, 25),
        }

    # ── OCF Margin ───────────────────────────────────────
    rows = cur.execute("""
        SELECT f.operating_cf / f.revenue * 100 as ocf_margin
        FROM financials f
        WHERE f.operating_cf IS NOT NULL
          AND f.revenue IS NOT NULL
          AND f.revenue > 0
          AND f.year >= 2018
        ORDER BY ocf_margin
    """).fetchall()
    ocf_vals = sorted([r[0] for r in rows if r[0] is not None and r[0] > -50])
    if len(ocf_vals) >= 20:
        thresholds['ocf_margin'] = {
            'p90': _percentile(ocf_vals, 90),
            'p75': _percentile(ocf_vals, 75),
            'p50': _percentile(ocf_vals, 50),
            'p25': _percentile(ocf_vals, 25),
        }

    # ── FCF Yield ────────────────────────────────────────
    # FCF yield = (operating_cf - capex) / market_cap * 100
    rows = cur.execute("""
        SELECT (f.operating_cf - COALESCE(f.capex, 0)) / p.market_cap * 100 as fcf_yield
        FROM financials f
        JOIN (
            SELECT ticker, market_cap FROM prices
            WHERE (ticker, date) IN (
                SELECT ticker, MAX(date) FROM prices GROUP BY ticker
            )
        ) p ON f.ticker = p.ticker
        WHERE f.operating_cf IS NOT NULL
          AND p.market_cap IS NOT NULL
          AND p.market_cap > 0
          AND f.year >= 2018
        ORDER BY fcf_yield
    """).fetchall()
    fcf_vals = sorted([r[0] for r in rows if r[0] is not None and 0 < r[0] < 50])
    if len(fcf_vals) >= 20:
        thresholds['fcf_yield'] = {
            'p90': _percentile(fcf_vals, 90),
            'p75': _percentile(fcf_vals, 75),
            'p50': _percentile(fcf_vals, 50),
            'p25': _percentile(fcf_vals, 25),
        }

    conn.close()

    # Write to settings table
    for metric, vals in thresholds.items():
        set_setting(f'health_threshold_{metric}', json.dumps(vals))

    print(f"  Calibrated {len(thresholds)} metrics: {list(thresholds.keys())}")
    return thresholds


def get_health_thresholds() -> dict:
    """
    Load health thresholds from settings table (calibrated values).
    Falls back to config.py HEALTH_THRESHOLDS if not calibrated.
    """
    from config import HEALTH_THRESHOLDS
    from db.db_settings import get_setting

    result = {}
    for metric in HEALTH_THRESHOLDS:
        raw = get_setting(f'health_threshold_{metric}')
        if raw:
            try:
                result[metric] = json.loads(raw)
            except Exception:
                result[metric] = HEALTH_THRESHOLDS[metric]
        else:
            result[metric] = HEALTH_THRESHOLDS[metric]
    return result


if __name__ == '__main__':
    thresholds = calibrate_health_thresholds()
    for metric, vals in thresholds.items():
        print(f"  {metric}: {vals}")
    if not thresholds:
        print("  No data in DB yet. Run scraper first.")
