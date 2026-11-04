"""
Tests for pse_quant.core.sector_groups
"""

from pse_quant.core.sector_groups import get_scoring_group, describe_group, get_layer_config


def test_bank_resolution():
    assert get_scoring_group({"ticker": "BDO", "sector": "Services"}) == "bank"
    assert get_scoring_group({"ticker": "XYZ", "is_bank": True}) == "bank"
    assert describe_group({"ticker": "BDO"}) == "Bank"


def test_reit_resolution():
    assert get_scoring_group({"ticker": "AREIT", "sector": "Property"}) == "reit"
    assert get_scoring_group({"ticker": "XYZ", "is_reit": True}) == "reit"
    assert describe_group({"ticker": "AREIT"}) == "REIT"


def test_sector_string_resolution():
    assert get_scoring_group({"ticker": "AC", "sector": "Holding Firms"}) == "holding"
    assert get_scoring_group({"ticker": "SMPH", "sector": "Property"}) == "property"
    assert get_scoring_group({"ticker": "NIKL", "sector": "Mining and Oil"}) == "mining"
    assert get_scoring_group({"ticker": "UNKNOWN_TICKER", "sector": "Unknown"}) == "general"


def test_layer_config_retrieval():
    bank_health = get_layer_config("bank", "health")
    assert "roe" in bank_health
    assert "de_ratio" not in bank_health  # Bank excludes D/E
    assert sum(bank_health.values()) == 1.0

    reit_health = get_layer_config("reit", "health")
    assert "dividend_yield" in reit_health
    assert sum(reit_health.values()) == 1.0
