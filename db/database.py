# ============================================================
# database.py — SQLite Database Layer
# PSE Quant SaaS — Phase 3
# ============================================================
# Single source of truth for all database operations.
# Call init_db() once at startup — it creates all tables
# safely (IF NOT EXISTS) on every run.
#
# DB file: db/pse_quant.db (auto-created on first run)
# ============================================================

import sqlite3
import os
from pathlib import Path

# DB path: AppData\Local\pse_quant\ (never synced by OneDrive).
# Override with PSE_DB_PATH environment variable or .env entry if needed.
_default_db = Path(os.environ.get('LOCALAPPDATA',
                   Path.home() / 'AppData' / 'Local')) / 'pse_quant' / 'pse_quant.db'
DB_PATH = Path(os.environ.get('PSE_DB_PATH', _default_db))


def get_connection() -> sqlite3.Connection:
    """
    Returns a SQLite connection to pse_quant.db.
    Row factory is set so rows can be accessed by column name.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent read/write performance
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    """
    Creates all tables if they do not already exist.
    Safe to call on every startup — idempotent.
    """
    print(f"  DB location: {DB_PATH}")
    conn = get_connection()
    conn.executescript("""
        -- ── Master stock list ───────────────────────────────
        CREATE TABLE IF NOT EXISTS stocks (
            ticker       TEXT PRIMARY KEY,
            name         TEXT,
            sector       TEXT,
            is_reit      INTEGER DEFAULT 0,
            is_bank      INTEGER DEFAULT 0,
            last_updated TEXT
        );

        -- ── Annual financial data (from PSE Edge filings) ───
        CREATE TABLE IF NOT EXISTS financials (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker       TEXT NOT NULL,
            year         INTEGER NOT NULL,
            revenue      REAL,
            net_income   REAL,
            equity       REAL,
            total_debt   REAL,
            cash         REAL,
            operating_cf REAL,
            capex        REAL,
            ebitda       REAL,
            eps          REAL,
            dps          REAL,
            UNIQUE(ticker, year),
            FOREIGN KEY (ticker) REFERENCES stocks(ticker)
        );

        -- ── Daily closing prices ─────────────────────────────
        CREATE TABLE IF NOT EXISTS prices (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker     TEXT NOT NULL,
            date       TEXT NOT NULL,
            close      REAL,
            market_cap REAL,
            UNIQUE(ticker, date),
            FOREIGN KEY (ticker) REFERENCES stocks(ticker)
        );

        -- ── Portfolio scores and rankings per run ────────────
        -- One row per (ticker, run_date).
        -- All three portfolio scores live in the same row so
        -- a single query can compare across portfolios.
        CREATE TABLE IF NOT EXISTS scores (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                TEXT NOT NULL,
            run_date              TEXT NOT NULL,
            pure_dividend_score   REAL,
            pure_dividend_rank    INTEGER,
            dividend_growth_score REAL,
            dividend_growth_rank  INTEGER,
            value_score           REAL,
            value_rank            INTEGER,
            UNIQUE(ticker, run_date),
            FOREIGN KEY (ticker) REFERENCES stocks(ticker)
        );

        -- ── PSE Edge disclosure index ─────────────────────────
        CREATE TABLE IF NOT EXISTS disclosures (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date   TEXT NOT NULL,
            type   TEXT,
            title  TEXT,
            url    TEXT,
            UNIQUE(ticker, date, url),
            FOREIGN KEY (ticker) REFERENCES stocks(ticker)
        );

        -- ── News sentiment cache (24-hour TTL via UNIQUE) ────
        CREATE TABLE IF NOT EXISTS sentiment (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker             TEXT NOT NULL,
            date               TEXT NOT NULL,
            score              REAL,
            category           TEXT,
            key_events         TEXT,
            summary            TEXT,
            opportunistic_flag INTEGER DEFAULT 0,
            risk_flag          INTEGER DEFAULT 0,
            headlines          TEXT,
            UNIQUE(ticker, date),
            FOREIGN KEY (ticker) REFERENCES stocks(ticker)
        );

        -- ── Indexes for common query patterns ────────────────
        CREATE INDEX IF NOT EXISTS idx_prices_ticker_date
            ON prices(ticker, date);
        CREATE INDEX IF NOT EXISTS idx_scores_run_date
            ON scores(run_date);
        CREATE INDEX IF NOT EXISTS idx_financials_ticker_year
            ON financials(ticker, year);
        CREATE INDEX IF NOT EXISTS idx_sentiment_ticker_date
            ON sentiment(ticker, date);
    """)
    conn.commit()
    conn.close()
    print(f"Database ready: {DB_PATH}")


# ── Price helpers ────────────────────────────────────────────

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


# ── Score helpers ────────────────────────────────────────────

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


# ── Financial data helpers ───────────────────────────────────

def upsert_financials(ticker: str, year: int,
                      revenue: float = None, net_income: float = None,
                      equity: float = None, total_debt: float = None,
                      cash: float = None, operating_cf: float = None,
                      capex: float = None, ebitda: float = None,
                      eps: float = None, dps: float = None):
    """
    Inserts or updates one year of financial data for a ticker.
    Monetary values in millions PHP; eps and dps are per-share in PHP.
    COALESCE update: only overwrites existing values with non-None new values,
    so partial updates from different sources don't erase existing data.
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO financials
            (ticker, year, revenue, net_income, equity, total_debt,
             cash, operating_cf, capex, ebitda, eps, dps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, year) DO UPDATE SET
            revenue      = COALESCE(excluded.revenue,      revenue),
            net_income   = COALESCE(excluded.net_income,   net_income),
            equity       = COALESCE(excluded.equity,       equity),
            total_debt   = COALESCE(excluded.total_debt,   total_debt),
            cash         = COALESCE(excluded.cash,         cash),
            operating_cf = COALESCE(excluded.operating_cf, operating_cf),
            capex        = COALESCE(excluded.capex,        capex),
            ebitda       = COALESCE(excluded.ebitda,       ebitda),
            eps          = COALESCE(excluded.eps,          eps),
            dps          = COALESCE(excluded.dps,          dps)
    """, (ticker, year, revenue, net_income, equity, total_debt,
          cash, operating_cf, capex, ebitda, eps, dps))
    conn.commit()
    conn.close()


def get_financials(ticker: str, years: int = 5) -> list:
    """
    Returns the last N years of financial data for a ticker,
    ordered newest year first. Returns empty list if no data.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT year, revenue, net_income, equity, total_debt, cash,
               operating_cf, capex, ebitda, eps, dps
        FROM financials
        WHERE ticker = ?
        ORDER BY year DESC
        LIMIT ?
    """, (ticker, years)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Stock / financial helpers ─────────────────────────────────

def upsert_stock(ticker: str, name: str, sector: str,
                 is_reit: bool = False, is_bank: bool = False):
    """
    Inserts or updates a stock's identity record.
    """
    from datetime import datetime
    conn = get_connection()
    conn.execute("""
        INSERT INTO stocks (ticker, name, sector, is_reit, is_bank, last_updated)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker)
        DO UPDATE SET name         = excluded.name,
                      sector       = excluded.sector,
                      is_reit      = excluded.is_reit,
                      is_bank      = excluded.is_bank,
                      last_updated = excluded.last_updated
    """, (ticker, name, sector, int(is_reit), int(is_bank),
          datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()


def get_all_tickers() -> list:
    """Returns list of all ticker strings in the stocks table."""
    conn = get_connection()
    rows = conn.execute("SELECT ticker FROM stocks ORDER BY ticker").fetchall()
    conn.close()
    return [r['ticker'] for r in rows]


# ── Sentiment helpers ────────────────────────────────────────

def upsert_sentiment(ticker: str, date: str, data: dict) -> None:
    """
    Saves sentiment analysis result to DB.
    data keys: score, category, key_events (list), summary,
               opportunistic_flag, risk_flag, headlines (list)
    UNIQUE(ticker, date) ensures one row per stock per calendar day.
    """
    import json
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
    import json
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
    result['key_events'] = [e for e in result['key_events'].split('|') if e] if result['key_events'] else []
    result['headlines']  = json.loads(result['headlines']) if result['headlines'] else []
    return result


# ── Self-test ────────────────────────────────────────────────

if __name__ == '__main__':
    print("Initialising PSE Quant database...")
    init_db()

    # Verify tables were created
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
