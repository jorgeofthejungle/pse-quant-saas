"""
C1 scoring fixes — TDD test file.
Red phase: all three tests FAIL against current code.
Green phase: pass after fixes to scorer_improvement, scorer_health, scorer_persistence.

Run: .venv/bin/python tests/test_scoring_fixes_c1.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.scorer_improvement import _momentum_bonus
from engine.scorer_health import _score_eps_stability
from engine.scorer_persistence import _score_direction

PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'

errors = []


# ── Momentum bonus: ±8 ───────────────────────────────────────

def test_momentum_bonus_accelerating():
    # series newest-first: recent 2Y avg change (60%) >> prior 2Y avg change (29.2%)
    # changes: (12-10)/10=20%, (10-5)/5=100%, (5-4)/4=25%, (4-3)/3=33.3%
    # recent_avg=60, prior_avg=29.2 → accelerating → must return +8.0
    series = [12, 10, 5, 4, 3]
    result = _momentum_bonus(series)
    ok = result == 8.0
    print(f'  [{"  " + PASS if ok else FAIL}] momentum_bonus accelerating: expected 8.0, got {result}')
    if not ok:
        errors.append('momentum_bonus_accelerating')


def test_momentum_bonus_decelerating():
    # changes: (10-9)/9=11.1%, (9-8)/8=12.5%, (8-3)/3=166.7%, (3-2)/2=50%
    # recent_avg=11.8, prior_avg=108.3 → decelerating → must return -8.0
    series = [10, 9, 8, 3, 2]
    result = _momentum_bonus(series)
    ok = result == -8.0
    print(f'  [{PASS if ok else FAIL}] momentum_bonus decelerating: expected -8.0, got {result}')
    if not ok:
        errors.append('momentum_bonus_decelerating')


def test_momentum_bonus_insufficient_data():
    # 3 data points → 2 changes → < 4 required → 0.0 always
    series = [10, 8, 6]
    result = _momentum_bonus(series)
    ok = result == 0.0
    print(f'  [{PASS if ok else FAIL}] momentum_bonus insufficient data: expected 0.0, got {result}')
    if not ok:
        errors.append('momentum_bonus_insufficient_data')


# ── EPS stability: floor 15 for shrinking losses ─────────────

def test_eps_stability_shrinking_losses():
    # [-2, -4, -6] newest-first: each value > the next → losses consistently shrinking
    # mean_eps < 0, but trend improving → must return 15.0
    stock = {'eps_5y': [-2.0, -4.0, -6.0]}
    result = _score_eps_stability(stock, 'services')
    ok = result == 15.0
    print(f'  [{PASS if ok else FAIL}] eps_stability shrinking losses: expected 15.0, got {result}')
    if not ok:
        errors.append('eps_stability_shrinking_losses')


def test_eps_stability_erratic_losses():
    # [-5, -2, -8] newest-first: NOT consistently shrinking (jumps around)
    # mean_eps < 0, erratic → must return 5.0 (existing floor)
    stock = {'eps_5y': [-5.0, -2.0, -8.0]}
    result = _score_eps_stability(stock, 'services')
    ok = result == 5.0
    print(f'  [{PASS if ok else FAIL}] eps_stability erratic losses: expected 5.0, got {result}')
    if not ok:
        errors.append('eps_stability_erratic_losses')


def test_eps_stability_positive_mean_unaffected():
    # Positive mean EPS → uses CV path, floor logic not involved
    # eps=[10,10,10] → CV=0 → score=100
    stock = {'eps_5y': [10.0, 10.0, 10.0]}
    result = _score_eps_stability(stock, 'services')
    ok = result is not None and result > 50
    print(f'  [{PASS if ok else FAIL}] eps_stability positive mean unaffected: got {result} (expected >50)')
    if not ok:
        errors.append('eps_stability_positive_mean_unaffected')


# ── Direction sub-score: partial credit ──────────────────────

def test_direction_partial_credit():
    # revenue_5y=[10,8,6] newest-first: rev up in both periods
    # eps_5y=[10,15,12] newest-first: period-0 eps DOWN (10<15), period-1 eps UP (15>12)
    # Period 0: rev_up=True, eps_up=False → one metric up → 0.5 credit
    # Period 1: rev_up=True, eps_up=True  → both up        → 1.0 credit
    # Score: (0.5 + 1.0) / 2 * 100 = 75.0
    stock = {
        'revenue_5y': [10.0, 8.0, 6.0],
        'eps_5y':     [10.0, 15.0, 12.0],
    }
    result = _score_direction(stock, 'services')
    ok = abs(result - 75.0) < 0.1
    print(f'  [{PASS if ok else FAIL}] direction partial credit: expected 75.0, got {result}')
    if not ok:
        errors.append('direction_partial_credit')


def test_direction_both_up_full_credit():
    # All periods both metrics up → 100.0
    stock = {
        'revenue_5y': [10.0, 8.0, 6.0],
        'eps_5y':     [20.0, 15.0, 10.0],
    }
    result = _score_direction(stock, 'services')
    ok = abs(result - 100.0) < 0.1
    print(f'  [{PASS if ok else FAIL}] direction both up full credit: expected 100.0, got {result}')
    if not ok:
        errors.append('direction_both_up_full_credit')


def test_direction_both_down_no_credit():
    # All periods both metrics down → 0.0
    stock = {
        'revenue_5y': [6.0, 8.0, 10.0],
        'eps_5y':     [10.0, 15.0, 20.0],
    }
    result = _score_direction(stock, 'services')
    ok = abs(result - 0.0) < 0.1
    print(f'  [{PASS if ok else FAIL}] direction both down no credit: expected 0.0, got {result}')
    if not ok:
        errors.append('direction_both_down_no_credit')


if __name__ == '__main__':
    print('\nC1 Scoring Fixes — Red/Green Test Suite')
    print('=' * 50)
    print('\nMomentum bonus (±8):')
    test_momentum_bonus_accelerating()
    test_momentum_bonus_decelerating()
    test_momentum_bonus_insufficient_data()
    print('\nEPS stability floor (15 for shrinking losses):')
    test_eps_stability_shrinking_losses()
    test_eps_stability_erratic_losses()
    test_eps_stability_positive_mean_unaffected()
    print('\nDirection partial credit (0.5 for one-up):')
    test_direction_partial_credit()
    test_direction_both_up_full_credit()
    test_direction_both_down_no_credit()
    print()
    if errors:
        print(f'FAILED: {len(errors)} test(s) — {", ".join(errors)}')
        sys.exit(1)
    else:
        print('All tests passed.')
