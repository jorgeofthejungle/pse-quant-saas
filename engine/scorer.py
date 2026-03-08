# ============================================================
# scorer.py — Portfolio Scoring Engine (Institutional v2)
# PSE Quant SaaS — Phase 1
# ============================================================
# Sub-modules:
#   scorer_utils.py        — normalise(), _blend(), _eps_cagr(), _eps_vol_ratio()
#   scorer_explanations.py — all explain_*() functions
# ============================================================

try:
    from engine.scorer_utils import normalise, _blend, _eps_cagr, _eps_vol_ratio, _cf_quality, _growth_consistency, _dividend_stability
    from engine.scorer_explanations import (
        explain_dividend_yield, explain_dividend_cagr, explain_payout_ratio,
        explain_fcf_coverage, explain_eps_stability, explain_roe, explain_eps_growth,
        explain_pe, explain_pb, explain_ev_ebitda, explain_revenue_cagr,
        explain_de_ratio, explain_fcf_yield, explain_leverage_coverage,
        explain_relative_valuation, explain_valuation_composite,
        explain_quality_composite, explain_cash_flow_quality,
        explain_earnings_yield_spread, explain_growth_consistency,
        explain_dividend_stability,
    )
    from engine.scorer_momentum import compute_momentum_composite, explain_momentum
except ImportError:
    from scorer_utils import normalise, _blend, _eps_cagr, _eps_vol_ratio, _cf_quality, _growth_consistency, _dividend_stability
    from scorer_explanations import (
        explain_dividend_yield, explain_dividend_cagr, explain_payout_ratio,
        explain_fcf_coverage, explain_eps_stability, explain_roe, explain_eps_growth,
        explain_pe, explain_pb, explain_ev_ebitda, explain_revenue_cagr,
        explain_de_ratio, explain_fcf_yield, explain_leverage_coverage,
        explain_relative_valuation, explain_valuation_composite,
        explain_quality_composite, explain_cash_flow_quality,
        explain_earnings_yield_spread, explain_growth_consistency,
        explain_dividend_stability,
    )
    from scorer_momentum import compute_momentum_composite, explain_momentum

__all__ = [
    'score_pure_dividend', 'score_dividend_growth', 'score_value',
    'normalise', '_blend',
]


