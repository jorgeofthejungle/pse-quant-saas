# tests/test_phase12.py — Phase 12 unit tests
# Covers: REIT FFO metrics, REIT FCF health exemption, price staleness,
# scraper canary resilience, financial unit detection, health thresholds.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.metrics import calc_ffo, calc_ffo_yield, calc_ffo_payout


# ── Group 1: REIT FFO metrics (engine/metrics.py) ─────────────────────────

def test_calc_ffo_basic():
    """FFO = Net Income + Depreciation (no gains)."""
    result = calc_ffo(100, 20)
    assert result == 120.0, f"Expected 120.0, got {result}"
    print('  calc_ffo basic: PASS')


def test_calc_ffo_with_gains():
    """FFO deducts gains on property sale."""
    result = calc_ffo(100, 20, gains_on_sale=10)
    assert result == 110.0, f"Expected 110.0, got {result}"
    print('  calc_ffo with gains: PASS')


def test_calc_ffo_none_net_income():
    """None net_income -> None result."""
    assert calc_ffo(None, 20) is None
    print('  calc_ffo None net_income: PASS')


def test_calc_ffo_none_depreciation():
    """None depreciation -> None result."""
    assert calc_ffo(100, None) is None
    print('  calc_ffo None depreciation: PASS')


def test_calc_ffo_zero_gains_treated_as_no_deduction():
    """gains_on_sale=0 should not change FFO (same as omitting it)."""
    assert calc_ffo(100, 20, gains_on_sale=0) == calc_ffo(100, 20)
    print('  calc_ffo zero gains: PASS')


def test_calc_ffo_yield_basic():
    """FFO yield = FFO / market_cap * 100."""
    result = calc_ffo_yield(120, 2000)
    assert result == 6.0, f"Expected 6.0, got {result}"
    print('  calc_ffo_yield basic: PASS')


def test_calc_ffo_yield_none_ffo():
    """None FFO -> None result."""
    assert calc_ffo_yield(None, 2000) is None
    print('  calc_ffo_yield None ffo: PASS')


def test_calc_ffo_yield_zero_market_cap():
    """Zero market_cap -> None (division guard)."""
    assert calc_ffo_yield(120, 0) is None
    print('  calc_ffo_yield zero market_cap: PASS')


def test_calc_ffo_payout_basic():
    """FFO payout = (DPS * shares) / FFO * 100."""
    # 1 DPS, 1000 shares, FFO=2000 -> 50%
    result = calc_ffo_payout(1.0, 1000, 2000)
    assert result == 50.0, f"Expected 50.0, got {result}"
    print('  calc_ffo_payout basic: PASS')


def test_calc_ffo_payout_none_inputs():
    """None inputs -> None result."""
    assert calc_ffo_payout(None, 1000, 2000) is None
    assert calc_ffo_payout(1.0, None, 2000) is None
    assert calc_ffo_payout(1.0, 1000, None) is None
    print('  calc_ffo_payout None inputs: PASS')


# ── Group 2: REIT FCF scoring exemption (engine/scorer_health.py) ─────────

def _make_reit_stock(**overrides):
    """Minimal REIT stock dict for score_health()."""
    base = {
        'ticker': 'MREIT', 'name': 'Test REIT', 'sector': 'Property',
        'is_reit': True, 'is_bank': False,
        'roe': 8.0, 'de_ratio': 1.5,
        'fcf_yield': -5.0,   # structurally negative for REIT — should not penalise
        'ffo_yield': None,   # no FFO data yet
        'operating_cf': 500, 'revenue_5y': [5000, 4800],
        'eps_5y': [1.0, 0.9, 0.8],
        'pe': 15.0,
    }
    base.update(overrides)
    return base


def _make_non_reit_stock(**overrides):
    """Minimal non-REIT stock dict for score_health()."""
    base = {
        'ticker': 'TEST', 'name': 'Test Corp', 'sector': 'Property',
        'is_reit': False, 'is_bank': False,
        'roe': 8.0, 'de_ratio': 1.5,
        'fcf_yield': -5.0,
        'operating_cf': 500, 'revenue_5y': [5000, 4800],
        'eps_5y': [1.0, 0.9, 0.8],
        'pe': 15.0,
    }
    base.update(overrides)
    return base


