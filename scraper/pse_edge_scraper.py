# ============================================================
# pse_edge_scraper.py — PUBLIC FACADE + Main Entry Points
# PSE Quant SaaS — Phase 3
# ============================================================
# Sub-modules:
#   pse_session.py           — make_session(), _get(), URL constants, HEADERS
#   pse_lookup.py            — lookup_cmpy_id(), lookup_company_info(),
#                              get_companies_by_sector(), get_all_companies()
#   pse_stock_data.py        — scrape_stock_data(), scrape_dividend_history(),
#                              _parse_number()
#   pse_financial_reports.py — get_annual_report_edge_nos(),
#                              scrape_financial_reports_page()
#
# Usage:
#   py scraper/pse_edge_scraper.py                  # scrape all companies
#   py scraper/pse_edge_scraper.py --ticker DMC     # one ticker only
#   py scraper/pse_edge_scraper.py --sector Financials
# ============================================================

import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

import database as db
from config import SCRAPE_DELAY_SECS, STALE_SCRAPE_SUSPEND_DAYS

try:
    from scraper.pse_session import make_session, _get, PSE_SECTORS
    from scraper.pse_lookup import (
        lookup_cmpy_id, lookup_company_info,
        get_companies_by_sector, get_all_companies,
    )
    from scraper.pse_stock_data import scrape_stock_data, scrape_dividend_history
    from scraper.pse_financial_reports import (
        get_annual_report_edge_nos, scrape_financial_reports_page,
    )
except ImportError:
    from pse_session import make_session, _get, PSE_SECTORS
    from pse_lookup import (
        lookup_cmpy_id, lookup_company_info,
        get_companies_by_sector, get_all_companies,
    )
    from pse_stock_data import scrape_stock_data, scrape_dividend_history
    from pse_financial_reports import (
        get_annual_report_edge_nos, scrape_financial_reports_page,
    )

__all__ = [
    'make_session', '_get', 'PSE_SECTORS',
    'lookup_cmpy_id', 'lookup_company_info',
    'get_companies_by_sector', 'get_all_companies',
    'scrape_stock_data', 'scrape_dividend_history',
    'get_annual_report_edge_nos', 'scrape_financial_reports_page',
    'scrape_company_full', 'scrape_one', 'scrape_all_and_save',
    'scrape_daily_prices',
]


def scrape_company_full(session, ticker: str, cmpy_id: str) -> dict | None:
    """
    Scrapes all available data for one company from PSE Edge:
    - Current price, market cap
    - Dividend history (last 5 years)
    - Annual financial data (income statement + balance sheet)
    - Calculates dividend yield, CAGR, payout indicators

    Returns a stock dict ready for db saving.
    """
    today = datetime.now().strftime('%Y-%m-%d')

    time.sleep(SCRAPE_DELAY_SECS)
    stock_data = scrape_stock_data(session, cmpy_id)
    if not stock_data:
        print(f"    {ticker}: No stock data found")
        return None

    close      = stock_data.get('close')
    market_cap = stock_data.get('market_cap')
    pe         = stock_data.get('pe')    # will be None from scrape (AJAX)
    pb         = stock_data.get('pb')    # will be None from scrape (AJAX)

    time.sleep(SCRAPE_DELAY_SECS)
    div_history = scrape_dividend_history(session, cmpy_id)

    dps_last     = div_history[0]['dps'] if div_history else None
    dividends_5y = [d['dps'] for d in div_history[:5]]

    div_yield = None
    if dps_last and close and close > 0:
        div_yield = round((dps_last / close) * 100, 4)

    dividend_cagr = None
    if len(dividends_5y) >= 2:
        newest = dividends_5y[0]
        oldest = dividends_5y[-1]
        n = len(dividends_5y) - 1
        if oldest > 0 and newest > 0 and n > 0:
            dividend_cagr = round(((newest / oldest) ** (1.0 / n) - 1) * 100, 2)

    time.sleep(SCRAPE_DELAY_SECS)
    fin_data = scrape_financial_reports_page(session, cmpy_id)

    pb_computed = None
    if fin_data and close and close > 0:
        bvps = fin_data[0].get('book_value_per_share')
        if bvps and bvps > 0:
            pb_computed = round(close / bvps, 2)

    return {
        'ticker':           ticker,
        'current_price':    close,
        'market_cap':       market_cap,
        'pe':               pe,
        'pb':               pb_computed or pb,
        'dividend_yield':   div_yield,
        'dps_last':         dps_last,
        'dividends_5y':     dividends_5y,
        'dividend_cagr_5y': dividend_cagr,
        'div_history':      div_history,
        'fin_data':         fin_data,
        '_date':            today,
        '_cmpy_id':         cmpy_id,
    }