def score_pure_dividend(metrics: dict):
    """
    Pure Dividend portfolio scoring.
    Weights: yield 18%, fcf_yield 14%, quality_composite 18%, eps_stability 14%,
             leverage_coverage 14%, relative_valuation 12%, momentum 10%
    quality_composite = ROE 40% + Cash Flow Quality 30% + Dividend Stability 30%
    Returns (score: float, breakdown: dict).
    """
    div_yield = metrics.get('dividend_yield')
    yield_score = normalise(div_yield, [(3, 20), (5, 55), (7, 80), (9, 95), (12, 100)])
    if div_yield and div_yield > 12:
        yield_score = 50   # yield trap warning

    fcf_yield = metrics.get('fcf_yield')
    fcf_yield_score = normalise(fcf_yield, [(2, 15), (4, 40), (6, 65), (8, 85), (10, 100)])

    # Quality Composite: ROE 40% + Cash Flow Quality 30% + Dividend Stability 30%
    roe = metrics.get('roe')
    roe_score = normalise(roe, [(5, 10), (10, 40), (15, 65), (20, 85), (25, 100)]) if roe is not None else None

    operating_cf = metrics.get('operating_cf')
    net_income_3y = metrics.get('net_income_3y', [])
    cf_ratio = _cf_quality(operating_cf, net_income_3y)
    cf_score = normalise(cf_ratio, [(0.5, 10), (0.7, 25), (0.9, 45), (1.1, 65), (1.3, 85), (1.5, 100)]) if cf_ratio is not None else None

    dividends_5y = metrics.get('dividends_5y', [])
    div_stab_cv = _dividend_stability(dividends_5y)
    div_stab_score = normalise(div_stab_cv, [(0.10, 100), (0.20, 85), (0.35, 65), (0.50, 45), (0.70, 25)]) if div_stab_cv is not None else None

    quality_score = _blend([(roe_score, 0.40), (cf_score, 0.30), (div_stab_score, 0.30)])

    eps_5y = metrics.get('eps_5y', [])
    eps_3y = metrics.get('eps_3y', [])
    eps_history = eps_5y if len(eps_5y) >= 3 else eps_3y
    vol_ratio = _eps_vol_ratio(eps_history)

    if vol_ratio is not None:
        stability_score = normalise(vol_ratio, [
            (0.2, 100), (0.4, 85), (0.6, 70), (0.8, 55), (1.0, 35), (1.5, 15),
        ])
        stability_explanation = explain_eps_stability([], eps_vol_ratio=vol_ratio)
    else:
        positive_years = sum(1 for n in net_income_3y if n and n > 0)
        stability_score = [0, 20, 60, 100][min(positive_years, 3)]
        stability_explanation = explain_eps_stability(net_income_3y)

    de = metrics.get('de_ratio')
    fcf_cov = metrics.get('fcf_coverage')
    interest_cov = metrics.get('interest_coverage')

    de_score      = normalise(de,           [(0.3, 100), (0.7, 80), (1.2, 60), (2.0, 35), (3.0, 10)]) if de is not None else None
    fcf_cov_score = normalise(fcf_cov,      [(0.5, 10),  (1.0, 40), (1.5, 75), (2.0, 90), (3.0, 100)])if fcf_cov is not None else None
    int_cov_score = normalise(interest_cov, [(1.5, 10),  (3.0, 50), (5.0, 75), (8.0, 90), (12.0, 100)])if interest_cov is not None else None

    lev_score = _blend([(de_score, 0.40), (fcf_cov_score, 0.40), (int_cov_score, 0.20)])

    pe = metrics.get('pe')
    ev = metrics.get('ev_ebitda')
    pe_score = normalise(pe, [(8, 100), (12, 85), (18, 65), (28, 35), (40, 15)]) if pe is not None else None
    ev_score = normalise(ev, [(5, 100), (8, 80),  (12, 55), (18, 30), (25, 10)]) if ev is not None else None
    val_score = _blend([(pe_score, 0.50), (ev_score, 0.50)])

    positive_years_display = sum(1 for n in net_income_3y if n and n > 0)

    mom_score, mom_detail = compute_momentum_composite(metrics)
    mom_explanation = explain_momentum(
        mom_detail.get('rev_delta'), mom_detail.get('eps_delta'), mom_detail.get('ocf_delta')
    )

    breakdown = {
        'dividend_yield':     {'score': yield_score,    'weight': 0.18, 'value': div_yield, 'explanation': explain_dividend_yield(div_yield)},
        'fcf_yield':          {'score': fcf_yield_score,'weight': 0.14, 'value': fcf_yield, 'explanation': explain_fcf_yield(fcf_yield)},
        'quality_composite':  {'score': quality_score,  'weight': 0.18, 'value': roe,       'explanation': explain_quality_composite(roe, positive_years_display, cf_quality=cf_ratio, div_stability_cv=div_stab_cv)},
        'eps_stability':      {'score': stability_score,'weight': 0.14, 'value': vol_ratio, 'explanation': stability_explanation},
        'leverage_coverage':  {'score': lev_score,      'weight': 0.14, 'value': de,        'explanation': explain_leverage_coverage(de, fcf_cov, interest_cov)},
        'relative_valuation': {'score': val_score,      'weight': 0.12, 'value': pe,        'explanation': explain_relative_valuation(pe, ev)},
        'fundamental_momentum': {'score': mom_score,   'weight': 0.10, 'value': mom_detail, 'explanation': mom_explanation},
    }
    return round(sum(v['score'] * v['weight'] for v in breakdown.values()), 1), breakdown


