# ============================================================
# pse_index.py — PSEi Index Closing Price Scraper
# PSE Quant SaaS — scraper sub-module
# ============================================================
# Scrapes PSEi closing value from PSE Edge market summary page.
# URL: https://edge.pse.com.ph/marketSummary/form.do
# All parse/network failures are non-fatal (return None).
# ============================================================

import sys
import time
import argparse
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import PSE_EDGE_BASE_URL, SCRAPE_DELAY_SECS, REQUEST_TIMEOUT
from scraper.pse_session import make_session
from db.db_connection import get_connection

MARKET_SUMMARY_URL = f'{PSE_EDGE_BASE_URL}/marketSummary/form.do'
INDEX_NAME = 'PSEi'


# ── DB helpers ────────────────────────────────────────────────

def _cache_result(date_str: str, close: float) -> None:
    """Insert or replace a PSEi close value in the index_prices table."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO index_prices
               (index_name, date, close, created_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (INDEX_NAME, date_str, close),
        )
        conn.commit()
    finally:
        conn.close()


def _load_cached(date_str: str) -> float | None:
    """Return cached PSEi close for date_str, or None if not in DB."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT close FROM index_prices WHERE index_name=? AND date=?",
            (INDEX_NAME, date_str),
        ).fetchone()
        return float(row['close']) if row else None
    finally:
        conn.close()


# ── HTML parsing ──────────────────────────────────────────────

def _parse_psei_from_html(html: str) -> float | None:
    """
    Locate the PSEi row in the market summary HTML table.
    Searches for a <tr> whose first <td> contains 'psei', 'pse index',
    or 'composite', then extracts the first numeric cell value > 1000.
    Returns None if not found or on any parse error.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  [pse_index] beautifulsoup4 not installed — cannot parse HTML")
        return None

    try:
        soup = BeautifulSoup(html, 'html.parser')
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower()
            if 'psei' in label or 'pse index' in label or 'composite' in label:
                # Scan remaining cells for a parseable number
                for cell in cells[1:]:
                    raw = cell.get_text(strip=True).replace(',', '').replace(' ', '')
                    try:
                        val = float(raw)
                        if val > 1000:   # sanity: PSEi is always >1000
                            return val
                    except ValueError:
                        continue
    except Exception as e:
        print(f"  [pse_index] HTML parse error: {e}")
    return None


# ── Core fetch ────────────────────────────────────────────────

def fetch_psei_close(date_str: str) -> float | None:
    """
    Fetch PSEi closing value for a given date (YYYY-MM-DD) from PSE Edge.
    Passes `date` as a query param; PSE Edge may or may not honour it.
    Non-fatal — returns None on any network or parse error.
    Stores successful result in the index_prices table.
    """
    session = make_session()
    params = {'date': date_str}
    try:
        resp = session.get(
            MARKET_SUMMARY_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"  [pse_index] HTTP {resp.status_code} for {date_str}")
            return None
    except Exception as e:
        print(f"  [pse_index] Request failed for {date_str}: {e}")
        return None

    close = _parse_psei_from_html(resp.text)
    if close is None:
        print(f"  [pse_index] Could not parse PSEi value for {date_str} "
              f"(page structure may have changed or date not available)")
        return None

    _cache_result(date_str, close)
    print(f"  [pse_index] {date_str} -> {close:.2f}")
    return close


# ── Cached accessor ───────────────────────────────────────────

def get_psei_close(date_str: str) -> float | None:
    """
    Return PSEi closing value for date_str.
    Checks DB cache first; falls back to fetch_psei_close().
    """
    cached = _load_cached(date_str)
    if cached is not None:
        return cached
    return fetch_psei_close(date_str)


# ── Backfill ──────────────────────────────────────────────────

def backfill_psei(start_date: str, end_date: str) -> int:
    """
    Fetch PSEi closes for every weekday between start_date and end_date
    (both inclusive, YYYY-MM-DD strings). Skips weekends.
    Returns count of dates successfully fetched.
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    fetched = 0
    current = start
    while current <= end:
        if current.weekday() < 5:   # Mon=0 … Fri=4
            d_str = current.isoformat()
            # Skip if already cached
            if _load_cached(d_str) is not None:
                print(f"  [pse_index] {d_str} already cached — skipping")
            else:
                result = fetch_psei_close(d_str)
                if result is not None:
                    fetched += 1
                time.sleep(SCRAPE_DELAY_SECS)
        current += timedelta(days=1)
    print(f"[pse_index] Backfill complete: {fetched} dates fetched.")
    return fetched


# ── CLI ───────────────────────────────────────────────────────

def _main():
    parser = argparse.ArgumentParser(
        description='PSEi index price scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  py scraper/pse_index.py --fetch 2025-01-15\n'
            '  py scraper/pse_index.py --backfill --start 2024-01-01 --end 2024-12-31\n'
        ),
    )
    parser.add_argument('--fetch', metavar='DATE',
                        help='Fetch PSEi close for a single date (YYYY-MM-DD)')
    parser.add_argument('--backfill', action='store_true',
                        help='Backfill a date range (requires --start and --end)')
    parser.add_argument('--start', metavar='DATE', help='Backfill start date (YYYY-MM-DD)')
    parser.add_argument('--end', metavar='DATE', help='Backfill end date (YYYY-MM-DD)')
    args = parser.parse_args()

    if args.fetch:
        result = get_psei_close(args.fetch)
        if result is not None:
            print(f"PSEi close on {args.fetch}: {result:.2f}")
        else:
            print(f"PSEi close on {args.fetch}: not available")
    elif args.backfill:
        if not args.start or not args.end:
            parser.error('--backfill requires --start and --end')
        count = backfill_psei(args.start, args.end)
        print(f"Backfill done: {count} dates stored.")
    else:
        parser.print_help()


if __name__ == '__main__':
    _main()
