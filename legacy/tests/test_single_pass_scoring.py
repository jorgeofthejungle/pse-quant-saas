# tests/test_single_pass_scoring.py
# Verifies that _run_score_pipeline() performs a single pass — loading stocks
# once and scoring all portfolio types from the same eligible/fins_map.
#
# Run with: .venv/bin/python tests/test_single_pass_scoring.py

import sys
import os
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import scheduler_jobs.daily_jobs as djobs
from scheduler_jobs.daily_jobs import _run_score_pipeline


# ============================================================
# Helpers
# ============================================================

def _make_stock(ticker='TEST'):
    return {
        'ticker':          ticker,
        'name':            ticker + ' Corp',
        'sector':          'Holdings',
        'is_reit':         False,
        'is_bank':         False,
        'score':           70.0,
        'rank':            1,
        'score_breakdown': {},
        'current_price':   10.0,
        'dividend_yield':  5.0,
        'net_income_3y':   [1000, 900, 800],
        'dividends_5y':    [0.5, 0.5, 0.5, 0.5, 0.5],
        'payout_ratio':    40.0,
        'de_ratio':        0.5,
        'operating_cf':    1200,
        'fcf_3y':          [1100, 1000, 900],
        'category':        'High Yield',
    }


FAKE_SCORER_WEIGHTS = {
    'unified':  {'health': 0.30, 'improvement': 0.28, 'persistence': 0.42},
    'dividend': {'health': 0.30, 'improvement': 0.25, 'persistence': 0.45},
    'value':    {'health': 0.35, 'improvement': 0.30, 'persistence': 0.35},
}


def _run_pipeline_with_mocks(portfolio_types=None):
    """
    Call _run_score_pipeline() with all external dependencies patched.
    Returns (ranked_sections, load_stocks_mock).
    """
    stock = _make_stock()
    ranked = [stock]

    load_mock = MagicMock(return_value=[stock])
    rank_mock = MagicMock(return_value=ranked)
    filter_mock = MagicMock(return_value=([stock], []))
    sector_mock = MagicMock(return_value={})
    db_mock = MagicMock()
    db_mock.get_financials.return_value = []
    db_mock.get_last_top5.return_value = []
    db_mock.get_last_scores.return_value = []

    with patch.object(djobs, '_load_stocks', load_mock), \
         patch('engine.filters_v2.filter_unified_batch', filter_mock), \
         patch('engine.scorer_v2.rank_stocks_v2', rank_mock), \
         patch('engine.sector_stats.compute_sector_stats', sector_mock), \
         patch.object(djobs, 'db', db_mock), \
         patch('config.SCORER_WEIGHTS', FAKE_SCORER_WEIGHTS):
        if portfolio_types is not None:
            result = _run_score_pipeline(portfolio_types=portfolio_types)
        else:
            result = _run_score_pipeline()

    return result, load_mock, rank_mock, filter_mock


# ============================================================
# Test: _load_stocks called exactly once (not twice)
# ============================================================

def test_load_stocks_called_once():
    """_run_score_pipeline() must call _load_stocks exactly once."""
    _, load_mock, _, _ = _run_pipeline_with_mocks()
    assert load_mock.call_count == 1, (
        f"_load_stocks should be called exactly once, was called {load_mock.call_count} time(s)"
    )


# ============================================================
# Test: ranked_sections contains all SCORER_WEIGHTS keys
# ============================================================

def test_ranked_sections_has_all_portfolio_types():
    """ranked_sections must contain a key for every entry in SCORER_WEIGHTS."""
    result, _, _, _ = _run_pipeline_with_mocks()
    ranked_sections = result[0]

    assert isinstance(ranked_sections, dict), (
        f"First return value must be a dict, got {type(ranked_sections)}"
    )

    for pt in FAKE_SCORER_WEIGHTS:
        assert pt in ranked_sections, (
            f"ranked_sections missing key '{pt}'. Keys present: {list(ranked_sections.keys())}"
        )


# ============================================================
# Test: rank_stocks_v2 called once per portfolio type
# ============================================================

def test_rank_stocks_v2_called_per_portfolio_type():
    """rank_stocks_v2 must be called exactly len(SCORER_WEIGHTS) times — once per type."""
    _, _, rank_mock, _ = _run_pipeline_with_mocks()
    expected = len(FAKE_SCORER_WEIGHTS)
    assert rank_mock.call_count == expected, (
        f"rank_stocks_v2 should be called {expected} times (one per portfolio type), "
        f"was called {rank_mock.call_count} time(s)"
    )