def score_dividend_growth(metrics: dict):
    """
    Dividend Growth portfolio scoring.
    Weights: cagr 17%, growth_composite 18%, quality_composite 14%,
             yield 14%, payout 14%, leverage 13%, momentum 10%
    growth_composite = EPS Growth 60% + Growth Consistency 40%
    quality_composite = ROE 50% + Cash Flow Quality 50%
    Returns (score: float, breakdown: dict).
    """
    is_reit = metrics.get('is_reit', False)

    cagr = metrics.get('dividend_cagr_5y')
    cagr_score = normalise(cagr, [(0, 10), (3, 40), (5, 60), (8, 80), (12, 95), (20, 100)])

    eps_5y = metrics.get('eps_5y', [])
    eps_3y = metrics.get('eps_3y', [])
    eps_history = eps_5y if len(eps_5y) >= 3 else eps_3y
    eps_growth = _eps_cagr(eps_history)

    vol_ratio = _eps_vol_ratio(eps_history)
    if eps_growth is not None and vol_ratio is not None and vol_ratio > 0.5:
        eps_growth = eps_growth * (1.0 - min(vol_ratio - 0.5, 0.5))
    if eps_growth is None:
        eps_growth = metrics.get('revenue_cagr')

    eps_growth_score = normalise(eps_growth, [(0, 10), (3, 30), (8, 60), (12, 80), (18, 95), (25, 100)])

    # Growth Consistency from revenue_5y (preferred) or eps_5y
    revenue_5y = metrics.get('revenue_5y', [])
    consistency_series = revenue_5y if len(revenue_5y) >= 3 else eps_history
    growth_cv = _growth_consistency(consistency_series)
    consistency_score = normalise(growth_cv, [(0.10, 100), (0.20, 85), (0.35, 65), (0.50, 45), (0.70, 25)]) if growth_cv is not None else None

    # Growth Composite: EPS Growth 60% + Consistency 40%
    growth_composite = _blend([(eps_growth_score, 0.60), (consistency_score, 0.40)])

    # Quality Composite: ROE 50% + Cash Flow Quality 50%
    roe = metrics.get('roe')
    roe_score = normalise(roe, [(5, 10), (10, 40), (15, 65), (20, 85), (25, 100)]) if roe is not None else None

    operating_cf = metrics.get('operating_cf')
    net_income_3y = metrics.get('net_income_3y', [])
    cf_ratio = _cf_quality(operating_cf, net_income_3y)
    cf_score = normalise(cf_ratio, [(0.5, 10), (0.7, 25), (0.9, 45), (1.1, 65), (1.3, 85), (1.5, 100)]) if cf_ratio is not None else None

    quality_score = _blend([(roe_score, 0.50), (cf_score, 0.50)])

    div_yield = metrics.get('dividend_yield')
    yield_score = normalise(div_yield, [(1, 10), (2, 30), (3, 55), (5, 80), (7, 90), (9, 75), (12, 55)])
    if div_yield and div_yield > 12:
        yield_score = 30

    payout = metrics.get('payout_ratio')
    if payout is None:
        payout_score = 0
    elif is_reit and payout <= 100:
        payout_score = 65
    elif payout <= 25:
        payout_score = 100
    elif payout <= 40:
        payout_score = 90
    elif payout <= 60:
        payout_score = 70
    elif payout <= 75:
        payout_score = 50
    elif payout <= 85:
        payout_score = 25
    else:
        payout_score = 10

    de = metrics.get('de_ratio')
    fcf_cov = metrics.get('fcf_coverage')
    de_score      = normalise(de,      [(0.3, 100), (0.7, 80), (1.2, 60), (2.0, 35), (3.0, 10)])  if de is not None      else None
    fcf_cov_score = normalise(fcf_cov, [(0.5, 10),  (1.0, 40), (1.5, 75), (2.0, 90), (3.0, 100)]) if fcf_cov is not None else None
    lev_score = _blend([(de_score, 0.50), (fcf_cov_score, 0.50)])

    positive_years_display = sum(1 for n in net_income_3y if n and n > 0)

    mom_score, mom_detail = compute_momentum_composite(metrics)
    mom_explanation = explain_momentum(
        mom_detail.get('rev_delta'), mom_detail.get('eps_delta'), mom_detail.get('ocf_delta')
    )

    breakdown = {
        'dividend_cagr':        {'score': cagr_score,       'weight': 0.17, 'value': cagr,      'explanation': explain_dividend_cagr(cagr)},
        'growth_composite':     {'score': growth_composite,  'weight': 0.18, 'value': eps_growth, 'explanation': explain_eps_growth(eps_growth) + '  ' + explain_growth_consistency(growth_cv)},
        'quality_composite':    {'score': quality_score,     'weight': 0.14, 'value': roe,        'explanation': explain_quality_composite(roe, positive_years_display, cf_quality=cf_ratio)},
        'dividend_yield':       {'score': yield_score,       'weight': 0.14, 'value': div_yield,  'explanation': explain_dividend_yield(div_yield)},
        'payout_ratio':         {'score': payout_score,      'weight': 0.14, 'value': payout,     'explanation': explain_payout_ratio(payout, is_reit)},
        'leverage_stability':   {'score': lev_score,         'weight': 0.13, 'value': de,         'explanation': explain_leverage_coverage(de, fcf_cov, None)},
        'fundamental_momentum': {'score': mom_score,         'weight': 0.10, 'value': mom_detail, 'explanation': mom_explanation},
    }
    return round(sum(v['score'] * v['weight'] for v in breakdown.values()), 1), breakdown


