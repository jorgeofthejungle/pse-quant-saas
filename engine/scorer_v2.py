# ============================================================
# scorer_v2.py — Unified 3-Layer Scorer (Facade)
# PSE Quant SaaS
# ============================================================
# Combines Health, Improvement, and Persistence into a single
# unified score 0-100. Sector-specific metric selection driven
# by SECTOR_SCORING_CONFIG in config.py.
#
# Layer weights (loaded from config.SCORER_WEIGHTS):
#   Health      (Layer 1): 25-35%  — financial health today
#   Improvement (Layer 2): 25-30%  — fundamentals improving
#   Persistence (Layer 3): 35-45%  — improvement consistent
#
# Acceleration removed — signal folded into Improvement as a
# ±5pt momentum bonus for stocks with 5yr+ data.
#
# Result categories:
#   >= 75: Highest Quality  (Healthy + Improving + Persistent)
#   >= 55: Strong Growth    (Healthy + Improving)
#   >= 35: Watchlist        (Healthy but inconsistent trend)
#    < 35: Weak             (Multiple red flags)
#
# Usage:
#   from engine.scorer_v2 import score_unified, rank_stocks_v2
# ============================================================

from __future__ import annotations
import statistics as _stats

from engine.scorer_health      import score_health
from engine.scorer_improvement import score_improvement
from engine.scorer_persistence import score_persistence
from engine.sector_groups      import get_scoring_group
from engine.validator          import calc_data_confidence
from config                    import SCORER_WEIGHTS, MIN_SCORE_THRESHOLD

# ── Result categories ─────────────────────────────────────────
CATEGORIES = [
    (75, 'Highest Quality',   'Healthy, improving, and consistently growing.'),
    (55, 'Strong Growth',     'Fundamentally healthy with improving trends.'),
    (35, 'Watchlist',         'Healthy today but growth momentum limited.'),
    (0,  'Weak',              'Multiple red flags in health or trend metrics.'),
]


def _layer_summary(name: str, score: float | None) -> str:
    """One-line plain-English summary for each layer, keyed by score band."""
    if score is None:
        return 'Insufficient data to score this layer.'
    thresholds = {
        'health': [
            (75, 'Financially strong — ROE, margins, and leverage all healthy.'),
            (55, 'Fundamentally sound with minor weaknesses in one or two areas.'),
            (35, 'Below-average financial health — some metrics require attention.'),
            (0,  'Weak financial health — multiple red flags in key metrics.'),
        ],
        'improvement': [
            (75, 'Strong upward trend — revenue and EPS improving rapidly.'),
            (55, 'Fundamentals improving across most key metrics over recent years.'),
            (35, 'Mixed improvement — some metrics improving, others flat or declining.'),
            (0,  'Fundamentals deteriorating — most metrics trending downward.'),
        ],
        'persistence': [
            (75, 'Highly consistent — revenue and EPS improved reliably for years.'),
            (55, 'Generally consistent improvement with only occasional setbacks.'),
            (35, 'Mixed consistency — improvements are not reliably sustained year after year.'),
            (0,  'Erratic — fundamentals show no consistent pattern of improvement.'),
        ],
    }
    for threshold, text in thresholds.get(name, []):
        if score >= threshold:
            return text
    return f'Layer score: {score:.0f}/100.'


