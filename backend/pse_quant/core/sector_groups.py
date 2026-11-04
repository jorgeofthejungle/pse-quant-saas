"""
pse_quant/core/sector_groups.py — Sector Classification & Scoring Groups
Resolves stocks into one of 7 scoring archetypes:
bank, reit, holding, property, industrial, mining, services.
"""

from __future__ import annotations
from typing import Any
from pse_quant.config import REIT_WHITELIST, BANK_TICKERS, SECTOR_SCORING_CONFIG, SECTOR_MANUAL_MAP

_SECTOR_TO_GROUP: dict[str, str] = {
    "Financials":     "services",   # Non-bank financials (brokers, finance houses)
    "Industrial":     "industrial",
    "Holding Firms":  "holding",
    "Property":       "property",
    "Services":       "services",
    "Mining and Oil": "mining",
}


def get_scoring_group(stock: dict[str, Any]) -> str:
    """
    Resolves the scoring archetype group for a stock.
    Priority:
      1. is_bank flag or BANK_TICKERS whitelist
      2. is_reit flag or REIT_WHITELIST
      3. Sector from SECTOR_MANUAL_MAP (if unknown or corrected)
      4. PSE sector string
      5. Fallback -> 'general' (which inherits 'services')
    """
    ticker = (stock.get("ticker") or "").upper().strip()

    # 1. Banks
    if stock.get("is_bank") or ticker in BANK_TICKERS:
        return "bank"

    # 2. REITs
    if stock.get("is_reit") or ticker in REIT_WHITELIST:
        return "reit"

    # 3. Sector string (resolve manual overrides if needed)
    raw_sector = (stock.get("sector") or "").strip()
    sector = SECTOR_MANUAL_MAP.get(ticker, raw_sector)

    if sector in _SECTOR_TO_GROUP:
        return _SECTOR_TO_GROUP[sector]

    return "general"


def get_layer_config(group: str, layer: str) -> dict[str, float]:
    """Retrieves sub-score weights for a specific scoring group and layer."""
    cfg = SECTOR_SCORING_CONFIG.get(group) or SECTOR_SCORING_CONFIG["general"]
    return cfg.get(layer, {})


def describe_group(stock: dict[str, Any]) -> str:
    """Human-readable display name for the scoring group."""
    labels = {
        "bank":       "Bank",
        "reit":       "REIT",
        "holding":    "Conglomerate",
        "property":   "Property",
        "industrial": "Industrial",
        "mining":     "Mining & Oil",
        "services":   "Services",
        "general":    "General",
    }
    return labels.get(get_scoring_group(stock), "General")
