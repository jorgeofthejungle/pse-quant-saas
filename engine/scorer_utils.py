# ============================================================
# scorer_utils.py — Scoring Utility Functions
# PSE Quant SaaS
# ============================================================
# Shared helpers used by the three portfolio scoring functions.
# normalise()   — maps raw metric value → 0-100 sub-score
# _blend()      — weighted average ignoring missing values
# _eps_cagr()   — annualised EPS growth rate
# _eps_vol_ratio() — EPS volatility ratio (StdDev / Mean)
# ============================================================

import statistics as _stats


def normalise(value, thresholds: list):
    """
    Converts a raw metric value into a 0-100 sub-score.
    thresholds = list of (max_value, score) pairs, in ascending order.
    Returns 0 if value is None.
    """
    if value is None:
        return 0
    for max_val, score in thresholds:
        if value <= max_val:
            return score
    return thresholds[-1][1] if thresholds else 0


def _blend(scores_weights: list) -> float:
    """
    Blends multiple (score, weight) pairs, ignoring pairs where score is None.
    Redistributes weight to available scores.
    Returns 0 if no scores are available.
    """
    valid = [(s, w) for s, w in scores_weights if s is not None]
    if not valid:
        return 0
    total_w = sum(w for _, w in valid)
    return sum(s * (w / total_w) for s, w in valid)


def _eps_cagr(eps_history: list) -> float | None:
    """
    Computes annualised EPS growth rate from a history list (newest first).
    Returns None if insufficient data or negative base EPS.
    """
    valid = [e for e in eps_history if e is not None]
    if len(valid) < 2:
        return None
    newest = valid[0]
    oldest = valid[-1]
    n = len(valid) - 1
    if oldest <= 0 or newest <= 0:
        return None
    cagr = ((newest / oldest) ** (1.0 / n) - 1) * 100
    return round(cagr, 2)


def _eps_vol_ratio(eps_history: list) -> float | None:
    """
    Computes EPS Volatility Ratio = StdDev / Mean.
    Returns None if insufficient data or mean <= 0.
    """
    valid = [e for e in eps_history if e is not None]
    if len(valid) < 3:
        return None
    mean_eps = sum(valid) / len(valid)
    if mean_eps <= 0:
        return None
    stdev_eps = _stats.pstdev(valid)
    return round(stdev_eps / mean_eps, 3)
