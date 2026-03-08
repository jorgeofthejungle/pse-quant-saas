# ============================================================
# pse_stock_builder.py — Stock Dict Builder from Database
# PSE Quant SaaS — scraper sub-module
# ============================================================
# Builds the full stock dict format expected by filters, scorer,
# and MoS engine from data stored in the SQLite database.
#
# Extracted from pse_scraper.py to keep file sizes under 500 lines.
#
# Entry points:
#   build_stock_dict_from_db(ticker) -> dict | None
#   load_stocks_from_db()            -> list[dict]
# ============================================================

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT))

import database as db
from metrics import (calculate_roe, calculate_de, calculate_dividend_yield,
                     calculate_payout_ratio, calculate_cagr, calculate_fcf,
                     calculate_fcf_yield, calculate_fcf_coverage,
                     calculate_ev_ebitda)


def build_stock_dict_from_db(ticker: str) -> dict | None:
    """
    Builds a full stock dict (format expected by filters/scorer/mos)
    by combining the latest price from `prices` table with the most
    recent annual data from the `financials` table.

    Unit notes:
      - financials table: all monetary values in MILLIONS PHP
      - prices table: close in PHP per share, market_cap in ABSOLUTE PHP
      - All ratios and per-share values returned in standard units

    Returns None if:
      - Ticker not in DB
      - Stock is marked 'suspended' or 'delisted'
      - No price data exists
      - No financial data exists
    """
    conn = db.get_connection()

    stock_row = conn.execute(
        "SELECT ticker, name, sector, is_reit, is_bank, status FROM stocks WHERE ticker = ?",
        (ticker,)
    ).fetchone()
    if not stock_row:
        conn.close()
        return None

    # Pre-filter: skip non-active stocks entirely
    stock_status = stock_row['status'] if stock_row['status'] else 'active'
    if stock_status not in ('active', None):
        conn.close()
        return None

    price_row = conn.execute("""
        SELECT close, market_cap, date AS price_date FROM prices
        WHERE ticker = ? ORDER BY date DESC LIMIT 1
    """, (ticker,)).fetchone()
    if not price_row:
        conn.close()
        return None

    fin_rows = conn.execute("""
        SELECT year, revenue, net_income, equity, total_debt, cash,
               operating_cf, capex, ebitda, eps, dps
        FROM financials
        WHERE ticker = ? ORDER BY year DESC LIMIT 10
    """, (ticker,)).fetchall()
    conn.close()

    fins = [dict(r) for r in fin_rows]
    if not fins:
        return None

    # ── Base values ───────────────────────────────────────────
    current_price = price_row['close']
    market_cap    = price_row['market_cap']   # absolute PHP
    price_date    = price_row['price_date']   # 'YYYY-MM-DD' string

    # Approximate shares outstanding from market cap / price
    shares = (market_cap / current_price) if (market_cap and current_price) else None

    # Most recent year WITH actual financial data (skip DPS-only rows).
    f0 = next(
        (f for f in fins
         if f.get('net_income') is not None or f.get('eps') is not None
            or f.get('revenue') is not None),
        fins[0]
    )

    # ── Multi-year lists ──────────────────────────────────────
    eps_3y     = [f['eps']        for f in fins if f['eps']        is not None][:3]
    eps_5y     = [f['eps']        for f in fins if f['eps']        is not None]
    net_inc_3y = [f['net_income'] for f in fins if f['net_income'] is not None][:3]
    dps_vals   = [f['dps']        for f in fins if f['dps']        is not None]
    rev_vals   = [f['revenue']    for f in fins if f['revenue']    is not None]
    revenue_5y = [f['revenue']    for f in fins if f['revenue']    is not None]
    operating_cf_history = [f['operating_cf'] for f in fins if f['operating_cf'] is not None]

    # ── Completed-year DPS ────────────────────────────────────
    current_year  = datetime.now().year
    completed_dps = [(f['year'], f['dps']) for f in fins
                     if f['dps'] is not None and f['year'] < current_year]

    dps_last = (completed_dps[0][1] if completed_dps
                else (dps_vals[0] if dps_vals else None))

    # ── P/E ───────────────────────────────────────────────────
    eps_latest = f0.get('eps')
    pe = (current_price / eps_latest) if (eps_latest and eps_latest > 0) else None

    # ── P/B ───────────────────────────────────────────────────
    equity_m = f0.get('equity')   # millions
    pb = None
    if market_cap and equity_m and equity_m > 0:
        pb = round(market_cap / (equity_m * 1_000_000), 2)

    # ── ROE ───────────────────────────────────────────────────
    roe = calculate_roe(f0.get('net_income'), equity_m)

    # ── D/E ───────────────────────────────────────────────────
    de_ratio = calculate_de(f0.get('total_debt'), equity_m)

    # ── Dividend metrics ──────────────────────────────────────
    div_yield    = calculate_dividend_yield(dps_last, current_price) if dps_last else None
    payout_ratio = calculate_payout_ratio(dps_last, eps_latest) if dps_last else None

    dividend_cagr = None
    if len(completed_dps) >= 2:
        newest_yr, newest_dps = completed_dps[0]
        oldest_yr, oldest_dps = completed_dps[-1]
        year_span = newest_yr - oldest_yr
        if year_span > 0 and oldest_dps and oldest_dps > 0:
            dividend_cagr = calculate_cagr(oldest_dps, newest_dps, year_span)
    elif len(dps_vals) >= 2:
        dividend_cagr = calculate_cagr(dps_vals[-1], dps_vals[0], len(dps_vals) - 1)

    # ── Revenue CAGR ──────────────────────────────────────────
    revenue_cagr = None
    if len(rev_vals) >= 2:
        revenue_cagr = calculate_cagr(rev_vals[-1], rev_vals[0], len(rev_vals) - 1)

    # ── FCF metrics ───────────────────────────────────────────
    fcf_m         = None
    fcf_per_share = None
    fcf_yield_val = None
    fcf_coverage  = None
    fcf_3y        = []

    cf_row = next((f for f in fins if f.get('operating_cf') is not None), None)
    op_cf  = cf_row.get('operating_cf') if cf_row else None
    capex  = cf_row.get('capex')        if cf_row else None

    if op_cf is not None and capex is not None:
        fcf_m = calculate_fcf(op_cf, capex)

    if fcf_m is not None:
        if market_cap:
            fcf_yield_val = calculate_fcf_yield(fcf_m * 1_000_000, market_cap)
        if shares:
            fcf_per_share = round(fcf_m * 1_000_000 / shares, 4)
        if dps_last and shares:
            dividends_paid_m = dps_last * shares / 1_000_000
            fcf_coverage = calculate_fcf_coverage(fcf_m, dividends_paid_m)

    for f in fins[:3]:
        if f.get('operating_cf') is not None and f.get('capex') is not None:
            fcf_3y.append(calculate_fcf(f['operating_cf'], f['capex']))

    # ── EV/EBITDA ─────────────────────────────────────────────
    ebitda     = f0.get('ebitda')
    total_debt = f0.get('total_debt')
    cash       = f0.get('cash')

    ev_ebitda = None
    if market_cap and total_debt is not None and cash is not None:
        market_cap_m = market_cap / 1_000_000
        ev_ebitda = calculate_ev_ebitda(market_cap_m, total_debt, cash, ebitda)

    # ── Return full stock dict ────────────────────────────────
    return {
        # Identity
        'ticker':           stock_row['ticker'],
        'name':             stock_row['name'],
        'sector':           stock_row['sector'],
        'is_reit':          bool(stock_row['is_reit']),
        'is_bank':          bool(stock_row['is_bank']),
        # Price
        'current_price':    current_price,
        'price_date':       price_date,         # 'YYYY-MM-DD' — used by validator staleness check
        # Dividend
        'dividend_yield':   div_yield,
        'dividend_cagr_5y': dividend_cagr,
        'payout_ratio':     payout_ratio,
        'dps_last':         dps_last,
        'dividends_5y':     dps_vals[:5],
        # Earnings
        'eps_3y':           eps_3y,
        'eps_5y':           eps_5y,
        'net_income_3y':    net_inc_3y,
        'roe':              roe,
        # Cash flow
        'operating_cf':          op_cf,
        'operating_cf_history':  operating_cf_history,
        'fcf_coverage':          fcf_coverage,
        'fcf_yield':        fcf_yield_val,
        'fcf_per_share':    fcf_per_share,
        'fcf_3y':           fcf_3y,
        # Valuation
        'pe':               pe,
        'pb':               pb,
        'ev_ebitda':        ev_ebitda,
        # Growth & leverage
        'revenue_cagr':     revenue_cagr,
        'revenue_5y':       revenue_5y,
        'de_ratio':         de_ratio,
        # Optional institutional filter fields (None if not scraped)
        'interest_coverage':    None,
        'avg_daily_value_6m':   None,
        # Validator sets True when a special/one-time dividend is detected
        'special_dividend_flag': False,
    }


def load_stocks_from_db() -> list:
    """
    Loads all active tickers from the DB and builds stock dicts.
    Skips tickers marked as 'suspended' or 'delisted'.
    Returns a list of complete stock dicts ready for the engine.
    """
    tickers = db.get_all_tickers(active_only=True)
    if not tickers:
        return []

    stocks = []
    for ticker in tickers:
        stock = build_stock_dict_from_db(ticker)
        if stock:
            stocks.append(stock)

    print(f"  Loaded {len(stocks)} active stocks from database.")
    return stocks
