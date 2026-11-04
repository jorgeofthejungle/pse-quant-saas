# ============================================================
# test_scorer_v2.py — Tests for the Unified 3-Layer Scorer
# PSE Quant SaaS — Phase 13 (sector-specific scoring)
# ============================================================
# Run: py tests/test_scorer_v2.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.scorer_v2      import score_unified, rank_stocks_v2, get_category
from engine.scorer_health  import score_health
from engine.scorer_improvement import score_improvement
from engine.scorer_persistence import score_persistence
from engine.sector_groups  import get_scoring_group

# ── Shared test fixtures ─────────────────────────────────────

STRONG_STOCK = {
    'ticker': 'TST',  'name': 'Test Corp', 'sector': 'Industrials',
    'is_reit': False, 'is_bank': False,
    'current_price': 10.0, 'roe': 18.0, 'de_ratio': 0.4,
    'pe': 8.0, 'pb': 1.2, 'ev_ebitda': 6.0,
    'fcf_yield': 7.0, 'fcf_coverage': 2.0,
    'revenue_cagr': 10.0, 'eps_3y': [3.0, 2.7, 2.4],
    'net_income_3y': [6000, 5400, 4800],
    'revenue_5y':          [30000, 27000, 24000, 21000, 18000],
    'eps_5y':              [3.0,   2.7,   2.4,   2.1,   1.8],
    'dps_history':         [1.0,   0.9,   0.8,   0.7,   0.6],
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
    'revenue_5y':          [10000, 11000, 12000, 11500, 10800],
    'eps_5y':              [-0.5, -0.3, 0.1, -0.2, 0.3],
    'dps_history':         [0.0,   0.0,  0.0,  0.0,  0.0],
    'operating_cf_history':[300,   800,  1200,  600,  900],
}

BANK_STOCK = {
    'ticker': 'BNK', 'name': 'Test Bank', 'sector': 'Financials',
    'is_reit': False, 'is_bank': True,
    'current_price': 50.0, 'roe': 12.0, 'de_ratio': 8.0,
    'pe': 10.0, 'pb': 1.1, 'ev_ebitda': None,
    'fcf_yield': None, 'fcf_coverage': None,
    'revenue_cagr': 8.0, 'eps_3y': [5.0, 4.5, 4.0],
    'net_income_3y': [15000, 13500, 12000],
    'revenue_5y':          [50000, 46000, 42000, 38000, 34000],
    'eps_5y':              [5.0,   4.5,   4.0,   3.6,   3.2],
    'dps_history':         [2.0,   1.8,   1.6,   1.4,   1.2],
    'operating_cf_history':[None,  None,  None,  None,  None],
}


# ── Category thresholds ──────────────────────────────────────

def test_get_category_thresholds():
    assert get_category(75)[0] == 'Highest Quality'
    assert get_category(55)[0] == 'Strong Growth'
    assert get_category(35)[0] == 'Watchlist'
    assert get_category(0)[0]  == 'Weak'
    assert get_category(74.9)[0] == 'Strong Growth'
    print('  get_category thresholds: PASS')


# ── Sector group resolution ──────────────────────────────────

def test_sector_group_bank():
    grp = get_scoring_group(BANK_STOCK)
    assert grp == 'bank', f"Expected 'bank', got '{grp}'"
    print(f'  sector_group bank: PASS')


def test_sector_group_general():
    grp = get_scoring_group(STRONG_STOCK)
    assert grp in ('industrial', 'services', 'general'), f"Unexpected group: {grp}"
    print(f'  sector_group general/industrial: PASS')


# ── Layer 1: Health ──────────────────────────────────────────

def test_health_strong():
    grp = get_scoring_group(STRONG_STOCK)
    sc, bd = score_health(STRONG_STOCK, grp)
    assert sc is not None and 0 <= sc <= 100
    assert sc > 50, f"Strong stock should score > 50 on health, got {sc}"
    print(f'  health strong stock: {sc:.1f}/100 - PASS')


def test_health_weak():
    grp = get_scoring_group(WEAK_STOCK)
    sc, bd = score_health(WEAK_STOCK, grp)
    assert sc is not None and 0 <= sc <= 100
    assert sc < 50, f"Weak stock should score < 50 on health, got {sc}"
    print(f'  health weak stock: {sc:.1f}/100 - PASS')


def test_health_bank_excludes_de():
    grp = get_scoring_group(BANK_STOCK)
    sc, bd = score_health(BANK_STOCK, grp)
    assert sc is not None and sc > 0, "Bank should not score 0 on health"
    factors = bd.get('factors', {})
    assert factors.get('de_ratio') is None, "Bank D/E should be excluded (None)"
    print(f'  health bank D/E excluded: {sc:.1f}/100 - PASS')


# ── Layer 2: Improvement ─────────────────────────────────────

def test_improvement_strong():
    grp = get_scoring_group(STRONG_STOCK)
    fins = [
        {'year': 2024, 'equity': 33000, 'net_income': 6000},
        {'year': 2023, 'equity': 30000, 'net_income': 5400},
        {'year': 2022, 'equity': 27000, 'net_income': 4800},
    ]
    sc, bd = score_improvement(STRONG_STOCK, fins, grp)
    assert sc is not None and 0 <= sc <= 100
    assert sc > 50, f"Improving stock should score > 50, got {sc}"
    print(f'  improvement strong: {sc:.1f}/100 - PASS')


