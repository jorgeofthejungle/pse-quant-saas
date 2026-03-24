# ============================================================
# scorer_persistence.py — Persistence Layer Scorer (Sector-Specific)
# PSE Quant SaaS
# ============================================================
# Answers: "Is the improvement consistent and sustainable?"
#
# Sub-scores and weights driven by SECTOR_SCORING_CONFIG in config.py.
#
# Available sub-scores:
#   revenue   — persistence of revenue growth
#   eps       — persistence of EPS growth
#   dps       — persistence of dividend payments (REITs)
#   direction — % of years where all available metrics improved together
#
# Each metric persistence = direction(60pts) + magnitude(20pts) + streak(20pts)
#
# Entry: score_persistence(stock, scoring_group)
#        → (score: float | None, breakdown: dict)
# ============================================================

from __future__ import annotations
from engine.scorer_utils import _blend_checked
from engine.sector_groups import get_layer_config
from config import MIN_SUBSCORES_PER_LAYER


def _yoy_changes(series: list) -> list:
    """YoY % changes from a series (newest first). Returns newest-first."""
    valid = [v for v in series if v is not None]
    changes = []
    for i in range(len(valid) - 1):
        curr, prev = valid[i], valid[i + 1]
        if prev and prev != 0:
            changes.append((curr - prev) / abs(prev) * 100)
    return changes  # newest first


def _single_persistence(series: list) -> float | None:
    """
    Score persistence of a single metric series.
    Formula: direction(60pts) + magnitude(20pts) + streak_bonus(20pts)
    Returns None if fewer than 2 data points.
    """
    changes = _yoy_changes(series)
    if not changes:
        return None

    pos = [c for c in changes if c > 0]
    ratio = len(pos) / len(changes)

    # Direction score (0-60)
    direction = ratio * 60

    # Magnitude score (0-20) — avg positive YoY change
    if pos:
        avg_pos = sum(pos) / len(pos)
        if avg_pos >= 15:   magnitude = 20
        elif avg_pos >= 10: magnitude = 15
        elif avg_pos >= 5:  magnitude = 10
        elif avg_pos >= 1:  magnitude = 5
        else:               magnitude = 2
    else:
        magnitude = 0

    # Streak bonus (0-20) — consecutive positive years (newest first)
    streak = 0
    for c in changes:
        if c > 0:
            streak += 1
        else:
            break
    bonus = min(streak * 5, 20)

    raw = direction + magnitude + bonus
    # Penalty: if most recent year declined and score is inflated
    if streak == 0 and raw > 65:
        raw = 65

    return min(float(raw), 100.0)


def _score_revenue(stock: dict, _group: str) -> float | None:
    series = stock.get('revenue_5y') or []
    return _single_persistence(series)


def _score_eps(stock: dict, _group: str) -> float | None:
    series = stock.get('eps_5y') or stock.get('eps_3y') or []
    return _single_persistence(series)


def _score_dps(stock: dict, _group: str) -> float | None:
    """Dividend persistence — primarily for REITs."""
    series = stock.get('dividends_5y') or []
    paying = [d for d in series if d and d > 0]
    if len(paying) < 2:
        return None
    return _single_persistence(paying)


def _score_direction(stock: dict, _group: str) -> float | None:
    """
    % of years where all available metrics improved together.
    Uses Revenue and EPS as the two core universal signals.
    Returns None if insufficient data.
    """
    rev_series = stock.get('revenue_5y') or []
    eps_series = stock.get('eps_5y') or stock.get('eps_3y') or []

    rev_valid = [v for v in rev_series if v is not None]
    eps_valid = [v for v in eps_series if v is not None]

    years = min(len(rev_valid), len(eps_valid))
    if years < 3:
        return None

    # How many years did both rev AND eps improve?
    both_pos = 0
    total    = 0
    for i in range(min(years - 1, 4)):
        rev_up = (rev_valid[i] - rev_valid[i + 1]) / abs(rev_valid[i + 1]) > 0 if rev_valid[i + 1] else False
        eps_up = (eps_valid[i] - eps_valid[i + 1]) / abs(eps_valid[i + 1]) > 0 if eps_valid[i + 1] else False
        total += 1
        if rev_up and eps_up:
            both_pos += 1

    if total == 0:
        return None
    return (both_pos / total) * 100


# ── Sub-score dispatcher ──────────────────────────────────

_SUBSCORERS = {
    'revenue':   _score_revenue,
    'eps':       _score_eps,
    'dps':       _score_dps,
    'direction': _score_direction,
}


# ── Main entry ────────────────────────────────────────────

def score_persistence(stock: dict,
                      scoring_group: str) -> tuple[float | None, dict]:
    """
    Score the Persistence layer for this stock using sector-specific config.

    Args:
        stock:         canonical stock dict
        scoring_group: from engine.sector_groups.get_scoring_group()

    Returns:
        (score: float | None, breakdown: dict)
    """
    layer_cfg = get_layer_config(scoring_group, 'persistence')
    if not layer_cfg:
        return None, {'error': f'No persistence config for group={scoring_group}'}

    scores_weights = []
    factors: dict  = {}

    for sub_name, weight in layer_cfg.items():
        fn = _SUBSCORERS.get(sub_name)
        if fn is None:
            continue
        s = fn(stock, scoring_group)
        scores_weights.append((s, weight))
        factors[sub_name] = round(s, 1) if s is not None else None

    score = _blend_checked(scores_weights, min_subscores=MIN_SUBSCORES_PER_LAYER)

    breakdown = {
        'score':   round(score, 1) if score is not None else None,
        'group':   scoring_group,
        'factors': factors,
    }
    return score, breakdown
