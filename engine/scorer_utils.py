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


def _cf_quality(operating_cf, net_income_3y: list) -> float | None:
    """
    Computes Cash Flow Quality = Operating CF / abs(most recent Net Income).
    Ratio >= 1.0 means earnings are fully backed by real cash.
    Returns None if data is missing or net income is zero.
    """
    if operating_cf is None:
        return None
    if not net_income_3y:
        return None
    ni = net_income_3y[0] if net_income_3y[0] is not None else None
    if ni is None or ni == 0:
        return None
    return round(operating_cf / abs(ni), 3)


def _dividend_stability(dividends_5y: list) -> float | None:
    """
    Computes Dividend Stability as the Coefficient of Variation (CV)
    of dividend payments over the past 5 years.
    CV = StdDev / Mean. Lower CV = more stable dividend stream.
    Returns None if fewer than 3 data points or mean <= 0.

    Used in the Pure Dividend Quality Composite alongside ROE and CF Quality.
    A company can have volatile EPS but maintain stable dividends (e.g. utilities).
    """
    valid = [d for d in dividends_5y if d is not None and d > 0]
    if len(valid) < 3:
        return None
    mean_d = sum(valid) / len(valid)
    if mean_d <= 0:
        return None
    stdev_d = _stats.pstdev(valid)
    return round(stdev_d / mean_d, 3)


def _growth_consistency(series: list) -> float | None:
    """
    Computes Growth Consistency as the Coefficient of Variation (CV) of a series.
    CV = StdDev / Mean. Lower CV = more consistent growth.
    Returns None if insufficient data or mean <= 0.
    """
    valid = [v for v in series if v is not None and v > 0]
    if len(valid) < 3:
        return None
    mean_val = sum(valid) / len(valid)
    if mean_val <= 0:
        return None
    stdev_val = _stats.pstdev(valid)
    return round(stdev_val / mean_val, 3)
