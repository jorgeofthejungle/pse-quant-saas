"""
Tests for pse_quant.core.filters
"""

from pse_quant.core.filters import filter_unified, filter_unified_batch


def test_filter_unified_healthy_stock():
    stock = {
        "ticker": "DMC",
        "eps_5y": [1.2, 1.1, 0.9, 0.8, 0.7],
        "revenue_5y": [40000, 38000, 35000, 32000, 30000],
        "operating_cf_history": [10000, 9000, 8000],
        "de_ratio": 0.5,
    }
    passed, reason = filter_unified(stock)
    assert passed is True


def test_filter_unified_insufficient_history():
    stock = {
        "ticker": "NEW",
        "eps_5y": [1.0],  # only 1 year
        "revenue_5y": [5000],
    }
    passed, reason = filter_unified(stock)
    assert passed is False
    assert "insufficient EPS history" in reason


def test_filter_unified_negative_earnings():
    stock = {
        "ticker": "LOSS",
        "eps_5y": [-1.0, -0.5, -0.2],
        "revenue_5y": [5000, 4800, 4500],
    }
    passed, reason = filter_unified(stock)
    assert passed is False
    assert "persistent negative earnings" in reason


def test_filter_unified_excessive_leverage():
    # Normal stock capped at 3.0x
    stock = {
        "ticker": "DEBT",
        "eps_5y": [1.0, 1.0],
        "revenue_5y": [5000, 5000],
        "de_ratio": 4.5,
    }
    passed, reason = filter_unified(stock)
    assert passed is False
    assert "excessive leverage" in reason

    # Bank permitted up to 10.0x
    bank_stock = {
        "ticker": "BDO",
        "is_bank": True,
        "eps_5y": [10.0, 9.0],
        "revenue_5y": [50000, 45000],
        "de_ratio": 7.5,
    }
    bank_passed, _ = filter_unified(bank_stock)
    assert bank_passed is True


def test_filter_unified_batch():
    stocks = [
        {"ticker": "GOOD", "eps_5y": [1.0, 1.0], "revenue_5y": [100, 100], "de_ratio": 1.0},
        {"ticker": "BAD", "eps_5y": [1.0], "revenue_5y": [100]},
    ]
    eligible, rejected = filter_unified_batch(stocks)
    assert len(eligible) == 1
    assert eligible[0]["ticker"] == "GOOD"
    assert len(rejected) == 1
    assert rejected[0]["ticker"] == "BAD"
