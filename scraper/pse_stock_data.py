# ============================================================
# pse_stock_data.py — Stock Data & Dividend History Scraping
# PSE Quant SaaS — scraper sub-module
# ============================================================

import re
import time
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import SCRAPE_DELAY_SECS, PSE_EDGE_BASE_URL

try:
    from scraper.pse_session import _get, STOCK_DATA_URL, DIVIDENDS_LIST_URL
except ImportError:
    from pse_session import _get, STOCK_DATA_URL, DIVIDENDS_LIST_URL


def _parse_number(text: str) -> float | None:
    """Parses a formatted number string like '130,650,304,800.00' → float."""
    if not text:
        return None
    cleaned = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        return float(cleaned)
    except ValueError:
        return None


def scrape_stock_data(session, cmpy_id: str) -> dict | None:
    """
    Scrapes the stockData.do page for a company.
    This page is SERVER-RENDERED — no JS needed, no session required.

    PSE Edge HTML structure (confirmed live):
        <tr>
          <th>Last Traded Price</th>
          <td>9.65</td>
          <th>Open</th>
          <td>9.84</td>
        </tr>
    Each <th> is a label; the immediately-following <td> is the value.

    Returns:
        {close, market_cap, pe, pb, shares_outstanding} or None
    """
    resp = _get(session, STOCK_DATA_URL, params={'cmpy_id': cmpy_id})
    if not resp:
        return None

    soup   = BeautifulSoup(resp.text, 'lxml')
    result = {}

    label_patterns = {
        'close':              [r'last\s+traded\s+price', r'last\s+price'],
        'market_cap':         [r'market\s+cap(?:italization)?'],
        'pe':                 [r'p/?e\s+ratio', r'price[\s/.]earnings'],
        'pb':                 [r'p/?bv?\s+ratio', r'price[\s/.]book'],
        'shares_outstanding': [r'outstanding\s+shares', r'listed\s+shares'],
    }

    for row in soup.find_all('tr'):
        for th in row.find_all('th'):
            label = th.get_text(strip=True).lower()
            td = th.find_next_sibling('td')
            if not td:
                continue
            value = td.get_text(strip=True)
            if not value:
                continue

            for field, patterns in label_patterns.items():
                if field in result:
                    continue
                for pat in patterns:
                    if re.search(pat, label, re.I):
                        parsed = _parse_number(value)
                        if parsed is not None:
                            result[field] = parsed
                        break

    if not result.get('close'):
        return None

    return result


def scrape_dividend_history(session, cmpy_id: str) -> list:
    """
    Scrapes dividend history for a company.

    Uses the confirmed working endpoint:
      GET /companyPage/dividends_and_rights_list.ax?DividendsOrRights=Dividends&cmpy_id={id}

    The form page must be loaded first to set the session cookie.

    Table columns (confirmed live):
      [0] Type of Security  (e.g. COMMON)
      [1] Type of Dividend  (e.g. Cash, Stock)
      [2] Dividend Rate     (e.g. 'P0.48 PER SHARES', 'P0.25')
      [3] Ex-Dividend Date  (e.g. 'Nov 04, 2025') ← used for year
      [4] Record Date
      [5] Payment Date
      [6] Circular Number

    Aggregates all cash dividend payments per calendar year.
    Returns: [{year: int, dps: float}, ...] newest first (up to 6 years)
    """
    _get(session, f'{PSE_EDGE_BASE_URL}/companyPage/dividends_and_rights_form.do',
         params={'cmpy_id': cmpy_id})

    resp = _get(session, DIVIDENDS_LIST_URL,
                params={'DividendsOrRights': 'Dividends', 'cmpy_id': cmpy_id})
    if not resp or len(resp.text) < 300:
        return []

    soup   = BeautifulSoup(resp.text, 'lxml')
    yearly = defaultdict(float)

    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 4:
            continue

        div_type = cells[1].get_text(strip=True).lower()
        if 'cash' not in div_type:
            continue

        rate_text  = cells[2].get_text(strip=True)
        rate_match = re.search(r'[\d.]+', rate_text)
        if not rate_match:
            continue
        per_share = float(rate_match.group())
        if not (0.001 < per_share < 100):
            continue

        date_text = cells[3].get_text(strip=True)
        yr_match  = re.search(r'\b(20\d{2})\b', date_text)
        if not yr_match:
            continue
        year = int(yr_match.group(1))

        yearly[year] += per_share

    if not yearly:
        return []

    return [{'year': yr, 'dps': round(dps, 4)}
            for yr, dps in sorted(yearly.items(), reverse=True)[:6]]
