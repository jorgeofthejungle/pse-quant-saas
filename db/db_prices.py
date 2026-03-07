# ============================================================
# db_prices.py — Daily Price Data Operations
# PSE Quant SaaS
# ============================================================

from db.db_connection import get_connection


def upsert_price(ticker: str, date: str, close: float, market_cap: float = None):
    """
    Inserts a daily price record.
    If the same (ticker, date) already exists, updates close and market_cap.
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO prices (ticker, date, close, market_cap)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(ticker, date)
        DO UPDATE SET close      = excluded.close,
                      market_cap = excluded.market_cap
    """, (ticker, date, close, market_cap))
    conn.commit()
    conn.close()


def get_latest_price(ticker: str) -> dict | None:
    """
    Returns the most recent price record for a ticker as a dict,
    or None if no price data exists.
    """
    conn = get_connection()
    row = conn.execute("""
        SELECT ticker, date, close, market_cap
        FROM prices
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT 1
    """, (ticker,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
