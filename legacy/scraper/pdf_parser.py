# ============================================================
# pdf_parser.py — PSE Annual Report PDF Parser (facade)
# PSE Quant SaaS — Phase 3
# ============================================================
# Downloads and parses SEC Form 17-A annual report PDFs from
# PSE Edge, then saves extracted data to the local database.
#
# Sub-modules:
#   pdf_parser_utils.py — number parsing, download, page classification
#   pdf_parser_dps.py   — DPS extraction from Notes pages
#
# Usage (CLI):
#   py scraper/pdf_parser.py --ticker DMC --all
#   py scraper/pdf_parser.py --ticker DMC --edge-no 2fd88ba354823b28abca0fa0c5b4e4d0
#   py scraper/pdf_parser.py --ticker DMC --pdf "C:\path\to\file.pdf"
#
# Output: All monetary values in millions PHP. EPS/DPS in PHP per share.
# ============================================================

import re
import sys
import time
import argparse
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT))

import database as db
import pse_edge_scraper as edge

from pdf_parser_utils import (
    RAW_DIR, PSE_EDGE_BASE,
    _to_m, _detect_divisor, _extract_years,
    _extract_row, _find_revenue_row, _find_capex_row,
    _has_year_header, get_file_ids, download_pdf,
    _IS_INCOME_RE, _IS_CF_RE, _IS_BS_RE,
)
from pdf_parser_dps import _extract_dps_from_notes


# ── Main parser ───────────────────────────────────────────────

