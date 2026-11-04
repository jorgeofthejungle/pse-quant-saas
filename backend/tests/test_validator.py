"""
Tests for pse_quant.core.validator
"""

from pse_quant.core.validator import (
    validate_stock,
    validate_all,
    detect_and_cap_special_dividend,
)


def test_validate_healthy_stock():
    stock = {
        "ticker": "DMC",
        "current_price": 11.5,
        "roe": 15.5,
        "pb": 1.1,
        "pe": 5.0,
        "dividend_yield": 8.0,
    }
    report = validate_stock(stock)
    assert report["valid"] is True
    assert len(report["errors"]) == 0


def test_validate_missing_price():
    stock = {
        "ticker": "NOPRICE",
        "current_price": None,
        "roe": 15.0,
    }
    report = validate_stock(stock)
    assert report["valid"] is False
    assert any("current_price" in err for err in report["errors"])


def test_validate_hard_block_thresholds():
    # Extreme P/B > 50 -> Hard Block
    stock_pb = {"ticker": "BADPB", "current_price": 5.0, "pb": 75.0}
    report_pb = validate_stock(stock_pb)
    assert report_pb["valid"] is False
    assert any("P/B" in err for err in report_pb["errors"])

    # Extreme ROE < -50 -> Hard Block
    stock_roe = {"ticker": "BADROE", "current_price": 5.0, "roe": -60.0}
    report_roe = validate_stock(stock_roe)
    assert report_roe["valid"] is False
    assert any("ROE" in err for err in report_roe["errors"])


def test_special_dividend_capping():
    # 300% special dividend should be capped to 20%
    stock = {
        "ticker": "SPEC",
        "current_price": 10.0,
        "dividend_yield": 300.0,
        "dps_last": 30.0,
    }
    updated, warns = detect_and_cap_special_dividend(stock)
    assert updated["special_dividend_flag"] is True
    assert updated["dividend_yield"] == 20.0
    assert updated["dps_last"] == 2.0
    assert len(warns) == 1


def test_validate_all():
    stocks = [
        {"ticker": "OK", "current_price": 10.0, "roe": 15.0},
        {"ticker": "BLOCK", "current_price": 10.0, "roe": -70.0},
    ]
    valid_stocks, reports = validate_all(stocks)
    assert len(valid_stocks) == 1
    assert valid_stocks[0]["ticker"] == "OK"
    assert len(reports) == 2
