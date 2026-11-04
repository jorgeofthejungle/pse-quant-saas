"""
Tests for pse_quant.core.mos
"""

from pse_quant.core.mos import (
    calc_required_return,
    calc_ddm,
    calc_two_stage_ddm,
    calc_eps_pe,
    calc_dcf,
    calc_hybrid_intrinsic,
    calc_mos_pct,
    calc_mos_price,
    apply_conglomerate_discount,
    enrich_stock_valuation,
)


def test_calc_required_return():
    # Large Cap Financial: 6.5% + 5.0% + 0.0% + 0.0% = 11.5%
    r_large = calc_required_return(market_cap=150e9, sector="Financials")
    assert r_large == 0.115

    # Small Cap Mining: 6.5% + 5.0% + 3.0% + 2.0% = 16.5%
    r_mining = calc_required_return(market_cap=10e9, sector="Mining and Oil")
    assert r_mining == 0.165


def test_calc_ddm():
    # DPS = 1.0, g = 5%, r = 11.5% -> DPS1 = 1.05 -> IV = 1.05 / (0.115 - 0.05) = 16.15
    iv, status = calc_ddm(dps_last=1.0, dividend_cagr=5.0, required_return=0.115)
    assert iv == 16.15
    assert "DDM applied" in status

    # Negative / None dps
    iv_none, _ = calc_ddm(dps_last=None, dividend_cagr=5.0)
    assert iv_none is None


def test_calc_eps_pe():
    # Normalised EPS = 2.0, Target PE = 15.0, ROE = 16% (15% premium -> 17.25x) -> IV = 34.50
    iv, status = calc_eps_pe(eps_3y=[2.2, 2.0, 1.8], target_pe=15.0, roe=16.0)
    assert iv == 34.50
    assert "EPS-PE applied" in status


def test_calc_dcf():
    iv, status = calc_dcf(fcf_per_share=2.0, growth_rate=0.06, required_return=0.115)
    assert iv is not None
    assert iv > 20.0
    assert "DCF applied" in status


def test_calc_hybrid_intrinsic():
    # Default weights: (0.30 DDM, 0.35 EPS, 0.35 DCF)
    # 0.30*10 + 0.35*20 + 0.35*30 = 3 + 7 + 10.5 = 20.5
    iv, status = calc_hybrid_intrinsic(ddm_value=10.0, eps_pe_value=20.0, dcf_value=30.0, portfolio_type="unified")
    assert iv == 20.5
    assert "Hybrid blend" in status


def test_apply_conglomerate_discount():
    assert apply_conglomerate_discount(100.0, "Holding Firms") == 80.0
    assert apply_conglomerate_discount(100.0, "Property") == 100.0
    assert apply_conglomerate_discount(None, "Holding Firms") is None


def test_calc_mos_pct_and_price():
    # IV = 100, Price = 80 -> MoS = +20.0%
    assert calc_mos_pct(100.0, 80.0) == 20.0
    # IV = 100, Price = 120 -> MoS = -20.0%
    assert calc_mos_pct(100.0, 120.0) == -20.0
    # MoS Buy Price with 25% target
    assert calc_mos_price(100.0, target_margin=0.25) == 75.0


def test_enrich_stock_valuation():
    stock = {
        "ticker": "DMC",
        "sector": "Holding Firms",
        "market_cap": 120e9,
        "current_price": 10.0,
        "dps_last": 0.96,
        "dividend_cagr_5y": 6.0,
        "eps_3y": [1.5, 1.3, 1.1],
        "roe": 18.0,
        "fcf_per_share": 1.2,
        "revenue_cagr": 7.0,
    }
    enriched = enrich_stock_valuation(stock)
    assert enriched["intrinsic_value"] is not None
    assert enriched["mos_pct"] is not None
    assert enriched["valuation"]["conglomerate_discount_applied"] is True
