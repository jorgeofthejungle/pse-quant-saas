# ============================================================
# test_filters_v2.py — Tests for the Unified Health Filter
# PSE Quant SaaS — Phase 9B
# ============================================================
# Run: py tests/test_filters_v2.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.filters_v2 import filter_unified, filter_unified_batch

# ── Fixtures ─────────────────────────────────────────────────

PASS_STOCK = {
    'ticker': 'OK',  'name': 'OK Corp', 'sector': 'Industrials',
    'is_reit': False, 'is_bank': False,
    'de_ratio': 1.5,
    'eps_3y': [1.5, 1.3, 1.1],
    'revenue_5y': [20000, 18000, 16000],
    'operating_cf_history': [4000, 3500, 3200],
}

# ── Filter pass ──────────────────────────────────────────────

def test_healthy_stock_passes():
    eligible, reason = filter_unified(PASS_STOCK)
    assert eligible, f"Healthy stock should pass. Reason: {reason}"
    print('  healthy stock passes: PASS')


# ── Minimum data requirement ─────────────────────────────────

def test_insufficient_eps_data():
    s = dict(PASS_STOCK, eps_3y=[1.5, 1.3])
    eligible, reason = filter_unified(s)
    assert not eligible, "Should fail: only 2 EPS years"
    assert 'EPS' in reason or 'data' in reason.lower()
    print('  insufficient EPS data rejected: PASS')


def test_insufficient_revenue_data():
    s = dict(PASS_STOCK, revenue_5y=[20000, 18000])
    eligible, reason = filter_unified(s)
    assert not eligible, "Should fail: only 2 revenue years"
    print('  insufficient revenue data rejected: PASS')


def test_missing_eps_data():
    s = dict(PASS_STOCK, eps_3y=None)
    eligible, reason = filter_unified(s)
    assert not eligible
    print('  missing EPS data rejected: PASS')


# ── Negative earnings filter ─────────────────────────────────

def test_negative_3y_avg_eps_rejected():
    s = dict(PASS_STOCK, eps_3y=[-0.5, -0.3, -0.2])
    eligible, reason = filter_unified(s)
    assert not eligible, "Should fail: negative 3Y avg EPS"
    print('  negative 3Y avg EPS rejected: PASS')


def test_mostly_negative_eps_rejected():
    # Two negatives, one small positive → avg negative
    s = dict(PASS_STOCK, eps_3y=[-1.0, -0.5, 0.1])
    eligible, reason = filter_unified(s)
    assert not eligible
    print('  mostly negative EPS rejected: PASS')


def test_borderline_positive_eps_passes():
    # Avg = (0.1 + 0.2 + 0.3) / 3 = 0.2 > 0
    s = dict(PASS_STOCK, eps_3y=[0.1, 0.2, 0.3])
    eligible, reason = filter_unified(s)
    assert eligible, f"Positive avg EPS should pass. Reason: {reason}"
    print('  positive avg EPS passes: PASS')


# ── Consecutive negative OCF filter ──────────────────────────

def test_two_consecutive_negative_ocf_rejected():
    s = dict(PASS_STOCK, operating_cf_history=[-200, -500, 3200])
    eligible, reason = filter_unified(s)
    assert not eligible, "Should fail: 2 consecutive negative OCF"
    print('  2 consecutive negative OCF rejected: PASS')


def test_one_negative_ocf_passes():
    # Only 1 consecutive negative → should pass
    s = dict(PASS_STOCK, operating_cf_history=[-200, 3500, 3200])
    eligible, reason = filter_unified(s)
    assert eligible, f"One negative OCF should still pass. Reason: {reason}"
    print('  1 negative OCF passes: PASS')


# ── D/E ratio limits ─────────────────────────────────────────

def test_non_bank_de_limit():
    s = dict(PASS_STOCK, de_ratio=3.1, is_bank=False)
    eligible, reason = filter_unified(s)
    assert not eligible, "Non-bank D/E > 3.0 should fail"
    print('  non-bank D/E > 3.0 rejected: PASS')