def test_reit_gets_neutral_score_when_no_ffo():
    """REIT with no ffo_yield (depreciation missing) should score as neutral, not penalised."""
    from engine.scorer_health import score_health
    reit = _make_reit_stock(ffo_yield=None, fcf_yield=-5.0)
    score, breakdown = score_health(reit)
    # FCF sub-score for REIT with no FFO data should be neutral (50), not near-zero
    fcf_sub = breakdown.get('fcf_yield', {}).get('score', 0)
    assert fcf_sub >= 40, f"REIT FCF sub-score should be neutral (>=40), got {fcf_sub}"
    assert score > 0, "Overall score should be positive"
    print(f'  REIT neutral when no FFO: fcf_sub={fcf_sub}, score={score} — PASS')


def test_reit_scores_well_with_good_ffo_yield():
    """REIT with strong ffo_yield (6%+) should score high on FCF component."""
    from engine.scorer_health import score_health
    reit = _make_reit_stock(ffo_yield=7.0, fcf_yield=-3.0)
    score, breakdown = score_health(reit)
    fcf_sub = breakdown.get('fcf_yield', {}).get('score', 0)
    assert fcf_sub >= 80, f"Strong FFO yield should score >=80, got {fcf_sub}"
    print(f'  REIT strong FFO yield scores well: fcf_sub={fcf_sub} — PASS')


def test_non_reit_penalised_for_negative_fcf():
    """Non-REIT with negative FCF yield should score below neutral (< 50) on FCF component."""
    from engine.scorer_health import score_health
    non_reit = _make_non_reit_stock(fcf_yield=-5.0)
    score, breakdown = score_health(non_reit)
    fcf_sub = breakdown.get('fcf_yield', {}).get('score', 0)
    # _score_fcf_yield(-5) = 15 (between -5 and 0 threshold)
    assert fcf_sub < 30, f"Non-REIT with -5% FCF should score <30, got {fcf_sub}"
    print(f'  Non-REIT penalised for negative FCF: fcf_sub={fcf_sub} — PASS')


def test_reit_non_reit_comparison_same_conditions():
    """REIT should outscore non-REIT when both have negative FCF and no FFO data."""
    from engine.scorer_health import score_health
    reit = _make_reit_stock(ffo_yield=None, fcf_yield=-5.0)
    non_reit = _make_non_reit_stock(fcf_yield=-5.0)
    reit_score, _ = score_health(reit)
    non_reit_score, _ = score_health(non_reit)
    assert reit_score > non_reit_score, (
        f"REIT ({reit_score:.1f}) should outscore non-REIT ({non_reit_score:.1f}) "
        f"when both have negative FCF"
    )
    print(f'  REIT vs non-REIT: {reit_score:.1f} > {non_reit_score:.1f} — PASS')


# ── Group 3: Price staleness (engine/validator.py) ────────────────────────

def test_check_price_staleness_fresh():
    """Today's price date -> is_stale=False, is_critical=False."""
    from datetime import date
    from engine.validator import check_price_staleness
    stock = {'ticker': 'TEST', 'price_date': date.today().isoformat()}
    result = check_price_staleness(stock)
    assert result['is_stale'] is False, f"Today's price should not be stale: {result}"
    assert result['is_critical'] is False, f"Today's price should not be critical: {result}"
    assert result['days_stale'] == 0
    print('  price_staleness fresh: PASS')


def test_check_price_staleness_old():
    """Price from 2020 -> is_critical=True, large days_stale."""
    from engine.validator import check_price_staleness
    stock = {'ticker': 'TEST', 'price_date': '2020-01-01'}
    result = check_price_staleness(stock)
    assert result['is_critical'] is True, "2020 price should be critical"
    assert result['days_stale'] is not None and result['days_stale'] > 30
    print(f"  price_staleness old: days_stale={result['days_stale']} — PASS")


