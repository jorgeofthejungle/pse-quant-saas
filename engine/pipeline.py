# ============================================================
# pipeline.py — Shared Score-and-Rank Pipeline
# PSE Quant SaaS — engine sub-module
# ============================================================
# Single source of truth for the filter → score → IV → MoS
# pipeline used by both main.py (manual runs) and
# scheduler_jobs.py (daily scheduled job).
# ============================================================

try:
    from engine.mos import (
        calc_ddm, calc_two_stage_ddm, calc_eps_pe, calc_dcf,
        calc_mos_price, calc_mos_pct, calc_hybrid_intrinsic,
        apply_conglomerate_discount, _sector_median_pe,
    )
except ImportError:
    from mos import (
        calc_ddm, calc_two_stage_ddm, calc_eps_pe, calc_dcf,
        calc_mos_price, calc_mos_pct, calc_hybrid_intrinsic,
        apply_conglomerate_discount, _sector_median_pe,
    )

# Portfolio-specific IV blend weights: (DDM weight, EPS-PE weight, DCF weight)
# These are intentional design decisions — do not change without explicit instruction.
IV_WEIGHTS = {
    'pure_dividend':   (0.50, 0.25, 0.25),
    'dividend_growth': (0.40, 0.30, 0.30),
    'value':           (0.20, 0.40, 0.40),
}


def score_and_rank(
    filtered_stocks: list,
    portfolio_type:  str,
    score_fn,
    all_stocks:      list = None,
) -> list:
    """
    Scores each stock, calculates intrinsic value and Margin of Safety,
    and returns the list sorted by score (highest first).

    Parameters:
        filtered_stocks -- stocks that have already passed the portfolio filter
        portfolio_type  -- 'pure_dividend' | 'dividend_growth' | 'value'
        score_fn        -- scoring function for this portfolio (from scorer.py)
        all_stocks      -- full stock universe for sector-median PE computation.
                           Falls back to filtered_stocks if not provided.

    Returns:
        List of stock dicts enriched with:
            score, score_breakdown, intrinsic_value, mos_price, mos_pct
    """
    universe   = all_stocks if all_stocks else filtered_stocks
    iv_weights = IV_WEIGHTS.get(portfolio_type, (0.40, 0.40, 0.20))

    # Pre-compute sector PE medians (cached per sector) from the full universe
    sector_pe_cache = {}

    result = []
    for stock in filtered_stocks:
        score, breakdown = score_fn(stock)

        sector = stock.get('sector', '')
        if sector not in sector_pe_cache:
            sector_pe_cache[sector] = _sector_median_pe(sector, universe)
        sector_pe = sector_pe_cache[sector]

        # DDM: Two-Stage for dividend_growth (explicit 5yr + terminal),
        #      Gordon Growth Model for pure_dividend and value portfolios
        if portfolio_type == 'dividend_growth':
            ddm_val, _ = calc_two_stage_ddm(
                stock.get('dps_last'),
                stock.get('revenue_cagr'),
            )
        else:
            ddm_val, _ = calc_ddm(
                stock.get('dps_last'),
                stock.get('dividend_cagr_5y'),
            )

        eps_val, _ = calc_eps_pe(
            stock.get('eps_3y', []),
            target_pe=sector_pe,
            roe=stock.get('roe'),
        )
        dcf_val, _ = calc_dcf(
            stock.get('fcf_per_share'),
            stock.get('revenue_cagr'),
        )

        iv, _ = calc_hybrid_intrinsic(ddm_val, eps_val, dcf_val, weights=iv_weights)
        iv = apply_conglomerate_discount(iv, sector)

        mos_price = calc_mos_price(iv, portfolio_type)
        mos_pct   = calc_mos_pct(iv, stock.get('current_price'))

        result.append({
            **stock,
            'score':           score,
            'score_breakdown': breakdown,
            'intrinsic_value': iv,
            'mos_price':       mos_price,
            'mos_pct':         mos_pct,
        })

    result.sort(key=lambda x: x['score'], reverse=True)
    return result