def test_improvement_missing_data_returns_none():
    minimal = dict(STRONG_STOCK, revenue_5y=[], eps_5y=[])
    grp = get_scoring_group(minimal)
    sc, bd = score_improvement(minimal, [], grp)
    assert sc is None or sc == 0.0, f"Missing data should return None or 0, got {sc}"
    print(f'  improvement missing data -> None/0: PASS')


# ── Layer 3: Persistence ─────────────────────────────────────

def test_persistence_strong():
    grp = get_scoring_group(STRONG_STOCK)
    sc, bd = score_persistence(STRONG_STOCK, grp)
    assert sc is not None and sc > 50, f"Steadily growing stock should score > 50, got {sc}"
    print(f'  persistence strong: {sc:.1f}/100 - PASS')


def test_persistence_erratic():
    erratic = dict(STRONG_STOCK,
                   revenue_5y=[30000, 25000, 28000, 22000, 26000],
                   eps_5y=[3.0, 2.0, 2.5, 1.8, 2.2])
    grp = get_scoring_group(erratic)
    sc, _ = score_persistence(erratic, grp)
    assert sc is not None and sc < 80, f"Erratic stock should not score > 80, got {sc}"
    print(f'  persistence erratic: {sc:.1f}/100 - PASS')


# ── Unified scorer ───────────────────────────────────────────

def test_score_unified_strong():
    sc, bd = score_unified(STRONG_STOCK)
    assert 0 <= sc <= 100
    assert sc > 50, f"Strong stock should score > 50 unified, got {sc}"
    assert 'layers' in bd
    assert set(bd['layers'].keys()) == {'health', 'improvement', 'persistence'}
    print(f'  score_unified strong: {sc:.1f}/100 - PASS')


def test_score_unified_returns_breakdown():
    sc, bd = score_unified(STRONG_STOCK)
    for layer_name in ('health', 'improvement', 'persistence'):
        layer = bd['layers'][layer_name]
        assert 'score'   in layer
        assert 'weight'  in layer
        assert 'factors' in layer
    print('  score_unified breakdown structure: PASS')


def test_score_unified_deterministic():
    sc1, _ = score_unified(STRONG_STOCK)
    sc2, _ = score_unified(STRONG_STOCK)
    assert sc1 == sc2, "Scorer must be deterministic"
    print('  score_unified deterministic: PASS')


def test_score_unified_bank():
    sc, bd = score_unified(BANK_STOCK)
    assert sc is not None and 0 <= sc <= 100
    assert bd.get('scoring_group') == 'bank'
    print(f'  score_unified bank sector: {sc:.1f}/100 - PASS')


# ── rank_stocks_v2 ───────────────────────────────────────────

def test_rank_stocks_v2_order():
    ranked = rank_stocks_v2([WEAK_STOCK, STRONG_STOCK])
    assert ranked[0]['ticker'] == 'TST', "Strong stock should rank first"
    assert ranked[0]['rank'] == 1
    print('  rank_stocks_v2 order: PASS')


def test_rank_stocks_v2_adds_score_breakdown():
    ranked = rank_stocks_v2([STRONG_STOCK])
    r = ranked[0]
    assert 'score_breakdown' in r
    for layer in ('health', 'improvement', 'persistence'):
        assert layer in r['score_breakdown']
        data = r['score_breakdown'][layer]
        assert 'score'   in data
        assert 'weight'  in data
    print('  rank_stocks_v2 score_breakdown: PASS')


def test_rank_stocks_v2_empty():
    ranked = rank_stocks_v2([])
    assert ranked == []
    print('  rank_stocks_v2 empty list: PASS')


# ── Dynamic threshold ─────────────────────────────────────────

def test_dynamic_threshold_filters_weak():
    # With enough stocks, dynamic threshold should exclude the weakest
    stocks = [STRONG_STOCK] + [dict(WEAK_STOCK, ticker=f'WK{i}') for i in range(10)]
    ranked = rank_stocks_v2(stocks)
    tickers = [r['ticker'] for r in ranked]
    # Strong stock should always make it; many weak ones should be filtered
    assert 'TST' in tickers, "Strong stock should always pass dynamic threshold"
    print(f'  dynamic threshold: {len(ranked)} of {len(stocks)} passed - PASS')


# ── Run all ──────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_get_category_thresholds,
        test_sector_group_bank,
        test_sector_group_general,
        test_health_strong,
        test_health_weak,
        test_health_bank_excludes_de,
        test_improvement_strong,
        test_improvement_missing_data_returns_none,
        test_persistence_strong,
        test_persistence_erratic,
        test_score_unified_strong,
        test_score_unified_returns_breakdown,
        test_score_unified_deterministic,
        test_score_unified_bank,
        test_rank_stocks_v2_order,
        test_rank_stocks_v2_adds_score_breakdown,
        test_rank_stocks_v2_empty,
        test_dynamic_threshold_filters_weak,
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
