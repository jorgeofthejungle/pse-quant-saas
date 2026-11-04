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
# Imported from pse_stock_builder to keep this file under 500 lines.

try:
    from scraper.pse_stock_builder import build_stock_dict_from_db, load_stocks_from_db
except ImportError:
    from pse_stock_builder import build_stock_dict_from_db, load_stocks_from_db




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
