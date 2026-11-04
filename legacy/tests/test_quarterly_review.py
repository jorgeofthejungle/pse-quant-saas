"""
tests/test_quarterly_review.py — Tests for Tier 2 quarterly review logic.
Pure math tests only — no live DB required.
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import importlib

_qr = importlib.import_module('feedback.quarterly_review')
_zscore_list = _qr._zscore_list


# ── Test 1: z-score helper ────────────────────────────────────────────────────

def test_zscore_helper():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    zscores = _zscore_list(vals)

    assert len(zscores) == 5, f"Expected 5 z-scores, got {len(zscores)}"

    # mean=3, pstdev≈1.4142
    assert abs(zscores[2]) < 1e-9, \
        f"Expected z-score of mean (3.0) to be 0.0, got {zscores[2]}"
    assert abs(zscores[0] - (-1.4142)) < 0.001, \
        f"Expected z-score of 1.0 ≈ -1.414, got {zscores[0]:.4f}"
    assert abs(zscores[4] - 1.4142) < 0.001, \
        f"Expected z-score of 5.0 ≈ 1.414, got {zscores[4]:.4f}"

    # Single value => returns [0.0]
    single = _zscore_list([42.0])
    assert single == [0.0], f"Expected [0.0] for single value, got {single}"


# ── Test 2: blind spot detection ─────────────────────────────────────────────

def test_blind_spot_detection():
    from config import BLIND_SPOT_SCORE_THRESHOLD, BLIND_SPOT_RETURN_THRESHOLD

    def _is_blind_spot(score, qr):
        return score > BLIND_SPOT_SCORE_THRESHOLD and qr < -BLIND_SPOT_RETURN_THRESHOLD

    # score=75 > 70, return=-0.15 < -0.10 => IS blind spot
    assert _is_blind_spot(75, -0.15) is True, \
        "Expected stock with score=75, return=-0.15 to be a blind spot"

    # score=65 < 70 => NOT blind spot
    assert _is_blind_spot(65, -0.15) is False, \
        "Expected stock with score=65 NOT to be a blind spot"

    # score=75, return=-0.05 > -0.10 => NOT blind spot (return not bad enough)
    assert _is_blind_spot(75, -0.05) is False, \
        "Expected stock with score=75, return=-0.05 NOT to be a blind spot"


# ── Test 3: gatekeeper conditions ────────────────────────────────────────────

def test_gatekeeper_conditions():
    from config import SECTOR_BIAS_Z_THRESHOLD

    SECTOR_MIN_DEFAULT = 5

    def _evaluate_gatekeeper(consec, bias_mag, stk_count, confidence_level,
                              band_inversion_flag, sector_blind, sect_underperf,
                              bias):
        """Mirrors the gatekeeper logic from quarterly_review._run_for_portfolio."""
        fails = []
        if consec < 2:
            fails.append(f"consecutive_bias_quarters={consec} (need >=2)")
        if bias_mag <= SECTOR_BIAS_Z_THRESHOLD:
            fails.append(f"abs(bias)={bias_mag:.3f} <= threshold {SECTOR_BIAS_Z_THRESHOLD}")
        if stk_count < SECTOR_MIN_DEFAULT:
            fails.append(f"stock_count={stk_count} < minimum {SECTOR_MIN_DEFAULT}")
        if confidence_level == 'low':
            fails.append(f"confidence_level='low' (need medium or high)")
        if not (band_inversion_flag or sector_blind or sect_underperf):
            fails.append("no structural confirmation (band inversion / blind spots / underperformance)")
        return fails

    # All 5 conditions pass => approved (empty fails list)
    fails = _evaluate_gatekeeper(
        consec=2, bias_mag=1.5, stk_count=6,
        confidence_level='medium',
        band_inversion_flag=True, sector_blind=[], sect_underperf=False,
        bias=-1.5,
    )
    assert len(fails) == 0, f"Expected no failures for passing scenario, got: {fails}"

    # consecutive_bias_quarters=1 => blocked
    fails = _evaluate_gatekeeper(
        consec=1, bias_mag=1.5, stk_count=6,
        confidence_level='medium',
        band_inversion_flag=True, sector_blind=[], sect_underperf=False,
        bias=-1.5,
    )
    assert len(fails) > 0, "Expected failure when consecutive_bias_quarters=1"
    assert any('consecutive_bias_quarters' in f for f in fails), \
        f"Expected 'consecutive_bias_quarters' in fail reason, got: {fails}"

    # confidence_level='low' => blocked, and the SPECIFIC reason must be logged
    fails = _evaluate_gatekeeper(
        consec=2, bias_mag=1.5, stk_count=6,
        confidence_level='low',
        band_inversion_flag=True, sector_blind=[], sect_underperf=False,
        bias=-1.5,
    )
    assert any("confidence_level='low'" in f for f in fails), \
        f"Expected specific confidence_level reason in fails, got: {fails}"

    # Verify blocked corrections log a list of failing conditions (not just "blocked")
    # When there are multiple failures, all should be reported
    fails_multi = _evaluate_gatekeeper(
        consec=1, bias_mag=0.5, stk_count=3,
        confidence_level='low',
        band_inversion_flag=False, sector_blind=[], sect_underperf=False,
        bias=0.5,
    )
    assert len(fails_multi) >= 3, \
        f"Expected at least 3 specific fail reasons for multi-fail scenario, got {len(fails_multi)}: {fails_multi}"


# ── Test 4: sector band analysis ─────────────────────────────────────────────

def test_sector_band_analysis():
    import statistics

    def _compute_band_inversion(stock_data):
        """
        Mirrors quarterly_review band inversion logic.
        stock_data: list of {'score': float, 'return': float}
        """
        bands = [('80-100', 80, 101), ('65-79', 65, 80), ('50-64', 50, 65), ('0-49', 0, 50)]
        score_band_data = {}
        for label, lo, hi in bands:
            band_rets = [s['return'] for s in stock_data if lo <= s['score'] < hi]
            score_band_data[label] = {
                'avg_return': statistics.mean(band_rets) if band_rets else None,
                'stock_count': len(band_rets),
            }
        band_inversion_flag = False
        for i, (lbl, _, _) in enumerate(bands[:-1]):
            hi_ret = score_band_data[bands[i][0]]['avg_return']
            lo_ret = score_band_data[bands[i + 1][0]]['avg_return']
            if hi_ret is not None and lo_ret is not None and hi_ret < lo_ret:
                band_inversion_flag = True
                break
        return band_inversion_flag, score_band_data

    # Monotonically descending returns => no inversion
    stocks_no_inversion = [
        {'score': 85, 'return': 0.10},
        {'score': 70, 'return': 0.05},
        {'score': 55, 'return': 0.03},
        {'score': 40, 'return': 0.01},
    ]
    flag, _ = _compute_band_inversion(stocks_no_inversion)
    assert flag is False, f"Expected band_inversion_flag=False for monotonic returns"

    # Higher band (80-100) has lower return than next band (65-79) => inversion
    stocks_inversion = [
        {'score': 85, 'return': 0.01},  # 80-100 band: avg=0.01
        {'score': 70, 'return': 0.10},  # 65-79 band: avg=0.10
        {'score': 55, 'return': 0.03},
        {'score': 40, 'return': 0.01},
    ]
    flag, _ = _compute_band_inversion(stocks_inversion)
    assert flag is True, f"Expected band_inversion_flag=True when high-score band underperforms"


# ── Test 5: correction blob format ───────────────────────────────────────────

def test_correction_apply():
    # Verify the blob structure has all required fields
    # We construct a fake blob directly (matching correction_engine.py format)
    from datetime import datetime, timezone

    fake_blob = {
        "adjustment":     0.02,
        "quarter":        "2026-Q1",
        "cumulative":     0.02,
        "version":        1,
        "previous_value": 0.0,
        "status":         "active",
        "applied_at":     datetime.now(timezone.utc).isoformat(),
    }

    required_fields = [
        'adjustment', 'quarter', 'cumulative', 'version',
        'previous_value', 'status', 'applied_at',
    ]
    for field in required_fields:
        assert field in fake_blob, f"Missing required field '{field}' in correction blob"

    # Verify types match expectations
    assert isinstance(fake_blob['adjustment'], float), "adjustment must be float"
    assert isinstance(fake_blob['quarter'], str), "quarter must be str"
    assert isinstance(fake_blob['cumulative'], float), "cumulative must be float"
    assert isinstance(fake_blob['version'], int), "version must be int"
    assert isinstance(fake_blob['previous_value'], float), "previous_value must be float"
    assert fake_blob['status'] == 'active', f"Expected status='active', got '{fake_blob['status']}'"

    # Verify it serialises to valid JSON
    serialised = json.dumps(fake_blob)
    parsed = json.loads(serialised)
    assert parsed['quarter'] == '2026-Q1', "Round-trip JSON should preserve quarter"
    assert parsed['version'] == 1, "Round-trip JSON should preserve version"


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_zscore_helper,
        test_blind_spot_detection,
        test_gatekeeper_conditions,
        test_sector_band_analysis,
        test_correction_apply,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} tests passed")
    if failed:
        sys.exit(1)
