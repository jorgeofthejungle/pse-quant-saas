"""
C3 scoring fixes — TDD test file.
Red phase: CONFIDENCE_TIERS[2] == 0.65 → FAIL (expected 0.60).
Green phase: pass after updating config.py.

Run: .venv/bin/python tests/test_scoring_fixes_c3.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config

PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'

errors = []


# ── Confidence tier multipliers ───────────────────────────────

def test_confidence_tier_2yr():
    # 2-year data → multiplier changed from 0.65 to 0.60
    # Rationale: 2yr is the absolute minimum; heavier penalty reflects
    # the higher model uncertainty at that data depth.
    got = config.CONFIDENCE_TIERS.get(2)
    ok  = got == 0.60
    print(f'  [{PASS if ok else FAIL}] CONFIDENCE_TIERS[2] == 0.60: got {got}')
    if not ok:
        errors.append('confidence_tier_2yr')


def test_confidence_tier_full_structure():
    # Verify all tiers are intact and in expected order
    expected = {5: 1.00, 4: 0.90, 3: 0.80, 2: 0.60, 1: 0.00}
    got = config.CONFIDENCE_TIERS
    ok  = got == expected
    print(f'  [{PASS if ok else FAIL}] full CONFIDENCE_TIERS structure: got {got}')
    if not ok:
        errors.append('confidence_tier_full_structure')


def test_confidence_tiers_monotonic():
    # Each tier's multiplier must be strictly greater than the tier below it
    tiers = sorted(config.CONFIDENCE_TIERS.items())  # ascending by key
    ok = all(tiers[i][1] < tiers[i + 1][1] for i in range(len(tiers) - 1))
    print(f'  [{PASS if ok else FAIL}] tiers are strictly monotonic')
    if not ok:
        errors.append('confidence_tiers_monotonic')


if __name__ == '__main__':
    print('\nC3 Scoring Fixes — Red/Green Test Suite')
    print('=' * 50)
    print('\nData confidence tiers:')
    test_confidence_tier_2yr()
    test_confidence_tier_full_structure()
    test_confidence_tiers_monotonic()
    print()
    if errors:
        print(f'FAILED: {len(errors)} test(s) — {", ".join(errors)}')
        sys.exit(1)
    else:
        print('All tests passed.')
