# ============================================================
# pse_edge_scraper.py — PSE Edge Fundamental Data Scraper
# PSE Quant SaaS — Phase 3
# ============================================================
# Scrapes company directory, stock data, dividend history,
# and annual report PDF links from edge.pse.com.ph.
#
# Two data layers:
#   1. Stock data (price, P/E, P/BV, market cap, dividends)
#      → scraped per company from server-rendered HTML pages
#   2. Annual report PDFs (EPS, revenue, equity, etc.)
#      → discovered here, downloaded + parsed by pdf_parser.py
#
# Confirmed working endpoints (no login required):
#   /autoComplete/searchCompanyNameSymbol.ax             → JSON with cmpyId
#   /companyDirectory/search.ax                          → HTML company table
#   /companyPage/stockData.do                            → HTML stock data
#     └─ Uses <th>label</th><td>value</td> structure
#     └─ P/E and P/BV are AJAX-loaded (empty in HTML) — calculated from DB
#   /companyPage/dividends_and_rights_form.do            → Form page (sets session)
#   /companyPage/dividends_and_rights_list.ax            → AJAX dividend table
#     └─ Requires DividendsOrRights=Dividends param
#     └─ Returns current-year dividends only; history from PDF parser
#   /companyPage/financial_reports_view.do               → Financial reports tab
#   /financialReports/search.ax                          → HTML report list (session)
#
# Usage:
#   py scraper/pse_edge_scraper.py                  # scrape all companies
#   py scraper/pse_edge_scraper.py --ticker DMC     # one ticker only
#   py scraper/pse_edge_scraper.py --sector Financials
# ============================================================

import sys
import os
import re
import time
import json
import argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# ── Path setup ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

import database as db
from config import (PSE_EDGE_BASE_URL, SCRAPE_DELAY_SECS,
                    REQUEST_TIMEOUT, MAX_RETRIES)

# ── Constants ─────────────────────────────────────────────────
AUTOCOMPLETE_URL    = f'{PSE_EDGE_BASE_URL}/autoComplete/searchCompanyNameSymbol.ax'
DIRECTORY_SEARCH    = f'{PSE_EDGE_BASE_URL}/companyDirectory/search.ax'
STOCK_DATA_URL      = f'{PSE_EDGE_BASE_URL}/companyPage/stockData.do'
COMPANY_INFO_URL    = f'{PSE_EDGE_BASE_URL}/companyInformation/form.do'
FIN_REPORTS_FORM    = f'{PSE_EDGE_BASE_URL}/financialReports/form.do'
FIN_REPORTS_VIEW    = f'{PSE_EDGE_BASE_URL}/companyPage/financial_reports_view.do'
FIN_REPORTS_SEARCH  = f'{PSE_EDGE_BASE_URL}/financialReports/search.ax'

# ── Confirmed working dividend endpoint (discovered via page source inspection) ──
# PSE Edge dividend list uses a separate AJAX file triggered by the Dividends tab
DIVIDENDS_LIST_URL = f'{PSE_EDGE_BASE_URL}/companyPage/dividends_and_rights_list.ax'

# PSE market sectors for directory iteration
PSE_SECTORS = [
    'Financials',
    'Industrial',
    'Holding Firms',
    'Property',
    'Services',
    'Mining and Oil',
]

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': PSE_EDGE_BASE_URL,
}


# ── Session factory ───────────────────────────────────────────

