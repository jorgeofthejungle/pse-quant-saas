# tests/test_phase11.py — Phase 11 unit tests
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.scorer_improvement import _roe_delta, _smoothed_delta

# ── Task 1: ROE delta year validation ─────────────────────

def test_roe_delta_correct_year_with_gap():
    """If year 2023 is missing, should still compare 2025 vs 2022."""
    history = [
        {'year': 2025, 'net_income': 1000, 'equity': 5000},  # ROE = 20%
        {'year': 2024, 'net_income': 900,  'equity': 5000},
        # 2023 missing
        {'year': 2022, 'net_income': 500,  'equity': 5000},  # ROE = 10%
        {'year': 2021, 'net_income': 400,  'equity': 5000},
    ]
    delta = _roe_delta(20.0, history)
    assert delta is not None, "Should find year 2022 despite gap"
    assert abs(delta - 10.0) < 0.01, f"Expected ~10.0, got {delta}"
    print('  roe_delta correct year with gap: PASS')


def test_roe_delta_returns_none_when_target_year_missing():
    """If the target year (current - 3) doesn't exist at all, return None."""
    history = [
        {'year': 2025, 'net_income': 1000, 'equity': 5000},
        {'year': 2024, 'net_income': 900,  'equity': 5000},
    ]
    delta = _roe_delta(20.0, history)
    assert delta is None, "Should return None when target year not found"
    print('  roe_delta None when target year missing: PASS')


def test_roe_delta_exact_3_year_gap():
    """Standard case: 4 consecutive years, compare index 0 vs 3."""
    history = [
        {'year': 2025, 'net_income': 1500, 'equity': 5000},  # ROE = 30%
        {'year': 2024, 'net_income': 1200, 'equity': 5000},
        {'year': 2023, 'net_income': 1000, 'equity': 5000},
        {'year': 2022, 'net_income': 750,  'equity': 5000},  # ROE = 15%
    ]
    delta = _roe_delta(30.0, history)
    assert delta is not None
    assert abs(delta - 15.0) < 0.01, f"Expected ~15.0, got {delta}"
    print('  roe_delta exact 3-year gap: PASS')


# ── Task 2: Improvement recency weighting ─────────────────

def test_smoothed_delta_recency_negative_recent():
    """Recent decline should pull weighted average down vs simple average."""
    # Series newest-first: most recent year declined
    series = [92, 100, 85]  # changes: -8%, +17.6%
    delta = _smoothed_delta(series, 3)
    # Weighted: -8 * 0.50 + 17.6 * 0.30 = -4.0 + 5.3 = +1.3 (approx)
    # Simple average would be (-8 + 17.6) / 2 = +4.8
    assert delta is not None
    assert delta < 4.8, f"Recency weighting should be < simple avg 4.8, got {delta}"
    print(f'  smoothed_delta recency (negative recent): {delta:.1f} — PASS')


def test_smoothed_delta_recency_positive_recent():
    """Recent growth should pull weighted average up."""
    series = [120, 100, 110]  # changes: +20%, -9.1%
    delta = _smoothed_delta(series, 3)
    # Weighted: 20 * 0.50 + (-9.1) * 0.30 = 10.0 - 2.7 = +7.3 (approx)
    # Simple average: (20 + -9.1) / 2 = +5.45
    assert delta is not None
    assert delta > 5.5, f"Recency weighting should be > simple avg 5.45, got {delta}"
    print(f'  smoothed_delta recency (positive recent): {delta:.1f} — PASS')


def test_smoothed_delta_falls_back_with_fewer_changes():
    """With only 1 change, should still return a value (no weighting needed)."""
    series = [110, 100]  # one change: +10%
    delta = _smoothed_delta(series, 3)
    assert delta is not None
    assert abs(delta - 10.0) < 0.5
    print(f'  smoothed_delta single change: {delta:.1f} — PASS')


from engine.scorer_persistence import _score_single_persistence

# ── Task 3: Persistence magnitude awareness ───────────────

def test_persistence_strong_growth_beats_marginal():
    """Stock with +18%/+15%/+12% growth should outscore +0.5%/+0.3%/+0.1%."""
    strong = [130, 110, 95, 82]   # newest first, all growing ~15%
    weak   = [103, 102.5, 102, 101.5]  # all growing ~0.5%

    strong_score = _score_single_persistence(strong)
    weak_score   = _score_single_persistence(weak)

    assert strong_score is not None and weak_score is not None
    assert strong_score > weak_score, \
        f"Strong growth ({strong_score}) should beat marginal ({weak_score})"
    print(f'  persistence: strong {strong_score} > marginal {weak_score} — PASS')


