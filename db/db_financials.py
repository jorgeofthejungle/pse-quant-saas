# ============================================================
# db_financials.py — Financial Data & Stock Identity Operations
# PSE Quant SaaS
# ============================================================

from datetime import datetime
from db.db_connection import get_connection


def upsert_financials(ticker: str, year: int,
                      revenue: float = None, net_income: float = None,
                      equity: float = None, total_debt: float = None,
                      cash: float = None, operating_cf: float = None,
                      capex: float = None, ebitda: float = None,
                      eps: float = None, dps: float = None,
                      force: bool = False):
    """
    Inserts or updates one year of financial data for a ticker.
    Monetary values in millions PHP; eps and dps are per-share in PHP.

    force=False (default): COALESCE — only fills in missing values.
                           Partial updates from different sources are merged.
    force=True:  Full overwrite — replaces ALL fields with the new values.
                 Use when re-fetching corrected or restated filings.

    Always sets updated_at to the current timestamp on any upsert.
    """
    now = datetime.now().isoformat()
    conn = get_connection()

    if force:
        conn.execute("""
            INSERT INTO financials
                (ticker, year, revenue, net_income, equity, total_debt,
                 cash, operating_cf, capex, ebitda, eps, dps, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, year) DO UPDATE SET
                revenue      = excluded.revenue,
                net_income   = excluded.net_income,
                equity       = excluded.equity,
                total_debt   = excluded.total_debt,
                cash         = excluded.cash,
                operating_cf = excluded.operating_cf,
                capex        = excluded.capex,
                ebitda       = excluded.ebitda,
                eps          = excluded.eps,
                dps          = excluded.dps,
                updated_at   = excluded.updated_at
        """, (ticker, year, revenue, net_income, equity, total_debt,
              cash, operating_cf, capex, ebitda, eps, dps, now))
    else:
        conn.execute("""
            INSERT INTO financials
                (ticker, year, revenue, net_income, equity, total_debt,
                 cash, operating_cf, capex, ebitda, eps, dps, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                dps          = COALESCE(excluded.dps,          dps),
                updated_at   = excluded.updated_at
        """, (ticker, year, revenue, net_income, equity, total_debt,
              cash, operating_cf, capex, ebitda, eps, dps, now))

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


def get_all_cmpy_ids() -> dict:
    """
    Returns {ticker: cmpy_id} for all active stocks that have a stored cmpy_id.
    Used by the daily price scraper to avoid per-ticker autocomplete lookups.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, cmpy_id FROM stocks WHERE cmpy_id IS NOT NULL AND status = 'active'"
    ).fetchall()
    conn.close()
    return {r['ticker']: r['cmpy_id'] for r in rows}


def upsert_stock(ticker: str, name: str, sector: str,
                 is_reit: bool = False, is_bank: bool = False,
                 last_scraped: str = None, status: str = None,
                 cmpy_id: str = None):
    """
    Inserts or updates a stock's identity record.

    last_scraped — ISO timestamp of the last successful PSE Edge scrape.
                   Pass datetime.now().isoformat() after a successful scrape.
    status       — 'active' | 'suspended' | 'delisted'.
                   Pass explicitly to override; omit to keep existing value.
    """
    now = datetime.now().strftime('%Y-%m-%d')
    conn = get_connection()

    # Build SET clause dynamically so we only overwrite status/last_scraped
    # when explicitly provided (None means "leave unchanged").
    extra_set = ""
    params = [name, sector, int(is_reit), int(is_bank), now]

    if last_scraped is not None:
        params_insert = [ticker, name, sector, int(is_reit), int(is_bank),
                         now, last_scraped, status or 'active', cmpy_id]
        conn.execute("""
            INSERT INTO stocks
                (ticker, name, sector, is_reit, is_bank, last_updated,
                 last_scraped, status, cmpy_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name         = excluded.name,
                sector       = excluded.sector,
                is_reit      = excluded.is_reit,
                is_bank      = excluded.is_bank,
                last_updated = excluded.last_updated,
                last_scraped = excluded.last_scraped,
                cmpy_id      = COALESCE(excluded.cmpy_id, cmpy_id)
        """, params_insert)
    else:
        conn.execute("""
            INSERT INTO stocks
                (ticker, name, sector, is_reit, is_bank, last_updated, status, cmpy_id)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name         = excluded.name,
                sector       = excluded.sector,
                is_reit      = excluded.is_reit,
                is_bank      = excluded.is_bank,
                last_updated = excluded.last_updated,
                cmpy_id      = COALESCE(excluded.cmpy_id, cmpy_id)
        """, (ticker, name, sector, int(is_reit), int(is_bank), now, cmpy_id))

    if status is not None:
        conn.execute(
            "UPDATE stocks SET status = ? WHERE ticker = ?",
            (status, ticker)
        )

    conn.commit()
    conn.close()


def mark_stock_status(ticker: str, status: str):
    """
    Updates the status of a stock: 'active', 'suspended', or 'delisted'.
    Used by the scraper to flag tickers missing from PSE Edge.
    """
    conn = get_connection()
    conn.execute("UPDATE stocks SET status = ? WHERE ticker = ?", (status, ticker))
    conn.commit()
    conn.close()


def get_all_tickers(active_only: bool = True) -> list:
    """
    Returns list of all ticker strings in the stocks table.
    active_only=True (default): only returns tickers with status='active'.
    active_only=False: returns all tickers including suspended/delisted.
    """
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            "SELECT ticker FROM stocks WHERE status = 'active' OR status IS NULL ORDER BY ticker"
        ).fetchall()
    else:
        rows = conn.execute("SELECT ticker FROM stocks ORDER BY ticker").fetchall()
    conn.close()
    return [r['ticker'] for r in rows]


def get_stale_financials_tickers(days: int = 90) -> list:
    """
    Returns tickers whose financial data has not been updated in the last
    `days` days.  Used by the weekly scrape to trigger forced re-fetches.
    Returns tickers where updated_at IS NULL (never stamped) or is old.
    """
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT ticker FROM financials
        WHERE updated_at IS NULL OR updated_at < ?
        ORDER BY ticker
    """, (cutoff,)).fetchall()
    conn.close()
    return [r['ticker'] for r in rows]
