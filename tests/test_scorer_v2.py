# ============================================================
# test_scorer_v2.py — Tests for the Unified 4-Layer Scorer
# PSE Quant SaaS — Phase 9B
# ============================================================
# Run: py tests/test_scorer_v2.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.scorer_v2       import score_unified, rank_stocks_v2, get_category
from engine.scorer_health   import score_health
from engine.scorer_improvement import score_improvement
from engine.scorer_acceleration import score_acceleration
from engine.scorer_persistence  import score_persistence

# ── Shared test fixture ──────────────────────────────────────

STRONG_STOCK = {
    'ticker': 'TST',  'name': 'Test Corp', 'sector': 'Industrials',
    'is_reit': False, 'is_bank': False,
    'current_price': 10.0, 'roe': 18.0, 'de_ratio': 0.4,
    'pe': 8.0, 'pb': 1.2, 'ev_ebitda': 6.0,
    'fcf_yield': 7.0, 'fcf_coverage': 2.0,
    'revenue_cagr': 10.0, 'eps_3y': [3.0, 2.7, 2.4],
    'net_income_3y': [6000, 5400, 4800],
    'operating_cf': 7200,
    'revenue_5y':          [30000, 27000, 24000, 21000, 18000],
    'eps_5y':              [3.0,   2.7,   2.4,   2.1,   1.8],
    'operating_cf_history':[7200,  6600,  6000,  5400,  4800],
}

WEAK_STOCK = {
    'ticker': 'WK', 'name': 'Weak Inc', 'sector': 'Services',
    'is_reit': False, 'is_bank': False,
    'current_price': 5.0, 'roe': 3.0, 'de_ratio': 3.5,
    'pe': 50.0, 'pb': 4.0, 'ev_ebitda': 30.0,
    'fcf_yield': -2.0, 'fcf_coverage': 0.3,
    'revenue_cagr': -5.0, 'eps_3y': [-0.5, -0.3, 0.1],
    'net_income_3y': [-1000, -600, 200],
    'operating_cf': 300,
    'revenue_5y':          [10000, 11000, 12000, 11500, 10800],
    'eps_5y':              [-0.5, -0.3, 0.1, -0.2, 0.3],
    'operating_cf_history':[300,   800,  1200,  600,  900],
}


# ── Category thresholds ──────────────────────────────────────

def test_get_category_thresholds():
    assert get_category(75)[0] == 'Highest Quality'
    assert get_category(55)[0] == 'Strong Growth'
    assert get_category(35)[0] == 'Watchlist'
    assert get_category(0)[0]  == 'Weak'
    assert get_category(74.9)[0] == 'Strong Growth'
    print('  get_category thresholds: PASS')


# ── Layer 1: Health ──────────────────────────────────────────

def test_health_strong():
    sc, bd = score_health(STRONG_STOCK)
    assert 0 <= sc <= 100
    assert isinstance(bd, dict)
    assert sc > 50, f"Strong stock should score > 50 on health, got {sc}"
    print(f'  health strong stock: {sc:.1f}/100 — PASS')


def test_health_weak():
    sc, bd = score_health(WEAK_STOCK)
    assert 0 <= sc <= 100
    assert sc < 50, f"Weak stock should score < 50 on health, got {sc}"
    print(f'  health weak stock: {sc:.1f}/100 — PASS')


def test_health_bank_de_adjustment():
    bank = dict(STRONG_STOCK, is_bank=True, de_ratio=8.0)
    sc, _ = score_health(bank)
    assert sc > 0, "Bank with D/E=8 should not score 0"
    print(f'  health bank D/E adjustment: {sc:.1f}/100 — PASS')


# ── Layer 2: Improvement ─────────────────────────────────────

def test_improvement_strong():
    sc, bd = score_improvement(STRONG_STOCK)
    assert 0 <= sc <= 100
    assert sc > 50
    print(f'  improvement strong: {sc:.1f}/100 — PASS')


def test_improvement_missing_data():
    minimal = dict(STRONG_STOCK, revenue_5y=[], eps_5y=[], operating_cf_history=[])
    sc, bd = score_improvement(minimal)
    assert sc == 0.0
    print('  improvement missing data -> 0: PASS')


# ── Layer 3: Acceleration ────────────────────────────────────

def test_acceleration_requires_5_years():
    short = dict(STRONG_STOCK,
                 revenue_5y=[30000, 27000, 24000],
                 eps_5y=[3.0, 2.7, 2.4],
                 operating_cf_history=[7200, 6600, 6000])
    sc, bd = score_acceleration(short)
    all_none = all(v.get('score') is None for v in bd.values())
    assert all_none, "With < 5 years, all acceleration sub-scores should be None"
    print('  acceleration < 5 years -> all None: PASS')