def _blend_layers(scores_weights: list) -> float | None:
    """Weighted average, redistributing weight from None layers. Returns None if all layers are None."""
    valid = [(s, w) for s, w in scores_weights if s is not None]
    if not valid:
        return None
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
                  financials_history: list | None = None,
                  portfolio_type: str = 'unified',
                  ) -> tuple[float, dict]:
    """
    Compute the unified 3-layer score for a single stock.
    Returns (final_score: float 0-100, full_breakdown: dict).

    Args:
        stock:              Standard stock dict (see CLAUDE.md §5)
        sector_stats:       Unused — retained for backward-compat call signature.
                            Sector-specific scoring is now handled internally via
                            get_scoring_group() and SECTOR_SCORING_CONFIG.
        financials_history: Annual DB rows (newest first) for ROE delta
                            in Layer 2. If None, ROE delta is skipped.
        portfolio_type:     One of 'unified', 'dividend', 'value'.
                            Selects the correct layer weights from
                            config.SCORER_WEIGHTS.
    """
    weights = SCORER_WEIGHTS.get(portfolio_type, SCORER_WEIGHTS['unified'])

    # Resolve sector-specific scoring group for this stock
    scoring_group = get_scoring_group(stock)

    # ── Layer 1: Health ───────────────────────────────────────
    h_score, h_breakdown = score_health(stock, scoring_group)

    # ── Layer 2: Improvement ──────────────────────────────────
    i_score, i_breakdown = score_improvement(stock, financials_history or [], scoring_group)

    # ── Layer 3: Persistence ──────────────────────────────────
    p_score, p_breakdown = score_persistence(stock, scoring_group)

    # ── Final weighted blend (3 layers) ──────────────────────
    final_score = _blend_layers([
        (h_score, weights['health']),
        (i_score, weights['improvement']),
        (p_score, weights['persistence']),
    ])

    category, category_desc = get_category(final_score)

    full_breakdown = {
        'final_score': final_score,
        'category':    category,
        'category_description': category_desc,
        'portfolio_type': portfolio_type,
        'scoring_group':  scoring_group,
        'layers': {
            'health': {
                'score':   h_breakdown.get('score'),
                'weight':  weights['health'],
                'factors': h_breakdown.get('factors', {}),
            },
            'improvement': {
                'score':   i_breakdown.get('score'),
                'weight':  weights['improvement'],
                'factors': i_breakdown.get('factors', {}),
            },
            'persistence': {
                'score':   p_breakdown.get('score'),
                'weight':  weights['persistence'],
                'factors': p_breakdown.get('factors', {}),
            },
        },
    }

    # ── Optional: conglomerate segment blending ───────────────
    segment_data = stock.get('segment_data')
    if segment_data:
        try:
            from engine.conglomerate_scorer import apply_conglomerate_scoring
            final_score, full_breakdown = apply_conglomerate_scoring(
                final_score, full_breakdown, stock, segment_data
            )
        except Exception:
            pass   # Never break standard scoring

    # ── Data confidence multiplier ────────────────────────────
    # 5yr=1.0, 4yr=0.9, 3yr=0.8, 2yr=0.65, 1yr=0.0
    confidence = calc_data_confidence(stock)
    final_score = round(final_score * confidence, 1)
    full_breakdown['confidence']   = confidence
    full_breakdown['final_score']  = final_score

    return final_score, full_breakdown


def rank_stocks_v2(stocks: list,
                   sector_stats: dict | None = None,
                   financials_map: dict | None = None,
                   portfolio_type: str = 'unified',
                   ) -> list:
    """
    Score and rank a list of pre-filtered stocks using the unified model.

    Args:
        stocks:          List of stock dicts (all must have passed filter_unified)
        sector_stats:    Unused — retained for backward-compat call signature.
        financials_map:  Dict of {ticker: [annual_rows]} from DB — used for
                         ROE delta. If None, ROE delta is skipped.
        portfolio_type:  One of 'unified', 'dividend', 'value'.
                         Passed to score_unified for weight selection.

    Returns:
        List of stock dicts sorted by score descending, filtered by
        MIN_SCORE_THRESHOLD. Each stock has 'score', 'rank', 'category',
        'breakdown', and 'score_breakdown' added.
    """
    scored = []
    for stock in stocks:
        # REITs are income vehicles — exclude from Value portfolio
        if portfolio_type == 'value' and stock.get('is_reit'):
            continue
        fins_history = (financials_map or {}).get(stock.get('ticker'), [])
        score, breakdown = score_unified(stock, sector_stats, fins_history,
                                        portfolio_type=portfolio_type)
        enriched = dict(stock)
        enriched['score']         = score
        enriched['category']      = breakdown['category']
        enriched['breakdown']     = breakdown
        enriched['confidence']    = breakdown.get('confidence', 1.0)
        enriched['scoring_group'] = breakdown.get('scoring_group', 'general')
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

    # ── Dynamic threshold: mean + 0.5 SD of this run's scores ────
    # Step 1: apply hard absolute floor to remove junk scores before
    #         computing the distribution (avoids dragging the mean down).
    # Step 2: compute mean + 0.5 SD on the remaining pool.
    # Step 3: use whichever is higher — dynamic or hard floor.
    above_floor = [s['score'] for s in scored if s['score'] >= MIN_SCORE_THRESHOLD]
    if len(above_floor) >= 2:
        mean  = _stats.mean(above_floor)
        stdev = _stats.stdev(above_floor)
        dynamic_threshold = round(mean + 0.5 * stdev, 1)
        threshold = max(dynamic_threshold, MIN_SCORE_THRESHOLD)
    else:
        threshold = MIN_SCORE_THRESHOLD

    scored = [s for s in scored if s['score'] >= threshold]
    for i, s in enumerate(scored):
        s['rank'] = i + 1
        s['score_threshold'] = threshold  # expose for PDF/logging
    return scored
