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

        -- ── Unified scores (v2 — clean schema) ─────────────────
        -- One row per (ticker, run_date). Stores score, rank,
        -- grade category, and full breakdown as JSON.
        CREATE TABLE IF NOT EXISTS scores_v2 (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker         TEXT NOT NULL,
            run_date       TEXT NOT NULL,
            score          REAL,
            rank           INTEGER,
            category       TEXT,
            breakdown_json TEXT,
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

        -- ── Conglomerate segment financials ──────────────────
        -- Manual data entry for Top 5 PH holding firms.
        -- Used by conglomerate_scorer.py for segment-level scoring.
        CREATE TABLE IF NOT EXISTS conglomerate_segments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        -- ── Member stock watchlists ──────────────────────────
        CREATE TABLE IF NOT EXISTS watchlists (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id TEXT NOT NULL,
            ticker     TEXT NOT NULL,
            added_at   TEXT NOT NULL,
            UNIQUE(discord_id, ticker),
            FOREIGN KEY (ticker) REFERENCES stocks(ticker)
        );

        -- ── Indexes for common query patterns ────────────────
        CREATE INDEX IF NOT EXISTS idx_prices_ticker_date
            ON prices(ticker, date);
        CREATE INDEX IF NOT EXISTS idx_scores_run_date
            ON scores(run_date);
        CREATE INDEX IF NOT EXISTS idx_scores_v2_run_date
            ON scores_v2(run_date);
        CREATE INDEX IF NOT EXISTS idx_scores_v2_ticker
            ON scores_v2(ticker);
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
        CREATE INDEX IF NOT EXISTS idx_segments_parent_year
            ON conglomerate_segments(parent_ticker, year);
        CREATE INDEX IF NOT EXISTS idx_watchlists_discord_id
            ON watchlists(discord_id);

        -- ── PSEi / benchmark index daily prices ──────────────
        CREATE TABLE IF NOT EXISTS index_prices (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            index_name TEXT NOT NULL,
            date       DATE NOT NULL,
            close      REAL,
            created_at TEXT,
            UNIQUE(index_name, date)
        );

        -- ── Feedback Loop: point-in-time stock snapshots ─────
        CREATE TABLE IF NOT EXISTS feedback_snapshots (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        -- ── Feedback Loop: monthly per-stock return outcomes ─
        CREATE TABLE IF NOT EXISTS feedback_stock_returns (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        -- ── Feedback Loop: monthly aggregate metrics ─────────
        CREATE TABLE IF NOT EXISTS feedback_monthly (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        -- ── Feedback Loop: quarterly rolled-up analysis ───────
        CREATE TABLE IF NOT EXISTS feedback_quarterly (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        -- ── Feedback Loop: per-metric diagnostic detail ───────
        CREATE TABLE IF NOT EXISTS feedback_diagnostic_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        -- ── Feedback Loop: publishable track-record summary ──
        CREATE TABLE IF NOT EXISTS feedback_track_record (
            id                                     INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        -- ── Feedback Loop indexes ─────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_index_prices_date
            ON index_prices(index_name, date);
        CREATE INDEX IF NOT EXISTS idx_feedback_snapshots_date
            ON feedback_snapshots(snapshot_date, portfolio_type);
        CREATE INDEX IF NOT EXISTS idx_feedback_monthly_month
            ON feedback_monthly(month, portfolio_type);
        CREATE INDEX IF NOT EXISTS idx_feedback_quarterly_quarter
            ON feedback_quarterly(quarter, portfolio_type);
        CREATE INDEX IF NOT EXISTS idx_feedback_stock_returns_ticker
            ON feedback_stock_returns(ticker, month, portfolio_type);
    """)
    conn.commit()

    # ── Schema migrations for existing DBs ───────────────────
    # SQLite does not support IF NOT EXISTS on ALTER TABLE.
    # We catch the OperationalError that fires when the column already exists.
    migrations = [
        "ALTER TABLE stocks     ADD COLUMN last_scraped TEXT",
        "ALTER TABLE stocks     ADD COLUMN status       TEXT DEFAULT 'active'",
        "ALTER TABLE stocks     ADD COLUMN cmpy_id      TEXT",
        "ALTER TABLE financials ADD COLUMN updated_at   TEXT",
        # Deprecated: v2 unified scorer columns (legacy migration, superseded by scores_v2 table)
        "ALTER TABLE scores ADD COLUMN unified_score REAL",
        "ALTER TABLE scores ADD COLUMN unified_rank  INTEGER",
        # Stage 4.3: subscription tier for access control ('free' or 'paid')
        "ALTER TABLE members ADD COLUMN tier TEXT DEFAULT 'paid'",
        # Phase 11: fiscal year end month for dividend attribution
        "ALTER TABLE stocks ADD COLUMN fiscal_year_end_month INTEGER DEFAULT 12",
        # Phase 11: depreciation and amortization for REIT FFO calculation
        "ALTER TABLE financials ADD COLUMN depreciation REAL",
        "ALTER TABLE financials ADD COLUMN amortization  REAL",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass   # column already exists — safe to ignore
    conn.commit()

    # Migration: add confidence column to scores_v2
    cur = conn.cursor()
    cols_v2 = [row[1] for row in cur.execute("PRAGMA table_info(scores_v2)").fetchall()]
    if 'confidence' not in cols_v2:
        cur.execute("ALTER TABLE scores_v2 ADD COLUMN confidence REAL DEFAULT 1.0")
    conn.commit()

    # Migration: add portfolio_type column + fix UNIQUE constraint
    # SQLite cannot modify UNIQUE constraints, so we recreate the table.
    cols_v2 = [row[1] for row in cur.execute("PRAGMA table_info(scores_v2)").fetchall()]
    if 'portfolio_type' not in cols_v2:
        cur.execute("ALTER TABLE scores_v2 RENAME TO scores_v2_old")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scores_v2 (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker         TEXT NOT NULL,
                run_date       TEXT NOT NULL,
                portfolio_type TEXT NOT NULL DEFAULT 'unified',
                score          REAL,
                confidence     REAL DEFAULT 1.0,
                rank           INTEGER,
                category       TEXT,
                breakdown_json TEXT,
                UNIQUE(ticker, run_date, portfolio_type)
            )
        """)
        cur.execute("""
            INSERT INTO scores_v2
                (ticker, run_date, portfolio_type, score,
                 confidence, rank, category, breakdown_json)
            SELECT ticker, run_date, 'unified', score,
                   COALESCE(confidence, 1.0), rank, category, breakdown_json
            FROM scores_v2_old
        """)
        cur.execute("DROP TABLE scores_v2_old")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_scores_v2_run_date ON scores_v2(run_date)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_scores_v2_ticker ON scores_v2(ticker)"
        )
        conn.commit()

    # Migration: fix REIT misclassification
    for reit_ticker in ('VREIT', 'PREIT', 'MREIT', 'AREIT'):
        try:
            cur = conn.cursor()
            cur.execute("UPDATE stocks SET is_reit = 1 WHERE ticker = ?", (reit_ticker,))
        except Exception:
            pass
    conn.commit()

    # Migration: fix sector and bank flags for stocks scraped as "Unknown"
    try:
        from config import SECTOR_MANUAL_MAP, BANK_TICKERS
        cur = conn.cursor()
        for ticker, sector in SECTOR_MANUAL_MAP.items():
            cur.execute(
                "UPDATE stocks SET sector = ? WHERE ticker = ? AND (sector IS NULL OR sector = '' OR sector = 'Unknown')",
                (sector, ticker)
            )
        for ticker in BANK_TICKERS:
            cur.execute("UPDATE stocks SET is_bank = 1 WHERE ticker = ?", (ticker,))
        conn.commit()
    except Exception:
        pass

    # Add the status index only after the column migration has run
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stocks_status ON stocks(status)")
        conn.commit()
    except Exception:
        pass
    conn.close()
    print(f"Database ready: {DB_PATH}")
