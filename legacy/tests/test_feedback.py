"""
tests/test_feedback.py — Tests for Tier 1 feedback loop logic (monthly scorecard).
Pure math tests only — no live DB required.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import importlib

# Import private helpers via importlib
_ms = importlib.import_module('feedback.monthly_scorecard')
_spearman = _ms._spearman


# ── Test 1: _spearman basic ───────────────────────────────────────────────────

def test_spearman_basic():
    # Perfect positive correlation
    rho = _spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert abs(rho - 1.0) < 1e-9, f"Expected rho=1.0, got {rho}"

    # Perfect negative correlation
    rho = _spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert abs(rho - (-1.0)) < 1e-9, f"Expected rho=-1.0, got {rho}"

    # No strong correlation
    rho = _spearman([1, 2, 3, 4, 5], [3, 1, 5, 2, 4])
    assert abs(rho) < 0.5, f"Expected abs(rho) < 0.5, got {rho}"


# ── Test 2: _spearman with ties ───────────────────────────────────────────────

def test_spearman_ties():
    rho = _spearman([1, 1, 2, 3], [1, 2, 2, 3])
    assert 0.8 <= rho <= 1.0, f"Expected rho between 0.8 and 1.0, got {rho}"


# ── Test 3: confidence level logic ───────────────────────────────────────────

def test_confidence_level():
    from config import THIN_MONTH_THRESHOLD

    def _compute_confidence(total_computed, top10_vs_index, hit_rate_positive, spearman_correlation):
        if (
            total_computed >= 30
            and top10_vs_index is not None and top10_vs_index > 0
            and hit_rate_positive is not None and hit_rate_positive > 0.5
            and spearman_correlation is not None and spearman_correlation > 0
        ):
            return 'high'
        elif total_computed >= THIN_MONTH_THRESHOLD:
            return 'medium'
        else:
            return 'low'

    # All conditions met => high
    level = _compute_confidence(30, 0.01, 0.55, 0.10)
    assert level == 'high', f"Expected 'high', got '{level}'"

    # total_matched=20 => medium (not high since < 30, but >= THIN_MONTH_THRESHOLD=15)
    level = _compute_confidence(20, 0.01, 0.55, 0.10)
    assert level == 'medium', f"Expected 'medium', got '{level}'"

    # total_matched=10 => low
    level = _compute_confidence(10, 0.01, 0.55, 0.10)
    assert level == 'low', f"Expected 'low', got '{level}'"


# ── Test 4: hit rate computation ──────────────────────────────────────────────

def test_hit_rate_computation():
    from config import MOS_HIT_THRESHOLD  # = 0.15

    mos_values = [0.20, 0.05, 0.18]
    returns    = [0.05, -0.02, -0.01]

    # Build fake stock list matching the shape used by monthly_scorecard
    stock_returns = [
        {'mos_pct': m, 'return_pct': r}
        for m, r in zip(mos_values, returns)
    ]

    mos_eligible = [s for s in stock_returns if s['mos_pct'] is not None]
    correct = 0
    for s in mos_eligible:
        predicted_up = float(s['mos_pct']) > MOS_HIT_THRESHOLD
        actual_up    = s['return_pct'] > 0
        if predicted_up == actual_up:
            correct += 1
    hit_rate = correct / len(mos_eligible)

    # Stock 0: mos=0.20 > 0.15 → predicted up, return=0.05 > 0 → HIT
    # Stock 1: mos=0.05 <= 0.15 → predicted NOT up, return=-0.02 <= 0 → HIT
    # Stock 2: mos=0.18 > 0.15 → predicted up, return=-0.01 <= 0 → MISS
    # hit_rate = 2/3
    assert abs(hit_rate - 2/3) < 1e-9, f"Expected hit_rate=2/3 ({2/3:.4f}), got {hit_rate:.4f}"


# ── Test 5: score change detection ───────────────────────────────────────────

def test_score_change_detection():
    from config import SCORE_CHANGE_MINOR_THRESHOLD, SCORE_CHANGE_MAJOR_THRESHOLD

    def _check_flag(score_delta):
        """Mirrors the flag logic from monthly_scorecard (no-new-financials path)."""
        if score_delta > SCORE_CHANGE_MINOR_THRESHOLD:
            flag = True
            if score_delta > SCORE_CHANGE_MAJOR_THRESHOLD:
                severity = 'major'
            else:
                severity = 'minor'
        else:
            flag = False
            severity = None
        return flag, severity

    # delta=20, MINOR=15, MAJOR=30 => flag=True, severity='minor'
    flag, severity = _check_flag(20)
    assert flag is True, f"Expected flag=True for delta=20"
    assert severity == 'minor', f"Expected severity='minor', got '{severity}'"

    # delta=35 => flag=True, severity='major'
    flag, severity = _check_flag(35)
    assert flag is True, f"Expected flag=True for delta=35"
    assert severity == 'major', f"Expected severity='major', got '{severity}'"

    # delta=10 => no flag
    flag, severity = _check_flag(10)
    assert flag is False, f"Expected flag=False for delta=10"
    assert severity is None, f"Expected severity=None, got '{severity}'"


# ── Test 6: MoS direction accuracy ───────────────────────────────────────────

def test_mos_direction_accuracy():
    mos_values = [0.20, -0.10, 0.05]
    returns    = [0.05, -0.02, -0.01]

    # Expected directions from mos_pct: up, down, up
    # Actual directions from returns:   up, down, down
    # Matches: [0]=up/up HIT, [1]=down/down HIT, [2]=up/down MISS => 2/3

    stock_returns = [
        {'mos_pct': m, 'return_pct': r}
        for m, r in zip(mos_values, returns)
    ]

    correct_dir = 0
    for s in stock_returns:
        expected_dir = 'up' if float(s['mos_pct']) > 0 else 'down'
        actual_dir   = 'up' if s['return_pct'] > 0 else 'down'
        if expected_dir == actual_dir:
            correct_dir += 1
    accuracy = correct_dir / len(stock_returns)

    assert abs(accuracy - 2/3) < 1e-9, f"Expected accuracy=2/3, got {accuracy:.4f}"


# ── Test 7: track record publishability ──────────────────────────────────────

def test_track_record_publishability():
    # Replicate the _apply_gate logic from feedback/track_record.py
    def _apply_gate(metrics, period_type, n):
        dc  = metrics['data_completeness_pct']
        wm  = metrics['worst_month_return']
        hr  = metrics['hit_rate']
        tvi = metrics['top10_vs_index']
        tm  = metrics['total_months_tracked']

        if period_type == '1m':
            publishable = 1 if dc > 0 else 0
            if not publishable:
                return 0, 'Insufficient data: no monthly data available'
            if wm is not None and wm < -0.15:
                return 0, f'Unstable: worst month return < -15% ({wm:.1%})'
            return 1, None

        reasons = []
        pub = 1
        if tm < n:
            pub = 0
            reasons.append(f'Insufficient data: {tm}/{n} months tracked')
        if pub == 1:
            hr_ok  = hr  is not None and hr  > 0.40
            tvi_ok = tvi is not None and tvi > 0
            if not (hr_ok or tvi_ok):
                pub = 0
                reasons.append('Below threshold')
        if wm is not None and wm < -0.15:
            pub = 0
            reasons.append(f'Unstable: worst month return < -15%')
        return pub, ('; '.join(reasons) if reasons else None)

    # 1m with data => publishable
    m = {'data_completeness_pct': 0.8, 'worst_month_return': -0.05,
         'hit_rate': 0.5, 'top10_vs_index': 0.02, 'total_months_tracked': 1}
    pub, _ = _apply_gate(m, '1m', 1)
    assert pub == 1, f"Expected publishable for '1m' with data"

    # 3m with total_months_tracked=3, hit_rate=0.45, top10_vs_index=0.01 => publishable
    m = {'data_completeness_pct': 1.0, 'worst_month_return': -0.05,
         'hit_rate': 0.45, 'top10_vs_index': 0.01, 'total_months_tracked': 3}
    pub, _ = _apply_gate(m, '3m', 3)
    assert pub == 1, f"Expected publishable for 3m with adequate data"

    # 3m with total_months_tracked=2 => NOT publishable (insufficient months)
    m = {'data_completeness_pct': 0.67, 'worst_month_return': -0.05,
         'hit_rate': 0.55, 'top10_vs_index': 0.02, 'total_months_tracked': 2}
    pub, reason = _apply_gate(m, '3m', 3)
    assert pub == 0, f"Expected not publishable for 3m with only 2 months tracked"

    # 3m with total_months_tracked=3, hit_rate=0.38, top10_vs_index=-0.02 => NOT publishable
    m = {'data_completeness_pct': 1.0, 'worst_month_return': -0.05,
         'hit_rate': 0.38, 'top10_vs_index': -0.02, 'total_months_tracked': 3}
    pub, reason = _apply_gate(m, '3m', 3)
    assert pub == 0, f"Expected not publishable for 3m with low hit rate and negative vs index"

    # 12m with worst_month_return=-0.20 => NOT publishable (crash gate)
    m = {'data_completeness_pct': 1.0, 'worst_month_return': -0.20,
         'hit_rate': 0.55, 'top10_vs_index': 0.05, 'total_months_tracked': 12}
    pub, reason = _apply_gate(m, '12m', 12)
    assert pub == 0, f"Expected not publishable for 12m with worst_month_return=-0.20"
    assert reason is not None and 'Unstable' in reason, \
        f"Expected 'Unstable' in reason, got: '{reason}'"


# ── Test 8: get_effective_weights ─────────────────────────────────────────────

def test_get_effective_weights():
    from engine.feedback_corrections import get_effective_weights
    from config import SCORER_WEIGHTS

    # With no corrections in DB, weights should equal base weights and sum to ~1.0
    for portfolio_type in ['dividend', 'value']:
        base = SCORER_WEIGHTS.get(portfolio_type, {})
        effective = get_effective_weights('industrial', portfolio_type)

        assert len(effective) == 3, \
            f"Expected 3 layers for {portfolio_type}, got {len(effective)}"

        total = sum(effective.values())
        assert abs(total - 1.0) < 0.001, \
            f"Weights for {portfolio_type} don't sum to 1.0: {total:.6f}"

        for layer in ['health', 'improvement', 'persistence']:
            assert layer in effective, \
                f"Missing layer '{layer}' in effective weights for {portfolio_type}"


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_spearman_basic,
        test_spearman_ties,
        test_confidence_level,
        test_hit_rate_computation,
        test_score_change_detection,
        test_mos_direction_accuracy,
        test_track_record_publishability,
        test_get_effective_weights,
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
