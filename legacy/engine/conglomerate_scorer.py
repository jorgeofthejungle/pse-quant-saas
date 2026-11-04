# ============================================================
# conglomerate_scorer.py — Segment-Level Scoring for PH Holding Firms
# PSE Quant SaaS
# ============================================================
# Replaces the flat 20% conglomerate IV discount with a
# calculated discount (5-25%) based on segment quality,
# diversity, and transparency.
#
# Also blends per-segment health scores with the parent's
# standard v2 score for a more accurate overall rating.
#
# Usage (called from scorer_v2.score_unified when segment_data present):
#   from engine.conglomerate_scorer import apply_conglomerate_scoring
#   final_score, breakdown = apply_conglomerate_scoring(
#       final_score, breakdown, stock, segment_data
#   )
# ============================================================

from __future__ import annotations

# All PH conglomerates covered by segment scoring
# Sourced from engine/conglomerate_map.py — kept in sync
from engine.conglomerate_map import ALL_CONGLOMERATE_TICKERS as CONGLOMERATE_TICKERS


# ── Per-segment health scoring ────────────────────────────────

def _score_segment(segment: dict) -> float | None:
    """
    Simplified health score (0-100) for a single segment using
    only the data available: revenue, net_income, equity.
    Returns None if insufficient data.
    """
    scores = []

    revenue    = segment.get('revenue')
    net_income = segment.get('net_income')
    equity     = segment.get('equity')

    # ROE score
    if net_income is not None and equity and equity > 0:
        roe = (net_income / equity) * 100
        if   roe >= 20: scores.append(90)
        elif roe >= 15: scores.append(75)
        elif roe >= 10: scores.append(60)
        elif roe >= 5:  scores.append(45)
        elif roe >= 0:  scores.append(30)
        else:           scores.append(10)

    # Net margin score
    if net_income is not None and revenue and revenue > 0:
        margin = (net_income / revenue) * 100
        if   margin >= 20: scores.append(90)
        elif margin >= 12: scores.append(75)
        elif margin >= 6:  scores.append(55)
        elif margin >= 0:  scores.append(35)
        else:              scores.append(10)

    return round(sum(scores) / len(scores), 1) if scores else None


def score_all_segments(segments: list[dict]) -> list[dict]:
    """
    Scores each segment and computes its revenue share.
    Returns enriched segment list with 'health_score' and 'revenue_share' added.
    """
    total_rev = sum(
        s.get('revenue') or 0 for s in segments if s.get('revenue') is not None
    ) or None

    enriched = []
    for seg in segments:
        rev   = seg.get('revenue')
        share = (rev / total_rev) if (rev and total_rev) else None
        enriched.append({
            **seg,
            'health_score':  _score_segment(seg),
            'revenue_share': round(share, 4) if share else None,
        })
    return enriched


def weighted_segment_score(scored_segments: list[dict]) -> float | None:
    """
    Revenue-weighted average of segment health scores.
    Returns None if no scored segments with revenue data.
    """
    pairs = [
        (s['health_score'], s['revenue_share'])
        for s in scored_segments
        if s.get('health_score') is not None and s.get('revenue_share') is not None
    ]
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if not total_w:
        return None
    return round(sum(sc * (w / total_w) for sc, w in pairs), 1)


# ── Discount calculation ──────────────────────────────────────

def compute_conglomerate_discount(
    segments: list[dict],
    w_score:  float | None,
) -> float:
    """
    Returns a calculated IV discount % (5-25%) for a holding firm.
    Replaces the flat 20% in mos.py / routes_stocks.py.

    Factors:
      - Base: 10%
      - Quality adjustment: ±5% based on weighted segment health score
      - Complexity: +1.5% per segment beyond 3
      - Transparency: +2% per segment without a listed ticker (unlisted subs)
    """
    base = 10.0

    # Quality: score 50 = neutral; higher = less discount, lower = more
    quality_adj = 0.0
    if w_score is not None:
        quality_adj = (50.0 - w_score) * 0.10   # -5 to +5 range for 0-100

    # Complexity
    n = len(segments)
    complexity_adj = max(0.0, (n - 3) * 1.5)

    # Transparency
    unlisted = sum(1 for s in segments if not s.get('segment_ticker'))
    transparency_adj = unlisted * 1.5

    discount = base + quality_adj + complexity_adj + transparency_adj
    return max(5.0, min(25.0, round(discount, 1)))


# ── Main integration hook ─────────────────────────────────────

def apply_conglomerate_scoring(
    base_score:    float,
    breakdown:     dict,
    stock:         dict,
    segment_data:  list[dict],
) -> tuple[float, dict]:
    """
    Blends the standard v2 score with segment-level quality scores
    and injects conglomerate metadata into the breakdown dict.

    Blend: 70% standard v2 score + 30% segment weighted score.
    (If no segment scores available, returns base_score unchanged.)

    Returns (adjusted_score, enriched_breakdown).
    """
    scored_segs  = score_all_segments(segment_data)
    w_score      = weighted_segment_score(scored_segs)
    discount_pct = compute_conglomerate_discount(scored_segs, w_score)

    if w_score is not None:
        adjusted = round(0.70 * base_score + 0.30 * w_score, 1)
    else:
        adjusted = base_score

    breakdown['conglomerate'] = {
        'segment_count':   len(scored_segs),
        'weighted_score':  w_score,
        'discount_pct':    discount_pct,
        'segments':        scored_segs,
        'blend_note': (
            f'Score blended: 70% fundamental ({base_score}) '
            f'+ 30% segment quality ({w_score}). '
            f'IV discount: {discount_pct:.0f}% (calculated, replaces flat 20%).'
        ) if w_score is not None else (
            'No segment quality data — standard scoring used. '
            f'IV discount: {discount_pct:.0f}%.'
        ),
    }

    return adjusted, breakdown