def test_non_bank_de_at_limit_passes():
    s = dict(PASS_STOCK, de_ratio=3.0, is_bank=False)
    eligible, reason = filter_unified(s)
    assert eligible, f"D/E = 3.0 should pass. Reason: {reason}"
    print('  non-bank D/E = 3.0 passes: PASS')


def test_bank_de_limit():
    s = dict(PASS_STOCK, de_ratio=10.5, is_bank=True)
    eligible, reason = filter_unified(s)
    assert not eligible, "Bank D/E > 10.0 should fail"
    print('  bank D/E > 10.0 rejected: PASS')


def test_bank_de_within_limit_passes():
    s = dict(PASS_STOCK, de_ratio=8.0, is_bank=True)
    eligible, reason = filter_unified(s)
    assert eligible, f"Bank D/E=8.0 should pass. Reason: {reason}"
    print('  bank D/E = 8.0 passes: PASS')


def test_reit_de_limit():
    s = dict(PASS_STOCK, de_ratio=4.1, is_reit=True, is_bank=False)
    eligible, reason = filter_unified(s)
    assert not eligible, "REIT D/E > 4.0 should fail"
    print('  REIT D/E > 4.0 rejected: PASS')


def test_reit_de_within_limit_passes():
    s = dict(PASS_STOCK, de_ratio=3.5, is_reit=True, is_bank=False)
    eligible, reason = filter_unified(s)
    assert eligible, f"REIT D/E=3.5 should pass. Reason: {reason}"
    print('  REIT D/E = 3.5 passes: PASS')


def test_missing_de_ratio_passes():
    s = dict(PASS_STOCK, de_ratio=None)
    eligible, reason = filter_unified(s)
    assert eligible, f"Missing D/E should not block (no leverage data). Reason: {reason}"
    print('  missing D/E passes: PASS')


# ── filter_unified_batch ─────────────────────────────────────

def test_batch_splits_correctly():
    stocks = [
        PASS_STOCK,
        dict(PASS_STOCK, ticker='NEG', eps_3y=[-1.0, -0.8, -0.5]),
    ]
    eligible, rejected = filter_unified_batch(stocks)
    assert len(eligible) == 1
    assert len(rejected) == 1
    assert eligible[0]['ticker'] == 'OK'
    assert rejected[0]['stock']['ticker'] == 'NEG'
    assert 'reason' in rejected[0]
    print('  filter_unified_batch splits correctly: PASS')


def test_batch_empty():
    eligible, rejected = filter_unified_batch([])
    assert eligible == []
    assert rejected == []
    print('  filter_unified_batch empty: PASS')


def test_batch_all_pass():
    stocks = [PASS_STOCK, dict(PASS_STOCK, ticker='OK2')]
    eligible, rejected = filter_unified_batch(stocks)
    assert len(eligible) == 2
    assert len(rejected) == 0
    print('  filter_unified_batch all pass: PASS')


# ── Run all ──────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_healthy_stock_passes,
        test_insufficient_eps_data,
        test_insufficient_revenue_data,
        test_missing_eps_data,
        test_negative_3y_avg_eps_rejected,
        test_mostly_negative_eps_rejected,
        test_borderline_positive_eps_passes,
        test_two_consecutive_negative_ocf_rejected,
        test_one_negative_ocf_passes,
        test_non_bank_de_limit,
        test_non_bank_de_at_limit_passes,
        test_bank_de_limit,
        test_bank_de_within_limit_passes,
        test_reit_de_limit,
        test_reit_de_within_limit_passes,
        test_missing_de_ratio_passes,
        test_batch_splits_correctly,
        test_batch_empty,
        test_batch_all_pass,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f'  FAIL {t.__name__}: {e}')
            failed += 1
        except Exception as e:
            print(f'  ERROR {t.__name__}: {e}')
            failed += 1

    print(f'\n{"="*50}')
    print(f'  {passed} passed, {failed} failed')
    print(f'{"="*50}')
    if failed:
        sys.exit(1)
