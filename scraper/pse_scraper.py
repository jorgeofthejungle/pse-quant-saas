# ============================================================
# pse_scraper.py — PSE Edge / PSE Website Price Scraper
# PSE Quant SaaS — Phase 3
# ============================================================
# Scrapes the latest closing prices from the PSE website.
# Runs daily at end of trading (~4:00 PM PHT) via scheduler.py.
#
# SCOPE — what changes DAILY:
#   current_price, market_cap (affect yield, P/E, P/B, MoS)
#
# SCOPE — what changes ANNUALLY (Phase 3b, not here):
#   EPS, net income, dividends, revenue (from annual reports)
#
# NOTE: The HTML selectors below are based on the PSE website
# structure at time of writing. If the site layout changes,
# update the selectors in _parse_price_table().
#
# Data source: https://www.pse.com.ph
# PSE trading hours: 9:30 AM – 3:30 PM PHT, Mon–Fri
# ============================================================

import sys
import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT))

import database as db
from config import SCRAPE_DELAY_SECS, REQUEST_TIMEOUT, MAX_RETRIES
from metrics import (calculate_roe, calculate_de, calculate_dividend_yield,
                     calculate_payout_ratio, calculate_cagr, calculate_fcf,
                     calculate_fcf_yield, calculate_fcf_coverage,
                     calculate_ev_ebitda)

# ── Constants ─────────────────────────────────────────────────
PSE_MARKET_URL  = 'https://www.pse.com.ph/stockMarket/home.do'
PSE_QUOTE_URL   = 'https://www.pse.com.ph/stockMarket/companyInfo.do'

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
}


# ── HTTP helpers ─────────────────────────────────────────────

def _get(url: str, params: dict = None, retries: int = MAX_RETRIES) -> requests.Response | None:
    """
    Makes a GET request with retry logic.
    Returns the Response on success, None on failure.
    """
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp
            print(f"  HTTP {resp.status_code} from {url} (attempt {attempt}/{retries})")
        except requests.RequestException as e:
            print(f"  Request error: {e} (attempt {attempt}/{retries})")
        if attempt < retries:
            time.sleep(SCRAPE_DELAY_SECS)
    return None


# ── Parsing ──────────────────────────────────────────────────

def _parse_price_table(html: str) -> list:
    """
    Parses the PSE stock market summary page and extracts
    ticker → close price pairs.

    Returns list of dicts:
        [{'ticker': 'DMC', 'close': 11.50, 'market_cap': None}, ...]

    NOTE: The PSE website uses a table with class 'table_price' or similar.
    If parsing fails (site structure changed), returns empty list.
    This function must be verified against the live PSE website.
    """
    results = []
    try:
        soup = BeautifulSoup(html, 'lxml')

        # PSE main market table (adjust selector if site changes)
        # The table typically has columns: Symbol, Company, Price, Change, %Change, Volume
        table = soup.find('table', {'class': 'table_price'})
        if not table:
            # Try alternate selector — PSE site has changed layout before
            table = soup.find('table', id='stockTable')
        if not table:
            # Last resort: find any table with a 'Symbol' header
            for t in soup.find_all('table'):
                headers = [th.get_text(strip=True).lower() for th in t.find_all('th')]
                if 'symbol' in headers or 'ticker' in headers:
                    table = t
                    break

        if not table:
            print("  WARNING: Could not find stock price table in PSE page.")
            print("  The site structure may have changed — update _parse_price_table().")
            return []

        rows = table.find_all('tr')[1:]   # skip header row
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            ticker = cells[0].get_text(strip=True).upper()
            price_text = cells[2].get_text(strip=True).replace(',', '')
            try:
                close = float(price_text)
                results.append({
                    'ticker':     ticker,
                    'close':      close,
                    'market_cap': None,   # market cap requires additional data
                })
            except ValueError:
                continue   # skip rows with non-numeric prices

    except Exception as e:
        print(f"  Parse error: {e}")

    return results


def _parse_single_quote(html: str, ticker: str) -> dict | None:
    """
    Parses an individual stock quote page from PSE.
    Returns {'ticker', 'close', 'market_cap'} or None.
    """
    try:
        soup = BeautifulSoup(html, 'lxml')

        # PSE quote pages vary — look for the closing price in common patterns
        # Adjust these selectors based on the actual page structure
        price_elem = (
            soup.find(class_='lastPrice') or
            soup.find(id='lastPrice') or
            soup.find('span', {'data-field': 'LAST_PRICE'})
        )
        if not price_elem:
            return None

        close = float(price_elem.get_text(strip=True).replace(',', ''))

        # Market cap (optional — not all pages show this directly)
        mc_elem = soup.find(class_='marketCap') or soup.find(id='marketCap')
        market_cap = None
        if mc_elem:
            try:
                market_cap = float(mc_elem.get_text(strip=True).replace(',', ''))
            except ValueError:
                pass

        return {'ticker': ticker, 'close': close, 'market_cap': market_cap}

    except Exception as e:
        print(f"  Parse error for {ticker}: {e}")
        return None


# ── Main scrape functions ────────────────────────────────────

