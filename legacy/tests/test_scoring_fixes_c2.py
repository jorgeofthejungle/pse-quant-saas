"""
C2 scoring fixes — TDD test file.
Red phase: all tests FAIL against current code.
Green phase: pass after adding IV_WEIGHTS_DIVIDEND / IV_WEIGHTS_VALUE to
config.py and wiring portfolio_type into calc_hybrid_intrinsic().

Run: .venv/bin/python tests/test_scoring_fixes_c2.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config
from engine.mos import calc_hybrid_intrinsic

PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'

errors = []


# ── Config constants exist ────────────────────────────────────

def test_iv_weights_dividend_exists():
    ok = hasattr(config, 'IV_WEIGHTS_DIVIDEND') and config.IV_WEIGHTS_DIVIDEND == (0.50, 0.25, 0.25)
    print(f'  [{PASS if ok else FAIL}] IV_WEIGHTS_DIVIDEND == (0.50, 0.25, 0.25): got {getattr(config, "IV_WEIGHTS_DIVIDEND", "MISSING")}')
    if not ok:
        errors.append('iv_weights_dividend_exists')


def test_iv_weights_value_exists():
    ok = hasattr(config, 'IV_WEIGHTS_VALUE') and config.IV_WEIGHTS_VALUE == (0.20, 0.40, 0.40)
    print(f'  [{PASS if ok else FAIL}] IV_WEIGHTS_VALUE == (0.20, 0.40, 0.40): got {getattr(config, "IV_WEIGHTS_VALUE", "MISSING")}')
    if not ok:
        errors.append('iv_weights_value_exists')


# ── calc_hybrid_intrinsic portfolio_type dispatch ─────────────

def test_hybrid_dividend_weights():
    # portfolio_type='dividend' → IV_WEIGHTS_DIVIDEND = (0.50, 0.25, 0.25)
    # 10*0.50 + 20*0.25 + 30*0.25 = 5 + 5 + 7.5 = 17.5
    result, _ = calc_hybrid_intrinsic(10.0, 20.0, 30.0, portfolio_type='dividend')
    ok = result is not None and abs(result - 17.5) < 0.05
    print(f'  [{PASS if ok else FAIL}] hybrid dividend weights: expected 17.5, got {result}')
    if not ok:
        errors.append('hybrid_dividend_weights')


def test_hybrid_value_weights():
    # portfolio_type='value' → IV_WEIGHTS_VALUE = (0.20, 0.40, 0.40)
    # 10*0.20 + 20*0.40 + 30*0.40 = 2 + 8 + 12 = 22.0
    result, _ = calc_hybrid_intrinsic(10.0, 20.0, 30.0, portfolio_type='value')
    ok = result is not None and abs(result - 22.0) < 0.05
    print(f'  [{PASS if ok else FAIL}] hybrid value weights: expected 22.0, got {result}')
    if not ok:
        errors.append('hybrid_value_weights')


def test_hybrid_unified_uses_config_weights():
    # No portfolio_type (or 'unified') → IV_WEIGHTS = (0.30, 0.35, 0.35)
    # 10*0.30 + 20*0.35 + 30*0.35 = 3 + 7 + 10.5 = 20.5
    result, _ = calc_hybrid_intrinsic(10.0, 20.0, 30.0)
    expected = 10.0 * config.IV_WEIGHTS[0] + 20.0 * config.IV_WEIGHTS[1] + 30.0 * config.IV_WEIGHTS[2]
    ok = result is not None and abs(result - expected) < 0.05
    print(f'  [{PASS if ok else FAIL}] hybrid unified uses IV_WEIGHTS: expected {round(expected,2)}, got {result}')
    if not ok:
        errors.append('hybrid_unified_uses_config_weights')


def test_hybrid_dividend_none_ddm_redistributes():
    # DDM=None, eps_pe=20, dcf=30, portfolio_type='dividend'
    # IV_WEIGHTS_DIVIDEND ddm_w=0.50 is dropped; remaining eps_w=0.25, dcf_w=0.25
    # Normalised: each gets 0.25/0.50 = 0.5
    # 20*0.5 + 30*0.5 = 25.0
    result, _ = calc_hybrid_intrinsic(None, 20.0, 30.0, portfolio_type='dividend')
    ok = result is not None and abs(result - 25.0) < 0.05
    print(f'  [{PASS if ok else FAIL}] hybrid dividend None DDM redistributes: expected 25.0, got {result}')
    if not ok:
        errors.append('hybrid_dividend_none_ddm_redistributes')


def test_hybrid_value_none_ddm_redistributes():
    # DDM=None, eps_pe=20, dcf=30, portfolio_type='value'
    # IV_WEIGHTS_VALUE ddm_w=0.20 is dropped; remaining eps_w=0.40, dcf_w=0.40
    # Normalised: each gets 0.40/0.80 = 0.5
    # 20*0.5 + 30*0.5 = 25.0
    result, _ = calc_hybrid_intrinsic(None, 20.0, 30.0, portfolio_type='value')
    ok = result is not None and abs(result - 25.0) < 0.05
    print(f'  [{PASS if ok else FAIL}] hybrid value None DDM redistributes: expected 25.0, got {result}')
    if not ok:
        errors.append('hybrid_value_none_ddm_redistributes')


if __name__ == '__main__':
    print('\nC2 Scoring Fixes — Red/Green Test Suite')
    print('=' * 50)
    print('\nConfig constants:')
    test_iv_weights_dividend_exists()
    test_iv_weights_value_exists()
    print('\ncalc_hybrid_intrinsic portfolio_type dispatch:')
    test_hybrid_dividend_weights()
    test_hybrid_value_weights()
    test_hybrid_unified_uses_config_weights()
    test_hybrid_dividend_none_ddm_redistributes()
    test_hybrid_value_none_ddm_redistributes()
    print()
    if errors:
        print(f'FAILED: {len(errors)} test(s) — {", ".join(errors)}')
        sys.exit(1)
    else:
        print('All tests passed.')