def test_acceleration_full_data():
    sc, bd = score_acceleration(STRONG_STOCK)
    assert 0 <= sc <= 100
    print(f'  acceleration full data: {sc:.1f}/100 — PASS')


# ── Layer 4: Persistence ─────────────────────────────────────

def test_persistence_strong():
    sc, bd = score_persistence(STRONG_STOCK)
    assert sc > 60, f"Steadily growing stock should persist > 60, got {sc}"
    print(f'  persistence strong: {sc:.1f}/100 — PASS')


def test_persistence_erratic():
    erratic = dict(STRONG_STOCK,
                   revenue_5y=[30000, 25000, 28000, 22000, 26000],
                   eps_5y=[3.0, 2.0, 2.5, 1.8, 2.2],
                   operating_cf_history=[7200, 5000, 6500, 4000, 6000])
    sc, _ = score_persistence(erratic)
    assert sc < 80, f"Erratic stock should not score > 80 on persistence, got {sc}"
    print(f'  persistence erratic: {sc:.1f}/100 — PASS')


# ── Unified scorer ───────────────────────────────────────────

def test_score_unified_strong():
    sc, bd = score_unified(STRONG_STOCK)
    assert 0 <= sc <= 100
    assert sc > 60, f"Strong stock should score > 60 unified, got {sc}"
    assert 'layers' in bd
    assert set(bd['layers'].keys()) == {'health', 'improvement', 'acceleration', 'persistence'}
    print(f'  score_unified strong: {sc:.1f}/100 — PASS')


def test_score_unified_returns_breakdown():
    sc, bd = score_unified(STRONG_STOCK)
    for layer_name in ('health', 'improvement', 'acceleration', 'persistence'):
        layer = bd['layers'][layer_name]
        assert 'score'  in layer
        assert 'weight' in layer
        assert 'factors' in layer
    print('  score_unified breakdown structure: PASS')


def test_score_unified_same_inputs_same_output():
    sc1, _ = score_unified(STRONG_STOCK)
    sc2, _ = score_unified(STRONG_STOCK)
    assert sc1 == sc2, "Scorer must be deterministic"
    print('  score_unified deterministic: PASS')


# ── rank_stocks_v2 ───────────────────────────────────────────

def test_rank_stocks_v2_order():
    ranked = rank_stocks_v2([WEAK_STOCK, STRONG_STOCK])
    assert ranked[0]['ticker'] == 'TST', "Strong stock should rank first"
    assert ranked[1]['ticker'] == 'WK'
    assert ranked[0]['rank'] == 1
    assert ranked[1]['rank'] == 2
    print('  rank_stocks_v2 order: PASS')


def test_rank_stocks_v2_adds_score_breakdown():
    ranked = rank_stocks_v2([STRONG_STOCK])
    r = ranked[0]
    assert 'score_breakdown' in r
    assert set(r['score_breakdown'].keys()) == {'health', 'improvement', 'acceleration', 'persistence'}
    for layer, data in r['score_breakdown'].items():
        assert 'score'       in data
        assert 'weight'      in data
        assert 'explanation' in data
    print('  rank_stocks_v2 score_breakdown: PASS')


def test_rank_stocks_v2_empty():
    ranked = rank_stocks_v2([])
    assert ranked == []
    print('  rank_stocks_v2 empty list: PASS')


# ── Weight redistribution (None layer) ──────────────────────

def test_acceleration_none_redistributed():
    # Stock with < 5 years, acceleration layer returns None
    short_stock = dict(STRONG_STOCK,
                       revenue_5y=[30000, 27000, 24000],
                       eps_5y=[3.0, 2.7, 2.4],
                       operating_cf_history=[7200, 6600, 6000])
    sc, bd = score_unified(short_stock)
    assert sc > 0, "Score should be > 0 even with acceleration None"
    assert bd['layers']['acceleration']['score'] is None
    print(f'  acceleration None -> weight redistributed: {sc:.1f}/100 - PASS')


# ── Run all ──────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_get_category_thresholds,
        test_health_strong,
        test_health_weak,
        test_health_bank_de_adjustment,
        test_improvement_strong,
        test_improvement_missing_data,
        test_acceleration_requires_5_years,
        test_acceleration_full_data,
        test_persistence_strong,
        test_persistence_erratic,
        test_score_unified_strong,
        test_score_unified_returns_breakdown,
        test_score_unified_same_inputs_same_output,
        test_rank_stocks_v2_order,
        test_rank_stocks_v2_adds_score_breakdown,
        test_rank_stocks_v2_empty,
        test_acceleration_none_redistributed,
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
