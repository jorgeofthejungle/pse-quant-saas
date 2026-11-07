"""
backend/tests/test_golden_math_lock.py — Golden Dataset Math Lock Regression Test Spec
====================================================================================
System Design Pattern: Golden Master / Snapshot Regression Lock.

Ensures that pure quant scoring (Health, Improvement, Persistence) and 3-model
intrinsic valuations (DDM, DCF, EPS-PE) never drift due to accidental formula
edits, refactoring regressions, or numerical precision errors.

Frozen Fixture: tests/fixtures/golden_pse_records.json
Archetypes Tested:
  - AREIT: REIT Archetype (High dividend yield, DDM + DCF focus, low leverage)
  - BDO: Bank Archetype (Deposit-funded leverage exemption, ROE/P-B focus)
  - DMC: Conglomerate Archetype (20% holding-company discount, high FCF/coal dividends)
  - DITO: Distressed Archetype (Capital deficiency, negative equity, non-positive earnings)
"""

import json
from pathlib import Path
import pytest
from pse_quant.core.scoring import score_unified
from pse_quant.core.mos import enrich_stock_valuation

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden_pse_records.json"


@pytest.fixture(scope="module")
def golden_records():
    assert FIXTURE_PATH.exists(), f"Golden fixture missing at {FIXTURE_PATH}"
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TestGoldenMathLock:
    """Verifies that mathematical computations equal frozen baseline down to exact decimal limits."""

    @pytest.mark.parametrize("ticker", ["AREIT", "BDO", "DMC", "DITO"])
    def test_composite_score_and_layers_invariance(self, golden_records, ticker):
        spec = golden_records[ticker]
        stock_input = spec["input_stock"]
        hist_input = spec["input_financials_history"]

        # Run pure deterministic calculation
        score, breakdown = score_unified(stock_input, financials_history=hist_input, portfolio_type="unified")

        # 1. Verify Composite 3-Layer Score & Confidence
        assert score == pytest.approx(spec["expected_score"], abs=0.05), (
            f"[{ticker}] Composite score drifted: got {score}, expected {spec['expected_score']}"
        )
        assert breakdown["confidence"] == pytest.approx(spec["expected_confidence"], abs=0.01)
        assert breakdown["category"] == spec["expected_category"]

        # 2. Verify Exact Sub-Layer Scores
        exp_layers = spec["expected_layers"]
        actual_layers = breakdown["layers"]

        if exp_layers["health"] is not None:
            assert actual_layers["health"]["score"] == pytest.approx(exp_layers["health"], abs=0.1), (
                f"[{ticker}] Health layer drifted"
            )
        if exp_layers["improvement"] is not None:
            assert actual_layers["improvement"]["score"] == pytest.approx(exp_layers["improvement"], abs=0.1), (
                f"[{ticker}] Improvement layer drifted"
            )
        if exp_layers["persistence"] is not None:
            assert actual_layers["persistence"]["score"] == pytest.approx(exp_layers["persistence"], abs=0.1), (
                f"[{ticker}] Persistence layer drifted"
            )

    @pytest.mark.parametrize("ticker", ["AREIT", "BDO", "DMC", "DITO"])
    def test_intrinsic_valuation_and_mos_invariance(self, golden_records, ticker):
        spec = golden_records[ticker]
        stock_input = dict(spec["input_stock"])
        hist_input = spec["input_financials_history"]

        # First score
        score, breakdown = score_unified(stock_input, financials_history=hist_input, portfolio_type="unified")
        stock_input["score"] = score
        stock_input["category"] = breakdown["category"]
        stock_input["breakdown"] = breakdown
        stock_input["confidence"] = breakdown["confidence"]
        stock_input["scoring_group"] = breakdown["scoring_group"]

        # Run valuation enrichment
        enriched = enrich_stock_valuation(stock_input, portfolio_type="unified")

        # 1. Intrinsic Value & Margin of Safety
        exp_iv = spec["expected_intrinsic_value"]
        exp_mos = spec["expected_mos_pct"]
        exp_target = spec["expected_mos_target_price"]

        if exp_iv is None:
            assert enriched.get("intrinsic_value") is None, f"[{ticker}] Expected None IV for distressed stock"
            assert enriched.get("mos_pct") is None
        else:
            assert enriched["intrinsic_value"] == pytest.approx(exp_iv, abs=0.01), (
                f"[{ticker}] Intrinsic Value drifted: got {enriched['intrinsic_value']}, expected {exp_iv}"
            )
            assert enriched["mos_pct"] == pytest.approx(exp_mos, abs=0.05), (
                f"[{ticker}] Margin of Safety drifted: got {enriched['mos_pct']}, expected {exp_mos}"
            )
            if exp_target is not None:
                assert enriched["mos_target_price"] == pytest.approx(exp_target, abs=0.01)

        # 2. Valuation Components (DDM, DCF, EPS-PE)
        exp_components = spec["expected_valuation_components"]
        val_block = enriched.get("valuation", {})

        for model_name in ["ddm", "eps_pe", "dcf"]:
            exp_val = exp_components.get(model_name)
            actual_val = val_block.get(model_name, {}).get("value")

            if exp_val is None:
                assert actual_val is None, f"[{ticker}] Expected None for model {model_name}"
            else:
                assert actual_val == pytest.approx(exp_val, abs=0.01), (
                    f"[{ticker}] Valuation model {model_name} drifted: got {actual_val}, expected {exp_val}"
                )
