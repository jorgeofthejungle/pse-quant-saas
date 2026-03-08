# ============================================================
# db_schema.py — Database Schema Initialisation
# PSE Quant SaaS
# ============================================================
# Creates all tables and indexes. Safe to call on every startup
# (IF NOT EXISTS guards make it idempotent).
# ============================================================

from db.db_connection import get_connection, DB_PATH


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
            last_updated TEXT,
            last_scraped TEXT,
            status       TEXT DEFAULT 'active'
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
            updated_at   TEXT,
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

        -- ── Discord members / subscribers ─────────────────────
        CREATE TABLE IF NOT EXISTS members (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id   TEXT UNIQUE,
            discord_name TEXT NOT NULL,
            email        TEXT,
            plan         TEXT DEFAULT 'monthly',
            status       TEXT DEFAULT 'active',
            joined_date  TEXT NOT NULL,
            expiry_date  TEXT,
            notes        TEXT,
            created_at   TEXT NOT NULL
        );

        -- ── Payment / billing records ──────────────────────────
        CREATE TABLE IF NOT EXISTS subscriptions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id      INTEGER NOT NULL,
            payment_id     TEXT,
            amount         REAL NOT NULL,
            plan           TEXT NOT NULL,
            status         TEXT DEFAULT 'paid',
            payment_method TEXT,
            paid_date      TEXT NOT NULL,
            period_start   TEXT NOT NULL,
            period_end     TEXT NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        -- ── System activity log ────────────────────────────────
        CREATE TABLE IF NOT EXISTS activity_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            category  TEXT NOT NULL,
            action    TEXT NOT NULL,
            detail    TEXT,
            status    TEXT DEFAULT 'ok'
        );

        -- ── Runtime settings (key-value, overrides config.py) ─
        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
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
        CREATE INDEX IF NOT EXISTS idx_members_status
            ON members(status);
        CREATE INDEX IF NOT EXISTS idx_members_expiry
            ON members(expiry_date);
        CREATE INDEX IF NOT EXISTS idx_activity_timestamp
            ON activity_log(timestamp);
    """)
    conn.commit()

    # ── Schema migrations for existing DBs ───────────────────
    # SQLite does not support IF NOT EXISTS on ALTER TABLE.
    # We catch the OperationalError that fires when the column already exists.
    migrations = [
        "ALTER TABLE stocks     ADD COLUMN last_scraped TEXT",
        "ALTER TABLE stocks     ADD COLUMN status       TEXT DEFAULT 'active'",
        "ALTER TABLE financials ADD COLUMN updated_at   TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass   # column already exists — safe to ignore
    conn.commit()

    # Add the status index only after the column migration has run
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stocks_status ON stocks(status)")
        conn.commit()
    except Exception:
        pass
    conn.close()
    print(f"Database ready: {DB_PATH}")
