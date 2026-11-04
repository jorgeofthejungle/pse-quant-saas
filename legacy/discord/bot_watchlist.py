# ============================================================
# bot_watchlist.py — /watchlist Command Logic
# PSE Quant SaaS — Discord Bot
# ============================================================
# /watchlist show              — list all watchlist stocks with scores
# /watchlist add <ticker>      — add a stock (max 20)
# /watchlist remove <ticker>   — remove a stock
#
# Premium-gated, DM-only.
# ============================================================

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in ['db', 'engine', 'scraper']:
    sys.path.insert(0, str(ROOT / p))
sys.path.insert(0, str(ROOT))

COLOUR_BLUE  = 0x2980B9
COLOUR_GREEN = 0x27AE60
COLOUR_RED   = 0xE74C3C
COLOUR_GREY  = 0x95A5A6
MAX_SIZE     = 20


def _grade(score: float) -> str:
    if score >= 80: return 'A'
    if score >= 65: return 'B'
    if score >= 50: return 'C'
    if score >= 35: return 'D'
    return 'F'


def get_watchlist_embed(discord_id: str) -> dict:
    """
    Returns a Discord embed showing all stocks in the member's watchlist
    with their current scores, grades, and MoS status.
    Returns {'error': str} on failure.
    """
    try:
        import database as db
        from db.db_watchlist import get_watchlist
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    tickers = get_watchlist(discord_id)

    if not tickers:
        return {
            'title':       'Your Watchlist',
            'description': 'Your watchlist is empty.',
            'color':       COLOUR_GREY,
            'fields': [{
                'name':   'Get started',
                'value':  'Use `/watchlist add <ticker>` to add up to 20 stocks.\nExample: `/watchlist add DMC`',
                'inline': False,
            }],
            'footer': {'text': 'StockPilot PH · Watchlist'},
        }

    # Load latest scores for all watchlist tickers
    all_scores = db.get_last_scores_v2() or []
    score_map  = {s['ticker']: s.get('score', 0) or 0 for s in all_scores}

    # Load names
    conn      = db.get_connection()
    name_rows = conn.execute("SELECT ticker, name FROM stocks").fetchall()
    conn.close()
    name_map  = {r['ticker']: r['name'] for r in name_rows}

    lines = []
    for i, ticker in enumerate(tickers, 1):
        score = score_map.get(ticker)
        name  = name_map.get(ticker, ticker)
        if score is not None:
            grade = _grade(score)
            lines.append(f'`{i:2}.` **{ticker}** — {score:.1f} ({grade})  ·  {name}')
        else:
            lines.append(f'`{i:2}.` **{ticker}** — not yet scored  ·  {name}')

    return {
        'title':       f'Your Watchlist  ({len(tickers)}/{MAX_SIZE})',
        'description': '\n'.join(lines),
        'color':       COLOUR_BLUE,
        'fields': [{
            'name':   'Commands',
            'value':  '`/watchlist add <ticker>` · `/watchlist remove <ticker>`',
            'inline': False,
        }],
        'footer': {'text': 'StockPilot PH · Scores updated daily at 5:30 PM PHT.'},
    }


def add_watchlist_embed(discord_id: str, ticker: str) -> dict:
    """
    Adds a ticker to the watchlist and returns a confirmation embed.
    Returns {'error': str} on failure.
    """
    try:
        from db.db_watchlist import add_to_watchlist
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    ok, message = add_to_watchlist(discord_id, ticker.upper().strip())
    return {
        'title':       'Watchlist Updated' if ok else 'Could Not Add Stock',
        'description': message,
        'color':       COLOUR_GREEN if ok else COLOUR_RED,
        'fields':      [],
        'footer':      {'text': 'StockPilot PH · Use /watchlist show to see your full list.'},
    }


def remove_watchlist_embed(discord_id: str, ticker: str) -> dict:
    """
    Removes a ticker from the watchlist and returns a confirmation embed.
    Returns {'error': str} on failure.
    """
    try:
        from db.db_watchlist import remove_from_watchlist
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    ok, message = remove_from_watchlist(discord_id, ticker.upper().strip())
    return {
        'title':       'Watchlist Updated' if ok else 'Could Not Remove Stock',
        'description': message,
        'color':       COLOUR_GREEN if ok else COLOUR_RED,
        'fields':      [],
        'footer':      {'text': 'StockPilot PH · Use /watchlist show to see your full list.'},
    }