def scrape_prices(tickers: list = None) -> list:
    """
    Scrapes the latest closing prices from the PSE website.

    Parameters:
        tickers — optional list of specific tickers to scrape.
                  If None, scrapes the full PSE market summary page.

    Returns list of dicts:
        [{'ticker': 'DMC', 'close': 11.50, 'market_cap': None, 'date': '2026-02-28'}, ...]

    Returns empty list on failure — graceful, does not crash scheduler.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    results = []

    print(f"  Scraping PSE prices for {today}...")

    if tickers:
        # Scrape individual quote pages for specific tickers
        for ticker in tickers:
            resp = _get(PSE_QUOTE_URL, params={'method': 'get', 'security': ticker})
            if resp:
                data = _parse_single_quote(resp.text, ticker)
                if data:
                    data['date'] = today
                    results.append(data)
                    print(f"    {ticker}: P{data['close']:.2f}")
            time.sleep(SCRAPE_DELAY_SECS)
    else:
        # Scrape the full market summary page
        resp = _get(PSE_MARKET_URL)
        if resp:
            results = _parse_price_table(resp.text)
            for r in results:
                r['date'] = today
            print(f"  Scraped {len(results)} prices from market summary.")
        else:
            print("  FAILED to reach PSE website. Prices not updated.")

    return results


def scrape_and_save(tickers: list = None) -> list:
    """
    Scrapes prices and saves them to the prices table in the DB.
    Returns the list of price dicts that were saved.
    """
    prices = scrape_prices(tickers)
    if not prices:
        print("  No price data retrieved — skipping DB update.")
        return []

    saved = 0
    for p in prices:
        try:
            db.upsert_price(
                ticker     = p['ticker'],
                date       = p['date'],
                close      = p['close'],
                market_cap = p.get('market_cap'),
            )
            saved += 1
        except Exception as e:
            print(f"  DB error for {p['ticker']}: {e}")

    print(f"  Saved {saved}/{len(prices)} prices to database.")
    return prices


# ── Stock dict builder ───────────────────────────────────────

def build_stock_dict_from_db(ticker: str) -> dict | None:
    """
    Builds a full stock dict (format expected by filters/scorer/mos)
    by combining the latest price from `prices` table with the most
    recent annual data from the `financials` table.

    Unit notes:
      - financials table: all monetary values in MILLIONS PHP
      - prices table: close in PHP per share, market_cap in ABSOLUTE PHP
      - All ratios and per-share values returned in standard units

    Returns None if insufficient data exists in DB for this ticker.
    """
    # ── Fetch from DB ─────────────────────────────────────────
    conn = db.get_connection()

    stock_row = conn.execute(
        "SELECT ticker, name, sector, is_reit, is_bank FROM stocks WHERE ticker = ?",
        (ticker,)
    ).fetchone()
    if not stock_row:
        conn.close()
        return None

    price_row = conn.execute("""
        SELECT close, market_cap FROM prices
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

    # Approximate shares outstanding from market cap / price
    shares = (market_cap / current_price) if (market_cap and current_price) else None

    # Most recent year WITH actual financial data (skip DPS-only rows).
    # The dividend scraper saves DPS entries for the current year before
    # annual financials are filed, so fins[0] may have dps but no eps/revenue.
    f0 = next(
        (f for f in fins
         if f.get('net_income') is not None or f.get('eps') is not None
            or f.get('revenue') is not None),
        fins[0]
    )

    # ── Multi-year lists ──────────────────────────────────────
    # Build from all available rows (not just first N), so DPS-only rows
    # don't take up slots in the financial history lists.
    eps_3y     = [f['eps']        for f in fins if f['eps']        is not None][:3]
    eps_5y     = [f['eps']        for f in fins if f['eps']        is not None]
    net_inc_3y = [f['net_income'] for f in fins if f['net_income'] is not None][:3]
    dps_vals   = [f['dps']        for f in fins if f['dps']        is not None]
    rev_vals   = [f['revenue']    for f in fins if f['revenue']    is not None]
    revenue_5y = [f['revenue']    for f in fins if f['revenue']    is not None]

    # ── Completed-year DPS ────────────────────────────────────
    # The dividend scraper runs in the current calendar year and stores
    # partial-year DPS (e.g. only Q1 declarations as of March 2026).
    # Using partial 2026 DPS for yield/CAGR severely understates the
    # annual income. Instead, prefer the most recent COMPLETED year.
    current_year = datetime.now().year
    completed_dps = [(f['year'], f['dps']) for f in fins
                     if f['dps'] is not None and f['year'] < current_year]

    # dps_last for yield/payout: most recent completed year, fall back to partial
    dps_last = (completed_dps[0][1] if completed_dps
                else (dps_vals[0] if dps_vals else None))

    # ── P/E ───────────────────────────────────────────────────
    eps_latest = f0.get('eps')
    pe = (current_price / eps_latest) if (eps_latest and eps_latest > 0) else None

    # ── P/B ───────────────────────────────────────────────────
    # equity is in millions PHP; convert to absolute for ratio
    equity_m = f0.get('equity')   # millions
    pb = None
    if market_cap and equity_m and equity_m > 0:
        pb = round(market_cap / (equity_m * 1_000_000), 2)

    # ── ROE ───────────────────────────────────────────────────
    # calculate_roe expects same-unit numerator/denominator (both millions here)
    roe = calculate_roe(f0.get('net_income'), equity_m)

    # ── D/E ───────────────────────────────────────────────────
    de_ratio = calculate_de(f0.get('total_debt'), equity_m)

    # ── Dividend metrics ──────────────────────────────────────
    div_yield    = calculate_dividend_yield(dps_last, current_price) if dps_last else None
    payout_ratio = calculate_payout_ratio(dps_last, eps_latest) if dps_last else None

    # Dividend CAGR: use completed years with actual year span for accuracy.
    # Partial current-year DPS would make CAGR look negative for growing payers.
    dividend_cagr = None
    if len(completed_dps) >= 2:
        newest_yr, newest_dps = completed_dps[0]
        oldest_yr, oldest_dps = completed_dps[-1]
        year_span = newest_yr - oldest_yr
        if year_span > 0 and oldest_dps and oldest_dps > 0:
            dividend_cagr = calculate_cagr(oldest_dps, newest_dps, year_span)
    elif len(dps_vals) >= 2:
        # Fallback when we only have current-year partial data
        dividend_cagr = calculate_cagr(dps_vals[-1], dps_vals[0], len(dps_vals) - 1)

    # ── Revenue CAGR ──────────────────────────────────────────
    revenue_cagr = None
    if len(rev_vals) >= 2:
        revenue_cagr = calculate_cagr(rev_vals[-1], rev_vals[0], len(rev_vals) - 1)

    # ── FCF metrics ───────────────────────────────────────────
    # FCF in millions PHP (same units as operating_cf and capex)
    fcf_m         = None
    fcf_per_share = None
    fcf_yield_val = None
    fcf_coverage  = None
    fcf_3y        = []

    # Use most recent year that has operating_cf data
    # (PDF parser fills historical years; HTML scraper only fills income/balance sheet)
    cf_row = next((f for f in fins if f.get('operating_cf') is not None), None)
    op_cf  = cf_row.get('operating_cf') if cf_row else None
    capex  = cf_row.get('capex')        if cf_row else None

    if op_cf is not None and capex is not None:
        fcf_m = calculate_fcf(op_cf, capex)   # millions PHP

    if fcf_m is not None:
        # FCF yield: convert FCF to absolute PHP for ratio vs market_cap
        if market_cap:
            fcf_yield_val = calculate_fcf_yield(fcf_m * 1_000_000, market_cap)

        # FCF per share: convert FCF to absolute PHP, divide by shares
        if shares:
            fcf_per_share = round(fcf_m * 1_000_000 / shares, 4)

        # FCF coverage: how many times FCF covers total dividends paid
        # dividends_paid in millions = dps * shares / 1_000_000
        if dps_last and shares:
            dividends_paid_m = dps_last * shares / 1_000_000
            fcf_coverage = calculate_fcf_coverage(fcf_m, dividends_paid_m)

    # FCF history (millions PHP) for last 3 years
    for f in fins[:3]:
        if f.get('operating_cf') is not None and f.get('capex') is not None:
            fcf_3y.append(calculate_fcf(f['operating_cf'], f['capex']))

    # ── EV/EBITDA ─────────────────────────────────────────────
    # convert market_cap to millions to match financials table units
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
        'operating_cf':     op_cf,
        'fcf_coverage':     fcf_coverage,
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
        'interest_coverage':    None,   # EBIT/Interest — not in DB yet
        'avg_daily_value_6m':   None,   # liquidity filter — not in DB yet
        # Validator sets True when a special/one-time dividend is detected
        'special_dividend_flag': False,
    }


def load_stocks_from_db() -> list:
    """
    Loads all tickers from the DB and builds stock dicts.
    Returns a list of complete stock dicts ready for the engine.
    Returns empty list if DB has no data yet.
    """
    tickers = db.get_all_tickers()
    if not tickers:
        return []

    stocks = []
    for ticker in tickers:
        stock = build_stock_dict_from_db(ticker)
        if stock:
            stocks.append(stock)

    print(f"  Loaded {len(stocks)} stocks from database.")
    return stocks


# ── Self-test ────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 55)
    print("  PSE Quant SaaS — Price Scraper Test")
    print("=" * 55)

    db.init_db()

    print("\nScraping prices from PSE website...")
    prices = scrape_and_save()

    if prices:
        print(f"\nSample results:")
        for p in prices[:5]:
            print(f"  {p['ticker']:8}  P{p['close']:.2f}")
    else:
        print("\nNo prices scraped.")
        print("This is expected if:")
        print("  1. PSE market is closed (after 3:30 PM or weekend)")
        print("  2. The HTML selectors need updating for the current PSE site layout")
        print("  3. Network access is restricted in this environment")
        print("\nRun this script from your terminal during PSE trading hours")
        print("and check the output to verify the selectors work.")

    print()
    print("=" * 55)
