# tests/test_change_detection.py — plain-assert runner, no pytest
#
# Run with:  .venv/bin/python tests/test_change_detection.py
#
# All data is synthetic — no DB, no file I/O.

import sys
import os
from unittest.mock import patch, MagicMock

# Resolve the project root so all package imports work from here.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'engine'))
sys.path.insert(0, os.path.join(ROOT, 'reports'))
sys.path.insert(0, os.path.join(ROOT, 'discord'))
sys.path.insert(0, os.path.join(ROOT, 'db'))

from config import SCORE_CHANGE_THRESHOLD

# Patch the _build_shortlist_changes import that calls filter_unified so tests
# run without the full engine stack.
_fake_filter_unified = MagicMock(return_value=(False, 'Score dropped'))

with patch.dict('sys.modules', {
    'engine.filters_v2': MagicMock(filter_unified=_fake_filter_unified,
                                   filter_unified_batch=MagicMock(return_value=([], []))),
}):
    from scheduler_jobs.daily_jobs import detect_ranking_changes


# ── Helpers ────────────────────────────────────────────────────────────────────

def _stock(ticker, score, rank, **kwargs):
    """Minimal stock dict accepted by the change-detection helpers."""
    return {
        'ticker': ticker,
        'name':   ticker + ' Corp',
        'score':  float(score),
        'rank':   rank,
        **kwargs,
    }


def _new_stock(ticker, score, rank, **kwargs):
    """New-run stock dict (no rank key required for new_ranked)."""
    return _stock(ticker, score, rank, **kwargs)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_first_run_empty_old_data():
    """Empty old_top5 + empty old_scores → should_send=True, reason='first run'."""
    new_ranked = [_new_stock('AAA', 70, 1), _new_stock('BBB', 65, 2)]

    with patch('engine.filters_v2.filter_unified', _fake_filter_unified):
        result = detect_ranking_changes(
            old_top5   = [],
            old_scores = [],
            new_ranked = new_ranked,
            all_stocks = new_ranked,
        )

    assert result['should_send'] is True, f"Expected should_send=True, got {result['should_send']}"
    assert result['reason'] == 'first run', f"Expected 'first run', got '{result['reason']}'"


def test_top5_composition_changed():
    """When top-5 composition changes → should_send=True, reason='top-5 changed'."""
    old_top5   = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE']
    old_scores = [_stock(t, 70, i + 1) for i, t in enumerate(old_top5)]

    # Replace EEE with FFF in new ranking
    new_ranked = [
        _new_stock('AAA', 70, 1),
        _new_stock('BBB', 70, 2),
        _new_stock('CCC', 70, 3),
        _new_stock('DDD', 70, 4),
        _new_stock('FFF', 70, 5),   # EEE is gone
    ]

    with patch('engine.filters_v2.filter_unified', _fake_filter_unified):
        result = detect_ranking_changes(
            old_top5   = old_top5,
            old_scores = old_scores,
            new_ranked = new_ranked,
            all_stocks = new_ranked,
        )

    assert result['should_send'] is True, f"Expected should_send=True, got {result['should_send']}"
    assert result['reason'] == 'top-5 changed', f"Expected 'top-5 changed', got '{result['reason']}'"


def test_top5_rank_swap_within_top5():
    """A rank swap inside the top-5 (same tickers, different order) → should_send=True."""
    old_top5   = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE']
    old_scores = [_stock(t, 70, i + 1) for i, t in enumerate(old_top5)]

    # AAA and BBB swap positions
    new_ranked = [
        _new_stock('BBB', 70, 1),
        _new_stock('AAA', 70, 2),
        _new_stock('CCC', 70, 3),
        _new_stock('DDD', 70, 4),
        _new_stock('EEE', 70, 5),
    ]

    with patch('engine.filters_v2.filter_unified', _fake_filter_unified):
        result = detect_ranking_changes(
            old_top5   = old_top5,
            old_scores = old_scores,
            new_ranked = new_ranked,
            all_stocks = new_ranked,
        )

    assert result['should_send'] is True
    assert result['reason'] == 'top-5 changed'


