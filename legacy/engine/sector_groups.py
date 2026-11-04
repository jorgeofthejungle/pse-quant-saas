# ============================================================
# sector_groups.py — Scoring Group Resolution
# PSE Quant SaaS
# ============================================================
# Maps each stock to one of 7 scoring groups:
#   bank, reit, holding, property, industrial, mining, services
#
# Priority order:
#   1. is_bank flag (or BANK_TICKERS whitelist)
#   2. is_reit flag (or REIT_WHITELIST)
#   3. PSE sector string
#   4. fallback → 'services' (general config)
# ============================================================

from __future__ import annotations
from config import REIT_WHITELIST, BANK_TICKERS, SECTOR_SCORING_CONFIG


# PSE sector string → scoring group
_SECTOR_TO_GROUP: dict[str, str] = {
    'Financials':    'services',   # non-bank financials (brokers, insurance)
    'Industrial':    'industrial',
    'Holding Firms': 'holding',
    'Property':      'property',
    'Services':      'services',
    'Mining and Oil': 'mining',
}


def get_scoring_group(stock: dict) -> str:
    """
    Resolve which scoring group applies to this stock.

    Returns one of: 'bank', 'reit', 'holding', 'property',
                    'industrial', 'mining', 'services', 'general'
    """
    ticker = stock.get('ticker', '')

    # 1. Bank check (flag or whitelist)
    if stock.get('is_bank') or ticker in BANK_TICKERS:
        return 'bank'

    # 2. REIT check (flag or whitelist)
    if stock.get('is_reit') or ticker in REIT_WHITELIST:
        return 'reit'

    # 3. PSE sector string
    sector = (stock.get('sector') or '').strip()
    if sector in _SECTOR_TO_GROUP:
        return _SECTOR_TO_GROUP[sector]

    # 4. Fallback
    return 'general'


def get_layer_config(group: str, layer: str) -> dict[str, float]:
    """
    Return sub-score weights for a given scoring group and layer.

    Args:
        group: scoring group from get_scoring_group()
        layer: 'health' | 'improvement' | 'persistence'

    Returns:
        dict mapping sub-score name → weight (weights sum to 1.0)
    """
    cfg = SECTOR_SCORING_CONFIG.get(group) or SECTOR_SCORING_CONFIG['general']
    return cfg.get(layer, {})


def describe_group(stock: dict) -> str:
    """Human-readable label for the scoring group (for PDF/debug output)."""
    labels = {
        'bank':       'Bank',
        'reit':       'REIT',
        'holding':    'Conglomerate',
        'property':   'Property',
        'industrial': 'Industrial',
        'mining':     'Mining & Oil',
        'services':   'Services',
        'general':    'General',
    }
    return labels.get(get_scoring_group(stock), 'General')
