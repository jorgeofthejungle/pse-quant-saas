# ============================================================
# database.py — Public Facade (re-exports all DB operations)
# PSE Quant SaaS
# ============================================================
# All callers import from here — internal structure is hidden.
# Sub-modules:
#   db_connection.py  — connection factory & DB_PATH
#   db_schema.py      — init_db() / table creation
#   db_prices.py      — price data operations
#   db_scores.py      — score & ranking operations
#   db_financials.py  — financial & stock identity operations
#   db_sentiment.py   — sentiment cache operations
# ============================================================

from db.db_connection import get_connection, DB_PATH
from db.db_schema     import init_db
from db.db_prices     import upsert_price, get_latest_price
from db.db_scores     import save_scores, get_last_top5, get_last_scores
from db.db_financials import (upsert_financials, get_financials,
                               upsert_stock, get_all_tickers)
from db.db_sentiment  import upsert_sentiment, get_sentiment

__all__ = [
    'get_connection', 'DB_PATH',
    'init_db',
    'upsert_price', 'get_latest_price',
    'save_scores', 'get_last_top5', 'get_last_scores',
    'upsert_financials', 'get_financials', 'upsert_stock', 'get_all_tickers',
    'upsert_sentiment', 'get_sentiment',
]


# ── Self-test ────────────────────────────────────────────────

if __name__ == '__main__':
    print("Initialising PSE Quant database...")
    init_db()

    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()

    print("\nTables created:")
    for t in tables:
        print(f"  {t['name']}")

    print(f"\nDatabase file: {DB_PATH}")
    print("Database initialisation complete.")