def _save_company(company_info: dict, stock_data: dict):
    """
    Saves stock identity (stocks table) and current price (prices table).
    Also saves DPS per year and annual financials into the financials table.
    """
    ticker = company_info['ticker']

    db.upsert_stock(
        ticker       = ticker,
        name         = company_info.get('name', ''),
        sector       = company_info.get('sector', ''),
        is_reit      = company_info.get('is_reit', False),
        is_bank      = company_info.get('is_bank', False),
        last_scraped = datetime.now().isoformat(),
        status       = 'active',
        cmpy_id      = company_info.get('cmpy_id'),
    )

    if stock_data.get('current_price'):
        db.upsert_price(
            ticker     = ticker,
            date       = stock_data['_date'],
            close      = stock_data['current_price'],
            market_cap = stock_data.get('market_cap'),
        )

    # DPS sanity gate: skip any per-year DPS that implies an implausible yield.
    # This catches historical bad data being re-written and any future scraper
    # edge cases that slip past the per-declaration < 100 filter.
    current_price = stock_data.get('current_price')
    is_reit = company_info.get('is_reit', False)
    # Gate: reject only clearly impossible yields. Legitimate edge cases
    # (special dividends, high-yield penny stocks) can be up to ~35%.
    # The dividend calendar query has its own 0.5–20% filter for display.
    max_yield_pct = 35.0 if is_reit else 25.0

    for entry in stock_data.get('div_history', []):
        dps_val = entry['dps']
        if (current_price and current_price > 0
                and (dps_val / current_price * 100.0) > max_yield_pct):
            print(f"    {ticker} FY{entry['year']}: DPS={dps_val:.4f} implies "
                  f"{dps_val/current_price*100:.1f}% yield — skipping (likely bad data)")
            continue
        db.upsert_financials(
            ticker = ticker,
            year   = entry.get('fiscal_year', entry['year']),
            dps    = dps_val,
        )

    for fin in stock_data.get('fin_data', []):
        db.upsert_financials(
            ticker        = ticker,
            year          = fin['year'],
            revenue       = fin.get('revenue'),
            net_income    = fin.get('net_income'),
            equity        = fin.get('equity'),
            total_debt    = fin.get('total_debt'),
            eps           = fin.get('eps'),
            depreciation  = fin.get('depreciation'),
            amortization  = fin.get('amortization'),
        )


def scrape_one(ticker: str) -> dict | None:
    """
    Scrapes all PSE Edge data for a single ticker.
    Saves results to DB. Returns stock data dict or None.
    """
    session = make_session()

    info = lookup_company_info(session, ticker)
    if not info:
        print(f"  {ticker}: Company not found on PSE Edge")
        return None

    cmpy_id = info['cmpy_id']
    print(f"  {ticker}: cmpyId={cmpy_id}, name={info['name']}")

    stock_data = scrape_company_full(session, ticker, cmpy_id)
    if not stock_data:
        return None

    company_info = {**info, 'sector': 'Unknown', 'subsector': '',
                    'is_reit': False, 'is_bank': False}
    _save_company(company_info, stock_data)

    print(f"  {ticker}: Looking for annual reports...")
    edge_nos = get_annual_report_edge_nos(session, cmpy_id)
    if edge_nos:
        print(f"  {ticker}: Found {len(edge_nos)} annual report(s):")
        for r in edge_nos:
            print(f"    edge_no={r['edge_no']}  {r['date']}  {r['title'][:50]}")
    else:
        print(f"  {ticker}: No annual reports found via AJAX")

    return stock_data


