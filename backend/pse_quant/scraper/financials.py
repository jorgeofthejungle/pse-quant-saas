"""
pse_quant/scraper/financials.py — Scraper for Annual & Periodic Financial Statements
Parses Balance Sheet, Income Statement, and Cash Flow metrics from PSE Edge financial_reports_view.do.
"""

from __future__ import annotations
import re
import logging
from typing import Any
from bs4 import BeautifulSoup
from pse_quant.scraper.client import PseEdgeClient

logger = logging.getLogger("pse_quant.scraper.financials")

FINANCIAL_REPORTS_VIEW_URL = "/companyPage/financial_reports_view.do"


def detect_financial_unit(soup: BeautifulSoup | None) -> tuple[int, str]:
    """
    Scans HTML text for explicit financial unit indicators.
    Returns (raw_multiplier, unit_label):
      - "in billions"  -> (1_000_000_000, "billions")
      - "in millions"  -> (1_000_000, "millions")
      - "in thousands" -> (1_000, "thousands")
      - "in peso"      -> (1, "peso")
      - not found      -> (1_000_000, "millions_assumed")
    """
    if soup is None:
        return 1_000_000, "millions_assumed"

    text = soup.get_text()

    if re.search(r"in\s+billions", text, re.I):
        return 1_000_000_000, "billions"
    if re.search(r"in\s+millions", text, re.I):
        return 1_000_000, "millions"
    if re.search(r"in\s+thousands", text, re.I):
        return 1_000, "thousands"
    if re.search(r"in\s+(?:philippine\s+)?pesos?", text, re.I):
        return 1, "peso"

    currency_match = re.search(r"[Cc]urrency[^:\n]{0,30}:([^\n]{0,60})", text)
    if currency_match:
        cur_text = currency_match.group(1).lower()
        if "billion" in cur_text:
            return 1_000_000_000, "billions"
        if "million" in cur_text:
            return 1_000_000, "millions"
        if "thousand" in cur_text:
            return 1_000, "thousands"
        if "peso" in cur_text:
            return 1, "peso"

    return 1_000_000, "millions_assumed"


def parse_cell_number(text: str | None) -> float | None:
    """Parses numeric string including parentheses for negatives and comma separation."""
    if not text:
        return None
    cleaned = text.strip().replace("\xa0", "").replace(",", "")
    if cleaned in ("-", "—", "N/A", "n/a", ""):
        return None
    # Handle (123.45) as negative
    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()
    try:
        val = float(cleaned)
        return -val if is_negative else val
    except ValueError:
        return None


FIELD_MAP: dict[str, str] = {
    "gross revenue": "revenue",
    "total revenues": "revenue",
    "total revenue": "revenue",
    "revenues": "revenue",
    "total operating income": "revenue",
    "net income/(loss) attributable to parent": "net_income_parent",
    "net income attributable to parent": "net_income_parent",
    "net income/(loss) after tax": "net_income",
    "net income after tax": "net_income",
    "net income": "net_income",
    "net profit": "net_income",
    "stockholders' equity - parent": "equity_parent",
    "stockholders equity - parent": "equity_parent",
    "stockholders' equity": "equity",
    "stockholders equity": "equity",
    "total equity": "equity",
    "total liabilities": "total_debt",
    "total debt": "total_debt",
    "book value per share": "bvps",
    "earnings/(loss) per share (basic)": "eps",
    "earnings per share (basic)": "eps",
    "earnings per share": "eps",
    "basic earnings per share": "eps",
    "depreciation and amortization": "depreciation",
    "depreciation & amortization": "depreciation",
    "depreciation expense": "depreciation",
    "depreciation": "depreciation",
    "amortization": "amortization",
    "net cash provided by (used in) operating activities": "operating_cash_flow",
    "operating cash flows": "operating_cash_flow",
    "cash flows from operating activities": "operating_cash_flow",
    "capital expenditures": "capital_expenditures",
    "additions to property, plant and equipment": "capital_expenditures",
}