def make_session() -> requests.Session:
    """
    Creates a requests.Session with standard headers and warms up
    cookies by loading the PSE Edge homepage first.
    Required for AJAX endpoints that check session state.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(PSE_EDGE_BASE_URL, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        pass   # continue even if warm-up fails
    return session


# ── HTTP helpers ─────────────────────────────────────────────

def _get(session, url: str, params: dict = None,
         retries: int = MAX_RETRIES) -> requests.Response | None:
    """
    GET request with retry logic. Returns Response or None on failure.
    Uses the shared session to maintain cookies across calls.
    """
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp
            print(f"  HTTP {resp.status_code} from {url} (attempt {attempt}/{retries})")
        except requests.RequestException as e:
            print(f"  Request error: {e} (attempt {attempt}/{retries})")
        if attempt < retries:
            time.sleep(SCRAPE_DELAY_SECS)
    return None


# ── Company lookup ────────────────────────────────────────────

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
        # If exact match not found, return first result
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


# ── Company directory ─────────────────────────────────────────

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
    total_expected = None   # parsed from first-page HTML

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

        # Parse total count once from the first page
        if total_expected is None:
            m = re.search(r'Total\s+(\d+)', resp.text)
            total_expected = int(m.group(1)) if m else None

        rows = soup.find_all('tr')
        found_on_page = 0

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            name_cell   = cells[0]
            symbol_cell = cells[1]
            sector_cell = cells[2]
            sub_cell    = cells[3]

            name_text   = name_cell.get_text(strip=True)
            symbol_text = symbol_cell.get_text(strip=True).upper()
            sector_text = sector_cell.get_text(strip=True)
            sub_text    = sub_cell.get_text(strip=True)

            if not symbol_text or not name_text:
                continue

            # Try to extract cmpy_id from onclick or href in the row
            cmpy_id = None
            onclick = row.get('onclick', '')
            if not onclick:
                for tag in row.find_all(onclick=True):
                    onclick = tag.get('onclick', '')
                    if onclick:
                        break
            # Pattern: location.href = '/companyInformation/form.do?cmpy_id=188'
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

        # Stop if we've collected all expected companies (PSE Edge wraps around)
        if total_expected is not None and len(companies) >= total_expected:
            break
        if found_on_page < limit:
            break   # last page (no wrap-around detected)
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

    # Phase 1: directory search (up to 50 per sector)
    for sector in PSE_SECTORS:
        print(f"  Loading {sector} companies...")
        sector_companies = get_companies_by_sector(session, sector)
        for c in sector_companies:
            _classify_and_append(c)
        time.sleep(SCRAPE_DELAY_SECS)
        print(f"    {len(sector_companies)} returned (may be capped at 50)")

    phase1_count = len(all_companies)
    print(f"  Phase 1 total: {phase1_count} companies")

    # Phase 2: autocomplete sweep A-Z to catch any PSE Edge missed
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


# ── Stock data scraping ───────────────────────────────────────

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
    A single <tr> may contain multiple <th>/<td> pairs.

    Returns:
        {close, market_cap, pe, pb, shares_outstanding} or None
    """
    resp = _get(session, STOCK_DATA_URL, params={'cmpy_id': cmpy_id})
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, 'lxml')
    result = {}

    label_patterns = {
        'close':              [r'last\s+traded\s+price', r'last\s+price'],
        'market_cap':         [r'market\s+cap(?:italization)?'],
        'pe':                 [r'p/?e\s+ratio', r'price[\s/.]earnings'],
        'pb':                 [r'p/?bv?\s+ratio', r'price[\s/.]book'],
        'shares_outstanding': [r'outstanding\s+shares', r'listed\s+shares'],
    }

    # PSE Edge uses <th>Label</th><td>Value</td> pairs within each <tr>.
    # Iterate every <th>; grab its immediately-following sibling <td>.
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


# ── Dividend history scraping ─────────────────────────────────

def scrape_dividend_history(session, cmpy_id: str) -> list:
    """
    Scrapes dividend history for a company.

    Uses the confirmed working endpoint (discovered via PSE Edge page source):
      GET /companyPage/dividends_and_rights_list.ax?DividendsOrRights=Dividends&cmpy_id={id}

    The form page must be loaded first to set the session cookie, then the
    AJAX call returns the dividend table (same domain, session-scoped).

    Table columns (confirmed live):
      [0] Type of Security  (e.g. COMMON)
      [1] Type of Dividend  (e.g. Cash, Stock)
      [2] Dividend Rate     (e.g. 'P0.48 PER SHARES', 'P0.25')
      [3] Ex-Dividend Date  (e.g. 'Nov 04, 2025') ← used for year
      [4] Record Date
      [5] Payment Date
      [6] Circular Number

    Note: PSE Edge returns only the most recent dividend declarations
    (typically current year). Historical DPS (5Y) is supplemented by
    the PDF parser from annual report filings.

    Aggregates all cash dividend payments per calendar year.
    Returns: [{year: int, dps: float}, ...] newest first (up to 6 years)
    """
    # Warm up session with the form page (sets required cookie/session)
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

        # Column 1: Type of Dividend — cash only
        div_type = cells[1].get_text(strip=True).lower()
        if 'cash' not in div_type:
            continue

        # Column 2: Dividend Rate — parse numeric PHP amount
        # Formats seen: 'P0.48 PER SHARES', 'P0.25', '0.35'
        rate_text  = cells[2].get_text(strip=True)
        rate_match = re.search(r'[\d.]+', rate_text)
        if not rate_match:
            continue
        per_share = float(rate_match.group())
        if not (0.001 < per_share < 100):   # sanity range
            continue

        # Column 3: Ex-Dividend Date — extract year
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



