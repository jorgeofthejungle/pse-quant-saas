# ============================================================
# db_maintenance.py — Database Cleanup & Vacuuming
# PSE Quant SaaS
# ============================================================
# Called after the weekly scrape to prune stale records and
# keep the SQLite file from growing without bound.
# ============================================================

from datetime import datetime, timedelta
from db.db_connection import get_connection


def clean_bad_dps(max_yield_non_reit: float = 20.0,
                  max_yield_reit:     float = 30.0,
                  dry_run: bool = False) -> dict:
    """
    NULLs out DPS values that imply implausibly high dividend yields.

    Compares each ticker's latest price against its stored DPS values.
    Any non-REIT row where (dps/price * 100) > max_yield_non_reit is cleared.
    REIT rows are held to the looser max_yield_reit threshold.

    Args:
        max_yield_non_reit: yield threshold for regular stocks (default 20%)
        max_yield_reit:     yield threshold for REITs (default 30%)
        dry_run:            if True, report without making changes

    Returns:
        dict with 'nulled' (count), 'tickers_affected' (list)
    """
    conn = get_connection()

    # Join financials with latest price and REIT flag
    rows = conn.execute("""
        SELECT f.ticker, f.year, f.dps, p.close, s.is_reit,
               round(f.dps / p.close * 100.0, 1) AS yield_pct
        FROM financials f
        JOIN stocks s ON f.ticker = s.ticker
        JOIN (
            SELECT ticker, close FROM prices p2
            WHERE date = (SELECT MAX(date) FROM prices WHERE ticker = p2.ticker)
        ) p ON f.ticker = p.ticker
        WHERE f.dps IS NOT NULL AND f.dps > 0
          AND p.close > 0
    """).fetchall()

    to_null = []
    for r in rows:
        threshold = max_yield_reit if r['is_reit'] else max_yield_non_reit
        if r['yield_pct'] > threshold:
            to_null.append((r['ticker'], r['year'], r['dps'], r['close'], r['yield_pct']))

    if not dry_run and to_null:
        conn.executemany(
            "UPDATE financials SET dps = NULL WHERE ticker = ? AND year = ?",
            [(t, y) for t, y, *_ in to_null]
        )
        conn.commit()

    conn.close()

    tickers = sorted(set(t for t, *_ in to_null))
    label = 'Would null' if dry_run else 'Nulled'
    for t, y, dps, price, yld in to_null:
        print(f"  {label}: {t} FY{y}  DPS={dps:.4f}  Price={price:.2f}  Yield={yld:.1f}%")

    return {'nulled': len(to_null), 'tickers_affected': tickers}


def cleanup_stale_data(
    prices_keep_days: int = 365,
    activity_keep_days: int = 90,
    sentiment_keep_days: int = 7,
    vacuum: bool = True,
) -> dict:
    """
    Prunes old records from prices, activity_log, and sentiment tables.

    Args:
        prices_keep_days:   Keep daily prices for this many days (default 1 year)
        activity_keep_days: Keep activity_log rows for this many days (default 90)
        sentiment_keep_days: Keep sentiment cache for this many days (default 7)
        vacuum:             Run VACUUM at the end to reclaim disk space

    Returns:
        dict with 'prices_deleted', 'activity_deleted', 'sentiment_deleted' counts
    """
    now = datetime.now()
    price_cutoff     = (now - timedelta(days=prices_keep_days)).strftime('%Y-%m-%d')
    activity_cutoff  = (now - timedelta(days=activity_keep_days)).strftime('%Y-%m-%d')
    sentiment_cutoff = (now - timedelta(days=sentiment_keep_days)).strftime('%Y-%m-%d')

    conn = get_connection()
    results = {}

    # Prune old price rows
    cur = conn.execute(
        "DELETE FROM prices WHERE date < ?", (price_cutoff,)
    )
    results['prices_deleted'] = cur.rowcount

    # Prune old activity log rows
    cur = conn.execute(
        "DELETE FROM activity_log WHERE timestamp < ?", (activity_cutoff,)
    )
    results['activity_deleted'] = cur.rowcount

    # Prune old sentiment cache rows
    cur = conn.execute(
        "DELETE FROM sentiment WHERE date < ?", (sentiment_cutoff,)
    )
    results['sentiment_deleted'] = cur.rowcount

    conn.commit()

    if vacuum:
        conn.execute("VACUUM")

    conn.close()
    return results
