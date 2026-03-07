# ============================================================
# pse_lookup.py — Company Lookup & Directory Scraping
# PSE Quant SaaS — scraper sub-module
# ============================================================

import re
import time
import json
from bs4 import BeautifulSoup

try:
    from scraper.pse_session import (
        _get, AUTOCOMPLETE_URL, DIRECTORY_SEARCH, PSE_SECTORS, SCRAPE_DELAY_SECS
    )
except ImportError:
    from pse_session import (
        _get, AUTOCOMPLETE_URL, DIRECTORY_SEARCH, PSE_SECTORS, SCRAPE_DELAY_SECS
    )

from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import SCRAPE_DELAY_SECS


def lookup_cmpy_id(session, ticker: str) -> str | None:
    """
    Uses PSE Edge autocomplete to resolve ticker → internal cmpyId.
    Returns cmpyId string (e.g. '188' for DMC) or None.
    """
    resp = _get(session, AUTOCOMPLETE_URL, params={'term': ticker})
    if not resp:
        return None
    try:
        data = resp.json()
        for item in data:
            if item.get('symbol', '').upper() == ticker.upper():
                return str(item['cmpyId'])
        if data:
            return str(data[0]['cmpyId'])
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def lookup_company_info(session, ticker: str) -> dict | None:
    """
    Returns {cmpy_id, name, ticker} for a given ticker symbol.
    """
    resp = _get(session, AUTOCOMPLETE_URL, params={'term': ticker})
    if not resp:
        return None
    try:
        data = resp.json()
        for item in data:
            if item.get('symbol', '').upper() == ticker.upper():
                return {
                    'cmpy_id': str(item['cmpyId']),
                    'name':    item.get('cmpyNm', ''),
                    'ticker':  item.get('symbol', ticker).upper(),
                }
        if data:
            return {
                'cmpy_id': str(data[0]['cmpyId']),
                'name':    data[0].get('cmpyNm', ''),
                'ticker':  data[0].get('symbol', ticker).upper(),
            }
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def get_companies_by_sector(session, sector: str) -> list:
    """
    Gets all companies in a PSE sector from the directory.
    Paginates until all results are fetched.
    Returns [{ticker, name, cmpy_id, sector, subsector}, ...]

    NOTE: PSE Edge wraps around after the last page (always returns 50 rows).
    We use the "Total N" counter in the HTML to know the real count and stop early.
    """
    companies = []
    start = 0
    limit = 50
    total_expected = None

    while True:
        params = {
            'method':      'searchCompanyDirectory',
            'sortType':    'N',
            'start':       start,
            'limit':       limit,
            'sector':      sector,
            'subsector':   'ALL',
            'companyName': '',
            'symbol':      '',
        }
        resp = _get(session, DIRECTORY_SEARCH, params=params)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, 'lxml')

        if total_expected is None:
            m = re.search(r'Total\s+(\d+)', resp.text)
            total_expected = int(m.group(1)) if m else None

        rows = soup.find_all('tr')
        found_on_page = 0

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            name_text   = cells[0].get_text(strip=True)
            symbol_text = cells[1].get_text(strip=True).upper()
            sector_text = cells[2].get_text(strip=True)
            sub_text    = cells[3].get_text(strip=True)

            if not symbol_text or not name_text:
                continue

            cmpy_id = None
            onclick = row.get('onclick', '')
            if not onclick:
                for tag in row.find_all(onclick=True):
                    onclick = tag.get('onclick', '')
                    if onclick:
                        break
            id_match = re.search(r'cmpy_id[=\'"\s]+(\d+)', onclick)
            if id_match:
                cmpy_id = id_match.group(1)

            companies.append({
                'ticker':    symbol_text,
                'name':      name_text,
                'cmpy_id':   cmpy_id,
                'sector':    sector_text or sector,
                'subsector': sub_text,
            })
            found_on_page += 1

        if total_expected is not None and len(companies) >= total_expected:
            break
        if found_on_page < limit:
            break
        start += limit
        time.sleep(SCRAPE_DELAY_SECS)

    return companies


def get_all_companies(session) -> list:
    """
    Builds the full PSE company list using two phases:

    Phase 1 — directory search per sector (up to 50 per sector).
    Phase 2 — autocomplete sweep A-Z to catch companies PSE Edge omits
              from the directory page (pagination is capped at 50).

    Returns [{ticker, name, cmpy_id, sector, subsector, is_reit, is_bank}]
    """
    all_companies = []
    seen_tickers  = set()

    def _classify_and_append(c):
        if c['ticker'] in seen_tickers:
            return
        seen_tickers.add(c['ticker'])
        if not c.get('cmpy_id'):
            info = lookup_company_info(session, c['ticker'])
            if info:
                c['cmpy_id'] = info['cmpy_id']
                if not c.get('name'):
                    c['name'] = info.get('name', '')
            time.sleep(SCRAPE_DELAY_SECS)
        name_lower = c.get('name', '').lower()
        sub_lower  = c.get('subsector', '').lower()
        c['is_reit'] = (
            'reit' in name_lower or
            'real estate investment trust' in sub_lower
        )
        c['is_bank'] = (
            'bank' in name_lower or
            'bancorp' in name_lower or
            'banks' in sub_lower
        )
        c.setdefault('subsector', '')
        all_companies.append(c)

    # Phase 1: directory search
    for sector in PSE_SECTORS:
        print(f"  Loading {sector} companies...")
        sector_companies = get_companies_by_sector(session, sector)
        for c in sector_companies:
            _classify_and_append(c)
        time.sleep(SCRAPE_DELAY_SECS)
        print(f"    {len(sector_companies)} returned (may be capped at 50)")

    phase1_count = len(all_companies)
    print(f"  Phase 1 total: {phase1_count} companies")

    # Phase 2: autocomplete sweep A-Z
    print("  Phase 2: autocomplete sweep to find remaining companies...")
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        resp = _get(session, AUTOCOMPLETE_URL, params={'term': letter})
        if not resp:
            continue
        try:
            items = resp.json()
        except Exception:
            continue
        for item in items:
            sym = item.get('symbol', '').upper().strip()
            if not sym or sym in seen_tickers:
                continue
            _classify_and_append({
                'ticker':    sym,
                'name':      item.get('cmpyNm', ''),
                'cmpy_id':   str(item.get('cmpyId', '')),
                'sector':    'Unknown',
                'subsector': '',
            })
        time.sleep(0.5)

    phase2_added = len(all_companies) - phase1_count
    print(f"  Phase 2 added: {phase2_added} more companies")
    print(f"  Total: {len(all_companies)} companies")
    return all_companies