def scrape_all_and_save(tickers: list = None, sector: str = None) -> None:
    """
    Full scrape: company directory → stock data → dividends → DB.

    Parameters:
        tickers — optional list of specific tickers to scrape
        sector  — optional PSE sector name to limit scope
    """
    session = make_session()
    today   = datetime.now().strftime('%Y-%m-%d')
    print(f"  PSE Edge scrape started: {today}")

    if tickers:
        for ticker in tickers:
            print(f"\n  Scraping {ticker}...")
            info = lookup_company_info(session, ticker)
            if not info:
                print(f"  {ticker}: Not found")
                continue
            stock_data = scrape_company_full(session, ticker, info['cmpy_id'])
            if stock_data:
                company_info = {**info, 'sector': 'Unknown',
                                'is_reit': False, 'is_bank': False}
                _save_company(company_info, stock_data)
                p = stock_data.get('current_price', 'N/A')
                y = stock_data.get('dividend_yield', 'N/A')
                print(f"    Price: PHP {p}  Yield: {y}%  PE: {stock_data.get('pe', 'N/A')}")
        return

    if sector:
        print(f"\n  Fetching {sector} directory...")
        all_companies = get_companies_by_sector(session, sector)
    else:
        all_companies = get_all_companies(session)

    print(f"\n  Found {len(all_companies)} companies total. Starting data scrape...")
    saved = 0

    for i, company_info in enumerate(all_companies, 1):
        ticker  = company_info['ticker']
        cmpy_id = company_info.get('cmpy_id')

        if not cmpy_id:
            info = lookup_company_info(session, ticker)
            if info:
                cmpy_id = info['cmpy_id']
                company_info['cmpy_id'] = cmpy_id
            else:
                print(f"  [{i}/{len(all_companies)}] {ticker}: cmpy_id not resolved, skipping")
                continue

        print(f"  [{i}/{len(all_companies)}] {ticker}...", end=' ', flush=True)
        stock_data = scrape_company_full(session, ticker, cmpy_id)

        if stock_data:
            _save_company(company_info, stock_data)
            saved += 1
            p = stock_data.get('current_price', '?')
            y = stock_data.get('dividend_yield', '')
            y_str = f"  yield={y:.1f}%" if y else ''
            print(f"PHP {p}{y_str}")
        else:
            print("no data")

    print(f"\n  Saved {saved}/{len(all_companies)} companies to database.")

    # ── New IPO detection ─────────────────────────────────────
    existing_tickers = set(db.get_all_tickers(active_only=False))
    scraped_tickers  = {c['ticker'] for c in all_companies if c.get('ticker')}
    new_tickers = scraped_tickers - existing_tickers
    if new_tickers:
        print(f"  New tickers detected on PSE Edge (possible IPOs): {', '.join(sorted(new_tickers))}")
        db.log_activity('scraper', 'new_ticker_detected',
                        f"Possible new IPOs: {', '.join(sorted(new_tickers))}", 'ok')

    # ── Suspension detection ──────────────────────────────────
    # Tickers that were in our DB (active) but were NOT in the PSE Edge
    # company directory today. If their last_scraped is > STALE_SCRAPE_SUSPEND_DAYS
    # old, we mark them as 'suspended'. They auto-reactivate on next successful scrape.
    from datetime import timedelta
    cutoff_dt = datetime.now() - timedelta(days=STALE_SCRAPE_SUSPEND_DAYS)
    cutoff    = cutoff_dt.isoformat()

    conn = db.get_connection()
    stale_rows = conn.execute("""
        SELECT ticker, last_scraped FROM stocks
        WHERE status = 'active'
          AND ticker NOT IN ({})
          AND (last_scraped IS NULL OR last_scraped < ?)
    """.format(','.join('?' * len(scraped_tickers))),
        (*scraped_tickers, cutoff)
    ).fetchall()
    conn.close()

    if stale_rows:
        for row in stale_rows:
            t = row['ticker']
            db.mark_stock_status(t, 'suspended')
            print(f"  SUSPENDED: {t} not found on PSE Edge for {STALE_SCRAPE_SUSPEND_DAYS}+ days")
        db.log_activity('scraper', 'tickers_suspended',
                        f"Suspended: {', '.join(r['ticker'] for r in stale_rows)}", 'warn')


