"""
pse_quant/scraper/directory.py — Listed Company Directory Scraper
Retrieves PSE listed equities, resolving ticker symbol, company name, cmpy_id, and sector.
"""

from __future__ import annotations
import re
import time
import logging
from typing import Any
from bs4 import BeautifulSoup
from pse_quant.scraper.client import PseEdgeClient
from pse_quant.config import SECTOR_MANUAL_MAP, REIT_WHITELIST, BANK_TICKERS

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
        symbol = cells[1].get_text(strip=True).upper().strip()
        sec = cells[2].get_text(strip=True)

        cmpy_id = None
        # Extract cmpy_id from onclick cmDetail('cmpy_id', 'security_id') or href
        onclick_str = ""
        if name_tag and name_tag.get("onclick"):
            onclick_str = name_tag.get("onclick")
        elif len(cells) > 1 and cells[1].find("a") and cells[1].find("a").get("onclick"):
            onclick_str = cells[1].find("a").get("onclick")
        elif row.get("onclick"):
            onclick_str = row.get("onclick")

        m_click = re.search(r"cmDetail\s*\(\s*['\"](\d+)['\"]", onclick_str)
        if m_click:
            cmpy_id = m_click.group(1)
        elif name_tag and name_tag.get("href"):
            m = re.search(r"cmpy_id=(\d+)", name_tag.get("href"))
            if m:
                cmpy_id = m.group(1)

        if symbol and name:
            companies.append({
                "ticker": symbol,
                "name": name,
                "sector": sec or sector,
                "cmpy_id": cmpy_id,
            })

    return companies


def fetch_all_companies(client: PseEdgeClient) -> list[dict[str, Any]]:
    """
    Scrapes the complete directory across all PSE sectors using a two-phase approach:
    Phase 1: Sector-by-sector directory search (with direct cmpy_id extraction)
    Phase 2: A-Z autocomplete sweep to catch any secondary/unlisted companies
    """
    all_companies: dict[str, dict[str, Any]] = {}

    # Phase 1: Sector search
    for sector in PSE_SECTORS:
        items = fetch_directory_by_sector(client, sector)
        for item in items:
            ticker = item["ticker"]
            if ticker not in all_companies:
                all_companies[ticker] = item

    # Phase 2: A-Z autocomplete sweep
    for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        resp = client.get(AUTOCOMPLETE_URL, params={"term": char})
        if not resp:
            continue
        try:
            items = resp.json()
            if isinstance(items, list):
                for it in items:
                    sym = it.get("symbol", "").upper().strip()
                    if not sym:
                        continue
                    cid = str(it.get("cmpyId", ""))
                    cname = it.get("cmpyNm", "").strip()

                    if sym in all_companies:
                        if not all_companies[sym].get("cmpy_id") and cid:
                            all_companies[sym]["cmpy_id"] = cid
                    else:
                        all_companies[sym] = {
                            "ticker": sym,
                            "name": cname or sym,
                            "sector": "Unknown",
                            "cmpy_id": cid or None,
                        }
        except Exception:
            pass

    # Post-process: Map known sectors and flags
    for ticker, info in all_companies.items():
        if info.get("sector") in ("Unknown", "", None) and ticker in SECTOR_MANUAL_MAP:
            info["sector"] = SECTOR_MANUAL_MAP[ticker]

        info["is_reit"] = (
            ticker in REIT_WHITELIST
            or ticker.endswith("REIT")
            or "REIT" in info.get("name", "").upper()
        )
        info["is_bank"] = (
            ticker in BANK_TICKERS
            or (
                info.get("sector") == "Financials"
                and any(b in info.get("name", "").upper() for b in ("BANK", "BANCORP"))
            )
        )

    return list(all_companies.values())