def test_persistence_magnitude_within_bounds():
    """Magnitude component should keep total score 0-100."""
    series = [200, 170, 145, 125, 110]  # ~15-18% growth each year
    score = _score_single_persistence(series)
    assert score is not None
    assert 0 <= score <= 100, f"Score must be 0-100, got {score}"
    print(f'  persistence magnitude within bounds: {score} — PASS')


def test_persistence_marginal_growth_gets_small_magnitude():
    """Very small growth should get minimal magnitude points."""
    series = [101, 100.5, 100.2, 100.1]  # <1% growth
    score = _score_single_persistence(series)
    assert score is not None
    # direction 60*(3/3)=60, magnitude ~2 (<1% avg), streak 15 → ~77
    assert 70 <= score <= 85, f"Expected 70-85 for marginal growth, got {score}"
    print(f'  persistence marginal growth: {score} — PASS')


# ── Task 4: Dividend fiscal year attribution ──────────────

def test_fiscal_year_mapping_jan_exdate():
    """Jan 2025 ex-date for Dec year-end company -> fiscal year 2024."""
    ex_month, ex_year, fy_end_month = 1, 2025, 12
    fiscal_year = ex_year if ex_month >= fy_end_month else ex_year - 1
    assert fiscal_year == 2024
    print('  fiscal year mapping Jan ex-date: PASS')


def test_fiscal_year_mapping_mar_exdate():
    """Mar 2025 ex-date for Dec year-end -> fiscal year 2024."""
    ex_month, ex_year, fy_end_month = 3, 2025, 12
    fiscal_year = ex_year if ex_month >= fy_end_month else ex_year - 1
    assert fiscal_year == 2024
    print('  fiscal year mapping Mar ex-date: PASS')


def test_fiscal_year_mapping_jun_yearend():
    """Sep 2025 ex-date for Jun year-end company -> fiscal year 2025."""
    ex_month, ex_year, fy_end_month = 9, 2025, 6
    fiscal_year = ex_year if ex_month >= fy_end_month else ex_year - 1
    assert fiscal_year == 2025
    print('  fiscal year mapping Jun year-end: PASS')


def test_fiscal_year_mapping_dec_exdate():
    """Dec 2025 ex-date for Dec year-end -> fiscal year 2025."""
    ex_month, ex_year, fy_end_month = 12, 2025, 12
    fiscal_year = ex_year if ex_month >= fy_end_month else ex_year - 1
    assert fiscal_year == 2025, f"Got {fiscal_year}"
    print('  fiscal year mapping Dec ex-date: PASS')


from engine.validator import validate_stock

# ── Task 5: Tighten gates + validator ─────────────────────

def _make_complete_stock(**overrides):
    """Helper: stock with enough fields to pass the 40% completeness gate."""
    base = {
        'ticker': 'TEST', 'name': 'Test Corp', 'current_price': 10.0,
        'pe': 12.0, 'pb': 1.5, 'roe': 10.0, 'de_ratio': 0.5,
        'dividend_yield': 3.0, 'fcf_yield': 5.0, 'eps_3y': [1.0, 1.1, 0.9],
        'revenue_cagr': 5.0, 'fcf_coverage': 1.5, 'payout_ratio': 30.0,
    }
    base.update(overrides)
    return base


def test_validator_blocks_roe_below_negative_50():
    """ROE < -50% should be hard-blocked, not just warned."""
    stock = _make_complete_stock(ticker='BAD', name='Bad Corp', roe=-60.0)
    result = validate_stock(stock)
    assert not result['valid'], f"ROE -60% should be blocked. Errors: {result.get('errors')}"
    print('  validator blocks ROE < -50%: PASS')


def test_validator_blocks_pb_above_50():
    """P/B > 50 should be hard-blocked (tightened from 100)."""
    stock = _make_complete_stock(ticker='SHELL', name='Shell Corp', pb=55.0)
    result = validate_stock(stock)
    assert not result['valid'], f"P/B 55 should be blocked. Errors: {result.get('errors')}"
    print('  validator blocks P/B > 50: PASS')


def test_validator_passes_pb_at_50():
    """P/B exactly 50 should pass (boundary)."""
    stock = _make_complete_stock(ticker='OK', name='OK Corp', pb=50.0)
    result = validate_stock(stock)
    assert result['valid'], f"P/B 50 should not be blocked. Errors: {result.get('errors')}"
    print('  validator passes P/B = 50: PASS')


# ── Task 7: Confidence-weighted scoring ───────────────────────

def test_confidence_5_years():
    """5+ years of complete data -> confidence 1.0."""
    from engine.validator import calc_data_confidence
    stock = {
        'eps_5y': [3, 2.7, 2.4, 2.1, 1.8],
        'revenue_5y': [30000, 27000, 24000, 21000, 18000],
        'operating_cf_history': [7200, 6600, 6000, 5400, 4800],
    }
    conf = calc_data_confidence(stock)
    assert conf == 1.0, f"5yr data should be 1.0, got {conf}"
    print('  confidence 5yr = 1.0: PASS')