def test_check_price_staleness_no_date_unknown_ticker():
    """No price_date, ticker not in DB -> is_critical=True."""
    from engine.validator import check_price_staleness
    stock = {'ticker': 'NOTEXIST_XYZ_999', 'price_date': None}
    result = check_price_staleness(stock)
    assert result['is_critical'] is True, f"Missing date should be critical: {result}"
    assert result['price_date'] is None
    print('  price_staleness no date: PASS')


def test_check_price_staleness_returns_expected_keys():
    """Result dict must always contain the expected keys."""
    from engine.validator import check_price_staleness
    stock = {'ticker': 'TEST', 'price_date': '2024-01-01'}
    result = check_price_staleness(stock)
    for key in ('price_date', 'days_stale', 'is_stale', 'is_critical', 'warning'):
        assert key in result, f"Missing key '{key}' in staleness result"
    print('  price_staleness keys present: PASS')


# ── Group 4: Scraper canary (scraper/scraper_canary.py) ───────────────────

def test_fire_canary_no_crash_without_discord():
    """fire_canary must not raise even when Discord env vars are missing."""
    import os
    os.environ.pop('ADMIN_DISCORD_ID', None)
    os.environ.pop('DISCORD_BOT_TOKEN', None)
    from scraper.scraper_canary import fire_canary
    # Should complete without raising any exception
    fire_canary('test_scraper', 'test_canary_unit_test', 'unit test - ignore this alert')
    print('  fire_canary no crash without Discord: PASS')


def test_fire_canary_logs_to_settings_silently():
    """fire_canary with no DB available should still not raise."""
    from scraper.scraper_canary import fire_canary
    try:
        fire_canary('test_scraper', 'no_db_canary', 'DB may not exist during testing')
    except Exception as e:
        assert False, f"fire_canary should not raise: {e}"
    print('  fire_canary tolerates missing DB: PASS')


# ── Group 5: Unit detection (scraper/pse_financial_reports.py) ────────────

def test_detect_financial_unit_millions():
    """'Amounts in Millions' -> (1_000_000, 'millions')."""
    from bs4 import BeautifulSoup
    from scraper.pse_financial_reports import _detect_financial_unit
    html = "<html><body><p>Amounts in Millions of Philippine Peso</p></body></html>"
    soup = BeautifulSoup(html, 'html.parser')
    mult, label = _detect_financial_unit(soup)
    assert mult == 1_000_000, f"Expected 1_000_000, got {mult}"
    assert label == 'millions', f"Expected 'millions', got {label}"
    print('  unit detect millions: PASS')


def test_detect_financial_unit_thousands():
    """'In Thousands' -> (1_000, 'thousands')."""
    from bs4 import BeautifulSoup
    from scraper.pse_financial_reports import _detect_financial_unit
    html = "<html><body><p>In Thousands</p></body></html>"
    soup = BeautifulSoup(html, 'html.parser')
    mult, label = _detect_financial_unit(soup)
    assert mult == 1_000, f"Expected 1_000, got {mult}"
    assert label == 'thousands', f"Expected 'thousands', got {label}"
    print('  unit detect thousands: PASS')


def test_detect_financial_unit_billions():
    """'In Billions' -> (1_000_000_000, 'billions')."""
    from bs4 import BeautifulSoup
    from scraper.pse_financial_reports import _detect_financial_unit
    html = "<html><body><p>In Billions</p></body></html>"
    soup = BeautifulSoup(html, 'html.parser')
    mult, label = _detect_financial_unit(soup)
    assert mult == 1_000_000_000, f"Expected 1_000_000_000, got {mult}"
    assert label == 'billions', f"Expected 'billions', got {label}"
    print('  unit detect billions: PASS')


def test_detect_financial_unit_default_on_none():
    """None soup -> (1_000_000, 'millions_assumed')."""
    from scraper.pse_financial_reports import _detect_financial_unit
    mult, label = _detect_financial_unit(None)
    assert mult == 1_000_000, f"Expected 1_000_000, got {mult}"
    assert 'assumed' in label, f"Expected 'assumed' in label, got '{label}'"
    print('  unit detect default on None: PASS')


