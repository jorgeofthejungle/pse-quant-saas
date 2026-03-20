# ============================================================
# pse_financial_reports.py — Annual Report & Financial Data Scraping
# PSE Quant SaaS — scraper sub-module
# ============================================================

import re
import time
from bs4 import BeautifulSoup
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import SCRAPE_DELAY_SECS

try:
    from scraper.pse_session import _get, FIN_REPORTS_FORM, FIN_REPORTS_VIEW, FIN_REPORTS_SEARCH
except ImportError:
    from pse_session import _get, FIN_REPORTS_FORM, FIN_REPORTS_VIEW, FIN_REPORTS_SEARCH

try:
    from scraper.scraper_canary import fire_canary
except ImportError:
    from scraper_canary import fire_canary


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

    # Canary 1: Financial reports search must return table rows with data.
    data_rows = [r for r in soup.find_all('tr') if len(r.find_all('td')) >= 5]
    if not data_rows:
        fire_canary('pse_financial_reports', 'reports_search_no_rows',
                    f'No report table rows (>=5 cells) for cmpy_id={cmpy_id} — search.ax structure may have changed')
        return []

    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        tmpl = cells[1].get_text(strip=True)
        date = cells[3].get_text(strip=True)
        rnum = cells[4].get_text(strip=True)

        if not any(k in tmpl.lower() for k in ['annual', '17-1', 'audited']):
            continue

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