# ============================================================
# Test: filter_unified_batch called exactly once (single filter pass)
# ============================================================

def test_filter_called_once():
    """filter_unified_batch must be called exactly once — same eligible list reused."""
    _, _, _, filter_mock = _run_pipeline_with_mocks()
    assert filter_mock.call_count == 1, (
        f"filter_unified_batch should be called exactly once, "
        f"was called {filter_mock.call_count} time(s)"
    )


# ============================================================
# Test: portfolio_types parameter restricts which types are scored
# ============================================================

def test_portfolio_types_param_restricts_scoring():
    """When portfolio_types=['unified'] is passed, only 'unified' is scored."""
    stock = _make_stock()
    ranked = [stock]

    load_mock = MagicMock(return_value=[stock])
    rank_mock = MagicMock(return_value=ranked)
    filter_mock = MagicMock(return_value=([stock], []))
    sector_mock = MagicMock(return_value={})
    db_mock = MagicMock()
    db_mock.get_financials.return_value = []
    db_mock.get_last_top5.return_value = []
    db_mock.get_last_scores.return_value = []

    with patch.object(djobs, '_load_stocks', load_mock), \
         patch('engine.filters_v2.filter_unified_batch', filter_mock), \
         patch('engine.scorer_v2.rank_stocks_v2', rank_mock), \
         patch('engine.sector_stats.compute_sector_stats', sector_mock), \
         patch.object(djobs, 'db', db_mock), \
         patch('config.SCORER_WEIGHTS', FAKE_SCORER_WEIGHTS):
        result = _run_score_pipeline(portfolio_types=['unified'])

    ranked_sections = result[0]
    assert list(ranked_sections.keys()) == ['unified'], (
        f"Expected only 'unified', got: {list(ranked_sections.keys())}"
    )
    assert rank_mock.call_count == 1, (
        f"rank_stocks_v2 should be called once, got {rank_mock.call_count}"
    )


# ============================================================
# Test: return tuple has the correct shape (6 elements)
# ============================================================

def test_return_tuple_shape():
    """_run_score_pipeline() must return a 6-tuple: (ranked_sections, all_stocks, old_top5, old_scores, eligible, fins_map)."""
    result, _, _, _ = _run_pipeline_with_mocks()
    assert len(result) == 6, (
        f"Expected 6-tuple return, got {len(result)} elements"
    )
    ranked_sections, all_stocks, old_top5, old_scores, eligible, fins_map = result
    assert isinstance(ranked_sections, dict), "ranked_sections must be a dict"
    assert isinstance(all_stocks, list), "all_stocks must be a list"
    assert isinstance(eligible, list), "eligible must be a list"
    assert isinstance(fins_map, dict), "fins_map must be a dict"


# ============================================================
# Test: unified key is present and is the primary ranking
# ============================================================

def test_unified_key_present():
    """ranked_sections must always contain 'unified'."""
    result, _, _, _ = _run_pipeline_with_mocks()
    ranked_sections = result[0]
    assert 'unified' in ranked_sections, (
        f"'unified' key missing from ranked_sections: {list(ranked_sections.keys())}"
    )


# ============================================================
# Run
# ============================================================

if __name__ == '__main__':
    tests = [
        test_load_stocks_called_once,
        test_ranked_sections_has_all_portfolio_types,
        test_rank_stocks_v2_called_per_portfolio_type,
        test_filter_called_once,
        test_portfolio_types_param_restricts_scoring,
        test_return_tuple_shape,
        test_unified_key_present,
    ]

    passed = 0
    failed = 0
    print()
    print('=' * 55)
    print('  SINGLE-PASS SCORING TESTS')
    print('=' * 55)
    for fn in tests:
        try:
            fn()
            print(f'  PASS  {fn.__name__}')
            passed += 1
        except AssertionError as e:
            print(f'  FAIL  {fn.__name__}: {e}')
            failed += 1
        except Exception as e:
            print(f'  ERROR {fn.__name__}: {type(e).__name__}: {e}')
            failed += 1

    print()
    print(f'  Results: {passed} passed, {failed} failed')
    print('=' * 55)
    if failed:
        raise SystemExit(1)