def test_detect_financial_unit_default_on_no_match():
    """Page with no unit indicator -> millions_assumed default."""
    from bs4 import BeautifulSoup
    from scraper.pse_financial_reports import _detect_financial_unit
    html = "<html><body><p>No unit mentioned here at all</p></body></html>"
    soup = BeautifulSoup(html, 'html.parser')
    mult, label = _detect_financial_unit(soup)
    assert mult == 1_000_000
    assert 'assumed' in label
    print('  unit detect default on no match: PASS')


# ── Group 6: get_health_thresholds (engine/calibrate_thresholds.py) ───────

def test_get_health_thresholds_returns_dict():
    """get_health_thresholds() should return a dict with known metrics."""
    from engine.calibrate_thresholds import get_health_thresholds
    thresholds = get_health_thresholds()
    assert isinstance(thresholds, dict), f"Expected dict, got {type(thresholds)}"
    assert len(thresholds) > 0, "Thresholds dict should not be empty"
    print(f'  get_health_thresholds returns dict with {len(thresholds)} metrics: PASS')


def test_get_health_thresholds_contains_roe():
    """Health thresholds must include ROE."""
    from engine.calibrate_thresholds import get_health_thresholds
    thresholds = get_health_thresholds()
    assert 'roe' in thresholds, f"'roe' not in thresholds. Keys: {list(thresholds.keys())}"
    print('  get_health_thresholds has roe: PASS')


def test_get_health_thresholds_percentile_keys():
    """Each metric must contain p50 and p90 percentile keys."""
    from engine.calibrate_thresholds import get_health_thresholds
    thresholds = get_health_thresholds()
    for metric, vals in thresholds.items():
        assert 'p50' in vals, f"'{metric}' missing p50. Keys: {list(vals.keys())}"
        assert 'p90' in vals, f"'{metric}' missing p90. Keys: {list(vals.keys())}"
    print(f'  health thresholds have p50/p90 for all {len(thresholds)} metrics: PASS')


def test_get_health_thresholds_p90_above_p50():
    """p90 >= p50 for higher-is-better metrics; inverse metrics (cv) are skipped."""
    from engine.calibrate_thresholds import get_health_thresholds
    thresholds = get_health_thresholds()
    # eps_stability_cv is an inverse metric: lower CV = more stable, so p90 < p50.
    # All other metrics are higher-is-better, so p90 >= p50.
    inverse_metrics = {'eps_stability_cv'}
    checked = 0
    for metric, vals in thresholds.items():
        if metric in inverse_metrics:
            continue
        p90 = vals.get('p90', 0)
        p50 = vals.get('p50', 0)
        assert p90 >= p50, (
            f"'{metric}': p90 ({p90}) should be >= p50 ({p50})"
        )
        checked += 1
    assert checked > 0, "Should have checked at least one metric"
    print(f'  health thresholds p90 >= p50 for {checked} non-inverse metrics: PASS')


# ── Runner ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_calc_ffo_basic,
        test_calc_ffo_with_gains,
        test_calc_ffo_none_net_income,
        test_calc_ffo_none_depreciation,
        test_calc_ffo_zero_gains_treated_as_no_deduction,
        test_calc_ffo_yield_basic,
        test_calc_ffo_yield_none_ffo,
        test_calc_ffo_yield_zero_market_cap,
        test_calc_ffo_payout_basic,
        test_calc_ffo_payout_none_inputs,
        test_reit_gets_neutral_score_when_no_ffo,
        test_reit_scores_well_with_good_ffo_yield,
        test_non_reit_penalised_for_negative_fcf,
        test_reit_non_reit_comparison_same_conditions,
        test_check_price_staleness_fresh,
        test_check_price_staleness_old,
        test_check_price_staleness_no_date_unknown_ticker,
        test_check_price_staleness_returns_expected_keys,
        test_fire_canary_no_crash_without_discord,
        test_fire_canary_logs_to_settings_silently,
        test_detect_financial_unit_millions,
        test_detect_financial_unit_thousands,
        test_detect_financial_unit_billions,
        test_detect_financial_unit_default_on_none,
        test_detect_financial_unit_default_on_no_match,
        test_get_health_thresholds_returns_dict,
        test_get_health_thresholds_contains_roe,
        test_get_health_thresholds_percentile_keys,
        test_get_health_thresholds_p90_above_p50,
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
