# ============================================================
# pdf_parser_dps.py — DPS extraction from Notes pages
# PSE Quant SaaS — scraper sub-module
# ============================================================

import re

_MONTH_NUM = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

# Pattern A — BOD narrative:
# "On [Month] [Day], [Year], ... declared cash dividends of P[X.XX] per [share]"
# Also handles DMCI format: "amounting to Php X.XX" / "in the amount of Php X.XX"
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
    r'(\w+)\s+\d+,\s+(20\d{2})\s+'
    r'\w+\s+\d+,\s+20\d{2}\s+'
    r'(?:P|PHP|Php)\s*([\d]+\.\d{1,4})\s+P[\d,]',
    re.I,
)

# Pattern C — payment-date reference:
# "P[X.XX] per outstanding [common] share ... paid on [Month] [Day], [Year]"
_DPS_PAT_C = re.compile(
    r'(?:P|PHP|Php)\s*([\d]+\.\d{1,4})\s+per\s+outstanding\s+(?:common\s+)?share'
    r'[^.]{0,200}?paid\s+on\s+(\w+)\s+\d+,\s+(20\d{2})',
    re.I | re.DOTALL,
)

# Pattern D — numbered sub-declarations within a BOD resolution:
# "(1) regular cash dividends in the amount of Php 0.61 per share"
_DPS_PAT_D = re.compile(
    r'\(\d+\)\s+(?:\w+\s+){0,3}cash\s+dividends\s+'
    r'(?:of\s+|amounting\s+(?:to\s+)?|in\s+the\s+amount\s+of\s+)'
    r'(?:P|PHP|Php)\s*([\d]+\.\d{1,4})'
    r'\s+(?:(?:regular|special|cash|stock)\s+dividends?\s+)?per',
    re.I | re.DOTALL,
)

# Pattern E — "and Php X.XX [regular/special] dividends per" continuation
_DPS_PAT_E = re.compile(
    r'\band\s+(?:P|PHP|Php)\s*([\d]+\.\d{1,4})'
    r'\s+(?:(?:regular|special|cash|stock)\s+dividends?\s+)?'
    r'per\s+(?:common\s+|outstanding\s+)?share',
    re.I,
)

# BOD declaration date — used to find year/month for Pattern D/E sub-declarations
_DATE_BOD_RE = re.compile(r'\bOn\s+(\w+)\s+\d+,\s+(20\d{2})\b', re.I)


def _extract_dps_from_notes(all_texts: list[str],
                             known_years: list[int]) -> dict[int, float]:
    """
    Scan Notes pages for explicit dividend-per-share declarations.

    Handles four common Philippine annual report formats:
      A) "On Feb 24, 2022, BOD declared cash dividends of P0.1352 per share"
      B) "Q3 of 2023 Nov 16, 2023 Dec 1, 2023 P0.55 P1,302.73 million ..."
      C) "P0.1495 per outstanding common share ... paid on March 23, 2023"
      D) "(1) regular cash dividends of Php 0.61 per..." — numbered sub-items

    Deduplication uses (amount, year, month) with a +-2-month window to merge
    consolidated/parent-company note duplicates without merging quarterly declarations.

    Returns {year: total_dps} for years in known_years.
    """
    year_set = set(known_years) if known_years else set(range(2018, 2027))
    seen: set[tuple] = set()
    year_dps: dict[int, float] = {}

    def _is_near_seen(amt_r: float, year: int, month: int) -> bool:
        for dm in range(-2, 3):
            if (amt_r, year, month + dm) in seen:
                return True
        return False

    def _record(amt: float, year: int, month: int) -> None:
        if not (0.01 <= amt <= 200):
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

        for m in _DPS_PAT_A.finditer(text):
            try:
                month = _MONTH_NUM.get(m.group(1).lower(), 0)
                year  = int(m.group(2))
                amt   = float(m.group(3))
            except (ValueError, IndexError):
                continue
            _record(amt, year, month)

        for m in _DPS_PAT_B.finditer(text):
            try:
                month = _MONTH_NUM.get(m.group(1).lower(), 0)
                year  = int(m.group(2))
                amt   = float(m.group(3))
            except (ValueError, IndexError):
                continue
            _record(amt, year, month)

        for m in _DPS_PAT_C.finditer(text):
            try:
                amt       = float(m.group(1))
                pay_month = _MONTH_NUM.get(m.group(2).lower(), 0)
                year      = int(m.group(3))
            except (ValueError, IndexError):
                continue
            _record(amt, year, pay_month)

        for m in _DPS_PAT_D.finditer(text):
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