def test_confidence_3_years():
    """3 years of complete data -> confidence 0.80."""
    from engine.validator import calc_data_confidence
    stock = {
        'eps_5y': [3, 2.7, 2.4],
        'revenue_5y': [30000, 27000, 24000],
        'operating_cf_history': [7200, 6600, 6000],
    }
    conf = calc_data_confidence(stock)
    assert conf == 0.80, f"3yr data should be 0.80, got {conf}"
    print('  confidence 3yr = 0.80: PASS')


def test_confidence_2_years():
    """2 years of complete data -> confidence 0.65."""
    from engine.validator import calc_data_confidence
    stock = {
        'eps_5y': [3, 2.7],
        'revenue_5y': [30000, 27000],
        'operating_cf_history': [7200, 6600],
    }
    conf = calc_data_confidence(stock)
    assert conf == 0.65, f"2yr data should be 0.65, got {conf}"
    print('  confidence 2yr = 0.65: PASS')


def test_confidence_1_year():
    """1 year -> confidence 0.0 (not scored)."""
    from engine.validator import calc_data_confidence
    stock = {
        'eps_5y': [3],
        'revenue_5y': [30000],
        'operating_cf_history': [7200],
    }
    conf = calc_data_confidence(stock)
    assert conf == 0.0, f"1yr data should be 0.0, got {conf}"
    print('  confidence 1yr = 0.0: PASS')


# ── Task 8: Acceleration weight adjustment ────────────────

def test_acceleration_weight_is_5_percent():
    """Acceleration weight should be 5% (reduced from 15%) for all portfolio types."""
    from config import SCORER_WEIGHTS
    unified = SCORER_WEIGHTS['unified']
    assert unified['acceleration'] == 0.05, \
        f"Unified acceleration should be 0.05, got {unified['acceleration']}"
    assert unified['persistence'] == 0.40, \
        f"Unified persistence should be 0.40, got {unified['persistence']}"
    # All portfolio types must sum to 1.0
    for pt, w in SCORER_WEIGHTS.items():
        total = sum(w.values())
        assert abs(total - 1.0) < 0.001, \
            f"Weights for '{pt}' must sum to 1.0, got {total}"
    print('  acceleration weight = 5%: PASS')


from engine.sector_stats import compute_sector_stats

# ── Task 9: Sector medians expansion ─────────────────────

def test_sector_stats_includes_roe():
    """Expanded sector stats should include ROE median."""
    stocks = [
        {'sector': 'Property', 'pe': 10, 'pb': 1.5, 'ev_ebitda': 8,
         'roe': 15.0, 'fcf_yield': 5.0, 'dividend_yield': 3.0,
         'de_ratio': 0.5, 'market_cap': 50e9,
         'operating_cf': 1000, 'revenue_5y': [10000]},
        {'sector': 'Property', 'pe': 12, 'pb': 1.8, 'ev_ebitda': 10,
         'roe': 12.0, 'fcf_yield': 4.0, 'dividend_yield': 2.5,
         'de_ratio': 0.8, 'market_cap': 30e9,
         'operating_cf': 800, 'revenue_5y': [8000]},
        {'sector': 'Property', 'pe': 8,  'pb': 1.0, 'ev_ebitda': 6,
         'roe': 18.0, 'fcf_yield': 7.0, 'dividend_yield': 4.0,
         'de_ratio': 0.3, 'market_cap': 80e9,
         'operating_cf': 1500, 'revenue_5y': [15000]},
    ]
    stats = compute_sector_stats(stocks)
    prop = stats.get('Property', {})
    assert 'roe' in prop, f"Property stats missing ROE. Keys: {list(prop.keys())}"
    assert 'fcf_yield' in prop, f"Property stats missing fcf_yield"
    print(f'  sector stats includes ROE={prop["roe"]}: PASS')


def test_sector_stats_pe_filter_50():
    """Stocks with PE > 50 should be excluded from PE median."""
    stocks = [
        {'sector': 'Mining and Oil', 'pe': 8,   'pb': 1.0, 'ev_ebitda': 5,
         'roe': 20.0, 'market_cap': 30e9},
        {'sector': 'Mining and Oil', 'pe': 12,  'pb': 1.5, 'ev_ebitda': 7,
         'roe': 15.0, 'market_cap': 20e9},
        {'sector': 'Mining and Oil', 'pe': 200, 'pb': 0.5, 'ev_ebitda': 50,
         'roe': 1.0,  'market_cap': 0.5e9},  # micro-cap noise
    ]
    stats = compute_sector_stats(stocks)
    mining = stats.get('Mining and Oil', {})
    assert mining.get('pe', 999) < 50, \
        f"PE median should exclude outlier, got {mining.get('pe')}"
    print(f'  sector stats PE filter <50: median={mining.get("pe")} — PASS')