def get_annual_report_edge_nos(session, cmpy_id: str) -> list:
    """
    Finds report references for the most recent Annual Reports on PSE Edge.
    Uses financialReports/search.ax with companyId + date range.

    Returns: [{'edge_no': str, 'date': str, 'title': str}, ...] newest first.
    'edge_no' is a hex hash used by openPopup() on PSE Edge — use it with
    the disc viewer endpoint to download the filing PDF.
    """
    _get(session, FIN_REPORTS_FORM, params=None)
    time.sleep(SCRAPE_DELAY_SECS)

    resp = _get(session, FIN_REPORTS_SEARCH,
                params={'companyId': cmpy_id, 'tmplNm': '',
                        'fromDate': '01-01-2018', 'toDate': '12-31-2026',
                        'sortType': 'D', 'pageNo': '1'})
    if not resp or len(resp.text) < 500:
        return []

    soup    = BeautifulSoup(resp.text, 'lxml')
    reports = []

    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        tmpl = cells[1].get_text(strip=True)
        date = cells[3].get_text(strip=True)
        rnum = cells[4].get_text(strip=True)

        # Keep only Annual Reports and Audited Financial Statements
        if not any(k in tmpl.lower() for k in ['annual', '17-1', 'audited']):
            continue

        # Extract openPopup hash from onclick attribute
        popup_id = ''
        for tag in row.find_all(onclick=True):
            m = re.search(r"openPopup\('([a-f0-9]+)'\)", tag.get('onclick', ''))
            if m:
                popup_id = m.group(1)
                break

        reports.append({
            'edge_no': popup_id,
            'date':    date,
            'title':   f"{tmpl} ({rnum})",
        })

    return reports


# ── Financial reports page scraper ───────────────────────────

