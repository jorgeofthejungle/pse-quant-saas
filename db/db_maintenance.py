# ============================================================
# db_maintenance.py — Database Cleanup & Vacuuming
# PSE Quant SaaS
# ============================================================
# Called after the weekly scrape to prune stale records and
# keep the SQLite file from growing without bound.
# ============================================================

from datetime import datetime, timedelta
from db.db_connection import get_connection


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
