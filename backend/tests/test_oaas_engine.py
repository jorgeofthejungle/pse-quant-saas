"""
backend/tests/test_oaas_engine.py — Comprehensive Test Suite for PSE-Native OaaS & Causal Alert Engine
"""

import pytest
import math
from pse_quant.core.oaas_engine import (
    PseStatutoryFees,
    PseTickLadder,
    PseMicrostructureModel,
    PseAlphaEngine,
    CrowdCapacityEngine,
    CausalTransmissionRouter,
    MacroShockVector,
    TickerBetaProfile,
)


class TestPseStatutoryFees:
    def test_fee_rates(self):
        # Buy side = 0.25% + 0.03% (VAT) + 0.005% (SEC) + 0.005% (PSE) + 0.01% (SCCP) = 0.30%
        assert pytest.approx(PseStatutoryFees.buy_side_pct(), rel=1e-5) == 0.00300
        # Sell side = 0.30% + 0.60% (STT) = 0.90%
        assert pytest.approx(PseStatutoryFees.sell_side_pct(), rel=1e-5) == 0.00900
        # Round trip = 1.20% (120 bps)
        assert pytest.approx(PseStatutoryFees.round_trip_statutory_pct(), rel=1e-5) == 0.01200

    def test_fee_calculation_with_broker_floor(self):
        # A tiny trade (PHP 1,000) hits the PHP 20 minimum broker commission floor
        fees = PseStatutoryFees.calculate_exact_fees(buy_value=1_000.0, sell_value=1_000.0)
        assert fees["buy_fee_php"] > 20.0  # includes VAT and exchange fees
        assert fees["effective_round_trip_pct"] > 0.01200  # elevated percentage due to floor


class TestPseTickLadder:
    def test_tick_tiers(self):
        # Test low price penny stock
        tick, lot = PseTickLadder.get_tier(0.42)
        assert tick == 0.0050
        assert lot == 10_000

        # Test middle price tier
        tick, lot = PseTickLadder.get_tier(37.50)
        assert tick == 0.0500
        assert lot == 100

        # Test blue chip tier
        tick, lot = PseTickLadder.get_tier(238.00)
        assert tick == 0.2000
        assert lot == 10

        # Test high price tier
        tick, lot = PseTickLadder.get_tier(890.00)
        assert tick == 0.5000
        assert lot == 10

    def test_discrete_tick_spread(self):
        spread_pct = PseTickLadder.discrete_tick_spread_pct(price=0.50, spread_ticks=1)
        # 0.01 / 0.50 = 2.0%
        assert pytest.approx(spread_pct, rel=1e-4) == 0.0200


class TestPseMicrostructureModel:
    def test_square_root_impact(self):
        # Test impact scales with square root of participation ratio
        impact_100k = PseMicrostructureModel.calculate_price_impact(
            trade_value_php=100_000.0, mdtv_20_php=10_000_000.0, daily_volatility=0.02
        )
        impact_400k = PseMicrostructureModel.calculate_price_impact(
            trade_value_php=400_000.0, mdtv_20_php=10_000_000.0, daily_volatility=0.02
        )
        # sqrt(4) = 2x impact
        assert pytest.approx(impact_400k / impact_100k, rel=1e-3) == 2.0

    def test_total_round_trip_friction(self):
        fric = PseMicrostructureModel.calculate_total_round_trip_friction(
            price=150.0, trade_value_php=50_000.0, mdtv_20_php=100_000_000.0, daily_volatility=0.015
        )
        assert fric["statutory_pct"] == 0.01200
        assert fric["total_friction_bps"] > 120.0


class TestPseAlphaEngine:
    def test_nff_score(self):
        # Positive foreign accumulation
        _, z_nff, score_pos = PseAlphaEngine.calculate_nff_score(
            net_foreign_flow_20d=100_000_000.0,
            total_traded_value_20d=1_000_000_000.0,
            hist_nff_ratio_mean=0.0,
            hist_nff_ratio_std=0.05,
            positive_foreign_days_20d=18,
        )
        assert z_nff > 1.5
        assert score_pos > 0.7

        # Negative foreign dumping
        _, z_dump, score_dump = PseAlphaEngine.calculate_nff_score(
            net_foreign_flow_20d=-200_000_000.0,
            total_traded_value_20d=1_000_000_000.0,
            hist_nff_ratio_mean=0.0,
            hist_nff_ratio_std=0.05,
            positive_foreign_days_20d=2,
        )
        assert z_dump < -2.0
        assert score_dump < -0.8

    def test_hnav_score(self):
        # Non-HoldCo returns 0
        _, _, s_neutral = PseAlphaEngine.calculate_hnav_score(
            is_holdco=False, current_nav_discount=0.30, historical_discount_mean=0.20, historical_discount_std=0.05
        )
        assert s_neutral == 0.0

        # Cheap HoldCo at wide discount
        _, z_nav, s_cheap = PseAlphaEngine.calculate_hnav_score(
            is_holdco=True, current_nav_discount=0.35, historical_discount_mean=0.20, historical_discount_std=0.05
        )
        assert pytest.approx(z_nav, rel=1e-5) == 3.0
        assert s_cheap > 0.9

    def test_tadc_score(self):
        # 10% tax deduction verification
        net_yd, carry_spread, score = PseAlphaEngine.calculate_tadc_score(
            gross_dividend_yield=0.08, is_reit=True, fcf_or_ffo_coverage=1.2, php_10y_bval_rate=0.06
        )
        assert pytest.approx(net_yd, rel=1e-4) == 0.072  # 8% * (1 - 0.10)
        assert pytest.approx(carry_spread, rel=1e-4) == 0.012  # 7.2% - 6.0% = +1.2%
        assert score > 0.0


class TestCrowdCapacityAndFalsification:
    def test_illiq_trap_rejected(self):
        # 3rd-liner illiquid momentum trap must be quarantined
        cap = CrowdCapacityEngine.evaluate_capacity(
            ticker="ILLIQ",
            price=0.42,
            mdtv_20_php=350_000.0,
            active_subscribers=150,
            target_allocation_per_sub_php=50_000.0,
        )
        assert cap["is_quarantined"] is True
        assert len(cap["quarantine_reasons"]) > 0

    def test_jfc_dumping_flagged(self):
        # JFC under foreign distribution
        fric = PseMicrostructureModel.calculate_total_round_trip_friction(
            price=238.0, trade_value_php=50_000.0, mdtv_20_php=185_000_000.0, daily_volatility=0.016
        )
        # Macro shock: US 10Y and USD/PHP surge
        shock = MacroShockVector(z_bsp_rate=0.5, z_us10y_yield=2.2, z_brent_crude=1.8, z_usd_php=2.5, z_msci_flow=-1.9)
        jfc_beta = TickerBetaProfile(beta_bsp=-0.4, beta_us10y=-0.5, beta_brent=-0.6, beta_usdphp=-0.8, beta_msci=1.2)
        macro_disp = CausalTransmissionRouter.calculate_macro_displacement(shock, jfc_beta, daily_volatility=0.016)

        triage = CausalTransmissionRouter.evaluate_triage_gate(
            ticker="JFC",
            price=238.0,
            macro_displacement_pct=macro_disp,
            factor_alpha_pct=-0.02,
            daily_volatility=0.016,
            round_trip_friction_pct=fric["total_friction_pct"],
            is_capacity_quarantined=False,
        )
        # Must be flagged as distribution warning or avoid
        assert "WARNING" in triage["action_channel"] or "AVOID" in triage["action_channel"]
        assert triage["net_return_hurdle_pct"] < 0