def parse_pdf(pdf_path: str | Path) -> dict[int, dict]:
    """
    Parse a PSE annual report PDF.

    Returns a dict keyed by fiscal year:
        {2023: {revenue, net_income, eps, operating_cf, capex,
                cash, equity, total_debt},
         2022: {...}, 2021: {...}}

    All monetary values in millions PHP. EPS in PHP per share.
    Returns {} if nothing found.
    """
    pdf_path  = str(pdf_path)
    result: dict[int, dict] = {}

    income_pages: list[str] = []
    cf_pages:     list[str] = []
    bs_pages:     list[str] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            all_texts = [page.extract_text() or '' for page in pdf.pages]
            n_pages   = len(all_texts)

            for i, text in enumerate(all_texts):
                if not text.strip():
                    continue
                top = text[:400].upper()

                if (_IS_INCOME_RE.search(top)
                        and 'REVENUE' in text.upper()
                        and _has_year_header(text)):
                    income_pages.append(text)

                if (_IS_CF_RE.search(top)
                        and 'CASH FLOWS FROM OPERATING' in text.upper()):
                    cf_pages.append(text)
                    if i + 1 < n_pages:
                        next_text = all_texts[i + 1]
                        if next_text.strip() and 'CASH FLOWS FROM' in next_text.upper():
                            cf_pages.append(next_text)

                if (_IS_BS_RE.search(top) and 'TOTAL' in text.upper()):
                    bs_pages.append(text)

    except Exception as e:
        print(f'    [pdf] pdfplumber error: {e}')
        return {}

    if not income_pages and not cf_pages:
        print('    [pdf] No financial statement pages found.')
        return {}

    divisor = 1_000_000
    years:  list[int] = []

    # ── Income statement ──────────────────────────────────────
    if income_pages:
        is_text = income_pages[0]
        years   = _extract_years(is_text)
        n       = len(years) if years else 3
        divisor = _detect_divisor(is_text)

        rev_vals = _find_revenue_row(is_text, n)

        ni_vals = _extract_row(is_text, [
            r'equity\s+holders\s+of\s+the\s+parent\s+company',
            r'equity\s+holders\s+of\s+\w',
            r'net\s+income\s+attributable\s+to\s+owners',
        ], n)
        if not any(v is not None for v in ni_vals):
            ni_vals = _extract_row(is_text, [
                r'net\s+income\s+after\s+(?:income\s+)?tax',
                r'net\s+income\b',
            ], n)

        eps_vals = _extract_row(is_text, [
            r'basic/diluted\s+earnings\s+per\s+share',
            r'basic\s+and\s+diluted\s+earnings\s+per\s+share',
            r'basic\s+earnings\s+per\s+share\s+attributable',
            r'basic\s+earnings\s+per\s+share\b',
            r'diluted\s+earnings\s+per\s+share\b',
            r'basic\s+and\s+diluted\b',
        ], n)

        for col, year in enumerate(years):
            d = result.setdefault(year, {})
            if col < len(rev_vals) and rev_vals[col] is not None:
                d['revenue']    = _to_m(rev_vals[col],  divisor)
            if col < len(ni_vals) and ni_vals[col] is not None:
                d['net_income'] = _to_m(ni_vals[col],   divisor)
            if col < len(eps_vals) and eps_vals[col] is not None:
                d['eps']        = eps_vals[col]

    # ── Cash flow statement ───────────────────────────────────
    if cf_pages:
        cf_text  = '\n'.join(cf_pages[:2])
        yrs_cf   = _extract_years(cf_text) or years
        n_cf     = len(yrs_cf) if yrs_cf else 3
        div_cf   = _detect_divisor(cf_text, default=divisor)

        ocf_vals = _extract_row(cf_text, [
            r'net\s+cash\s+provided\s+by\s+operating',
            r'net\s+cash\s+from\s+operating\s+activities',
            r'net\s+cash\s+flows?\s+from\s+operating\s+activities',
            r'net\s+cash\s+(?:flows?\s+)?(?:provided|generated)\s+(?:by|from)\s+operating',
        ], n_cf)

        capex_vals = _find_capex_row(cf_text, n_cf)

        cash_vals = _extract_row(cf_text, [
            r'cash\s+and\s+cash\s+equivalents\s+at\s+(?:end\s+of\s+(?:year|period)|close)',
            r'cash\s+at\s+(?:end\s+of\s+(?:year|period)|december\s+31)',
            r'at\s+december\s+31\b',
        ], n_cf)

        for col, year in enumerate(yrs_cf):
            d = result.setdefault(year, {})
            if col < len(ocf_vals) and ocf_vals[col] is not None:
                d['operating_cf'] = _to_m(ocf_vals[col], div_cf)
            if col < len(capex_vals) and capex_vals[col] is not None:
                d['capex']        = _to_m(capex_vals[col], div_cf)
            if col < len(cash_vals) and cash_vals[col] is not None:
                d['cash']         = _to_m(cash_vals[col], div_cf)

    # ── Balance sheet ─────────────────────────────────────────
    if bs_pages:
        bs_text = bs_pages[0]
        yrs_bs  = _extract_years(bs_text) or (years[:2] if years else [])
        n_bs    = len(yrs_bs) if yrs_bs else 2
        div_bs  = _detect_divisor(bs_text, default=divisor)

        eq_vals = _extract_row(bs_text, [
            r"stockholders'?\s+equity\s*[-\u2013]\s*parent",
            r"equity\s+attributable\s+to\s+(?:equity\s+holders|parent)",
            r"total\s+stockholders'?\s+equity\b",
            r"total\s+equity\b",
        ], n_bs)

        liab_vals = _extract_row(bs_text, [r'total\s+liabilities\b'], n_bs)

        for col, year in enumerate(yrs_bs):
            d = result.setdefault(year, {})
            if col < len(eq_vals) and eq_vals[col] is not None:
                v = _to_m(eq_vals[col], div_bs)
                if v is not None:
                    d['equity'] = v
            if col < len(liab_vals) and liab_vals[col] is not None:
                v = _to_m(liab_vals[col], div_bs)
                if v is not None:
                    d['total_debt'] = v

    # ── DPS from Notes ────────────────────────────────────────
    if years:
        dps_map = _extract_dps_from_notes(all_texts, years)
        for yr, dps_val in dps_map.items():
            d = result.setdefault(yr, {})
            if 'dps' not in d:
                d['dps'] = dps_val

    return result


def parse_and_save(ticker: str, pdf_path: str | Path) -> int:
    """Parse a PDF and save all extracted years to the database. Returns rows saved."""
    ticker = ticker.upper()
    print(f'  Parsing: {Path(pdf_path).name}')
    data = parse_pdf(pdf_path)

    if not data:
        print('    No data extracted.')
        return 0

    saved = 0
    for year, fields in sorted(data.items(), reverse=True):
        non_null = {k: v for k, v in fields.items() if v is not None}
        if not non_null:
            continue
        db.upsert_financials(ticker=ticker, year=year, **non_null)
        summary = ', '.join(f'{k}={v}' for k, v in non_null.items())
        print(f'    Saved {ticker} {year}: {summary}')
        saved += 1

    return saved


