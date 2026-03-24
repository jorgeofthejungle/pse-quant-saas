# ============================================================
# scorer_improvement.py — Improvement Layer Scorer (Sector-Specific)
# PSE Quant SaaS
# ============================================================
# Answers: "Are the company's fundamentals improving?"
#
# Uses recency-weighted smoothed deltas (50/30/20 newest-first).
# Sub-scores and weights driven by SECTOR_SCORING_CONFIG in config.py.
#
# Available sub-scores:
#   revenue_delta — smoothed YoY revenue growth (%)
#   eps_delta     — smoothed YoY EPS growth (%)
#   roe_delta     — absolute change in ROE vs 3 years ago (pp)
#   dps_delta     — smoothed YoY DPS growth (%) — REITs only
#
# Momentum bonus: stocks with 5yr+ data get a ±5pt adjustment based on
# whether recent growth (last 2Y) exceeds prior growth (prior 2Y).
#
# Entry: score_improvement(stock, financials_history, scoring_group)
#        → (score: float | None, breakdown: dict)
# ============================================================

from __future__ import annotations
from engine.scorer_utils import _blend_checked
from engine.sector_groups import get_layer_config
from config import IMPROVEMENT_RECENCY_WEIGHTS, MIN_SUBSCORES_PER_LAYER


# ── Threshold tables ──────────────────────────────────────

_REV_THRESHOLDS = [
    (-20, 5), (-10, 15), (-5, 25), (-2, 38),
    (  0, 50), ( 2, 62), ( 5, 75), (10, 88), (999, 100),
]
_EPS_THRESHOLDS = [
    (-30, 5), (-20, 12), (-10, 22), (-5, 35),
    (  0, 50), ( 5, 64), (10, 78), (20, 90), (999, 100),
]
_ROE_DELTA_THRESHOLDS = [   # in percentage points
    (-10, 5), (-5, 18), (-3, 32), (-1, 45),
    (  0, 55), ( 1, 65), ( 3, 78), ( 5, 88), (999, 100),
]
_DPS_THRESHOLDS = [         # REITs — distribution growth
    (-20, 5), (-10, 15), (-5, 28), (-2, 42),
    (  0, 55), ( 2, 68), ( 5, 80), (10, 92), (999, 100),
]


def _normalise(value, table: list) -> float | None:
    if value is None:
        return None
    for max_val, score in table:
        if value <= max_val:
            return float(score)
    return float(table[-1][1])


# ── Smoothed delta helpers ────────────────────────────────

def _yoy_changes(series: list) -> list:
    """Compute YoY % changes from a series (newest first). Returns newest-first."""
    valid = [v for v in series if v is not None]
    changes = []
    for i in range(len(valid) - 1):
        curr, prev = valid[i], valid[i + 1]
        if prev and prev != 0:
            changes.append((curr - prev) / abs(prev) * 100)
    return changes  # newest first


def _smoothed_delta(series: list) -> float | None:
    """
    Recency-weighted smoothed delta from the 3 most recent YoY changes.
    Weights: [0.50, 0.30, 0.20] newest first.
    Returns None if fewer than 2 data points.
    """
    changes = _yoy_changes(series)
    if not changes:
        return None
    weights = IMPROVEMENT_RECENCY_WEIGHTS
    recent  = changes[:len(weights)]
    if not recent:
        return None
    w_slice = weights[:len(recent)]
    total_w = sum(w_slice)
    return sum(c * w for c, w in zip(recent, w_slice)) / total_w


def _momentum_bonus(series: list) -> float:
    """
    Compare recent 2Y avg change vs prior 2Y avg change.
    Returns +5 if accelerating, -5 if decelerating, 0 if insufficient data.
    Requires 5+ data points.
    """
    changes = _yoy_changes(series)
    if len(changes) < 4:
        return 0.0
    recent_avg = sum(changes[:2]) / 2
    prior_avg  = sum(changes[2:4]) / 2
    if recent_avg > prior_avg + 1:
        return 5.0
    if recent_avg < prior_avg - 1:
        return -5.0
    return 0.0


