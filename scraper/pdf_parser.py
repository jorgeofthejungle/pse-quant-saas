# ============================================================
# pdf_parser.py  —  PSE Annual Report PDF Parser
# PSE Quant SaaS — Phase 3
# ============================================================
#
# Downloads and parses SEC Form 17-A annual report PDFs from
# PSE Edge, then saves extracted data to the local database.
#
# Each PDF typically contains 3 years of data in side-by-side
# columns. The parser extracts all 3 years per PDF.
#
# Usage (CLI):
#   py scraper/pdf_parser.py --ticker DMC --all
#       Download + parse all annual reports for DMC.
#
#   py scraper/pdf_parser.py --ticker DMC --edge-no 2fd88ba354823b28abca0fa0c5b4e4d0
#       Download + parse one specific disclosure by edge_no.
#
#   py scraper/pdf_parser.py --ticker DMC --pdf "C:\path\to\file.pdf"
#       Parse a local PDF (no download).
#
# Output: All monetary values saved in millions PHP.
#         EPS/DPS in PHP per share (no scaling).
# ============================================================

import os
import re
import sys
import time
import argparse
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT))

import database as db
import pse_edge_scraper as edge

# ── PDF storage directory ─────────────────────────────────────
RAW_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) \
          / 'pse_quant' / 'raw'

PSE_EDGE_BASE = 'https://edge.pse.com.ph'
DISC_VIEWER   = PSE_EDGE_BASE + '/openDiscViewer.do'
DOWNLOAD_FILE = PSE_EDGE_BASE + '/downloadFile.do'


# ── Number parsing ────────────────────────────────────────────

# Matches: P=1,234,567  or  1,234,567  or  (1,234,567)  or  1.86
# Must contain at least one digit ([\d,]+ alone also matches bare commas).
_RAW_NUM_RE = re.compile(r'P?=?\s*(\(\d[\d,]*(?:\.\d+)?\)|\d[\d,]*(?:\.\d+)?)')

# Strips "(Note X)", "(Notes X, X)" and similar footnote refs from a line
_NOTE_REF_RE = re.compile(r'\(Notes?\s+[\d,\s]+(?:and\s+\d+)?\)', re.I)


def _parse_num(s: str) -> float | None:
    """Parse '1,234,567' or '(1,234,567)' or 'P=1,234,567'. None on failure."""
    if not s:
        return None
    s = s.strip()
    negative = s.startswith('(') and s.endswith(')')
    s = s.strip('()').lstrip('P').lstrip('=').replace(',', '').strip()
    try:
        v = float(s)
        return -v if negative else v
    except ValueError:
        return None


def _to_m(v: float | None, divisor: int) -> float | None:
    """Convert raw value to millions PHP using divisor."""
    return round(v / divisor, 3) if v is not None else None


# ── PDF download helpers ──────────────────────────────────────

def get_file_ids(session: requests.Session, edge_no: str) -> list[dict]:
    """
    Open the PSE Edge disclosure viewer for edge_no.
    Returns list of {file_id, label} for all downloadable files.
    """
    try:
        resp = session.get(DISC_VIEWER, params={'edge_no': edge_no}, timeout=20)
    except Exception as exc:
        print(f'    [pdf] Viewer request failed: {exc}')
        return []

    if not resp or resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, 'lxml')
    sel  = soup.find('select', id='file_list')
    if not sel:
        return []

    results = []
    for opt in sel.find_all('option'):
        fid   = (opt.get('value') or '').strip()
        label = opt.get_text(' ', strip=True)
        if fid:
            results.append({'file_id': fid, 'label': label})

    # Sort: prefer AFS / 17-A / Annual Report over Sustainability/Certification
    def _file_rank(item: dict) -> int:
        lbl = item['label'].lower()
        if any(k in lbl for k in ['sustainability', 'certification', 'cover letter',
                                   'proxy', 'gis', 'minutes']):
            return 10  # deprioritise
        if '_afs' in lbl or ' afs' in lbl or 'audited financial' in lbl:
            return 1   # top priority: dedicated AFS file
        if '17-a' in lbl or '17a' in lbl or 'annual report' in lbl:
            return 2
        return 5

    results.sort(key=_file_rank)
    return results


