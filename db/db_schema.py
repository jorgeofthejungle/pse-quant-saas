# ============================================================
# db_schema.py — Database Schema Initialisation
# PSE Quant SaaS
# ============================================================
# Creates all tables and indexes. Safe to call on every startup
# (IF NOT EXISTS guards make it idempotent).
# Postgres-native DDL: SERIAL primary keys, no PRAGMA, no
# executescript. Migrations use SAVEPOINTs to stay in one txn.
# ============================================================

from db.db_connection import get_connection


_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS stocks (
        ticker       TEXT PRIMARY KEY,
        name         TEXT,
        sector       TEXT,
        is_reit      INTEGER DEFAULT 0,
        is_bank      INTEGER DEFAULT 0,
        last_updated TEXT,
        last_scraped TEXT,
        status       TEXT DEFAULT 'active',
        cmpy_id      TEXT,
        fiscal_year_end_month INTEGER DEFAULT 12
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financials (
        id           SERIAL PRIMARY KEY,
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
        depreciation REAL,
        amortization REAL,
        updated_at   TEXT,
        UNIQUE(ticker, year),
        FOREIGN KEY (ticker) REFERENCES stocks(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prices (
        id         SERIAL PRIMARY KEY,
        ticker     TEXT NOT NULL,
        date       TEXT NOT NULL,
        close      REAL,
        market_cap REAL,
        UNIQUE(ticker, date),
        FOREIGN KEY (ticker) REFERENCES stocks(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scores (
        id                    SERIAL PRIMARY KEY,
        ticker                TEXT NOT NULL,
        run_date              TEXT NOT NULL,
        pure_dividend_score   REAL,
        pure_dividend_rank    INTEGER,
        dividend_growth_score REAL,
        dividend_growth_rank  INTEGER,
        value_score           REAL,
        value_rank            INTEGER,
        unified_score         REAL,
        unified_rank          INTEGER,
        UNIQUE(ticker, run_date),
        FOREIGN KEY (ticker) REFERENCES stocks(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scores_v2 (
        id             SERIAL PRIMARY KEY,
        ticker         TEXT NOT NULL,
        run_date       TEXT NOT NULL,
        portfolio_type TEXT NOT NULL DEFAULT 'unified',
        score          REAL,
        confidence     REAL DEFAULT 1.0,
        rank           INTEGER,
        category       TEXT,
        breakdown_json TEXT,
        UNIQUE(ticker, run_date, portfolio_type),
        FOREIGN KEY (ticker) REFERENCES stocks(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS disclosures (
        id     SERIAL PRIMARY KEY,
        ticker TEXT NOT NULL,
        date   TEXT NOT NULL,
        type   TEXT,
        title  TEXT,
        url    TEXT,
        UNIQUE(ticker, date, url),
        FOREIGN KEY (ticker) REFERENCES stocks(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sentiment (
        id                 SERIAL PRIMARY KEY,
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS members (
        id           SERIAL PRIMARY KEY,
        discord_id   TEXT UNIQUE,
        discord_name TEXT NOT NULL,
        email        TEXT,
        plan         TEXT DEFAULT 'monthly',
        status       TEXT DEFAULT 'active',
        tier         TEXT DEFAULT 'paid',
        joined_date  TEXT NOT NULL,
        expiry_date  TEXT,
        notes        TEXT,
        created_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id             SERIAL PRIMARY KEY,
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS activity_log (
        id        SERIAL PRIMARY KEY,
        timestamp TEXT NOT NULL,
        category  TEXT NOT NULL,
        action    TEXT NOT NULL,
        detail    TEXT,
        status    TEXT DEFAULT 'ok'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conglomerate_segments (
        id             SERIAL PRIMARY KEY,
        parent_ticker  TEXT NOT NULL,
        segment_name   TEXT NOT NULL,
        segment_ticker TEXT,
        revenue        REAL,
        net_income     REAL,
        equity         REAL,
        year           INTEGER NOT NULL,
        notes          TEXT,
        updated_at     TEXT,
        UNIQUE(parent_ticker, segment_name, year),
        FOREIGN KEY (parent_ticker) REFERENCES stocks(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlists (
        id         SERIAL PRIMARY KEY,
        discord_id TEXT NOT NULL,
        ticker     TEXT NOT NULL,
        added_at   TEXT NOT NULL,
        UNIQUE(discord_id, ticker),
        FOREIGN KEY (ticker) REFERENCES stocks(ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS index_prices (
        id         SERIAL PRIMARY KEY,
        index_name TEXT NOT NULL,
        date       DATE NOT NULL,
        close      REAL,
        created_at TEXT,
        UNIQUE(index_name, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_snapshots (
        id                SERIAL PRIMARY KEY,
        ticker            TEXT NOT NULL,
        snapshot_date     DATE NOT NULL,
        portfolio_type    TEXT NOT NULL,
        score             REAL,
        rank              INTEGER,
        iv_estimate       REAL,
        price_at_snapshot REAL,
        mos_pct           REAL,
        sector            TEXT,
        is_top10          INTEGER DEFAULT 0,
        price_source      TEXT,
        UNIQUE(ticker, snapshot_date, portfolio_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_stock_returns (
        id                      SERIAL PRIMARY KEY,
        ticker                  TEXT NOT NULL,
        month                   TEXT NOT NULL,
        portfolio_type          TEXT NOT NULL,
        score_at_start          REAL,
        price_start             REAL,
        price_end               REAL,
        return_pct              REAL,
        rank_at_start           INTEGER,
        was_top10               INTEGER DEFAULT 0,
        score_change_flag       INTEGER DEFAULT 0,
        score_change_severity   TEXT,
        score_change_magnitude  REAL,
        consecutive_flag_months INTEGER DEFAULT 0,
        created_at              TEXT,
        UNIQUE(ticker, month, portfolio_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_monthly (
        id                       SERIAL PRIMARY KEY,
        month                    TEXT NOT NULL,
        portfolio_type           TEXT NOT NULL,
        top10_avg_return         REAL,
        top10_vs_index           REAL,
        hit_rate_positive        REAL,
        match_rate_pct           REAL,
        mos_direction_accuracy   REAL,
        iv_coverage_pct          REAL,
        spearman_correlation     REAL,
        avg_score_of_gainers     REAL,
        avg_score_of_losers      REAL,
        score_separation_power   REAL,
        total_previous           INTEGER,
        total_current            INTEGER,
        total_matched            INTEGER,
        market_positive_rate     REAL,
        score_change_flag_count  INTEGER DEFAULT 0,
        score_change_minor_count INTEGER DEFAULT 0,
        score_change_major_count INTEGER DEFAULT 0,
        confidence_level         TEXT,
        created_at               TEXT,
        UNIQUE(month, portfolio_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_quarterly (
        id                        SERIAL PRIMARY KEY,
        quarter                   TEXT NOT NULL,
        portfolio_type            TEXT NOT NULL,
        evaluation_window_start   DATE,
        evaluation_window_end     DATE,
        avg_monthly_top10_return  REAL,
        avg_monthly_hit_rate      REAL,
        avg_monthly_mos_accuracy  REAL,
        avg_spearman              REAL,
        blind_spot_count          INTEGER DEFAULT 0,
        blind_spot_tickers        TEXT,
        sector_bias_json          TEXT,
        sectors_flagged           TEXT,
        sectors_skipped           TEXT,
        score_band_json           TEXT,
        band_inversion_flag       INTEGER DEFAULT 0,
        consecutive_bias_quarters TEXT,
        total_stocks_evaluated    INTEGER DEFAULT 0,
        confidence_level          TEXT,
        corrections_applied_json  TEXT,
        corrections_blocked_json  TEXT,
        created_at                TEXT,
        UNIQUE(quarter, portfolio_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_diagnostic_log (
        id             SERIAL PRIMARY KEY,
        quarter        TEXT NOT NULL,
        portfolio_type TEXT NOT NULL,
        sector         TEXT,
        metric_name    TEXT,
        metric_value   REAL,
        z_score        REAL,
        met_threshold  INTEGER DEFAULT 0,
        bias_direction TEXT,
        bias_magnitude REAL,
        stock_count    INTEGER,
        notes          TEXT,
        created_at     TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_track_record (
        id                                     SERIAL PRIMARY KEY,
        period_type                            TEXT NOT NULL,
        portfolio_type                         TEXT NOT NULL,
        evaluation_date                        DATE NOT NULL,
        top10_avg_return                       REAL,
        top10_cumulative_return                REAL,
        index_cumulative_return                REAL,
        top10_vs_index                         REAL,
        hit_rate                               REAL,
        mos_accuracy                           REAL,
        total_months_tracked                   INTEGER DEFAULT 0,
        consecutive_months_outperforming_index INTEGER DEFAULT 0,
        best_month_return                      REAL,
        worst_month_return                     REAL,
        avg_spearman                           REAL,
        positive_spearman_ratio                REAL,
        data_completeness_pct                  REAL,
        publishable                            INTEGER DEFAULT 0,
        publish_reason                         TEXT,
        created_at                             TEXT,
        UNIQUE(period_type, portfolio_type, evaluation_date)
    )
    """,
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_prices_ticker_date        ON prices(ticker, date)",
    "CREATE INDEX IF NOT EXISTS idx_scores_run_date            ON scores(run_date)",
    "CREATE INDEX IF NOT EXISTS idx_scores_v2_run_date         ON scores_v2(run_date)",
    "CREATE INDEX IF NOT EXISTS idx_scores_v2_ticker           ON scores_v2(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_financials_ticker_year     ON financials(ticker, year)",
    "CREATE INDEX IF NOT EXISTS idx_sentiment_ticker_date      ON sentiment(ticker, date)",
    "CREATE INDEX IF NOT EXISTS idx_members_status             ON members(status)",
    "CREATE INDEX IF NOT EXISTS idx_members_expiry             ON members(expiry_date)",
    "CREATE INDEX IF NOT EXISTS idx_activity_timestamp         ON activity_log(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_segments_parent_year       ON conglomerate_segments(parent_ticker, year)",
    "CREATE INDEX IF NOT EXISTS idx_watchlists_discord_id      ON watchlists(discord_id)",
    "CREATE INDEX IF NOT EXISTS idx_index_prices_date          ON index_prices(index_name, date)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_snapshots_date    ON feedback_snapshots(snapshot_date, portfolio_type)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_monthly_month     ON feedback_monthly(month, portfolio_type)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_quarterly_quarter ON feedback_quarterly(quarter, portfolio_type)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_stock_returns_ticker ON feedback_stock_returns(ticker, month, portfolio_type)",
    "CREATE INDEX IF NOT EXISTS idx_stocks_status              ON stocks(status)",
]


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
    """, (table, column)).fetchone()
    return row is not None


def init_db():
    """
    Creates all tables and indexes if they do not already exist.
    Safe to call on every startup — idempotent.
    """
    conn = get_connection()

    for ddl in _TABLES:
        conn.execute(ddl)

    for ddl in _INDEXES:
        conn.execute(ddl)

    conn.commit()

    # ── Schema migrations for existing DBs ───────────────────────
    # Column additions: check information_schema first, then ALTER.
    # SAVEPOINTs keep the whole init in one transaction.
    migrations = [
        ("stocks",     "last_scraped",            "ALTER TABLE stocks ADD COLUMN last_scraped TEXT"),
        ("stocks",     "status",                  "ALTER TABLE stocks ADD COLUMN status TEXT DEFAULT 'active'"),
        ("stocks",     "cmpy_id",                 "ALTER TABLE stocks ADD COLUMN cmpy_id TEXT"),
        ("stocks",     "fiscal_year_end_month",   "ALTER TABLE stocks ADD COLUMN fiscal_year_end_month INTEGER DEFAULT 12"),
        ("financials", "updated_at",              "ALTER TABLE financials ADD COLUMN updated_at TEXT"),
        ("financials", "depreciation",            "ALTER TABLE financials ADD COLUMN depreciation REAL"),
        ("financials", "amortization",            "ALTER TABLE financials ADD COLUMN amortization REAL"),
        ("scores",     "unified_score",           "ALTER TABLE scores ADD COLUMN unified_score REAL"),
        ("scores",     "unified_rank",            "ALTER TABLE scores ADD COLUMN unified_rank INTEGER"),
        ("members",    "tier",                    "ALTER TABLE members ADD COLUMN tier TEXT DEFAULT 'paid'"),
        ("scores_v2",  "confidence",              "ALTER TABLE scores_v2 ADD COLUMN confidence REAL DEFAULT 1.0"),
        ("scores_v2",  "portfolio_type",          "ALTER TABLE scores_v2 ADD COLUMN portfolio_type TEXT NOT NULL DEFAULT 'unified'"),
    ]
    for table, column, sql in migrations:
        if not _column_exists(conn, table, column):
            conn.execute(sql)
    conn.commit()

    # ── Data migrations ───────────────────────────────────────────
    for reit_ticker in ('VREIT', 'PREIT', 'MREIT', 'AREIT'):
        try:
            conn.execute("UPDATE stocks SET is_reit = 1 WHERE ticker = %s", (reit_ticker,))
        except Exception:
            pass

    try:
        from config import SECTOR_MANUAL_MAP, BANK_TICKERS
        for ticker, sector in SECTOR_MANUAL_MAP.items():
            conn.execute(
                "UPDATE stocks SET sector = %s WHERE ticker = %s "
                "AND (sector IS NULL OR sector = '' OR sector = 'Unknown')",
                (sector, ticker)
            )
        for ticker in BANK_TICKERS:
            conn.execute("UPDATE stocks SET is_bank = 1 WHERE ticker = %s", (ticker,))
    except Exception:
        pass

    conn.commit()
    conn.close()
    print("Database ready (PostgreSQL)")
