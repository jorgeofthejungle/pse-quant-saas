# ============================================================
# scorer_explanations.py — Plain-English Score Explanations
# PSE Quant SaaS — engine facade
# ============================================================
# Re-exports all explain_*() functions from sub-modules.
# All callers import from here -- internal split is hidden.
#   scorer_explanations_dividend.py — yield, CAGR, payout, FCF, EPS stability
#   scorer_explanations_value.py    — P/E, P/B, ROE, EV/EBITDA, quality, leverage
# ============================================================

try:
    from engine.scorer_explanations_dividend import (
        explain_dividend_yield, explain_dividend_cagr, explain_payout_ratio,
        explain_fcf_coverage, explain_eps_stability, explain_fcf_yield,
        explain_dividend_stability,
    )
    from engine.scorer_explanations_value import (
        explain_roe, explain_eps_growth, explain_pe, explain_pb,
        explain_ev_ebitda, explain_revenue_cagr, explain_de_ratio,
        explain_leverage_coverage, explain_relative_valuation,
        explain_valuation_composite, explain_quality_composite,
        explain_cash_flow_quality, explain_earnings_yield_spread,
        explain_growth_consistency,
    )
except ImportError:
    from scorer_explanations_dividend import (
        explain_dividend_yield, explain_dividend_cagr, explain_payout_ratio,
        explain_fcf_coverage, explain_eps_stability, explain_fcf_yield,
        explain_dividend_stability,
    )
    from scorer_explanations_value import (
        explain_roe, explain_eps_growth, explain_pe, explain_pb,
        explain_ev_ebitda, explain_revenue_cagr, explain_de_ratio,
        explain_leverage_coverage, explain_relative_valuation,
        explain_valuation_composite, explain_quality_composite,
        explain_cash_flow_quality, explain_earnings_yield_spread,
        explain_growth_consistency,
    )

__all__ = [
    'explain_dividend_yield', 'explain_dividend_cagr', 'explain_payout_ratio',
    'explain_fcf_coverage', 'explain_eps_stability', 'explain_fcf_yield',
    'explain_dividend_stability',
    'explain_roe', 'explain_eps_growth', 'explain_pe', 'explain_pb',
    'explain_ev_ebitda', 'explain_revenue_cagr', 'explain_de_ratio',
    'explain_leverage_coverage', 'explain_relative_valuation',
    'explain_valuation_composite', 'explain_quality_composite',
    'explain_cash_flow_quality', 'explain_earnings_yield_spread',
    'explain_growth_consistency',
]