def parse_financial_html(html_content: str, cmpy_id: str = "") -> list[dict[str, Any]]:
    """
    Parses the financial statement HTML from financial_reports_view.do.
    Extracts Current Year and Previous Year financial data normalized into Millions PHP.
    Per-share figures (eps, bvps) remain untouched in raw per-share units.
    """
    soup = BeautifulSoup(html_content, "lxml")
    page_text = soup.get_text()

    # Look for fiscal year statement
    year_matches = re.findall(
        r"[Ff]or the fiscal year ended\s*[:\-]?\s*\w+\s+\d+,?\s*(\d{4})",
        page_text,
    )
    if not year_matches:
        year_matches = re.findall(r"fiscal year.{0,30}(\d{4})", page_text, re.I)

    if not year_matches:
        logger.warning(f"Could not locate fiscal year on financial report page for cmpy_id={cmpy_id}")
        return []

    try:
        current_year = int(year_matches[0])
    except ValueError:
        return []

    prev_year = current_year - 1

    multiplier, unit_label = detect_financial_unit(soup)

    # Multiplier converts raw figure to PHP. We store financial items in Millions PHP.
    # If raw is in thousands: raw * 1,000 / 1,000,000 = raw / 1,000
    # If raw is in millions:  raw * 1,000,000 / 1,000,000 = raw
    # If raw is in billions:  raw * 1,000,000,000 / 1,000,000 = raw * 1,000
    # If raw is in peso:      raw / 1,000,000
    if multiplier == 1:
        to_millions_factor = 1.0 / 1_000_000.0
    elif multiplier == 1_000:
        to_millions_factor = 1.0 / 1_000.0
    elif multiplier == 1_000_000:
        to_millions_factor = 1.0
    elif multiplier == 1_000_000_000:
        to_millions_factor = 1_000.0
    else:
        to_millions_factor = 1.0

    results: dict[int, dict[str, float]] = {current_year: {}, prev_year: {}}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        header_text = " ".join(c.get_text(strip=True).lower() for c in header_cells)
        if "current year" not in header_text or "previous year" not in header_text:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            label = cells[0].get_text(strip=True).lower()
            val_curr = parse_cell_number(cells[1].get_text(strip=True))
            val_prev = parse_cell_number(cells[2].get_text(strip=True))

            matched_field = None
            for pattern, field in FIELD_MAP.items():
                if pattern in label:
                    matched_field = field
                    break

            if not matched_field:
                continue

            if matched_field not in results[current_year] and val_curr is not None:
                results[current_year][matched_field] = val_curr
            if matched_field not in results[prev_year] and val_prev is not None:
                results[prev_year][matched_field] = val_prev

    output: list[dict[str, Any]] = []
    for yr in [current_year, prev_year]:
        data = results[yr]
        if not data:
            continue

        eq = data.get("equity_parent") if data.get("equity_parent") is not None else data.get("equity")
        net_inc = data.get("net_income_parent") if data.get("net_income_parent") is not None else data.get("net_income")

        def _to_m(val: float | None) -> float | None:
            if val is None:
                return None
            return round(val * to_millions_factor, 3)

        row: dict[str, Any] = {
            "year": yr,
            "revenue": _to_m(data.get("revenue")),
            "net_income": _to_m(net_inc),
            "equity": _to_m(eq),
            "total_debt": _to_m(data.get("total_debt")),
            "eps": data.get("eps"),
            "book_value_per_share": data.get("bvps"),
            "depreciation": _to_m(data.get("depreciation")),
            "amortization": _to_m(data.get("amortization")),
            "operating_cash_flow": _to_m(data.get("operating_cash_flow")),
            "capital_expenditures": _to_m(data.get("capital_expenditures")),
            "unit_label": unit_label,
        }

        # Check if we got at least one key field
        if any(v is not None for k, v in row.items() if k not in ("year", "unit_label")):
            output.append(row)

    return output


def fetch_financial_reports(client: PseEdgeClient, cmpy_id: str) -> list[dict[str, Any]]:
    """Fetches financial_reports_view.do from PSE Edge and parses the financial tables."""
    resp = client.get(FINANCIAL_REPORTS_VIEW_URL, params={"cmpy_id": cmpy_id})
    if not resp or len(resp.text) < 300:
        return []
    return parse_financial_html(resp.text, cmpy_id=cmpy_id)
