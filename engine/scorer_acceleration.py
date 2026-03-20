# ============================================================
# scorer_acceleration.py — Layer 3: Acceleration Score
# PSE Quant SaaS — Phase 9B (v2 Unified Scorer)
# ============================================================
# Answers: "Is the improvement getting stronger?"
#
# Uses 2-year window comparisons (not raw ΔΔ) to reduce noise
# from annual-only data. Compares:
#   recent 2-year delta vs prior 2-year delta
#
# Example:
#   Revenue growth 2022-2023: +5%  (prior window)
#   Revenue growth 2023-2024: +12% (recent window)
#   Acceleration = +7pp → growth momentum strengthening
#
# Signals:
#   - Revenue Acceleration (40%) — demand momentum
#   - EPS Acceleration     (35%) — earnings momentum
#   - OCF Acceleration     (25%) — cash flow momentum
#
# Weight in final score: 5% (reduced from 15%; rarely has 5yr data)
# Returns None → weight redistributed to other layers when data < 4 years.
#
# Returns: (score: float 0-100, breakdown: dict)
# ============================================================

from __future__ import annotations


def _normalise(value, thresholds: list) -> float:
    if value is None:
        return 0.0
    for max_val, score in thresholds:
        if value <= max_val:
            return float(score)
    return float(thresholds[-1][1])


def _blend(scores_weights: list) -> float:
    valid = [(s, w) for s, w in scores_weights if s is not None]
    if not valid:
        return 0.0
    total_w = sum(w for _, w in valid)
    return round(sum(s * (w / total_w) for s, w in valid), 1)


# ── Acceleration computation ──────────────────────────────────

def _two_window_delta(series: list) -> float | None:
    """
    Computes acceleration as: recent_2y_delta - prior_2y_delta
    where each window delta is the average YoY % change over 2 years.

    Requires at least 5 data points (newest first):
      [y0, y1, y2, y3, y4]
      recent delta = avg(y0/y1 - 1, y1/y2 - 1)
      prior delta  = avg(y2/y3 - 1, y3/y4 - 1)

    Returns None if insufficient data or zero/negative denominators.
    """
    clean = [v for v in series if v is not None]
    if len(clean) < 5:
        return None

    def pct_change(curr, prior):
        if prior == 0:
            return None
        return (curr - prior) / abs(prior) * 100

    # Recent window: y0→y1, y1→y2
    r1 = pct_change(clean[0], clean[1])
    r2 = pct_change(clean[1], clean[2])
    if r1 is None and r2 is None:
        return None
    recent_vals = [v for v in [r1, r2] if v is not None]
    recent_delta = sum(recent_vals) / len(recent_vals)

    # Prior window: y2→y3, y3→y4
    p1 = pct_change(clean[2], clean[3])
    p2 = pct_change(clean[3], clean[4])
    if p1 is None and p2 is None:
        return None
    prior_vals = [v for v in [p1, p2] if v is not None]
    prior_delta = sum(prior_vals) / len(prior_vals)

    return recent_delta - prior_delta


# ── Normalisation thresholds for acceleration (delta of delta in pp) ──
# Wider bands: at 5% weight, fine-grained differences matter less.
# Symmetric around 0: positive = accelerating, negative = decelerating
_ACCEL_THRESHOLDS = [
    (-15, 5),  (-10, 15), (-5, 30),  (-2, 40),
    (0,  50),  (2,  60),  (5, 75),   (10, 90),
    (15, 100),
]


def _score_acceleration(series: list | None) -> float | None:
    """Returns 0-100 acceleration score, or None if data insufficient."""
    if not series:
        return None
    accel = _two_window_delta(series)
    if accel is None:
        return None
    return _normalise(accel, _ACCEL_THRESHOLDS)


# ── Main scorer ───────────────────────────────────────────────

def score_acceleration(stock: dict) -> tuple[float, dict]:
    """
    Layer 3 — Acceleration Score.
    Evaluates whether the rate of improvement is strengthening.
    Returns (score 0-100, breakdown).

    Required stock dict keys:
        revenue_5y, eps_5y, operating_cf_history
        (each needs min 5 values for full signal; returns None if fewer)
    """
    rev_series = stock.get('revenue_5y') or []
    eps_series = stock.get('eps_5y') or []
    ocf_series = stock.get('operating_cf_history') or []

    rev_s = _score_acceleration(rev_series)
    eps_s = _score_acceleration(eps_series)
    ocf_s = _score_acceleration(ocf_series)

    score = _blend([
        (rev_s, 0.40),
        (eps_s, 0.35),
        (ocf_s, 0.25),
    ])

    rev_accel = _two_window_delta(rev_series)
    eps_accel = _two_window_delta(eps_series)
    ocf_accel = _two_window_delta(ocf_series)

    breakdown = {
        'revenue_acceleration': {
            'score':       rev_s,
            'weight':      0.40,
            'value':       round(rev_accel, 1) if rev_accel is not None else None,
            'explanation': _explain_accel('Revenue', rev_accel),
        },
        'eps_acceleration': {
            'score':       eps_s,
            'weight':      0.35,
            'value':       round(eps_accel, 1) if eps_accel is not None else None,
            'explanation': _explain_accel('EPS', eps_accel),
        },
        'ocf_acceleration': {
            'score':       ocf_s,
            'weight':      0.25,
            'value':       round(ocf_accel, 1) if ocf_accel is not None else None,
            'explanation': _explain_accel('Operating Cash Flow', ocf_accel),
        },
    }

    return score, breakdown


# ── Plain-English explanations ────────────────────────────────

def _explain_accel(metric: str, accel: float | None) -> str:
    if accel is None:
        return (f"{metric} acceleration data not available. "
                f"Requires 5+ years of data.")
    if accel >= 10:
        return (f"{metric} momentum strongly accelerating ({accel:+.1f}pp). "
                f"Growth rate picking up speed.")
    if accel >= 3:
        return (f"{metric} momentum accelerating ({accel:+.1f}pp). "
                f"Improvement is building.")
    if accel >= -3:
        return (f"{metric} momentum stable ({accel:+.1f}pp). "
                f"Pace of improvement unchanged.")
    if accel >= -10:
        return (f"{metric} momentum decelerating ({accel:+.1f}pp). "
                f"Improvement slowing down.")
    return (f"{metric} momentum sharply decelerating ({accel:+.1f}pp). "
            f"Growth losing steam rapidly.")