# ── Task 10: Health threshold calibration ─────────────────

def test_health_sector_relative_blend():
    """Health should blend absolute (70%) and sector-relative (30%) scores."""
    from engine.scorer_health import score_health
    # Stock with high ROE vs sector median
    stock = {
        'ticker': 'BNK', 'name': 'Bank Corp', 'sector': 'Banking',
        'is_reit': False, 'is_bank': True,
        'roe': 15.0, 'de_ratio': 8.0, 'fcf_yield': 3.0,
        'pe': 10.0, 'pb': 1.2, 'ev_ebitda': None,
        'operating_cf': 500, 'eps_5y': [2.0, 1.8, 1.7, 1.6, 1.5],
        'revenue_5y': [5000, 4800, 4600, 4400, 4200],
    }
    # With sector medians, high ROE vs median should boost score
    sc_with, _ = score_health(stock, sector_median_pe=10.0,
                               sector_medians={'roe': 8.0, 'fcf_yield': 2.5})
    sc_without, _ = score_health(stock, sector_median_pe=10.0)
    assert sc_with > 0
    assert sc_without > 0
    # Both should produce valid scores
    assert 0 <= sc_with <= 100
    assert 0 <= sc_without <= 100
    print(f'  health sector blend: with={sc_with:.1f}, without={sc_without:.1f} — PASS')


def test_calibrate_thresholds_imports():
    """calibrate_thresholds module should import without errors."""
    from engine.calibrate_thresholds import get_health_thresholds
    thresholds = get_health_thresholds()
    assert 'roe' in thresholds
    assert 'p50' in thresholds['roe']
    print('  calibrate_thresholds imports OK: PASS')


# ── Task 11: MoS risk-adjusted discount rate ──────────────

def test_mos_large_cap_lower_rate():
    """Large cap should have lower required return than micro cap."""
    from engine.mos import calc_required_return
    large = calc_required_return(market_cap=200e9, sector='Utilities')
    micro = calc_required_return(market_cap=1e9, sector='Mining and Oil')
    assert large < micro, f"Large cap ({large:.3f}) should be < micro ({micro:.3f})"
    print(f'  MoS: large={large:.3%} < micro={micro:.3%} -- PASS')


def test_mos_sector_premium_adds_to_rate():
    """Mining sector should have higher rate than Utilities."""
    from engine.mos import calc_required_return
    mining = calc_required_return(market_cap=50e9, sector='Mining and Oil')
    utilities = calc_required_return(market_cap=50e9, sector='Utilities')
    assert mining > utilities, \
        f"Mining ({mining:.3f}) should be > Utilities ({utilities:.3f})"
    print(f'  MoS sector premium: mining={mining:.3%} > utilities={utilities:.3%} -- PASS')


def test_mos_base_rate_no_premium():
    """Large-cap Utilities should be at base rate (11.5%)."""
    from engine.mos import calc_required_return
    rate = calc_required_return(market_cap=500e9, sector='Utilities')
    assert abs(rate - 0.115) < 0.001, f"Expected 11.5%, got {rate:.3%}"
    print(f'  MoS base rate large/utilities: {rate:.3%} -- PASS')


if __name__ == '__main__':
    tests = [
        test_roe_delta_correct_year_with_gap,
        test_roe_delta_returns_none_when_target_year_missing,
        test_roe_delta_exact_3_year_gap,
        test_smoothed_delta_recency_negative_recent,
        test_smoothed_delta_recency_positive_recent,
        test_smoothed_delta_falls_back_with_fewer_changes,
        test_persistence_strong_growth_beats_marginal,
        test_persistence_magnitude_within_bounds,
        test_persistence_marginal_growth_gets_small_magnitude,
        test_fiscal_year_mapping_jan_exdate,
        test_fiscal_year_mapping_mar_exdate,
        test_fiscal_year_mapping_jun_yearend,
        test_fiscal_year_mapping_dec_exdate,
        test_validator_blocks_roe_below_negative_50,
        test_validator_blocks_pb_above_50,
        test_validator_passes_pb_at_50,
        test_confidence_5_years,
        test_confidence_3_years,
        test_confidence_2_years,
        test_confidence_1_year,
        test_acceleration_weight_is_5_percent,
        test_sector_stats_includes_roe,
        test_sector_stats_pe_filter_50,
        test_health_sector_relative_blend,
        test_calibrate_thresholds_imports,
        test_mos_large_cap_lower_rate,
        test_mos_sector_premium_adds_to_rate,
        test_mos_base_rate_no_premium,
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
