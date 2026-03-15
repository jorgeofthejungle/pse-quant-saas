# ============================================================
# db_conglomerates.py — Conglomerate Segment Data CRUD
# PSE Quant SaaS
# ============================================================
# Stores manual segment financials for the Top 5 PH holding
# firms (SM, AC, JGS, GTCAP, DMC).
# Called from dashboard/routes_conglomerates.py (data entry)
# and engine/conglomerate_scorer.py (scoring).
# ============================================================

from datetime import datetime
from db.db_connection import get_connection


def upsert_segment(
    parent_ticker:  str,
    segment_name:   str,
    year:           int,
    revenue:        float | None = None,
    net_income:     float | None = None,
    equity:         float | None = None,
    segment_ticker: str | None = None,
    notes:          str | None = None,
) -> None:
    """Insert or replace a segment row."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO conglomerate_segments
            (parent_ticker, segment_name, segment_ticker,
             revenue, net_income, equity, year, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(parent_ticker, segment_name, year)
        DO UPDATE SET
            segment_ticker = excluded.segment_ticker,
            revenue        = excluded.revenue,
            net_income     = excluded.net_income,
            equity         = excluded.equity,
            notes          = excluded.notes,
            updated_at     = excluded.updated_at
    """, (
        parent_ticker.upper(), segment_name, segment_ticker or None,
        revenue, net_income, equity, year, notes,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    ))
    conn.commit()
    conn.close()


def get_segments(parent_ticker: str, year: int | None = None) -> list[dict]:
    """
    Returns segment rows for a parent ticker.
    If year given, returns only that year; otherwise returns all years
    sorted by year DESC, segment_name ASC.
    """
    conn = get_connection()
    if year is not None:
        rows = conn.execute("""
            SELECT * FROM conglomerate_segments
            WHERE parent_ticker = ? AND year = ?
            ORDER BY segment_name
        """, (parent_ticker.upper(), year)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM conglomerate_segments
            WHERE parent_ticker = ?
            ORDER BY year DESC, segment_name
        """, (parent_ticker.upper(),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_segments(parent_ticker: str) -> list[dict]:
    """Returns segments for the most recent year available."""
    conn = get_connection()
    row = conn.execute("""
        SELECT MAX(year) AS yr FROM conglomerate_segments
        WHERE parent_ticker = ?
    """, (parent_ticker.upper(),)).fetchone()
    if not row or not row['yr']:
        conn.close()
        return []
    year = row['yr']
    rows = conn.execute("""
        SELECT * FROM conglomerate_segments
        WHERE parent_ticker = ? AND year = ?
        ORDER BY revenue DESC NULLS LAST
    """, (parent_ticker.upper(), year)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_segment_years(parent_ticker: str) -> list[int]:
    """Returns sorted list of years with segment data for this ticker."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT year FROM conglomerate_segments
        WHERE parent_ticker = ?
        ORDER BY year DESC
    """, (parent_ticker.upper(),)).fetchall()
    conn.close()
    return [r['year'] for r in rows]


def delete_segment(parent_ticker: str, segment_name: str, year: int) -> bool:
    """Deletes one segment row. Returns True if a row was deleted."""
    conn = get_connection()
    cursor = conn.execute("""
        DELETE FROM conglomerate_segments
        WHERE parent_ticker = ? AND segment_name = ? AND year = ?
    """, (parent_ticker.upper(), segment_name, year))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def get_all_segment_years() -> dict[str, list[int]]:
    """Returns {parent_ticker: [years]} for all tickers with data."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT parent_ticker, year FROM conglomerate_segments
        GROUP BY parent_ticker, year
        ORDER BY parent_ticker, year DESC
    """).fetchall()
    conn.close()
    result: dict[str, list[int]] = {}
    for r in rows:
        result.setdefault(r['parent_ticker'], []).append(r['year'])
    return result