def download_pdf(session: requests.Session, file_id: str,
                 ticker: str, year: int) -> Path | None:
    """
    Download a PSE Edge PDF via POST to /downloadFile.do.
    Saves to RAW_DIR/{ticker}_{year}.pdf.
    Returns local Path or None on failure.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f'{ticker}_{year}.pdf'

    if out_path.exists():
        print(f'    [pdf] Using cached: {out_path.name}')
        return out_path

    try:
        resp = session.post(DOWNLOAD_FILE, data={'file_id': file_id},
                            timeout=120)
    except Exception as exc:
        print(f'    [pdf] Download error: {exc}')
        return None

    if not resp or resp.status_code != 200:
        print(f'    [pdf] HTTP {resp.status_code if resp else "?"}')
        return None

    if resp.content[:4] != b'%PDF':
        print(f'    [pdf] Not a PDF: {resp.content[:20]!r}')
        return None

    out_path.write_bytes(resp.content)
    print(f'    [pdf] Saved {len(resp.content) // 1024}KB -> {out_path.name}')
    return out_path


# ── Page classification ───────────────────────────────────────

_IS_INCOME_RE = re.compile(
    r'STATEMENTS?\s+OF\s+(?:TOTAL\s+)?(?:COMPREHENSIVE\s+)?INCOME\b|'
    r'STATEMENTS?\s+OF\s+OPERATIONS\b|'
    r'STATEMENTS?\s+OF\s+PROFIT\s+OR\s+LOSS\b', re.I)
# NOTE: 'INCOME STATEMENTS?' deliberately omitted — it matches narrative
# phrases like "income statement accounts" and "income statement analysis".
_IS_CF_RE = re.compile(r'STATEMENTS?\s+OF\s+CASH\s+FLOWS\b', re.I)
_IS_BS_RE = re.compile(
    r'STATEMENTS?\s+OF\s+FINANCIAL\s+POSITION\b|BALANCE\s+SHEETS?\b', re.I)

# Unit detection — covers thousands/millions or raw pesos.
# PSE filings say "of pesos", "of Philippine Peso", or just "(in thousands)".
_UNIT_RE = re.compile(
    r'amounts?\s+in\s+(thousands?|millions?)\s+of\s+(?:philippine\s+)?pesos?|'
    r'in\s+(thousands?|millions?)\s+of\s+(?:philippine\s+)?pesos?|'
    r'\(in\s+(thousands?|millions?)\)|'
    r'amounts\s+are\s+(?:stated|expressed|rounded)\s+in\s+(thousands?|millions?)',
    re.I)
# Detect raw-peso reporting (no thousands/millions qualifier)
_UNIT_RAW_PESO_RE = re.compile(
    r'all\s+amounts?\s+in\s+philippine\s+peso[^s]|'
    r'amounts?\s+in\s+philippine\s+peso[^s]|'
    r'philippine\s+peso,\s+(?:unless|which)', re.I)

_NUMS_ONLY_RE = re.compile(
    r'^(?:P?=?\s*\(?[\d,]+(?:\.\d+)?\)?)(?:\s+P?=?\s*\(?[\d,]+(?:\.\d+)?\)?){1,2}\s*$'
)


def _has_year_header(text: str, window: int = 600) -> bool:
    """
    Return True if the top of the page has a line with 2+ fiscal year
    column headers (e.g. '2023  2022  2021'). This confirms the page is
    an actual financial statement, not a narrative or notes page.
    """
    for line in text[:window].split('\n'):
        ys = re.findall(r'\b(20\d{2})\b', line)
        if len(ys) >= 2:
            return True
    return False


def _detect_divisor(text: str, default: int = 1_000_000) -> int:
    """
    Return divisor to convert raw values to millions PHP.

    `default` lets callers pass the IS divisor as a fallback — some PSE
    filings label the CF page '(All amounts in Philippine Peso)' even
    though the numbers use the same thousands/millions scale as the IS.
    """
    m = _UNIT_RE.search(text)
    if m:
        groups = [g for g in m.groups() if g]
        kind = groups[0].lower() if groups else ''
        if 'thousand' in kind:
            return 1_000
        if 'million' in kind:
            return 1
    # Explicit raw-peso label — trust it only when no IS default is given
    if _UNIT_RAW_PESO_RE.search(text):
        return default  # caller decides: raw peso (1_000_000) or inherit IS
    return default


def _extract_years(text: str) -> list[int]:
    """
    Find fiscal year columns from financial statement text.

    Strategy:
    1. Collect ALL 20xx years that appear on 'years ended / december 31'
       lines — handles multi-line headers like AREIT's
       ('For the year ended … 2023' + 'comparative figures … 2022 and 2021').
    2. Fallback: the line in the first 600 chars that has the most 20xx years.
    """
    # Phase 1: union of years from date-reference lines
    all_years: set[str] = set()
    for line in text.split('\n'):
        if re.search(r'years?\s+ended|december\s+31', line, re.I):
            all_years.update(re.findall(r'\b(20\d{2})\b', line))
    if len(all_years) >= 2:
        return sorted([int(y) for y in all_years], reverse=True)[:3]

    # Phase 2: line with the most 20xx years in the first 600 chars
    best: list[str] = []
    for line in text[:600].split('\n'):
        ys = re.findall(r'\b(20\d{2})\b', line.strip())
        if len(ys) > len(best):
            best = ys
    if len(best) >= 2:
        return [int(y) for y in best[:3]]
    return []


# ── Row value extraction ──────────────────────────────────────

def _extract_row(text: str, label_patterns: list[str],
                 n_cols: int = 3) -> list[float | None]:
    """
    Find a line matching any label_pattern (case-insensitive).
    Extract up to n_cols numbers from that line or the next 3 lines.
    Returns list of floats (None for missing columns).
    """
    lines = text.split('\n')
    label_re = re.compile('|'.join(label_patterns), re.I)

    for i, line in enumerate(lines):
        if not label_re.search(line):
            continue

        # Try this line first, then look ahead
        for j in range(i, min(i + 4, len(lines))):
            # Strip parenthesized footnote refs like "(Note 12)" or "(Notes 1, 2 and 3)"
            clean = _NOTE_REF_RE.sub('', lines[j])
            nums = _RAW_NUM_RE.findall(clean)
            if len(nums) >= 2:
                # Take LAST n_cols numbers: note references always appear BEFORE
                # the financial values in PSE filings (e.g. "Revenue 5,12,16 val1 val2")
                tail = nums[-n_cols:]
                vals = [_parse_num(n) for n in tail]
                while len(vals) < n_cols:
                    vals.insert(0, None)  # pad with None at the front
                return vals

    return [None] * n_cols


def _find_revenue_row(text: str, n_cols: int) -> list[float | None]:
    """
    Extract total revenue. Tries explicit labels first, then finds
    the unlabeled sum row in the REVENUE section.
    """
    # Explicit labeled total — only use patterns that clearly point to a
    # TOTAL line (not a section header or sub-component).
    for lbl in [r'total\s+revenues?', r'net\s+revenues?']:
        vals = _extract_row(text, [lbl], n_cols)
        if any(v is not None for v in vals):
            return vals

    # Unlabeled sum row (numbers-only line after REVENUE section)
    lines = text.split('\n')
    in_revenue = False
    for i, line in enumerate(lines):
        ls = line.strip()
        if re.match(r'REVENUES?\s*[\(\[]?', ls, re.I) and len(ls) < 30:
            in_revenue = True
            continue
        if in_revenue:
            if re.match(r'COSTS?\s+OF\b|GROSS\s+PROFIT\b', ls, re.I):
                break
            if _NUMS_ONLY_RE.match(ls):
                nums = _RAW_NUM_RE.findall(ls)
                if len(nums) >= 2:
                    vals = [_parse_num(n) for n in nums[:n_cols]]
                    while len(vals) < n_cols:
                        vals.append(None)
                    return vals

    return [None] * n_cols


def _find_capex_row(text: str, n_cols: int) -> list[float | None]:
    """
    Find capital expenditures in the investing section.
    Returns absolute values (positive).
    """
    # Restrict to investing section
    idx = text.upper().find('INVESTING ACTIVIT')
    chunk = text[idx:] if idx != -1 else text

    for lbl in [
        r'(?:additions\s+to\s+)?property,?\s+plant\s+and\s+equipment',
        r'acquisition\s+of\s+property',
        r'purchase\s+of\s+property',
        r'capital\s+expenditures?',
        r'(?:additions?\s+to\s+)?investment\s+properties?\b',  # REITs
    ]:
        vals = _extract_row(chunk, [lbl], n_cols)
        if any(v is not None for v in vals):
            return [abs(v) if v is not None else None for v in vals]

    return [None] * n_cols


# ── DPS extractor (Notes) ─────────────────────────────────────

_MONTH_NUM = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

# Pattern A — BOD narrative:
# "On [Month] [Day], [Year], ... declared cash dividends of P[X.XX] per [share]"
# Also handles:
#   "amounting to Php X.XX" and "in the amount of Php X.XX" (DMCI format)
#   "Php 0.72 special dividends per" — optional descriptor between amount and "per"
# Uses re.DOTALL so it spans line breaks often present in PSE PDF text.
_DPS_PAT_A = re.compile(
    r'On\s+(\w+)\s+\d+,\s+(20\d{2})[^.]{0,400}?'
    r'cash\s+dividends\s+'
    r'(?:of\s+|amounting\s+(?:to\s+)?|in\s+the\s+amount\s+of\s+)'
    r'(?:P|PHP|Php)\s*([\d]+\.\d{1,4})'
    r'\s+(?:(?:regular|special|cash|stock)\s+dividends?\s+)?per',
    re.I | re.DOTALL,
)

# Pattern B — quarterly table row (AREIT-style):
# "Q[N] of [applicable_year] [BOD_month] [day], [BOD_year] [rec_date] P[dps] P[total]"
_DPS_PAT_B = re.compile(
    r'Q\d\s+of\s+20\d{2}\s+'
    r'(\w+)\s+\d+,\s+(20\d{2})\s+'       # BOD date: month + year
    r'\w+\s+\d+,\s+20\d{2}\s+'           # record date
    r'(?:P|PHP|Php)\s*([\d]+\.\d{1,4})\s+P[\d,]',  # P[dps] P[total_amount]
    re.I,
)

# Pattern C — payment-date reference:
# "P[X.XX] per outstanding [common] share ... paid on [Month] [Day], [Year]"
# Used when Pattern A doesn't fire (BOD date on a different page).
# DOTALL handles the "per\noutstanding" line-break in some PSE PDFs.
_DPS_PAT_C = re.compile(
    r'(?:P|PHP|Php)\s*([\d]+\.\d{1,4})\s+per\s+outstanding\s+(?:common\s+)?share'
    r'[^.]{0,200}?paid\s+on\s+(\w+)\s+\d+,\s+(20\d{2})',
    re.I | re.DOTALL,
)

# Pattern D — numbered sub-declarations within a BOD resolution:
# "(1) regular cash dividends in the amount of Php 0.61 per share"
# "(2) special cash dividends of Php 0.11 per share"
# Year is found by searching backward for the nearest "On [Month] [Day], [Year]".
_DPS_PAT_D = re.compile(
    r'\(\d+\)\s+(?:\w+\s+){0,3}cash\s+dividends\s+'
    r'(?:of\s+|amounting\s+(?:to\s+)?|in\s+the\s+amount\s+of\s+)'
    r'(?:P|PHP|Php)\s*([\d]+\.\d{1,4})'
    r'\s+(?:(?:regular|special|cash|stock)\s+dividends?\s+)?per',
    re.I | re.DOTALL,
)

# Pattern E — "and Php X.XX [regular/special] dividends per" continuation:
# Captures secondary amounts in a BOD declaration like:
# "declared ... Php 0.34 regular dividends per share and Php 0.14 special dividends per share"
# Year is found by backward scan. Requires "per [common] share" to filter out total amounts.
_DPS_PAT_E = re.compile(
    r'\band\s+(?:P|PHP|Php)\s*([\d]+\.\d{1,4})'
    r'\s+(?:(?:regular|special|cash|stock)\s+dividends?\s+)?'
    r'per\s+(?:common\s+|outstanding\s+)?share',
    re.I,
)

# BOD declaration date — used to find year/month for Pattern D sub-declarations
_DATE_BOD_RE = re.compile(r'\bOn\s+(\w+)\s+\d+,\s+(20\d{2})\b', re.I)


def _extract_dps_from_notes(all_texts: list[str],
                             known_years: list[int]) -> dict[int, float]:
    """
    Scan Notes pages for explicit dividend-per-share declarations.

    Handles four common Philippine annual report formats:
      A) "On Feb 24, 2022, BOD declared cash dividends of P0.1352 per share"
         Also: "amounting to Php X.XX" and "in the amount of Php X.XX" (DMCI)
      B) "Q3 of 2023 Nov 16, 2023 Dec 1, 2023 P0.55 P1,302.73 million ..."
      C) "P0.1495 per outstanding common share ... paid on March 23, 2023"
      D) "(1) regular cash dividends of Php 0.61 per..." — numbered sub-items
         within a BOD resolution; year found by backward scan for "On [date]"

    Deduplication strategy — (amount, year, month) with a ±2-month window:
      - Philippine AFS files have BOTH consolidated AND parent-company notes.
        The same dividend is declared at slightly different BOD dates in each
        section (e.g., Feb for consolidated, Mar for parent) → different months.
      - Using a 2-month proximity window merges these duplicates.
      - Semi-annual / quarterly declarations of the same amount are ≥ 3 months
        apart, so they are NOT merged and both counted correctly.
      - Preferred-share dividends (P0.0047) are excluded via the ≥ 0.01 filter.

    Returns {year: total_dps} for years in known_years.
    """
    year_set = set(known_years) if known_years else set(range(2018, 2027))
    seen: set[tuple] = set()          # (amount_rounded, year, month)
    year_dps: dict[int, float] = {}

    def _is_near_seen(amt_r: float, year: int, month: int) -> bool:
        """True if a ±2-month nearby key is already in seen."""
        for dm in range(-2, 3):
            if (amt_r, year, month + dm) in seen:
                return True
        return False

    def _record(amt: float, year: int, month: int) -> None:
        if not (0.01 <= amt <= 200):    # exclude tiny preferred-share DPS
            return
        if year not in year_set:
            return
        amt_r = round(amt, 4)
        if not _is_near_seen(amt_r, year, month):
            seen.add((amt_r, year, month))
            year_dps[year] = round(year_dps.get(year, 0.0) + amt, 4)

    for text in all_texts:
        if not text or 'dividend' not in text.lower():
            continue

        # Pattern A: BOD narrative declaration
        for m in _DPS_PAT_A.finditer(text):
            try:
                month = _MONTH_NUM.get(m.group(1).lower(), 0)
                year  = int(m.group(2))
                amt   = float(m.group(3))
            except (ValueError, IndexError):
                continue
            _record(amt, year, month)

        # Pattern B: quarterly table (AREIT-style)
        for m in _DPS_PAT_B.finditer(text):
            try:
                month = _MONTH_NUM.get(m.group(1).lower(), 0)
                year  = int(m.group(2))
                amt   = float(m.group(3))
            except (ValueError, IndexError):
                continue
            _record(amt, year, month)

        # Pattern C: payment-date reference
        for m in _DPS_PAT_C.finditer(text):
            try:
                amt       = float(m.group(1))
                pay_month = _MONTH_NUM.get(m.group(2).lower(), 0)
                year      = int(m.group(3))
            except (ValueError, IndexError):
                continue
            _record(amt, year, pay_month)

        # Pattern D: numbered sub-declarations ("(1) regular cash dividends of Php X.XX per")
        # Find the nearest preceding "On [Month] [Day], [Year]" to determine the date.
        for m in _DPS_PAT_D.finditer(text):
            try:
                amt = float(m.group(1))
            except (ValueError, IndexError):
                continue
            # Search backward from this match for the most recent BOD date
            prefix = text[:m.start()]
            date_matches = list(_DATE_BOD_RE.finditer(prefix))
            if not date_matches:
                continue
            dm = date_matches[-1]   # last (nearest) date before this sub-declaration
            try:
                month = _MONTH_NUM.get(dm.group(1).lower(), 0)
                year  = int(dm.group(2))
            except (ValueError, IndexError):
                continue
            _record(amt, year, month)

        # Pattern E: "and Php X.XX [regular/special] dividends per share"
        # Captures secondary amounts in a declaration like
        # "Php 0.34 regular per share and Php 0.14 special dividends per share".
        # Year found by backward scan for nearest BOD date (same as Pattern D).
        for m in _DPS_PAT_E.finditer(text):
            try:
                amt = float(m.group(1))
            except (ValueError, IndexError):
                continue
            prefix = text[:m.start()]
            date_matches = list(_DATE_BOD_RE.finditer(prefix))
            if not date_matches:
                continue
            dm = date_matches[-1]
            try:
                month = _MONTH_NUM.get(dm.group(1).lower(), 0)
                year  = int(dm.group(2))
            except (ValueError, IndexError):
                continue
            _record(amt, year, month)

    return year_dps


# ── Main parser ───────────────────────────────────────────────

def parse_pdf(pdf_path: str | Path) -> dict[int, dict]:
    """
    Parse a PSE annual report PDF.

    Returns a dict keyed by fiscal year:
        {2023: {revenue, net_income, eps, operating_cf, capex,
                cash, equity, total_debt},
         2022: {...},
         2021: {...}}

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
            all_texts  = [page.extract_text() or '' for page in pdf.pages]
            n_pages    = len(all_texts)

            for i, text in enumerate(all_texts):
                if not text.strip():
                    continue
                # Only match pages where the statement header is near the top
                # (first 400 chars) AND the page contains actual financial data.
                top = text[:400].upper()

                # Income statement: must have the header near the top, revenue
                # data present (to exclude OCI-only pages), AND fiscal year
                # column headers present (to exclude narrative/notes pages).
                if (_IS_INCOME_RE.search(top)
                        and 'REVENUE' in text.upper()
                        and _has_year_header(text)):
                    income_pages.append(text)

                # Cash flow: require "CASH FLOWS FROM OPERATING" to be present
                # (rules out TOC/attachments pages that merely list the statement).
                if (_IS_CF_RE.search(top)
                        and 'CASH FLOWS FROM OPERATING' in text.upper()):
                    cf_pages.append(text)
                    # Include next page (statement often continues onto it)
                    if i + 1 < n_pages:
                        next_text = all_texts[i + 1]
                        if next_text.strip() and 'CASH FLOWS FROM' in next_text.upper():
                            cf_pages.append(next_text)

                if (_IS_BS_RE.search(top)
                        and 'TOTAL' in text.upper()):
                    bs_pages.append(text)
    except Exception as e:
        print(f'    [pdf] pdfplumber error: {e}')
        return {}

    if not income_pages and not cf_pages:
        print('    [pdf] No financial statement pages found.')
        return {}

    # Default unit: assume thousands unless IS detects otherwise.
    # CF and BS inherit this so filings that mislabel their CF/BS unit
    # (e.g. write "Philippine Peso" when they mean "thousands") still parse.
    divisor = 1_000_000
    years:  list[int] = []

    # ── Income statement ──────────────────────────────────────
    if income_pages:
        is_text  = income_pages[0]
        years    = _extract_years(is_text)
        n        = len(years) if years else 3
        divisor  = _detect_divisor(is_text)

        rev_vals = _find_revenue_row(is_text, n)

        # Net income: prefer parent-attributable figure to exclude minority
        # interest. Use patterns that match the NET INCOME ATTRIBUTION section
        # (lines WITH numbers) — NOT the EPS section header (no numbers).
        # Avoid r'attributable to equity holders' alone — it also matches
        # "Net income attributable to equity holders of [Company]" in the EPS
        # section header (no numbers on that line), then picks up EPS values.
        ni_vals = _extract_row(is_text, [
            r'equity\s+holders\s+of\s+the\s+parent\s+company',
            r'equity\s+holders\s+of\s+\w',   # "Equity holders of Ayala Land..."
            r'net\s+income\s+attributable\s+to\s+owners',
        ], n)
        if not any(v is not None for v in ni_vals):
            ni_vals = _extract_row(is_text, [
                r'net\s+income\s+after\s+(?:income\s+)?tax',
                r'net\s+income\b',
            ], n)

        # EPS (already per share — divisor=1)
        # NOTE: do NOT use generic 'earnings per share' — the unit header
        # "(Amounts in ... Except for Earnings Per Share Figures)" also matches
        # and appears before the actual EPS row, picking up year column numbers.
        eps_vals = _extract_row(is_text, [
            r'basic/diluted\s+earnings\s+per\s+share',
            r'basic\s+and\s+diluted\s+earnings\s+per\s+share',
            r'basic\s+earnings\s+per\s+share\s+attributable',
            r'basic\s+earnings\s+per\s+share\b',
            r'diluted\s+earnings\s+per\s+share\b',
            r'basic\s+and\s+diluted\b',  # ALI: "Basic and diluted 25 1.63..."
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
        # Inherit IS divisor as default: some filings label CF "(All amounts
        # in Philippine Peso)" even when numbers are in the same thousands/
        # millions scale as the income statement.
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
            r'at\s+december\s+31\b',  # AREIT: "At December 31 2 41,758,546 ..."
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
        bs_text  = bs_pages[0]
        yrs_bs   = _extract_years(bs_text) or (years[:2] if years else [])
        n_bs     = len(yrs_bs) if yrs_bs else 2
        div_bs   = _detect_divisor(bs_text, default=divisor)

        eq_vals = _extract_row(bs_text, [
            r"stockholders'?\s+equity\s*[-–]\s*parent",
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
    # Scan all text pages for explicit dividend-per-share declarations.
    # Only populates DPS for years already in `result` (avoids phantom years).
    if years:
        dps_map = _extract_dps_from_notes(all_texts, years)
        for yr, dps_val in dps_map.items():
            d = result.setdefault(yr, {})
            if 'dps' not in d:      # don't overwrite IS-extracted DPS if any
                d['dps'] = dps_val

    return result


def parse_and_save(ticker: str, pdf_path: str | Path) -> int:
    """
    Parse a PDF and save all extracted years to the database.
    Returns count of year-rows saved.
    """
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

def run_for_ticker(session: requests.Session, ticker: str,
                   cmpy_id: str, max_years: int = 5) -> int:
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

    total  = 0
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
        # Determine FY year: filing date year - 1 (filed in April for prior Dec FY)
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
    ap.add_argument('--ticker', required=True, help='Ticker, e.g. DMC')
    ap.add_argument('--edge-no', dest='edge_no',
                    help='Disclosure popup ID (hex hash)')
    ap.add_argument('--pdf',  help='Path to local PDF file')
    ap.add_argument('--all',  action='store_true',
                    help='Download + parse all annual reports')
    ap.add_argument('--max-years', type=int, default=5)
    args = ap.parse_args()

    db.init_db()

    if args.pdf:
        n = parse_and_save(args.ticker, args.pdf)
        print(f'\nDone — {n} year(s) saved.')

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
            print(f'\nDone — {n} year(s) saved.')

    elif args.all:
        sess    = edge.make_session()
        sess.get(PSE_EDGE_BASE, timeout=20)
        time.sleep(1)

        cmpy_id = edge.lookup_cmpy_id(sess, args.ticker)
        if not cmpy_id:
            print(f'Could not look up cmpy_id for {args.ticker}.')
            sys.exit(1)

        n = run_for_ticker(sess, args.ticker, cmpy_id,
                           max_years=args.max_years)
        print(f'\nDone — {n} year-row(s) saved for {args.ticker}.')

    else:
        ap.print_help()
