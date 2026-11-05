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

    if re.search(r"in\s+billions|\bphp\s+billions\b|amounts\s+in\s+billions", text, re.I):
        return 1_000_000_000, "billions"
    if re.search(r"in\s+millions|\bphp\s+millions\b|amounts\s+in\s+millions|\(in\s+millions\)", text, re.I):
        return 1_000_000, "millions"
    if re.search(r"in\s+thousands|\bphp\s+thousands\b|amounts\s+in\s+thousands|\(in\s+thousands\)|\(in\s+['’]?000s?\)|\bphp\s*['’]000\b", text, re.I):
        return 1_000, "thousands"
    if re.search(r"in\s+(?:philippine\s+)?pesos?|amounts\s+in\s+(?:philippine\s+)?pesos?|exact\s+pesos?|\(in\s+pesos?\)", text, re.I):
        return 1, "peso"

    currency_match = re.search(r"[Cc]urrency[^:\n]{0,30}:([^\n]{0,60})", text)
    if currency_match:
        cur_text = currency_match.group(1).lower()
        if "billion" in cur_text:
            return 1_000_000_000, "billions"
        if "million" in cur_text:
            return 1_000_000, "millions"
        if "thousand" in cur_text or "'000" in cur_text:
            return 1_000, "thousands"
        if "peso" in cur_text and not any(k in cur_text for k in ("million", "billion", "thousand")):
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
    # Revenues / Sales
    "gross revenue": "revenue",
    "total revenues": "revenue",
    "total revenue": "revenue",
    "revenues": "revenue",
    "revenue": "revenue",
    "total operating income": "revenue",
    "operating revenue": "revenue",
    "operating revenues": "revenue",
    "net sales": "revenue",
    "sale of goods": "revenue",
    "service revenues": "revenue",
    "revenues from contracts with customers": "revenue",
    "interest income": "revenue",
    "total interest income": "revenue",
    "gross income": "revenue",

    # Net Income / Profits
    "net income/(loss) attributable to parent": "net_income_parent",
    "net income attributable to parent": "net_income_parent",
    "net income attributable to equity holders": "net_income_parent",
    "net income/(loss) attributable to equity holders": "net_income_parent",
    "net income/(loss) after tax": "net_income",
    "net income after tax": "net_income",
    "net income for the period": "net_income",
    "net income (loss) for the period": "net_income",
    "net income": "net_income",
    "net profit after tax": "net_income",
    "net profit": "net_income",
    "profit for the year": "net_income",
    "profit for the period": "net_income",
    "total comprehensive income": "net_income",

    # Equity / Stockholders' Equity
    "stockholders' equity - parent": "equity_parent",
    "stockholders equity - parent": "equity_parent",
    "equity attributable to equity holders of parent": "equity_parent",
    "equity attributable to equity holders of the parent": "equity_parent",
    "stockholders' equity": "equity",
    "stockholders equity": "equity",
    "total stockholders' equity": "equity",
    "total stockholders equity": "equity",
    "total equity": "equity",

    # Debt / Liabilities
    "total liabilities": "total_debt",
    "total debt": "total_debt",
    "interest-bearing loans": "total_debt",
    "interest-bearing debt": "total_debt",
    "loans payable": "total_debt",
    "long-term debt": "total_debt",
    "short-term debt": "total_debt",

    # Per Share
    "book value per share": "bvps",
    "earnings/(loss) per share (basic)": "eps",
    "earnings per share (basic)": "eps",
    "basic earnings/(loss) per share": "eps",
    "basic earnings per share": "eps",
    "earnings per share": "eps",
    "basic eps": "eps",

    # Depreciation & Cash Flows
    "depreciation and amortization": "depreciation",
    "depreciation & amortization": "depreciation",
    "depreciation expense": "depreciation",
    "depreciation": "depreciation",
    "amortization": "amortization",
    "net cash provided by (used in) operating activities": "operating_cash_flow",
    "net cash provided by operating activities": "operating_cash_flow",
    "net cash flows from operating activities": "operating_cash_flow",
    "cash flows from operating activities": "operating_cash_flow",
    "operating cash flows": "operating_cash_flow",
    "capital expenditures": "capital_expenditures",
    "additions to property, plant and equipment": "capital_expenditures",
    "additions to property, plant & equipment": "capital_expenditures",
    "acquisition of property and equipment": "capital_expenditures",
    "payments for property, plant and equipment": "capital_expenditures",
}


def parse_financial_html(html_content: str, cmpy_id: str = "") -> list[dict[str, Any]]:
    """
    Parses the financial statement HTML from financial_reports_view.do.
    Extracts Current Year and Previous Year financial data normalized into Millions PHP.
    Per-share figures (eps, bvps) remain untouched in raw per-share units.
    """
    soup = BeautifulSoup(html_content, "lxml")
    page_text = soup.get_text()

    # Look for fiscal year statement or period ended statement
    year_matches = re.findall(
        r"(?:for the fiscal year ended|for the year ended|for the period ended|for the quarter ended|fiscal year ended|period ended|as of)\s*[:\-]?\s*[\w\s,.]*?(\b20\d\d\b)",
        page_text,
        re.I,
    )
    if not year_matches:
        year_matches = re.findall(r"\bfiscal year.{0,30}(\b20\d\d\b)", page_text, re.I)

    # Fallback: scan table headers for any 4-digit year
    if not year_matches:
        for th in soup.find_all(["th", "td"]):
            th_txt = th.get_text(strip=True)
            m = re.findall(r"\b(20\d\d)\b", th_txt)
            if m:
                year_matches.extend(m)
                break

    if not year_matches:
        logger.warning(f"Could not locate fiscal year on financial report page for cmpy_id={cmpy_id}")
        return []

    try:
        current_year = int(year_matches[0])
    except ValueError:
        return []

    prev_year = current_year - 1

    multiplier, unit_label = detect_financial_unit(soup)

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

        has_comparative = (
            ("current" in header_text and any(p in header_text for p in ["previous", "prior", "preceding", "same period"]))
            or (len(re.findall(r"\b20\d\d\b", header_text)) >= 2)
        )
        if not has_comparative:
            continue

        # Check column headers for explicit year overrides
        col1_txt = header_cells[1].get_text(strip=True) if len(header_cells) > 1 else ""
        col2_txt = header_cells[2].get_text(strip=True) if len(header_cells) > 2 else ""

        col1_years = re.findall(r"\b(20\d\d)\b", col1_txt)
        col2_years = re.findall(r"\b(20\d\d)\b", col2_txt)

        table_curr_year = int(col1_years[0]) if col1_years else current_year
        table_prev_year = int(col2_years[0]) if col2_years else (table_curr_year - 1)

        if table_curr_year not in results:
            results[table_curr_year] = {}
        if table_prev_year not in results:
            results[table_prev_year] = {}

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

            if matched_field not in results[table_curr_year] and val_curr is not None:
                results[table_curr_year][matched_field] = val_curr
            if matched_field not in results[table_prev_year] and val_prev is not None:
                results[table_prev_year][matched_field] = val_prev

    output: list[dict[str, Any]] = []
    for yr in sorted(results.keys(), reverse=True):
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
