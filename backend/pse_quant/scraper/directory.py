"""
pse_quant/scraper/directory.py — Listed Company Directory Scraper
Retrieves PSE listed equities, resolving ticker symbol, company name, cmpy_id, and sector.
"""

from __future__ import annotations
import re
import logging
from typing import Any
from bs4 import BeautifulSoup
from pse_quant.scraper.client import PseEdgeClient

logger = logging.getLogger("pse_quant.scraper.directory")

AUTOCOMPLETE_URL = "/autoComplete/searchCompanyNameSymbol.ax"
DIRECTORY_SEARCH_URL = "/companyDirectory/search.ax"

PSE_SECTORS = [
    "Financials",
    "Industrial",
    "Holding Firms",
    "Property",
    "Services",
    "Mining and Oil",
]


def lookup_company(client: PseEdgeClient, ticker: str) -> dict[str, str] | None:
    """Resolves a ticker symbol to internal PSE cmpy_id, name, and sector."""
    resp = client.get(AUTOCOMPLETE_URL, params={"term": ticker})
    if not resp:
        return None

    try:
        data = resp.json()
        if not isinstance(data, list):
            return None

        clean_ticker = ticker.upper().strip()
        for item in data:
            if item.get("symbol", "").upper().strip() == clean_ticker:
                return {
                    "ticker": clean_ticker,
                    "name": item.get("cmpyNm", "").strip(),
                    "cmpy_id": str(item.get("cmpyId", "")),
                }

        # Fallback to first item if symbol matched prefix
        if data:
            first = data[0]
            return {
                "ticker": first.get("symbol", "").upper().strip(),
                "name": first.get("cmpyNm", "").strip(),
                "cmpy_id": str(first.get("cmpyId", "")),
            }
    except Exception as e:
        logger.error(f"Error parsing autocomplete response for {ticker}: {e}")

    return None


def fetch_directory_by_sector(client: PseEdgeClient, sector: str) -> list[dict[str, Any]]:
    """Scrapes company directory for a given sector."""
    resp = client.get(DIRECTORY_SEARCH_URL, params={"sector": sector})
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    companies = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        name_tag = cells[0].find("a")
        name = name_tag.get_text(strip=True) if name_tag else cells[0].get_text(strip=True)
        symbol = cells[1].get_text(strip=True)
        sec = cells[2].get_text(strip=True)

        cmpy_id = None
        if name_tag and name_tag.get("href"):
            m = re.search(r"cmpy_id=(\d+)", name_tag.get("href"))
            if m:
                cmpy_id = m.group(1)

        if symbol and name:
            companies.append({
                "ticker": symbol.upper().strip(),
                "name": name,
                "sector": sec or sector,
                "cmpy_id": cmpy_id,
            })

    return companies


def fetch_all_companies(client: PseEdgeClient) -> list[dict[str, Any]]:
    """Scrapes the complete directory across all PSE sectors."""
    all_companies: dict[str, dict[str, Any]] = {}

    for sector in PSE_SECTORS:
        items = fetch_directory_by_sector(client, sector)
        for item in items:
            ticker = item["ticker"]
            if ticker not in all_companies:
                all_companies[ticker] = item

    return list(all_companies.values())