def scrape_financial_reports_page(session, cmpy_id: str) -> list:
    """
    Scrapes the PSE Edge Financial Reports tab for a company.
    URL: /companyPage/financial_reports_view.do?cmpy_id={id}

    The page shows structured HTML tables:
      Table 0: Balance Sheet (Annual)   — headers: Item | Current Year | Previous Year
      Table 1: Income Statement (Annual) — same headers
      Table 2: Balance Sheet (Quarterly)  — headers: Item | Period Ended | Fiscal Year Ended
      Table 3: Income Statement (Quarterly) — 4 value columns

    We only process Tables 0 and 1 (headers contain "Current Year").
    Data units: "In Php Thousands" — divide by 1000 to get millions PHP.
    EPS and Book Value Per Share are already per-share values — no unit conversion.

    Returns a list of dicts, newest year first:
      [{'year': 2024, 'revenue': ..., 'net_income': ..., 'equity': ...,
        'total_debt': ..., 'eps': ..., 'book_value_per_share': ...}, ...]
    Returns [] if page unavailable or no data found.
    """
    resp = _get(session, FIN_REPORTS_VIEW, params={'cmpy_id': cmpy_id})
    if not resp or len(resp.text) < 500:
        return []

    soup      = BeautifulSoup(resp.text, 'lxml')
    page_text = soup.get_text()

    # ── Detect fiscal year from page header ───────────────────
    # "For the fiscal year ended : Dec 31, 2024"
    year_matches = re.findall(
        r'[Ff]or the fiscal year ended\s*[:\-]?\s*\w+\s+\d+,?\s*(\d{4})',
        page_text
    )
    if not year_matches:
        year_matches = re.findall(r'fiscal year.{0,30}(\d{4})', page_text, re.I)
    if not year_matches:
        print(f"    fin_reports: fiscal year not found on page")
        return []

    current_year = int(year_matches[0])
    prev_year    = current_year - 1

    # ── Detect reporting unit and set divisor ─────────────────
    # PSE Edge shows unit in text like "Currency(and units) : In Php Thousands"
    # or "Philippine Pesos" (no multiplier). We normalise everything to millions PHP.
    unit_matches = re.findall(r'[Cc]urrency[^:\n]{0,30}:([^\n]{0,60})', page_text)
    unit_text    = unit_matches[0].lower().strip() if unit_matches else ''

    if 'thousand' in unit_text:
        divisor = 1_000          # thousands → millions
    elif 'million' in unit_text:
        divisor = 1              # already in millions
    else:
        divisor = 1_000_000     # plain pesos → millions

    print(f"    fin_reports: FY{current_year}+{current_year-1}  unit={unit_text!r}  divisor={divisor:,}")

    # ── Field mapping (lowercase label → internal field name) ─
    # IMPORTANT: More-specific patterns must come BEFORE shorter ones that
    # would accidentally match them (e.g. 'net income' is a substring of
    # 'net income attributable to parent', so list the longer key first).
    FIELD_MAP = {
        'gross revenue':                            'revenue',
        'total revenues':                           'revenue',
        'revenues':                                 'revenue',
        'net income/(loss) attributable to parent': 'net_income_parent',
        'net income attributable to parent':        'net_income_parent',
        'net income/(loss) after tax':              'net_income',
        'net income after tax':                     'net_income',
        'net income':                               'net_income',
        "stockholders' equity - parent":            'equity_parent',
        "stockholders' equity":                     'equity',
        "stockholders equity":                      'equity',
        'total liabilities':                        'total_debt',
        'book value per share':                     'bvps',
        'earnings/(loss) per share (basic)':        'eps',
        'earnings per share (basic)':               'eps',
        'earnings per share':                       'eps',
    }

    def _parse_num(text: str) -> float | None:
        t = text.strip().replace(',', '').replace('\xa0', '')
        if not t or t in ('-', '—', 'N/A', 'n/a', ''):
            return None
        try:
            return float(t)
        except ValueError:
            return None

    results = {current_year: {}, prev_year: {}}

    # ── Parse only annual tables (header row: "Current Year" / "Previous Year") ─
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue

        # Check if this is an annual table by inspecting the header row
        header_cells = rows[0].find_all(['th', 'td'])
        header_text  = ' '.join(c.get_text(strip=True).lower() for c in header_cells)
        if 'current year' not in header_text or 'previous year' not in header_text:
            continue   # skip quarterly tables

        for row in rows[1:]:   # skip header row
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:
                continue
            label    = cells[0].get_text(strip=True).lower()
            val_curr = _parse_num(cells[1].get_text(strip=True))
            val_prev = _parse_num(cells[2].get_text(strip=True))

            matched_field = None
            for key, field in FIELD_MAP.items():
                if key in label:
                    matched_field = field
                    break
            if not matched_field:
                continue

            if matched_field not in results[current_year] and val_curr is not None:
                results[current_year][matched_field] = val_curr
            if matched_field not in results[prev_year] and val_prev is not None:
                results[prev_year][matched_field] = val_prev

    # ── Build output: normalise to millions PHP ───────────────
    output = []
    for year in [current_year, prev_year]:
        d = results[year]
        if not d:
            continue

        eq      = d.get('equity_parent') or d.get('equity')
        net_inc = d.get('net_income_parent') or d.get('net_income')

        def _to_m(v):
            return round(v / divisor, 3) if v is not None else None

        row = {
            'year':                 year,
            'revenue':              _to_m(d.get('revenue')),
            'net_income':           _to_m(net_inc),
            'equity':               _to_m(eq),
            'total_debt':           _to_m(d.get('total_debt')),
            'eps':                  d.get('eps'),    # already per-share
            'book_value_per_share': d.get('bvps'),   # already per-share
        }
        if any(v is not None for k, v in row.items() if k != 'year'):
            output.append(row)
            print(f"    fin_reports {year}: "
                  f"rev={row['revenue']}M  NI={row['net_income']}M  "
                  f"EPS={row['eps']}  eq={row['equity']}M")

    return output


