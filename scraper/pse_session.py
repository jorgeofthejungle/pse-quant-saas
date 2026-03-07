# ============================================================
# pse_session.py — HTTP Session, Headers, URL Constants
# PSE Quant SaaS — scraper sub-module
# ============================================================

import time
import requests
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import PSE_EDGE_BASE_URL, SCRAPE_DELAY_SECS, REQUEST_TIMEOUT, MAX_RETRIES

# ── URL constants ─────────────────────────────────────────────
AUTOCOMPLETE_URL   = f'{PSE_EDGE_BASE_URL}/autoComplete/searchCompanyNameSymbol.ax'
DIRECTORY_SEARCH   = f'{PSE_EDGE_BASE_URL}/companyDirectory/search.ax'
STOCK_DATA_URL     = f'{PSE_EDGE_BASE_URL}/companyPage/stockData.do'
COMPANY_INFO_URL   = f'{PSE_EDGE_BASE_URL}/companyInformation/form.do'
FIN_REPORTS_FORM   = f'{PSE_EDGE_BASE_URL}/financialReports/form.do'
FIN_REPORTS_VIEW   = f'{PSE_EDGE_BASE_URL}/companyPage/financial_reports_view.do'
FIN_REPORTS_SEARCH = f'{PSE_EDGE_BASE_URL}/financialReports/search.ax'
DIVIDENDS_LIST_URL = f'{PSE_EDGE_BASE_URL}/companyPage/dividends_and_rights_list.ax'

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
        pass
    return session


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