def test_score_change_above_threshold_triggers_send():
    """Top-5 same, but a top-10 stock moved >= SCORE_CHANGE_THRESHOLD → should_send=True."""
    tickers    = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF', 'GGG', 'HHH', 'III', 'JJJ']
    old_top5   = tickers[:5]
    old_scores = [_stock(t, 70.0, i + 1) for i, t in enumerate(tickers)]

    # Same top-5 composition and order, but JJJ (rank 10) gained >= threshold points
    new_ranked = [
        _new_stock('AAA', 70.0, 1),
        _new_stock('BBB', 70.0, 2),
        _new_stock('CCC', 70.0, 3),
        _new_stock('DDD', 70.0, 4),
        _new_stock('EEE', 70.0, 5),
        _new_stock('FFF', 70.0, 6),
        _new_stock('GGG', 70.0, 7),
        _new_stock('HHH', 70.0, 8),
        _new_stock('III', 70.0, 9),
        _new_stock('JJJ', 70.0 + SCORE_CHANGE_THRESHOLD, 10),  # moved by exactly threshold
    ]

    with patch('engine.filters_v2.filter_unified', _fake_filter_unified):
        result = detect_ranking_changes(
            old_top5   = old_top5,
            old_scores = old_scores,
            new_ranked = new_ranked,
            all_stocks = new_ranked,
        )

    assert result['should_send'] is True, \
        f"Expected should_send=True for score delta={SCORE_CHANGE_THRESHOLD}"
    assert result['reason'] == f'score change >= {SCORE_CHANGE_THRESHOLD} pts in top-10', \
        f"Unexpected reason: '{result['reason']}'"


def test_no_meaningful_change():
    """Top-5 same and no score moves >= threshold → should_send=False."""
    tickers    = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE']
    old_top5   = tickers[:]
    old_scores = [_stock(t, 70.0, i + 1) for i, t in enumerate(tickers)]

    # Tiny score delta — well below threshold
    tiny_delta = SCORE_CHANGE_THRESHOLD - 1.0
    new_ranked = [
        _new_stock('AAA', 70.0 + tiny_delta, 1),
        _new_stock('BBB', 70.0, 2),
        _new_stock('CCC', 70.0, 3),
        _new_stock('DDD', 70.0, 4),
        _new_stock('EEE', 70.0, 5),
    ]

    with patch('engine.filters_v2.filter_unified', _fake_filter_unified):
        result = detect_ranking_changes(
            old_top5   = old_top5,
            old_scores = old_scores,
            new_ranked = new_ranked,
            all_stocks = new_ranked,
        )

    assert result['should_send'] is False, \
        f"Expected should_send=False, got {result['should_send']}"
    assert result['reason'] == 'no significant changes', \
        f"Expected 'no significant changes', got '{result['reason']}'"


def test_changes_list_structure():
    """
    'changes' list has the right keys and values for a known before/after pair.
    One stock changes rank, another is brand-new.
    """
    old_top5   = ['AAA', 'BBB']
    old_scores = [
        _stock('AAA', 70.0, 1),
        _stock('BBB', 65.0, 2),
    ]
    # BBB drops from rank 1 to rank 2, AAA climbs; CCC is a new entrant
    new_ranked = [
        _new_stock('BBB', 65.0, 1),   # same score, new rank
        _new_stock('AAA', 70.0, 2),   # same score, new rank
        _new_stock('CCC', 60.0, 3),   # brand new
    ]

    with patch('engine.filters_v2.filter_unified', _fake_filter_unified):
        result = detect_ranking_changes(
            old_top5   = old_top5,
            old_scores = old_scores,
            new_ranked = new_ranked,
            all_stocks = new_ranked,
        )

    changes = result['changes']
    assert isinstance(changes, list), "changes must be a list"

    tickers_in_changes = {c['ticker'] for c in changes}

    # BBB and AAA swapped ranks — both should appear in changes
    assert 'AAA' in tickers_in_changes or 'BBB' in tickers_in_changes, \
        f"Expected at least one of AAA/BBB in changes, got {tickers_in_changes}"

    # CCC is new — must be in changes
    assert 'CCC' in tickers_in_changes, \
        f"Expected CCC (new entrant) in changes, got {tickers_in_changes}"

    # Verify shape of each change entry
    required_keys = {'ticker', 'old_rank', 'new_rank', 'old_score', 'new_score'}
    for change in changes:
        missing = required_keys - change.keys()
        assert not missing, f"Change entry missing keys {missing}: {change}"


def test_return_dict_always_has_all_keys():
    """detect_ranking_changes always returns all four keys regardless of input."""
    with patch('engine.filters_v2.filter_unified', _fake_filter_unified):
        result = detect_ranking_changes([], [], [], [])

    assert set(result.keys()) == {'should_send', 'reason', 'changes', 'shortlist_changes'}, \
        f"Unexpected keys: {result.keys()}"
    assert isinstance(result['changes'], list)
    assert isinstance(result['shortlist_changes'], list)


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_first_run_empty_old_data,
        test_top5_composition_changed,
        test_top5_rank_swap_within_top5,
        test_score_change_above_threshold_triggers_send,
        test_no_meaningful_change,
        test_changes_list_structure,
        test_return_dict_always_has_all_keys,
    ]

    passed = 0
    failed = 0
    print()
    print('=' * 60)
    print('  CHANGE DETECTION TESTS')
    print('=' * 60)

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
    print('=' * 60)
    if failed:
        raise SystemExit(1)
