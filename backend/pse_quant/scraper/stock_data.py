"""
pse_quant/scraper/stock_data.py — Stock Quotes & Dividend History Scraper
Scrapes current trading price, market cap, and historical cash dividends from PSE Edge.
"""

from __future__ import annotations
import re
import logging
from datetime import datetime
from typing import Any
from bs4 import BeautifulSoup
from pse_quant.scraper.client import PseEdgeClient

logger = logging.getLogger("pse_quant.scraper.stock_data")

STOCK_DATA_URL = "/companyPage/stockData.do"
DIVIDENDS_LIST_URL = "/companyPage/dividends_and_rights_list.ax"


def _parse_float(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_stock_quote(client: PseEdgeClient, cmpy_id: str) -> dict[str, float | None] | None:
    """
    Scrapes the stockData.do page for a company.
    Returns: {close, market_cap, pe, pb, shares_outstanding}
    """
    resp = client.get(STOCK_DATA_URL, params={"cmpy_id": cmpy_id})
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    result: dict[str, float | None] = {}

    label_patterns = {
        "close": [r"last\s+traded\s+price", r"last\s+price"],
        "market_cap": [r"market\s+cap(?:italization)?"],
        "pe": [r"p/?e\s+ratio", r"price[\s/.]earnings"],
        "pb": [r"p/?bv?\s+ratio", r"price[\s/.]book"],
        "shares_outstanding": [r"outstanding\s+shares", r"listed\s+shares"],
    }

    for row in soup.find_all("tr"):
        for th in row.find_all("th"):
            label = th.get_text(strip=True).lower()
            td = th.find_next_sibling("td")
            if not td:
                continue
            val_text = td.get_text(strip=True)
            if not val_text:
                continue

            for field, patterns in label_patterns.items():
                if field in result:
                    continue
                for pat in patterns:
                    if re.search(pat, label, re.I):
                        parsed = _parse_float(val_text)
                        if parsed is not None:
                            result[field] = parsed
                        break

    return result if result.get("close") else None


def fetch_dividend_history(
    client: PseEdgeClient,
    cmpy_id: str,
    fiscal_year_end_month: int = 12,
) -> list[dict[str, Any]]:
    """
    Scrapes historical cash dividend declarations from PSE Edge.
    Maps dividends to fiscal year based on ex-date.
    Returns list of {'year': int, 'dps': float, 'ex_date': str} sorted newest-first.
    """
    resp = client.get(DIVIDENDS_LIST_URL, params={"cmpy_id": cmpy_id})
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    annual_dps: dict[int, float] = {}

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        div_type = cells[1].get_text(strip=True).upper()
        rate_str = cells[2].get_text(strip=True)
        ex_date_str = cells[5].get_text(strip=True)

        if "CASH" not in div_type:
            continue

        # Extract per share amount (e.g., 'PHP 0.96' or '0.96')
        rate = _parse_float(rate_str)
        if rate is None or rate <= 0:
            continue

        # Extract date
        try:
            dt = datetime.strptime(ex_date_str, "%b %d, %Y")
        except ValueError:
            try:
                dt = datetime.strptime(ex_date_str, "%m-%d-%Y")
            except ValueError:
                continue

        # Map to fiscal year
        if dt.month <= fiscal_year_end_month and fiscal_year_end_month != 12:
            fiscal_year = dt.year - 1
        else:
            fiscal_year = dt.year

        annual_dps[fiscal_year] = annual_dps.get(fiscal_year, 0.0) + rate

    return [
        {"year": yr, "dps": round(total_dps, 4)}
        for yr, total_dps in sorted(annual_dps.items(), reverse=True)
    ]
