# ============================================================
# pdf_parser_utils.py — Number parsing, PDF download helpers,
#                        page classification, row extraction
# PSE Quant SaaS — scraper sub-module
# ============================================================

import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scraper'))

import pse_edge_scraper as edge

# ── PDF storage directory ─────────────────────────────────────
RAW_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) \
          / 'pse_quant' / 'raw'

PSE_EDGE_BASE = 'https://edge.pse.com.ph'
DISC_VIEWER   = PSE_EDGE_BASE + '/openDiscViewer.do'
DOWNLOAD_FILE = PSE_EDGE_BASE + '/downloadFile.do'


# ── Number parsing ────────────────────────────────────────────

# Matches: P=1,234,567  or  1,234,567  or  (1,234,567)  or  1.86
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

    def _file_rank(item: dict) -> int:
        lbl = item['label'].lower()
        if any(k in lbl for k in ['sustainability', 'certification', 'cover letter',
                                   'proxy', 'gis', 'minutes']):
            return 10
        if '_afs' in lbl or ' afs' in lbl or 'audited financial' in lbl:
            return 1
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
        resp = session.post(DOWNLOAD_FILE, data={'file_id': file_id}, timeout=120)
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

_IS_CF_RE = re.compile(r'STATEMENTS?\s+OF\s+CASH\s+FLOWS\b', re.I)
_IS_BS_RE = re.compile(
    r'STATEMENTS?\s+OF\s+FINANCIAL\s+POSITION\b|BALANCE\s+SHEETS?\b', re.I)

_UNIT_RE = re.compile(
    r'amounts?\s+in\s+(thousands?|millions?)\s+of\s+(?:philippine\s+)?pesos?|'
    r'in\s+(thousands?|millions?)\s+of\s+(?:philippine\s+)?pesos?|'
    r'\(in\s+(thousands?|millions?)\)|'
    r'amounts\s+are\s+(?:stated|expressed|rounded)\s+in\s+(thousands?|millions?)',
    re.I)

_UNIT_RAW_PESO_RE = re.compile(
    r'all\s+amounts?\s+in\s+philippine\s+peso[^s]|'
    r'amounts?\s+in\s+philippine\s+peso[^s]|'
    r'philippine\s+peso,\s+(?:unless|which)', re.I)

_NUMS_ONLY_RE = re.compile(
    r'^(?:P?=?\s*\(?[\d,]+(?:\.\d+)?\)?)(?:\s+P?=?\s*\(?[\d,]+(?:\.\d+)?\)?){1,2}\s*$'
)


def _has_year_header(text: str, window: int = 600) -> bool:
    """Return True if the top of the page has 2+ fiscal year column headers."""
    for line in text[:window].split('\n'):
        ys = re.findall(r'\b(20\d{2})\b', line)
        if len(ys) >= 2:
            return True
    return False


def _detect_divisor(text: str, default: int = 1_000_000) -> int:
    """Return divisor to convert raw values to millions PHP."""
    m = _UNIT_RE.search(text)
    if m:
        groups = [g for g in m.groups() if g]
        kind = groups[0].lower() if groups else ''
        if 'thousand' in kind:
            return 1_000
        if 'million' in kind:
            return 1
    if _UNIT_RAW_PESO_RE.search(text):
        return default
    return default


def _extract_years(text: str) -> list[int]:
    """Find fiscal year columns from financial statement text."""
    all_years: set[str] = set()
    for line in text.split('\n'):
        if re.search(r'years?\s+ended|december\s+31', line, re.I):
            all_years.update(re.findall(r'\b(20\d{2})\b', line))
    if len(all_years) >= 2:
        return sorted([int(y) for y in all_years], reverse=True)[:3]

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
    """
    lines = text.split('\n')
    label_re = re.compile('|'.join(label_patterns), re.I)

    for i, line in enumerate(lines):
        if not label_re.search(line):
            continue
        for j in range(i, min(i + 4, len(lines))):
            clean = _NOTE_REF_RE.sub('', lines[j])
            nums = _RAW_NUM_RE.findall(clean)
            if len(nums) >= 2:
                tail = nums[-n_cols:]
                vals = [_parse_num(n) for n in tail]
                while len(vals) < n_cols:
                    vals.insert(0, None)
                return vals

    return [None] * n_cols


def _find_revenue_row(text: str, n_cols: int) -> list[float | None]:
    """Extract total revenue. Tries explicit labels first, then unlabeled sum."""
    for lbl in [r'total\s+revenues?', r'net\s+revenues?']:
        vals = _extract_row(text, [lbl], n_cols)
        if any(v is not None for v in vals):
            return vals

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
    """Find capital expenditures in the investing section. Returns absolute values."""
    idx = text.upper().find('INVESTING ACTIVIT')
    chunk = text[idx:] if idx != -1 else text

    for lbl in [
        r'(?:additions\s+to\s+)?property,?\s+plant\s+and\s+equipment',
        r'acquisition\s+of\s+property',
        r'purchase\s+of\s+property',
        r'capital\s+expenditures?',
        r'(?:additions?\s+to\s+)?investment\s+properties?\b',
    ]:
        vals = _extract_row(chunk, [lbl], n_cols)
        if any(v is not None for v in vals):
            return [abs(v) if v is not None else None for v in vals]

    return [None] * n_cols