def scrape_financial_reports_page(session, cmpy_id: str) -> list:
    """
    Scrapes the PSE Edge Financial Reports tab for a company.
    URL: /companyPage/financial_reports_view.do?cmpy_id={id}

    The page shows structured HTML tables:
      Table 0: Balance Sheet (Annual)    — headers: Item | Current Year | Previous Year
      Table 1: Income Statement (Annual) — same headers
      Table 2: Balance Sheet (Quarterly)
      Table 3: Income Statement (Quarterly)

    We only process Tables 0 and 1 (headers contain "Current Year").
    Data units: "In Php Thousands" — divide by 1000 to get millions PHP.
    EPS and Book Value Per Share are already per-share values.

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

    # Canary 1: Page must contain at least one financial table with
    # "Current Year" / "Previous Year" headers. If these are missing
    # the financial_reports_view.do page structure has changed.
    annual_tables = [
        t for t in soup.find_all('table')
        if 'current year' in t.get_text(strip=True).lower()
        and 'previous year' in t.get_text(strip=True).lower()
    ]
    if not annual_tables:
        fire_canary('pse_financial_reports', 'fin_reports_table_missing',
                    f'No annual table (Current Year / Previous Year) found for cmpy_id={cmpy_id}')
        return []

    year_matches = re.findall(
        r'[Ff]or the fiscal year ended\s*[:\-]?\s*\w+\s+\d+,?\s*(\d{4})',
        page_text
    )
    if not year_matches:
        year_matches = re.findall(r'fiscal year.{0,30}(\d{4})', page_text, re.I)
    if not year_matches:
        print(f"    fin_reports: fiscal year not found on page")
        # Canary 2: Fiscal year marker is a required field for correct data attribution.
        fire_canary('pse_financial_reports', 'fin_reports_fiscal_year_missing',
                    f'Fiscal year label not found in page text for cmpy_id={cmpy_id}')
        return []

    current_year = int(year_matches[0])
    prev_year    = current_year - 1

    unit_matches = re.findall(r'[Cc]urrency[^:\n]{0,30}:([^\n]{0,60})', page_text)
    unit_text    = unit_matches[0].lower().strip() if unit_matches else ''

    if 'thousand' in unit_text:
        divisor = 1_000
    elif 'million' in unit_text:
        divisor = 1
    else:
        divisor = 1_000_000

    print(f"    fin_reports: FY{current_year}+{current_year-1}  unit={unit_text!r}  divisor={divisor:,}")

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

    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue

        header_cells = rows[0].find_all(['th', 'td'])
        header_text  = ' '.join(c.get_text(strip=True).lower() for c in header_cells)
        if 'current year' not in header_text or 'previous year' not in header_text:
            continue

        for row in rows[1:]:
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

    # Canary 3: Revenue and Net Income are the two most critical fields.
    # If neither is found for the current year, the FIELD_MAP labels likely changed.
    curr = results.get(current_year, {})
    if curr and not curr.get('revenue') and not curr.get('net_income') \
            and not curr.get('net_income_parent'):
        fire_canary('pse_financial_reports', 'fin_reports_key_fields_missing',
                    f'Revenue and Net Income both absent for FY{current_year} cmpy_id={cmpy_id} '
                    f'— PSE Edge row labels may have changed')

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
            'eps':                  d.get('eps'),
            'book_value_per_share': d.get('bvps'),
        }
        if any(v is not None for k, v in row.items() if k != 'year'):
            output.append(row)
            print(f"    fin_reports {year}: "
                  f"rev={row['revenue']}M  NI={row['net_income']}M  "
                  f"EPS={row['eps']}  eq={row['equity']}M")

    return output


def _fetch_year_financials(session, cmpy_id: str, year: int) -> dict | None:
    """
    Fetch financials for a specific year from PSE Edge annual reports.
    Returns a single row dict {year, revenue, net_income, ...} or None.
    Uses get_annual_report_edge_nos() to find the right report, then
    scrape_financial_reports_page() to parse it.
    """
    try:
        reports = get_annual_report_edge_nos(session, cmpy_id)
        if not reports:
            return None
        # Annual report for fiscal year N is typically filed in year N or N+1
        for report in reports:
            report_year = int(str(report.get('date', ''))[:4]) if report.get('date') else 0
            if report_year in (year, year + 1):
                data_list = scrape_financial_reports_page(session, cmpy_id)
                if not data_list:
                    return None
                for row in data_list:
                    if row.get('year') == year:
                        return row
                # If no row matches exact year, check if data_list has any row
                # for a year within range (PSE Edge may label it differently)
        return None
    except Exception:
        return None


def backfill_historical_financials(session, cmpy_id: str, ticker: str,
                                    start_year: int = 2018,
                                    end_year: int = 2023) -> dict:
    """
    Fetch annual reports for historical years (2018-2023) individually.
    Uses upsert_financials(force=False) so existing data is never overwritten.
    Returns {'fetched': int, 'skipped': int, 'errors': int}.

    Rate-limited: uses SCRAPE_DELAY_SECS between requests.
    Resumable: skips years where ticker already has data.
    """
    from db.database import upsert_financials, get_financials

    # Check which years already have data
    existing = get_financials(ticker, years=20)
    existing_years = {row['year'] for row in existing} if existing else set()

    stats = {'fetched': 0, 'skipped': 0, 'errors': 0}

    for year in range(start_year, end_year + 1):
        if year in existing_years:
            stats['skipped'] += 1
            continue

        for attempt in range(3):  # 3 retries
            try:
                time.sleep(SCRAPE_DELAY_SECS)
                data = _fetch_year_financials(session, cmpy_id, year)
                if data:
                    upsert_financials(
                        ticker, year,
                        revenue=data.get('revenue'),
                        net_income=data.get('net_income'),
                        equity=data.get('equity'),
                        total_debt=data.get('total_debt'),
                        eps=data.get('eps'),
                        operating_cf=data.get('operating_cf'),
                        capex=data.get('capex'),
                        ebitda=data.get('ebitda'),
                        force=False,  # never overwrite existing data
                    )
                    stats['fetched'] += 1
                break  # success or no data found -- don't retry
            except Exception:
                if attempt == 2:
                    stats['errors'] += 1
                else:
                    time.sleep(5 * (attempt + 1))  # backoff: 5s, 10s

    return stats
