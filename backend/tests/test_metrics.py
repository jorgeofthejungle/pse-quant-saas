"""
Tests for pse_quant.core.metrics
"""

from pse_quant.core.metrics import (
    calculate_pe,
    calculate_pb,
    calculate_roe,
    calculate_de,
    calculate_dividend_yield,
    calculate_payout_ratio,
    calculate_fcf,
    calculate_fcf_yield,
    calculate_fcf_coverage,
    calculate_cagr,
    calculate_ev_ebitda,
    calc_ffo,
    calc_ffo_yield,
    calc_ffo_payout,
)


def test_calculate_pe():
    assert calculate_pe(100.0, 10.0) == 10.0
    assert calculate_pe(11.5, 3.8) == 3.03
    assert calculate_pe(10.0, 0.0) is None
    assert calculate_pe(10.0, -2.0) is None
    assert calculate_pe(None, 5.0) is None


def test_calculate_pb():
    assert calculate_pb(50.0, 25.0) == 2.0
    assert calculate_pb(11.5, 10.45) == 1.1
    assert calculate_pb(10.0, 0.0) is None
    assert calculate_pb(10.0, -5.0) is None


def test_calculate_roe():
    assert calculate_roe(15.0, 100.0) == 15.0
    assert calculate_roe(18500, 119000) == 15.55
    assert calculate_roe(-500, 1000) == -50.0
    assert calculate_roe(100, 0) is None
    assert calculate_roe(100, -500) is None


def test_calculate_de():
    assert calculate_de(50.0, 100.0) == 0.5
    assert calculate_de(59500, 119000) == 0.5
    assert calculate_de(100, 0) is None


def test_calculate_dividend_yield():
    assert calculate_dividend_yield(0.96, 11.50) == 8.35
    assert calculate_dividend_yield(0.0, 10.0) == 0.0
    assert calculate_dividend_yield(1.0, 0.0) is None
    assert calculate_dividend_yield(None, 10.0) is None


def test_calculate_payout_ratio():
    assert calculate_payout_ratio(0.96, 3.80) == 25.26
    assert calculate_payout_ratio(1.0, 0.0) is None
    assert calculate_payout_ratio(1.0, -2.0) is None


def test_calculate_fcf_and_yield():
    fcf = calculate_fcf(22000, 4500)
    assert fcf == 17500.0
    assert calculate_fcf_yield(fcf, 320000) == 5.47
    assert calculate_fcf_coverage(fcf, 9500) == 1.84


def test_calculate_cagr():
    assert calculate_cagr(100.0, 161.051, 5) == 10.0
    assert calculate_cagr(42000, 54500, 4) == 6.73
    assert calculate_cagr(0, 100, 5) is None
    assert calculate_cagr(100, 200, 0) is None


def test_calculate_ev_ebitda():
    assert calculate_ev_ebitda(320000, 59500, 12000, 28000) == 13.12
    assert calculate_ev_ebitda(100, 20, 10, 0) is None


def test_reit_ffo_metrics():
    ffo = calc_ffo(net_income=5000, depreciation=1200, gains_on_sale=200)
    assert ffo == 6000.0
    assert calc_ffo_yield(ffo, 60000) == 10.0
    assert calc_ffo_payout(dps=2.0, shares_outstanding=2500, ffo=ffo) == 83.33
