"""
backend/tests/test_fact_compiler.py — Verification Suite for Taglish Fact Card, Hype Check & PWYC
=================================================================================================
Tests:
1. 4-Part Taglish Fact Card (Verdict, Peso Value Test, Net Dividend per ₱10k, Health — zero board lot clutter).
2. Seasoned Numbers toggle payload (3-Layer scores, Intrinsic Value, MoS %, Net Dividend Yield, ROE, D/E).
3. Goal Bucket Classification & Hype Trap Quarantine (DITO, ILLIQ).
4. /api/v1/reports/done-for-you REST endpoint with FB Group Hype Check lookup.
5. PWYC (Pay-What-You-Can) checkout boundaries (₱49 floor enforced, community impact note returned).
"""

import pytest
from fastapi.testclient import TestClient
from pse_quant.api.main import app
from pse_quant.core.fact_compiler import DoneForYouFactCompiler


@pytest.fixture
def client():
    return TestClient(app)


class TestDoneForYouFactCompiler:
    def test_areit_fact_card_and_seasoned_numbers(self):
        stock = {
            "rank": 1,
            "ticker": "AREIT",
            "name": "AREIT, Inc.",
            "sector": "Property",
            "score": 73.0,
            "health_score": 78.5,
            "improvement_score": 69.0,
            "persistence_score": 71.5,
            "confidence": 1.0,
            "category": "Highest Quality",
            "current_price": 36.50,
            "intrinsic_value": 46.84,
            "mos_pct": 22.1,
            "dividend_yield": 7.15,
            "roe": 12.8,
            "debt_to_equity": 0.36,
        }
        res = DoneForYouFactCompiler.compile_stock_option(stock)
        assert res["bucket_tag"] == "PASSIVE_INCOME_CHAMPION"

        fc = res["fact_card"]
        sn = res["seasoned_numbers"]

        # Verify 4 core Fact Card fields (and no board lot clutter)
        assert "verdict" in fc
        assert "peso_value_test" in fc
        assert "net_dividend_per_10k" in fc
        assert "health" in fc
        assert "starting_pocket_fact" not in fc

        # Peso Value Test: 36.50 / 46.84 = 0.78
        assert "₱0.78 for every ₱1.00" in fc["peso_value_test"]

        # Net dividend per ₱10k: 7.15 * 0.90 = 6.44% -> ₱644/year
        assert sn["net_dividend_yield_pct"] == pytest.approx(6.44, rel=1e-2)
        assert sn["net_annual_cash_per_10k_php"] == pytest.approx(644.0, rel=1e-2)
        assert "₱644/year" in fc["net_dividend_per_10k"]

    def test_undervalued_blue_chip_bdo(self):
        stock = {
            "rank": 3,
            "ticker": "BDO",
            "name": "BDO Unibank",
            "sector": "Banks",
            "score": 71.4,
            "current_price": 148.50,
            "intrinsic_value": 182.00,
            "mos_pct": 18.4,
            "dividend_yield": 2.65,
            "roe": 15.2,
            "debt_to_equity": 0.85,
        }
        res = DoneForYouFactCompiler.compile_stock_option(stock)
        assert res["bucket_tag"] == "UNDERVALUED_BLUE_CHIP"
        assert "₱0.82 for every ₱1.00" in res["fact_card"]["peso_value_test"]

    def test_hype_trap_quarantine(self):
        trap = {
            "rank": 99,
            "ticker": "DITO",
            "name": "DITO CME Holdings Corp.",
            "sector": "Services",
            "score": 28.5,
            "current_price": 1.65,
            "intrinsic_value": 0.75,
            "mos_pct": -120.0,
            "dividend_yield": 0.0,
            "roe": -18.5,
            "debt_to_equity": 4.20,
        }
        res = DoneForYouFactCompiler.compile_stock_option(trap)
        assert res["bucket_tag"] == "VALUE_OR_HYPE_TRAP"
        assert "Iwas muna" in res["fact_card"]["verdict"]


class TestPwycAndMenuApi:
    def test_done_for_you_menu_with_hype_check(self, client):
        resp = client.get("/api/v1/reports/done-for-you?goal=all&hype_check_ticker=DITO")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hype_check_ticker"] == "DITO"
        assert data["hype_check_result"] is not None
        assert data["hype_check_result"]["ticker"] == "DITO"
        assert data["hype_check_result"]["bucket_tag"] == "VALUE_OR_HYPE_TRAP"
        assert data["teaser_sample"] is not None
        assert len(data["pwyc_tiers"]) == 3

    def test_pwyc_checkout_tiers_and_floor(self, client):
        # 1. Below ₱49 floor is rejected (422)
        low_resp = client.post(
            "/api/v1/customers/on-demand-checkout",
            json={"email": "bot@spam.ph", "amount_php": 10.0, "payment_method": "gcash"},
        )
        assert low_resp.status_code == 422

        # 2. Starter PWYC Pass (₱99) with Hype Check ticker succeeds
        starter_resp = client.post(
            "/api/v1/customers/on-demand-checkout",
            json={
                "email": "student@up.edu.ph",
                "amount_php": 99.0,
                "payment_method": "gcash",
                "investor_goal": "dividend",
                "hype_check_ticker": "JFC",
            },
        )
        assert starter_resp.status_code == 200
        s_data = starter_resp.json()
        assert s_data["amount_paid_php"] == 99.0
        assert "Starter Community Pass" in s_data["pwyc_impact_note"]

        # 3. Seasoned Supporter PWYC Pass (₱500) computes Pay-It-Forward impact
        supporter_resp = client.post(
            "/api/v1/customers/on-demand-checkout",
            json={
                "email": "seasoned@investor.ph",
                "amount_php": 500.0,
                "payment_method": "maya",
                "investor_goal": "value",
            },
        )
        assert supporter_resp.status_code == 200
        sup_data = supporter_resp.json()
        assert sup_data["amount_paid_php"] == 500.0
        assert "Pay-It-Forward Impact" in sup_data["pwyc_impact_note"]
