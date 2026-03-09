import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scheduler_jobs import (
    _top5_changed,
    _significant_score_change,
    _build_changes,
    _build_shortlist_changes,
)

# ============================================================
# Helpers
# ============================================================

def _make_stock(ticker, score, rank, breakdown=None):
    return {
        'ticker':          ticker,
        'name':            ticker + ' Corp',
        'sector':          'Holdings',
        'is_reit':         False,
        'is_bank':         False,
        'score':           score,
        'rank':            rank,
        'score_breakdown': breakdown or {},
        'current_price':   10.0,
        'dividend_yield':  5.0,
        'net_income_3y':   [1000, 900, 800],
        'dividends_5y':    [0.5, 0.5, 0.5, 0.5, 0.5],
        'payout_ratio':    40.0,
        'de_ratio':        0.5,
        'operating_cf':    1200,
        'fcf_3y':          [1100, 1000, 900],
    }


def _ranked(items):
    """Re-set rank to list index + 1."""
    for i, s in enumerate(items):
        s['rank'] = i + 1
    return items


# ============================================================
# _top5_changed
# ============================================================

def test_top5_unchanged():
    old = ['DMC', 'ALI', 'MWC', 'BDO', 'SM']
    new = ['ALI', 'DMC', 'BDO', 'SM', 'MWC']  # same set, different order
    assert not _top5_changed(old, new), "Same set in different order should NOT trigger"

def test_top5_one_replacement():
    old = ['DMC', 'ALI', 'MWC', 'BDO', 'SM']
    new = ['DMC', 'ALI', 'MWC', 'BDO', 'GTCAP']  # SM replaced by GTCAP
    assert _top5_changed(old, new), "One replacement should trigger"

def test_top5_complete_change():
    old = ['A', 'B', 'C', 'D', 'E']
    new = ['F', 'G', 'H', 'I', 'J']
    assert _top5_changed(old, new)

def test_top5_empty_both():
    assert not _top5_changed([], [])


# ============================================================
# _significant_score_change
# ============================================================

def test_significant_score_no_change():
    old = [_make_stock('DMC', 80.0, 1), _make_stock('ALI', 70.0, 2)]
    new = _ranked([_make_stock('DMC', 80.5, 1), _make_stock('ALI', 70.2, 2)])
    assert not _significant_score_change(old, new, threshold=5.0)

def test_significant_score_triggered():
    old = [_make_stock('DMC', 80.0, 1), _make_stock('ALI', 70.0, 2)]
    new = _ranked([_make_stock('DMC', 86.0, 1), _make_stock('ALI', 70.2, 2)])
    assert _significant_score_change(old, new, threshold=5.0)

def test_significant_score_exactly_at_threshold():
    old = [_make_stock('DMC', 80.0, 1)]
    new = _ranked([_make_stock('DMC', 85.0, 1)])
    assert _significant_score_change(old, new, threshold=5.0)

def test_significant_score_new_stock_ignored():
    # New stock not in old list — should not count as a score change
    old = [_make_stock('DMC', 80.0, 1)]
    new = _ranked([_make_stock('DMC', 80.0, 1), _make_stock('ALI', 99.0, 2)])
    assert not _significant_score_change(old, new, threshold=5.0)


# ============================================================
# _build_changes
# ============================================================

def test_build_changes_rank_moved():
    old = _ranked([_make_stock('DMC', 80.0, 1), _make_stock('ALI', 70.0, 2)])
    new = _ranked([_make_stock('ALI', 75.0, 1), _make_stock('DMC', 79.0, 2)])
    changes = _build_changes(new, old)
    tickers = [c['ticker'] for c in changes]
    assert 'DMC' in tickers and 'ALI' in tickers

def test_build_changes_new_entrant():
    old = [_make_stock('DMC', 80.0, 1)]
    new = _ranked([_make_stock('DMC', 80.0, 1), _make_stock('AREIT', 72.0, 2)])
    changes = _build_changes(new, old)
    areit_change = next((c for c in changes if c['ticker'] == 'AREIT'), None)
    assert areit_change is not None
    assert areit_change['old_rank'] == '—'

def test_build_changes_no_change():
    stocks = _ranked([_make_stock('DMC', 80.0, 1), _make_stock('ALI', 70.0, 2)])
    changes = _build_changes(stocks, stocks)
    assert changes == [], "Identical old and new should produce no changes"


# ============================================================
# _build_shortlist_changes
# ============================================================

def _full_stock(ticker, score, rank):
    """Stock with all fields needed to pass filters for a raw run."""
    s = _make_stock(ticker, score, rank)
    s.update({
        'dividend_yield':   5.0,
        'dividend_cagr_5y': 3.0,
        'payout_ratio':     40.0,
        'dps_last':         0.50,
        'dividends_5y':     [0.5, 0.5, 0.5, 0.5, 0.5],
        'eps_3y':           [1.0, 0.9, 0.8],
        'net_income_3y':    [1000, 900, 800],
        'roe':              12.0,
        'de_ratio':         0.5,
        'operating_cf':     1200,
        'fcf_3y':           [1100, 1000, 900],
        'fcf_coverage':     1.5,
        'fcf_yield':        6.0,
        'fcf_per_share':    0.60,
    })
    return s

def test_shortlist_no_change():
    old = [_full_stock('DMC', 80.0, 1)]
    new = _ranked([_full_stock('DMC', 81.0, 1)])
    all_stocks = [_full_stock('DMC', 81.0, 1)]
    changes = _build_shortlist_changes(old, new, all_stocks, 'pure_dividend')
    assert changes == [], "No shortlist change expected"

def test_shortlist_exit_detected():
    old = [_full_stock('DMC', 80.0, 1), _full_stock('ALI', 70.0, 2)]
    new = _ranked([_full_stock('DMC', 80.0, 1)])   # ALI dropped off
    all_stocks = [_full_stock('DMC', 80.0, 1), _full_stock('ALI', 70.0, 2)]
    changes = _build_shortlist_changes(old, new, all_stocks, 'pure_dividend')
    exits = [c for c in changes if c['type'] == 'exit']
    assert any(c['ticker'] == 'ALI' for c in exits)

def test_shortlist_entry_detected():
    old = [_full_stock('DMC', 80.0, 1)]
    new = _ranked([_full_stock('DMC', 80.0, 1), _full_stock('AREIT', 72.0, 2)])
    all_stocks = [_full_stock('DMC', 80.0, 1), _full_stock('AREIT', 72.0, 2)]
    changes = _build_shortlist_changes(old, new, all_stocks, 'pure_dividend')
    entries = [c for c in changes if c['type'] == 'entry']
    assert any(c['ticker'] == 'AREIT' for c in entries)


# ============================================================
# Run
# ============================================================

if __name__ == '__main__':
    tests = [
        test_top5_unchanged, test_top5_one_replacement,
        test_top5_complete_change, test_top5_empty_both,
        test_significant_score_no_change, test_significant_score_triggered,
        test_significant_score_exactly_at_threshold, test_significant_score_new_stock_ignored,
        test_build_changes_rank_moved, test_build_changes_new_entrant,
        test_build_changes_no_change,
        test_shortlist_no_change, test_shortlist_exit_detected, test_shortlist_entry_detected,
    ]

    passed = 0
    failed = 0
    print()
    print("=" * 55)
    print("  SCHEDULER CHANGE-DETECTION TESTS")
    print("=" * 55)
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 55)
    if failed:
        raise SystemExit(1)
