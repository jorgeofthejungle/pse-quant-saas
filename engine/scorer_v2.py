# ============================================================
# scorer_v2.py — Unified 4-Layer Scorer (Facade)
# PSE Quant SaaS — Phase 9B (v2 Unified Scorer)
# ============================================================
# Combines all 4 layers into a single unified score 0-100.
#
# Layer weights (Balanced — approved in planning):
#   Health (Layer 1):       25%
#   Improvement (Layer 2):  30%
#   Acceleration (Layer 3): 15%
#   Persistence (Layer 4):  30%
#
# Result categories:
#   >= 75: Highest Quality  (Healthy + Improving + Accelerating + Persistent)
#   >= 55: Strong Growth    (Healthy + Improving)
#   >= 35: Neutral/Watchlist (Healthy but slowing or inconsistent)
#    < 35: Weak             (Multiple red flags)
#
# Usage:
#   from engine.scorer_v2 import score_unified, rank_stocks_v2
# ============================================================

from __future__ import annotations

from engine.scorer_health      import score_health
from engine.scorer_improvement import score_improvement
from engine.scorer_acceleration import score_acceleration
from engine.scorer_persistence import score_persistence
from engine.sector_stats       import get_sector_pe

# ── Layer weights ─────────────────────────────────────────────
LAYER_WEIGHTS = {
    'health':       0.25,
    'improvement':  0.30,
    'acceleration': 0.15,
    'persistence':  0.30,
}

# ── Result categories ─────────────────────────────────────────
CATEGORIES = [
    (75, 'Highest Quality',   'Healthy, improving, accelerating, and consistent.'),
    (55, 'Strong Growth',     'Fundamentally healthy with improving trends.'),
    (35, 'Watchlist',         'Healthy today but growth momentum limited.'),
    (0,  'Weak',              'Multiple red flags in health or trend metrics.'),
]


def _layer_summary(name: str, score: float | None) -> str:
    """One-line plain-English summary for each layer, keyed by score band."""
    if score is None:
        return 'Insufficient data (requires 5+ years of financials).'
    thresholds = {
        'health': [
            (75, 'Financially strong — ROE, margins, cash flow, and leverage all healthy.'),
            (55, 'Fundamentally sound with minor weaknesses in one or two areas.'),
            (35, 'Below-average financial health — some metrics require attention.'),
            (0,  'Weak financial health — multiple red flags in key metrics.'),
        ],
        'improvement': [
            (75, 'Strong upward trend — revenue, EPS, and cash flow all improving rapidly.'),
            (55, 'Fundamentals improving across most key metrics over recent years.'),
            (35, 'Mixed improvement — some metrics improving, others flat or declining.'),
            (0,  'Fundamentals deteriorating — most metrics trending downward.'),
        ],
        'acceleration': [
            (65, 'Momentum sharply accelerating — the rate of improvement is picking up.'),
            (52, 'Growth momentum stable — recent pace similar to prior period.'),
            (35, 'Momentum decelerating — the rate of improvement is slowing.'),
            (0,  'Momentum sharply decelerating — growth losing steam rapidly.'),
        ],
        'persistence': [
            (75, 'Highly consistent — revenue, EPS, and cash flow improved reliably for years.'),
            (55, 'Generally consistent improvement with only occasional setbacks.'),
            (35, 'Mixed consistency — improvements are not reliably sustained year after year.'),
            (0,  'Erratic — fundamentals show no consistent pattern of improvement.'),
        ],
    }
    for threshold, text in thresholds.get(name, []):
        if score >= threshold:
            return text
    return f'Layer score: {score:.0f}/100.'


def _blend_layers(scores_weights: list) -> float:
    """Weighted average, redistributing weight from None layers."""
    valid = [(s, w) for s, w in scores_weights if s is not None]
    if not valid:
        return 0.0
    total_w = sum(w for _, w in valid)
    return round(sum(s * (w / total_w) for s, w in valid), 1)


def get_category(score: float) -> tuple[str, str]:
    """Returns (category_label, description) for a given score."""
    for threshold, label, desc in CATEGORIES:
        if score >= threshold:
            return label, desc
    return 'Weak', 'Multiple red flags in health or trend metrics.'


