# ============================================================
# db_watchlist.py — Watchlist DB Operations
# PSE Quant SaaS
# ============================================================

from datetime import datetime
from db.db_connection import get_connection

MAX_WATCHLIST_SIZE = 20


def get_watchlist(discord_id: str) -> list[str]:
    """Returns the list of tickers in a member's watchlist, ordered by added_at."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker FROM watchlists WHERE discord_id = ? ORDER BY added_at ASC",
        (discord_id,)
    ).fetchall()
    conn.close()
    return [r['ticker'] for r in rows]


def get_watchlist_count(discord_id: str) -> int:
    conn = get_connection()
    row  = conn.execute(
        "SELECT COUNT(*) AS cnt FROM watchlists WHERE discord_id = ?",
        (discord_id,)
    ).fetchone()
    conn.close()
    return row['cnt'] if row else 0


def add_to_watchlist(discord_id: str, ticker: str) -> tuple[bool, str]:
    """
    Adds a ticker to the member's watchlist.
    Returns (ok, message).
    Validates: ticker exists in stocks table, not already in list, under max size.
    """
    ticker = ticker.upper().strip()

    conn = get_connection()

    # Validate ticker exists
    row = conn.execute(
        "SELECT ticker FROM stocks WHERE ticker = ? AND status = 'active'",
        (ticker,)
    ).fetchone()
    if not row:
        conn.close()
        return False, f'**{ticker}** was not found in our stock universe. Check the ticker and try again.'

    # Check already in watchlist
    existing = conn.execute(
        "SELECT 1 FROM watchlists WHERE discord_id = ? AND ticker = ?",
        (discord_id, ticker)
    ).fetchone()
    if existing:
        conn.close()
        return False, f'**{ticker}** is already in your watchlist.'

    # Check max size
    count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM watchlists WHERE discord_id = ?",
        (discord_id,)
    ).fetchone()['cnt']
    if count >= MAX_WATCHLIST_SIZE:
        conn.close()
        return False, (
            f'Your watchlist is full ({MAX_WATCHLIST_SIZE} stocks max). '
            f'Remove a stock first with `/watchlist remove <ticker>`.'
        )

    # Insert
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "INSERT INTO watchlists (discord_id, ticker, added_at) VALUES (?, ?, ?)",
        (discord_id, ticker, now)
    )
    conn.commit()
    conn.close()
    return True, f'**{ticker}** added to your watchlist. ({count + 1}/{MAX_WATCHLIST_SIZE})'


def remove_from_watchlist(discord_id: str, ticker: str) -> tuple[bool, str]:
    """
    Removes a ticker from the member's watchlist.
    Returns (ok, message).
    """
    ticker = ticker.upper().strip()
    conn   = get_connection()
    cur    = conn.execute(
        "DELETE FROM watchlists WHERE discord_id = ? AND ticker = ?",
        (discord_id, ticker)
    )
    conn.commit()
    conn.close()
    if cur.rowcount:
        return True, f'**{ticker}** removed from your watchlist.'
    return False, f'**{ticker}** was not in your watchlist.'