# ── Full ticker pipeline ──────────────────────────────────────

def run_for_ticker(session, ticker: str, cmpy_id: str, max_years: int = 5) -> int:
    """
    Discover all annual reports, download and parse each PDF.
    Returns total year-rows saved to the DB.
    """
    ticker = ticker.upper()
    print(f'\n[{ticker}] Fetching annual report list...')

    reports = edge.get_annual_report_edge_nos(session, cmpy_id)
    if not reports:
        print(f'  No annual reports found for {ticker}.')
        return 0

    print(f'  Found {len(reports)} report(s):')
    for r in reports:
        print(f'    {r["date"]:<25}  {r["title"][:60]}')

    total = 0
    seen_years: set[int] = set()

    for report in reports[:max_years]:
        edge_no = report.get('edge_no', '')
        if not edge_no:
            continue

        time.sleep(edge.SCRAPE_DELAY_SECS)
        file_ids = get_file_ids(session, edge_no)
        if not file_ids:
            print(f'    No files for {edge_no[:16]}...')
            continue

        chosen = file_ids[0]
        yr_m = re.search(r'\b(20\d{2})\b', report.get('date', ''))
        fy   = int(yr_m.group(1)) - 1 if yr_m else 0

        if fy in seen_years:
            continue

        print(f'\n  Downloading FY{fy}: {chosen["label"][:60]}')
        pdf_path = download_pdf(session, chosen['file_id'], ticker, fy)
        if not pdf_path:
            continue

        time.sleep(0.5)
        n = parse_and_save(ticker, pdf_path)
        total += n
        if fy:
            seen_years.add(fy)

    return total


# ── CLI ───────────────────────────────────────────────────────

if __name__ == '__main__':
    ap = argparse.ArgumentParser(
        description='PSE Quant - Annual Report PDF Parser',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py scraper/pdf_parser.py --ticker DMC --all
  py scraper/pdf_parser.py --ticker DMC --edge-no 2fd88ba354823b28abca0fa0c5b4e4d0
  py scraper/pdf_parser.py --ticker DMC --pdf "C:\\path\\to\\file.pdf"
        """
    )
    ap.add_argument('--ticker',    required=True, help='Ticker, e.g. DMC')
    ap.add_argument('--edge-no',   dest='edge_no', help='Disclosure popup ID (hex hash)')
    ap.add_argument('--pdf',       help='Path to local PDF file')
    ap.add_argument('--all',       action='store_true', help='Download + parse all annual reports')
    ap.add_argument('--max-years', type=int, default=5)
    args = ap.parse_args()

    db.init_db()

    if args.pdf:
        n = parse_and_save(args.ticker, args.pdf)
        print(f'\nDone -- {n} year(s) saved.')

    elif args.edge_no:
        sess = edge.make_session()
        sess.get(PSE_EDGE_BASE, timeout=20)
        time.sleep(1)

        fids = get_file_ids(sess, args.edge_no)
        if not fids:
            print('No files found for that edge_no.')
            sys.exit(1)

        chosen = fids[0]
        yr_m  = re.search(r'\b20\d{2}\b', chosen['label'])
        fy    = int(yr_m.group()) - 1 if yr_m else 9999

        path = download_pdf(sess, chosen['file_id'], args.ticker, fy)
        if path:
            n = parse_and_save(args.ticker, path)
            print(f'\nDone -- {n} year(s) saved.')

    elif args.all:
        sess    = edge.make_session()
        sess.get(PSE_EDGE_BASE, timeout=20)
        time.sleep(1)

        cmpy_id = edge.lookup_cmpy_id(sess, args.ticker)
        if not cmpy_id:
            print(f'Could not look up cmpy_id for {args.ticker}.')
            sys.exit(1)

        n = run_for_ticker(sess, args.ticker, cmpy_id, max_years=args.max_years)
        print(f'\nDone -- {n} year-row(s) saved for {args.ticker}.')

    else:
        ap.print_help()