def score_unified(stock: dict,
                  sector_stats: dict | None = None,
                  financials_history: list | None = None
                  ) -> tuple[float, dict]:
    """
    Compute the unified 4-layer score for a single stock.
    Returns (final_score: float 0-100, full_breakdown: dict).

    Args:
        stock:              Standard stock dict (see CLAUDE.md §5)
        sector_stats:       Output of compute_sector_stats() — used for
                            sector-adjusted PE scoring in Layer 1
        financials_history: Annual DB rows (newest first) for ROE delta
                            in Layer 2. If None, ROE delta is skipped.
    """
    # Resolve sector median PE for this stock's sector
    sector_pe = None
    if sector_stats:
        sector_pe = get_sector_pe(stock.get('sector', ''), sector_stats)

    # ── Layer 1: Health ───────────────────────────────────────
    h_score, h_breakdown = score_health(stock, sector_median_pe=sector_pe)

    # ── Layer 2: Improvement ──────────────────────────────────
    i_score, i_breakdown = score_improvement(stock, financials_history)

    # ── Layer 3: Acceleration ─────────────────────────────────
    a_score, a_breakdown = score_acceleration(stock)
    # If all acceleration sub-scores are None (< 5 years data),
    # treat acceleration layer score as None → weight redistributed
    all_accel_none = all(
        v.get('score') is None for v in a_breakdown.values()
    )
    a_score_maybe = None if all_accel_none else a_score

    # ── Layer 4: Persistence ──────────────────────────────────
    p_score, p_breakdown = score_persistence(stock)

    # ── Final weighted blend ──────────────────────────────────
    final_score = _blend_layers([
        (h_score,       LAYER_WEIGHTS['health']),
        (i_score,       LAYER_WEIGHTS['improvement']),
        (a_score_maybe, LAYER_WEIGHTS['acceleration']),
        (p_score,       LAYER_WEIGHTS['persistence']),
    ])

    category, category_desc = get_category(final_score)

    full_breakdown = {
        'final_score': final_score,
        'category':    category,
        'category_description': category_desc,
        'layers': {
            'health': {
                'score':   h_score,
                'weight':  LAYER_WEIGHTS['health'],
                'factors': h_breakdown,
            },
            'improvement': {
                'score':   i_score,
                'weight':  LAYER_WEIGHTS['improvement'],
                'factors': i_breakdown,
            },
            'acceleration': {
                'score':   a_score_maybe,
                'weight':  LAYER_WEIGHTS['acceleration'],
                'factors': a_breakdown,
            },
            'persistence': {
                'score':   p_score,
                'weight':  LAYER_WEIGHTS['persistence'],
                'factors': p_breakdown,
            },
        },
    }

    return final_score, full_breakdown


def rank_stocks_v2(stocks: list,
                   sector_stats: dict | None = None,
                   financials_map: dict | None = None
                   ) -> list:
    """
    Score and rank a list of pre-filtered stocks using the unified model.

    Args:
        stocks:          List of stock dicts (all must have passed filter_unified)
        sector_stats:    Output of compute_sector_stats(all_stocks)
        financials_map:  Dict of {ticker: [annual_rows]} from DB — used for
                         ROE delta. If None, ROE delta is skipped.

    Returns:
        List of stock dicts sorted by score descending.
        Each stock has 'score', 'rank', 'category', and 'breakdown' added.
    """
    scored = []
    for stock in stocks:
        fins_history = (financials_map or {}).get(stock.get('ticker'), [])
        score, breakdown = score_unified(stock, sector_stats, fins_history)
        enriched = dict(stock)
        enriched['score']     = score
        enriched['category']  = breakdown['category']
        enriched['breakdown'] = breakdown
        # Flat score_breakdown for the PDF detail page bar-chart renderer
        enriched['score_breakdown'] = {
            layer_name: {
                'score':       (layer_data['score'] or 0.0),
                'weight':      layer_data['weight'],
                'value':       layer_data['score'],
                'explanation': _layer_summary(layer_name, layer_data['score']),
            }
            for layer_name, layer_data in breakdown['layers'].items()
        }
        scored.append(enriched)

    scored.sort(key=lambda s: s['score'], reverse=True)
    for i, s in enumerate(scored):
        s['rank'] = i + 1
    return scored