def score_value(metrics: dict):
    """
    Value portfolio scoring.
    Weights: valuation 27%, quality 27%, leverage 19%, growth 17%, momentum 10%
    valuation_composite = P/E 25% + EV/EBITDA 25% + FCF Yield 25% + EY vs Bonds 25%
    quality_composite   = ROE 40% + EPS Stability 30% + CF Quality 30%
    growth              = Revenue CAGR 60% + Growth Consistency 40%
    Returns (score: float, breakdown: dict).
    """
    try:
        from config import PH_RISK_FREE_RATE as _RFR
    except ImportError:
        _RFR = 0.065

    pe        = metrics.get('pe')
    ev        = metrics.get('ev_ebitda')
    fcf_yield = metrics.get('fcf_yield')

    pe_score    = normalise(pe,        [(8, 100), (12, 85), (18, 65), (28, 35), (40, 15)]) if pe        is not None else None
    ev_score    = normalise(ev,        [(5, 100), (8, 80),  (12, 55), (18, 30), (25, 10)]) if ev        is not None else None
    fcf_y_score = normalise(fcf_yield, [(2, 15),  (4, 40),  (6, 65),  (8, 85),  (10, 100)])if fcf_yield is not None else None

    # Earnings Yield vs Bond Rate
    ey_spread = None
    ey = None
    if pe is not None and pe > 0:
        ey = round((1 / pe) * 100, 2)
        ey_spread = round(ey - _RFR * 100, 2)
    ey_spread_score = normalise(ey_spread, [(-2, 10), (0, 30), (2, 50), (5, 75), (8, 90), (12, 100)]) if ey_spread is not None else None

    val_composite = _blend([(pe_score, 0.25), (ev_score, 0.25), (fcf_y_score, 0.25), (ey_spread_score, 0.25)])

    # Quality Composite: ROE 40% + EPS Stability 30% + CF Quality 30%
    roe = metrics.get('roe')
    roe_score = normalise(roe, [(5, 10), (10, 40), (15, 65), (20, 85), (25, 100)]) if roe is not None else None

    eps_5y = metrics.get('eps_5y', [])
    eps_3y = metrics.get('eps_3y', [])
    eps_history = eps_5y if len(eps_5y) >= 3 else eps_3y
    vol_ratio = _eps_vol_ratio(eps_history)
    net_income_3y = metrics.get('net_income_3y', [])

    if vol_ratio is not None:
        stab_score = normalise(vol_ratio, [(0.2, 100), (0.4, 85), (0.6, 70), (0.8, 55), (1.0, 35), (1.5, 15)])
    else:
        positive_years = sum(1 for n in net_income_3y if n and n > 0)
        stab_score = [0, 20, 60, 100][min(positive_years, 3)]

    operating_cf = metrics.get('operating_cf')
    cf_ratio = _cf_quality(operating_cf, net_income_3y)
    cf_score = normalise(cf_ratio, [(0.5, 10), (0.7, 25), (0.9, 45), (1.1, 65), (1.3, 85), (1.5, 100)]) if cf_ratio is not None else None

    quality_composite = _blend([(roe_score, 0.40), (stab_score, 0.30), (cf_score, 0.30)])
    positive_years_display = sum(1 for n in net_income_3y if n and n > 0)

    de = metrics.get('de_ratio')
    interest_cov = metrics.get('interest_coverage')
    de_score      = normalise(de,           [(0.3, 100), (0.7, 80), (1.2, 55), (2.0, 30), (3.0, 10)])   if de is not None           else None
    int_cov_score = normalise(interest_cov, [(1.5, 10),  (2.5, 35), (4.0, 60), (6.0, 80), (10.0, 100)]) if interest_cov is not None  else None
    lev_risk = _blend([(de_score, 0.60), (int_cov_score, 0.40)])

    # Growth: Revenue CAGR 60% + Growth Consistency 40%
    rev = metrics.get('revenue_cagr')
    rev_score = normalise(rev, [(0, 10), (3, 30), (5, 50), (10, 70), (15, 85), (20, 100)])

    revenue_5y = metrics.get('revenue_5y', [])
    consistency_series = revenue_5y if len(revenue_5y) >= 3 else eps_history
    growth_cv = _growth_consistency(consistency_series)
    consistency_score = normalise(growth_cv, [(0.10, 100), (0.20, 85), (0.35, 65), (0.50, 45), (0.70, 25)]) if growth_cv is not None else None

    growth_composite = _blend([(rev_score, 0.60), (consistency_score, 0.40)])

    mom_score, mom_detail = compute_momentum_composite(metrics)
    mom_explanation = explain_momentum(
        mom_detail.get('rev_delta'), mom_detail.get('eps_delta'), mom_detail.get('ocf_delta')
    )

    breakdown = {
        'valuation_composite':  {'score': val_composite,     'weight': 0.27, 'value': pe,  'explanation': explain_valuation_composite(pe, ev, fcf_yield, ey_spread)},
        'quality_composite':    {'score': quality_composite, 'weight': 0.27, 'value': roe, 'explanation': explain_quality_composite(roe, positive_years_display, cf_quality=cf_ratio)},
        'leverage_risk':        {'score': lev_risk,          'weight': 0.19, 'value': de,  'explanation': explain_leverage_coverage(de, None, interest_cov)},
        'growth_composite':     {'score': growth_composite,  'weight': 0.17, 'value': rev, 'explanation': explain_revenue_cagr(rev) + '  ' + explain_growth_consistency(growth_cv)},
        'fundamental_momentum': {'score': mom_score,         'weight': 0.10, 'value': mom_detail, 'explanation': mom_explanation},
    }
    return round(sum(v['score'] * v['weight'] for v in breakdown.values()), 1), breakdown


# ── Backwards-compatible aliases (used by tests/test_scorer.py) ──
score_dividend = score_pure_dividend
score_hybrid   = score_dividend_growth