def scrape_daily_prices(tickers: list = None) -> list:
    """
    Fetches today's closing prices from PSE Edge for all active tickers
    (or a specified subset). Saves results to the prices DB table.

    Uses stored cmpy_id from the stocks table for speed. Falls back to
    autocomplete lookup for any ticker not yet in the DB.

    Skips tickers that already have a price record for today.

    Returns list of {'ticker', 'close', 'market_cap', 'date'} dicts saved.
    """
    from datetime import datetime as _dt
    today   = _dt.now().strftime('%Y-%m-%d')
    session = make_session()

    # Get all stored cmpy_ids from DB
    stored_ids = db.get_all_cmpy_ids()

    # Determine which tickers to update
    if tickers:
        target = tickers
    else:
        target = db.get_all_tickers(active_only=True)

    # Skip tickers that already have today's price
    conn = db.get_connection()
    already_today = {
        r['ticker'] for r in conn.execute(
            "SELECT ticker FROM prices WHERE date = ?", (today,)
        ).fetchall()
    }
    conn.close()

    to_fetch = [t for t in target if t not in already_today]
    if not to_fetch:
        print(f"  All {len(target)} tickers already have prices for {today}.")
        return []

    print(f"  Fetching prices from PSE Edge for {len(to_fetch)} tickers...")
    saved = []

    for ticker in to_fetch:
        cmpy_id = stored_ids.get(ticker)

        if not cmpy_id:
            # First-time lookup — resolve and persist
            info = lookup_company_info(session, ticker)
            if not info:
                print(f"    {ticker}: cmpy_id not found, skipping")
                time.sleep(SCRAPE_DELAY_SECS)
                continue
            cmpy_id = info['cmpy_id']
            # Persist so we don't need to look it up again
            conn2 = db.get_connection()
            conn2.execute(
                "UPDATE stocks SET cmpy_id = ? WHERE ticker = ?",
                (cmpy_id, ticker)
            )
            conn2.commit()
            conn2.close()
            stored_ids[ticker] = cmpy_id
            time.sleep(SCRAPE_DELAY_SECS)

        data = scrape_stock_data(session, cmpy_id)
        if not data or not data.get('close'):
            print(f"    {ticker}: no price data")
            time.sleep(SCRAPE_DELAY_SECS)
            continue

        db.upsert_price(
            ticker     = ticker,
            date       = today,
            close      = data['close'],
            market_cap = data.get('market_cap'),
        )
        saved.append({
            'ticker':     ticker,
            'close':      data['close'],
            'market_cap': data.get('market_cap'),
            'date':       today,
        })
        print(f"    {ticker}: PHP {data['close']:.2f}")
        time.sleep(SCRAPE_DELAY_SECS)

    print(f"  Saved {len(saved)}/{len(to_fetch)} prices to database.")
    return saved


# ── CLI entry point ───────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='PSE Edge Fundamental Data Scraper'
    )
    parser.add_argument('--ticker', help='Scrape a single ticker (e.g. DMC)')
    parser.add_argument('--sector', choices=PSE_SECTORS,
                        help='Scrape one PSE sector only')
    args = parser.parse_args()

    print("=" * 55)
    print("  PSE Quant SaaS - PSE Edge Scraper")
    print("=" * 55)

    db.init_db()

    if args.ticker:
        print(f"\nScraping {args.ticker.upper()}...")
        result = scrape_one(args.ticker.upper())
        if result:
            print(f"\nResults for {args.ticker.upper()}:")
            print(f"  Price:      PHP {result.get('current_price', 'N/A')}")
            mc = result.get('market_cap')
            print(f"  Market Cap: PHP {mc:,.0f}" if mc else "  Market Cap: N/A")
            print(f"  P/E:        {result.get('pe', 'N/A')}")
            print(f"  P/B:        {result.get('pb', 'N/A')}")
            print(f"  Div Yield:  {result.get('dividend_yield', 'N/A')}%")
            print(f"  DPS Last:   PHP {result.get('dps_last', 'N/A')}")
            print(f"  Div CAGR:   {result.get('dividend_cagr_5y', 'N/A')}%")
            hist = result.get('div_history', [])
            if hist:
                print(f"  Div History ({len(hist)} years):")
                for h in hist:
                    print(f"    {h['year']}: PHP {h['dps']:.4f}/share")
            fin = result.get('fin_data', [])
            if fin:
                print(f"  Financials ({len(fin)} year(s) from PSE Edge):")
                for f in fin:
                    print(f"    {f['year']}: Rev={f.get('revenue')}M  "
                          f"NI={f.get('net_income')}M  "
                          f"EPS=PHP {f.get('eps')}  "
                          f"Equity={f.get('equity')}M")
            else:
                print("  Financials: not found on page")
    else:
        scrape_all_and_save(sector=args.sector)

    print("\n" + "=" * 55)