# ── Full company scrape ───────────────────────────────────────

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

    # ── Stock data ────────────────────────────────────────────
    time.sleep(SCRAPE_DELAY_SECS)
    stock_data = scrape_stock_data(session, cmpy_id)
    if not stock_data:
        print(f"    {ticker}: No stock data found")
        return None

    close      = stock_data.get('close')
    market_cap = stock_data.get('market_cap')
    # P/E and P/BV are AJAX-loaded on PSE Edge's stockData page and are not
    # available in server-rendered HTML.  They will be calculated later by
    # build_stock_dict_from_db() (pse_scraper.py) once EPS and equity data
    # arrive via the PDF parser.
    pe         = stock_data.get('pe')    # will be None from scrape
    pb         = stock_data.get('pb')    # will be None from scrape

    # ── Dividend history ──────────────────────────────────────
    time.sleep(SCRAPE_DELAY_SECS)
    div_history = scrape_dividend_history(session, cmpy_id)

    dps_last     = div_history[0]['dps'] if div_history else None
    dividends_5y = [d['dps'] for d in div_history[:5]]

    # Dividend yield = (DPS / Price) * 100
    div_yield = None
    if dps_last and close and close > 0:
        div_yield = round((dps_last / close) * 100, 4)

    # Dividend CAGR (5-year CAGR from oldest to newest)
    dividend_cagr = None
    if len(dividends_5y) >= 2:
        newest = dividends_5y[0]
        oldest = dividends_5y[-1]
        n = len(dividends_5y) - 1
        if oldest > 0 and newest > 0 and n > 0:
            dividend_cagr = round(((newest / oldest) ** (1.0 / n) - 1) * 100, 2)

    # ── Financial reports (income statement + balance sheet) ──
    time.sleep(SCRAPE_DELAY_SECS)
    fin_data = scrape_financial_reports_page(session, cmpy_id)

    # P/B from book value per share (more accurate than market_cap / equity)
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
        'div_history':      div_history,   # [{year, dps}] — for DB storage
        'fin_data':         fin_data,       # [{year, revenue, net_income, ...}] — for DB
        '_date':            today,
        '_cmpy_id':         cmpy_id,
    }


# ── Database saving ───────────────────────────────────────────

def _save_company(company_info: dict, stock_data: dict):
    """
    Saves stock identity (stocks table) and current price (prices table).
    Also saves DPS per year into financials table.
    """
    ticker = company_info['ticker']

    # Save identity
    db.upsert_stock(
        ticker   = ticker,
        name     = company_info.get('name', ''),
        sector   = company_info.get('sector', ''),
        is_reit  = company_info.get('is_reit', False),
        is_bank  = company_info.get('is_bank', False),
    )

    # Save current price + market cap
    if stock_data.get('current_price'):
        db.upsert_price(
            ticker     = ticker,
            date       = stock_data['_date'],
            close      = stock_data['current_price'],
            market_cap = stock_data.get('market_cap'),
        )

    # Save DPS history into financials table (one row per year)
    for entry in stock_data.get('div_history', []):
        db.upsert_financials(
            ticker = ticker,
            year   = entry['year'],
            dps    = entry['dps'],
        )

    # Save annual financial data (revenue, net income, equity, etc.)
    for fin in stock_data.get('fin_data', []):
        db.upsert_financials(
            ticker     = ticker,
            year       = fin['year'],
            revenue    = fin.get('revenue'),
            net_income = fin.get('net_income'),
            equity     = fin.get('equity'),
            total_debt = fin.get('total_debt'),
            eps        = fin.get('eps'),
        )


# ── Main entry points ─────────────────────────────────────────

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

    # Find annual report PDFs
    print(f"  {ticker}: Looking for annual reports...")
    edge_nos = get_annual_report_edge_nos(session, cmpy_id)
    if edge_nos:
        print(f"  {ticker}: Found {len(edge_nos)} annual report(s):")
        for r in edge_nos:
            print(f"    edge_no={r['edge_no']}  {r['date']}  {r['title'][:50]}")
    else:
        print(f"  {ticker}: No annual reports found via AJAX (may need manual lookup)")

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
        # Scrape specific tickers
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

    # Scrape by sector(s)
    if sector:
        # Single sector: use simple directory lookup
        print(f"\n  Fetching {sector} directory...")
        all_companies = get_companies_by_sector(session, sector)
    else:
        # Full scrape: use two-phase discovery (directory + A-Z autocomplete sweep)
        # to find all ~280+ listed companies, not just 50 per sector
        all_companies = get_all_companies(session)

    print(f"\n  Found {len(all_companies)} companies total. Starting data scrape...")
    saved = 0

    for i, company_info in enumerate(all_companies, 1):
        ticker  = company_info['ticker']
        cmpy_id = company_info.get('cmpy_id')

        if not cmpy_id:
            # Resolve via autocomplete
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


# ── Self-test ────────────────────────────────────────────────

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
