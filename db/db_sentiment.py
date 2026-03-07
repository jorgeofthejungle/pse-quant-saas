# ============================================================
# db_sentiment.py — News Sentiment Cache Operations
# PSE Quant SaaS
# ============================================================
# 24-hour cache via UNIQUE(ticker, date).
# One row per stock per calendar day.
# ============================================================

import json
from db.db_connection import get_connection


def upsert_sentiment(ticker: str, date: str, data: dict) -> None:
    """
    Saves sentiment analysis result to DB.
    data keys: score, category, key_events (list), summary,
               opportunistic_flag, risk_flag, headlines (list)
    UNIQUE(ticker, date) ensures one row per stock per calendar day.
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO sentiment
            (ticker, date, score, category, key_events, summary,
             opportunistic_flag, risk_flag, headlines)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            score              = excluded.score,
            category           = excluded.category,
            key_events         = excluded.key_events,
            summary            = excluded.summary,
            opportunistic_flag = excluded.opportunistic_flag,
            risk_flag          = excluded.risk_flag,
            headlines          = excluded.headlines
    """, (
        ticker, date,
        data.get('score'),
        data.get('category'),
        '|'.join(data.get('key_events') or []),
        data.get('summary'),
        int(data.get('opportunistic_flag', 0)),
        int(data.get('risk_flag', 0)),
        json.dumps(data.get('headlines') or []),
    ))
    conn.commit()
    conn.close()


def get_sentiment(ticker: str) -> dict | None:
    """
    Returns the most recent sentiment row for a ticker as a dict,
    or None if no sentiment data exists.
    """
    conn = get_connection()
    row = conn.execute("""
        SELECT ticker, date, score, category, key_events, summary,
               opportunistic_flag, risk_flag, headlines
        FROM sentiment
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT 1
    """, (ticker,)).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    result['key_events'] = [e for e in result['key_events'].split('|') if e] \
                           if result['key_events'] else []
    result['headlines']  = json.loads(result['headlines']) \
                           if result['headlines'] else []
    return result
