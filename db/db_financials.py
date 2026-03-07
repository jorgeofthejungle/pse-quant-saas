# ============================================================
# db_financials.py — Financial Data & Stock Identity Operations
# PSE Quant SaaS
# ============================================================

from db.db_connection import get_connection


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