# ── Sub-score functions ───────────────────────────────────

def _score_revenue_delta(stock: dict, _group: str) -> float | None:
    series = stock.get('revenue_5y') or []
    delta  = _smoothed_delta(series)
    return _normalise(delta, _REV_THRESHOLDS)


def _score_eps_delta(stock: dict, _group: str) -> float | None:
    series = stock.get('eps_5y') or stock.get('eps_3y') or []
    delta  = _smoothed_delta(series)
    return _normalise(delta, _EPS_THRESHOLDS)


def _score_roe_delta(stock: dict, financials_history: list) -> float | None:
    """ROE now vs 3 years ago (in percentage points)."""
    roe_now = stock.get('roe')
    if roe_now is None or not financials_history:
        return None
    # financials_history is newest-first; find row ~3 years back
    valid_rows = [r for r in financials_history
                  if r.get('equity') and r.get('net_income') is not None]
    if len(valid_rows) < 4:
        return None
    row_3y = valid_rows[3]
    eq = row_3y.get('equity')
    ni = row_3y.get('net_income')
    if not eq or eq == 0:
        return None
    roe_3y_ago = (ni / eq) * 100
    delta = roe_now - roe_3y_ago
    return _normalise(delta, _ROE_DELTA_THRESHOLDS)


def _score_dps_delta(stock: dict, _group: str) -> float | None:
    """Distribution growth for REITs."""
    series = stock.get('dividends_5y') or []
    # Filter out zeros (non-paying years)
    valid = [d for d in series if d and d > 0]
    if len(valid) < 2:
        return None
    delta = _smoothed_delta(valid)
    return _normalise(delta, _DPS_THRESHOLDS)


# ── Sub-score dispatcher ──────────────────────────────────

_SUBSCORERS = {
    'revenue_delta': _score_revenue_delta,
    'eps_delta':     _score_eps_delta,
    'dps_delta':     _score_dps_delta,
    # roe_delta handled separately (needs financials_history)
}


# ── Main entry ────────────────────────────────────────────

def score_improvement(stock: dict, financials_history: list,
                      scoring_group: str) -> tuple[float | None, dict]:
    """
    Score the Improvement layer for this stock using sector-specific config.

    Args:
        stock:             canonical stock dict
        financials_history: list of annual rows (newest first) from DB
        scoring_group:     from engine.sector_groups.get_scoring_group()

    Returns:
        (score: float | None, breakdown: dict)
    """
    layer_cfg = get_layer_config(scoring_group, 'improvement')
    if not layer_cfg:
        return None, {'error': f'No improvement config for group={scoring_group}'}

    scores_weights = []
    factors: dict  = {}
    bonus          = 0.0

    for sub_name, weight in layer_cfg.items():
        if sub_name == 'roe_delta':
            s = _score_roe_delta(stock, financials_history)
        else:
            fn = _SUBSCORERS.get(sub_name)
            s  = fn(stock, scoring_group) if fn else None

        scores_weights.append((s, weight))
        factors[sub_name] = round(s, 1) if s is not None else None

    # Momentum bonus — for stocks with 5yr+ EPS or Revenue data
    eps_series = stock.get('eps_5y') or []
    rev_series = stock.get('revenue_5y') or []
    if len([v for v in eps_series if v is not None]) >= 5:
        bonus = _momentum_bonus(eps_series)
    elif len([v for v in rev_series if v is not None]) >= 5:
        bonus = _momentum_bonus(rev_series)

    score = _blend_checked(scores_weights, min_subscores=MIN_SUBSCORES_PER_LAYER)
    if score is not None and bonus != 0:
        score = max(0.0, min(100.0, score + bonus))

    factors['_momentum_bonus'] = bonus if bonus != 0 else None

    breakdown = {
        'score':   round(score, 1) if score is not None else None,
        'group':   scoring_group,
        'factors': factors,
    }
    return score, breakdown
