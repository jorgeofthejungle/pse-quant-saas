# feedback/snapshot.py — Monthly Point-in-Time Snapshot Capture
# Captures score, rank, IV estimate, price, MoS%, sector, and
# top-10 status for every scored stock at the start of each month.

import json
from datetime import date

from db.db_connection import get_connection

PORTFOLIO_TYPES = ['dividend', 'value']


def _get_latest_run_date(conn, portfolio_type: str, snapshot_date: str) -> str | None:
    """Most recent run_date in scores_v2 <= snapshot_date for this portfolio."""
    row = conn.execute(
        "SELECT run_date FROM scores_v2 "
        "WHERE portfolio_type = ? AND run_date <= ? "
        "ORDER BY run_date DESC LIMIT 1",
        (portfolio_type, snapshot_date),
    ).fetchone()
    return row['run_date'] if row else None


def _get_scores_for_run(conn, portfolio_type: str, run_date: str) -> list:
    """All scored rows for a given portfolio_type + run_date."""
    return conn.execute(
        "SELECT ticker, score, rank, breakdown_json "
        "FROM scores_v2 WHERE portfolio_type = ? AND run_date = ?",
        (portfolio_type, run_date),
    ).fetchall()


def _get_latest_price(conn, ticker: str, snapshot_date: str) -> float | None:
    """Most recent close price on or before snapshot_date."""
    row = conn.execute(
        "SELECT close FROM prices WHERE ticker = ? AND date <= ? "
        "ORDER BY date DESC LIMIT 1",
        (ticker, snapshot_date),
    ).fetchone()
    return float(row['close']) if row and row['close'] is not None else None


def _get_sector(conn, ticker: str) -> str | None:
    """Sector for a ticker from the stocks table."""
    row = conn.execute("SELECT sector FROM stocks WHERE ticker = ?", (ticker,)).fetchone()
    return row['sector'] if row else None


def _extract_iv_estimate(breakdown_json: str | None) -> float | None:
    """Parse breakdown_json; return iv_estimate or intrinsic_value, or None."""
    if not breakdown_json:
        return None
    try:
        breakdown = json.loads(breakdown_json)
    except (json.JSONDecodeError, TypeError):
        return None
    iv = breakdown.get('iv_estimate') or breakdown.get('intrinsic_value')
    return float(iv) if iv is not None else None


def take_monthly_snapshot(snapshot_date: str | None = None) -> int:
    """
    Capture a point-in-time snapshot of all scored stocks for each portfolio type.

    Args:
        snapshot_date: YYYY-MM-DD string. Defaults to today.

    Returns:
        Total rows inserted across all portfolio types.
    """
    if snapshot_date is None:
        snapshot_date = date.today().isoformat()

    total_inserted = 0

    try:
        conn = get_connection()
    except Exception as exc:
        print(f"[snapshot] ERROR: could not open DB connection: {exc}")
        return 0

    try:
        for portfolio_type in PORTFOLIO_TYPES:
            run_date = _get_latest_run_date(conn, portfolio_type, snapshot_date)
            if not run_date:
                print(f"[snapshot] No scored data for '{portfolio_type}' "
                      f"on or before {snapshot_date} — skipping.")
                continue

            rows = _get_scores_for_run(conn, portfolio_type, run_date)
            if not rows:
                print(f"[snapshot] No rows for '{portfolio_type}' run_date={run_date} — skipping.")
                continue

            inserted = 0
            for row in rows:
                ticker = row['ticker']
                try:
                    score = float(row['score']) if row['score'] is not None else None
                    rank = int(row['rank']) if row['rank'] is not None else None
                    is_top10 = 1 if (rank is not None and rank <= 10) else 0

                    iv_estimate = _extract_iv_estimate(row['breakdown_json'])
                    price = _get_latest_price(conn, ticker, snapshot_date)
                    sector = _get_sector(conn, ticker)

                    mos_pct = None
                    if iv_estimate is not None and price is not None and price != 0:
                        mos_pct = (iv_estimate - price) / price

                    conn.execute(
                        "INSERT OR REPLACE INTO feedback_snapshots "
                        "(ticker, snapshot_date, portfolio_type, score, rank, "
                        " iv_estimate, price_at_snapshot, mos_pct, sector, "
                        " is_top10, price_source) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (ticker, snapshot_date, portfolio_type, score, rank,
                         iv_estimate, price, mos_pct, sector, is_top10, 'prices_table'),
                    )
                    inserted += 1

                except Exception as exc:
                    print(f"[snapshot] WARNING: skipping {ticker} ({portfolio_type}): {exc}")
                    continue

            conn.commit()
            print(f"[snapshot] {portfolio_type}: {inserted} rows inserted "
                  f"(snapshot_date={snapshot_date}, run_date={run_date})")
            total_inserted += inserted

    except Exception as exc:
        print(f"[snapshot] ERROR during snapshot: {exc}")
        return total_inserted
    finally:
        conn.close()

    print(f"[snapshot] Total rows inserted: {total_inserted}")
    return total_inserted
