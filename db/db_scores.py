# ============================================================
# db_scores.py — Portfolio Score & Ranking Operations
# PSE Quant SaaS
# ============================================================

import json
from db.db_connection import get_connection


def save_scores(run_date: str, ranked_stocks: list, portfolio_type: str):
    """
    Saves scores for one portfolio for a given run_date.

    Parameters:
        run_date       — 'YYYY-MM-DD' string
        ranked_stocks  — list of stock dicts sorted by score (index 0 = rank 1)
        portfolio_type — 'pure_dividend', 'dividend_growth', or 'value'

    Uses UPSERT so calling save_scores for multiple portfolios on the
    same day correctly populates all columns on each row.
    """
    score_col = f'{portfolio_type}_score'
    rank_col  = f'{portfolio_type}_rank'

    conn = get_connection()
    for rank, stock in enumerate(ranked_stocks, 1):
        conn.execute(f"""
            INSERT INTO scores (ticker, run_date, {score_col}, {rank_col})
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker, run_date)
            DO UPDATE SET {score_col} = excluded.{score_col},
                          {rank_col}  = excluded.{rank_col}
        """, (stock['ticker'], run_date, stock['score'], rank))
    conn.commit()
    conn.close()


def get_last_top5(portfolio_type: str) -> list:
    """
    Returns the list of top-5 tickers from the most recent run
    for the given portfolio type.

    Returns empty list on first-ever run (no prior data).
    The scheduler uses this to detect top-5 changes.
    """
    rank_col = f'{portfolio_type}_rank'
    conn = get_connection()

    row = conn.execute(f"""
        SELECT MAX(run_date) AS latest
        FROM scores
        WHERE {rank_col} IS NOT NULL
    """).fetchone()

    if not row or not row['latest']:
        conn.close()
        return []

    latest = row['latest']
    rows = conn.execute(f"""
        SELECT ticker
        FROM scores
        WHERE run_date = ? AND {rank_col} <= 5
        ORDER BY {rank_col}
    """, (latest,)).fetchall()

    conn.close()
    return [r['ticker'] for r in rows]


def get_last_scores(portfolio_type: str) -> list:
    """
    Returns [{ticker, score, rank}] from the most recent run.
    Used to build the changes list for send_rescore_notice().
    Returns empty list if no prior data.
    """
    score_col = f'{portfolio_type}_score'
    rank_col  = f'{portfolio_type}_rank'

    conn = get_connection()

    row = conn.execute(f"""
        SELECT MAX(run_date) AS latest
        FROM scores
        WHERE {rank_col} IS NOT NULL
    """).fetchone()

    if not row or not row['latest']:
        conn.close()
        return []

    latest = row['latest']
    rows = conn.execute(f"""
        SELECT ticker,
               {score_col} AS score,
               {rank_col}  AS rank
        FROM scores
        WHERE run_date = ? AND {rank_col} IS NOT NULL
        ORDER BY {rank_col}
    """, (latest,)).fetchall()

    conn.close()
    return [{'ticker': r['ticker'], 'score': r['score'], 'rank': r['rank']}
            for r in rows]


# ── Unified v2 scores table ───────────────────────────────────

def save_scores_v2(run_date: str, ranked_stocks: list):
    """
    Saves unified 4-layer scores to the scores_v2 table.
    Stores rank, score, grade category, and full breakdown as JSON.
    Each (ticker, run_date) pair is unique — upserts on conflict.
    """
    conn = get_connection()
    for rank, stock in enumerate(ranked_stocks, 1):
        breakdown = stock.get('breakdown') or {}
        category  = breakdown.get('category', '')
        conn.execute("""
            INSERT INTO scores_v2 (ticker, run_date, score, rank, category, breakdown_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, run_date)
            DO UPDATE SET score          = excluded.score,
                          rank           = excluded.rank,
                          category       = excluded.category,
                          breakdown_json = excluded.breakdown_json
        """, (
            stock['ticker'], run_date,
            stock.get('score'), rank, category,
            json.dumps(breakdown),
        ))
    conn.commit()
    conn.close()


def get_last_top5_v2() -> list:
    """
    Returns the list of top-5 tickers from the most recent scores_v2 run.
    Returns empty list if no data yet.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(run_date) AS latest FROM scores_v2 WHERE rank IS NOT NULL"
    ).fetchone()
    if not row or not row['latest']:
        conn.close()
        return []
    latest = row['latest']
    rows = conn.execute(
        "SELECT ticker FROM scores_v2 WHERE run_date = ? AND rank <= 5 ORDER BY rank",
        (latest,)
    ).fetchall()
    conn.close()
    return [r['ticker'] for r in rows]


def get_last_scores_v2() -> list:
    """
    Returns [{ticker, score, rank, category}] from the most recent scores_v2 run.
    Returns empty list if no data yet.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(run_date) AS latest FROM scores_v2 WHERE rank IS NOT NULL"
    ).fetchone()
    if not row or not row['latest']:
        conn.close()
        return []
    latest = row['latest']
    rows = conn.execute(
        """SELECT ticker, score, rank, category
           FROM scores_v2
           WHERE run_date = ? AND rank IS NOT NULL
           ORDER BY rank""",
        (latest,)
    ).fetchall()
    conn.close()
    return [{'ticker': r['ticker'], 'score': r['score'],
             'rank': r['rank'], 'category': r['category']}
            for r in rows]
