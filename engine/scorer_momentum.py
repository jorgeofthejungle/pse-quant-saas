# ============================================================
# scorer_momentum.py -- Fundamental Momentum Sub-Scores
# PSE Quant SaaS
# ============================================================
# Measures whether a company's key financial metrics are
# IMPROVING (accelerating) or DETERIORATING (decelerating)
# over time.  This is the "second derivative" of performance:
#   - Level factors  = What is the growth rate?
#   - Stability      = How predictable is it?
#   - Momentum       = Is growth speeding up or slowing down?
#
# Three signals are used (in order of reliability for PSE):
#   1. Revenue Momentum  -- hardest to manipulate, best for conglomerates
#   2. EPS Momentum      -- important but noisier (one-time items common in PH)
#   3. Operating CF Mom. -- detects earnings quality shifts
#
# ROE momentum is excluded (leverage/revaluation distorts it in PH).
# Dividend momentum is excluded (already captured by CAGR + stability).
#
# Algorithm: Split-Window CAGR Delta
#   Given N values (newest first), split into recent half and prior half.
#   Compute CAGR for each half. Momentum = recent CAGR - prior CAGR.
#   Positive = accelerating. Negative = decelerating. 0 = stable.
#   Minimum 4 data points required. Fewer --> returns None.
# ============================================================

try:
    from config import MOMENTUM_MIN_YEARS as _MIN_PTS
except ImportError:
    _MIN_PTS = 4

try:
    from engine.scorer_utils import normalise, _blend
except ImportError:
    from scorer_utils import normalise, _blend


# ── Internal helpers ─────────────────────────────────────────

def _cagr(oldest: float, newest: float, years: int) -> float | None:
    """Annualised growth rate between two values over N years."""
    if oldest is None or newest is None or years <= 0:
        return None
    if oldest <= 0 or newest <= 0:
        return None
    return round(((newest / oldest) ** (1.0 / years) - 1) * 100, 2)


def _momentum_delta(series: list, min_points: int = _MIN_PTS) -> float | None:
    """
    Split-Window CAGR Delta.

    Splits the historical series in half (newest first), computes CAGR
    for each half, and returns (recent CAGR - prior CAGR) in percentage
    points.  Positive = growth accelerating.  Negative = decelerating.

    Requires at least min_points valid (non-None, positive) values.
    Returns None if data is insufficient.
    """
    valid = [v for v in series if v is not None and v > 0]
    if len(valid) < min_points:
        return None

    mid   = len(valid) // 2
    recent = valid[:mid]        # newest half
    prior  = valid[mid:]        # older half

    if len(recent) < 2 or len(prior) < 2:
        return None

    # CAGR within each window: oldest value at end (series is newest-first)
    recent_cagr = _cagr(recent[-1], recent[0], len(recent) - 1)
    prior_cagr  = _cagr(prior[-1],  prior[0],  len(prior)  - 1)

    if recent_cagr is None or prior_cagr is None:
        return None

    return round(recent_cagr - prior_cagr, 2)


def _ocf_momentum(series: list, min_points: int = _MIN_PTS) -> float | None:
    """
    Operating Cash Flow Momentum.

    OCF can be negative (e.g. capex-heavy expansion years), so CAGR is
    invalid.  Instead, compares the MEAN of the recent half vs the mean
    of the prior half, expressed as a percentage change.

    Returns None if data is insufficient or prior mean is zero.
    """
    valid = [v for v in series if v is not None]
    if len(valid) < min_points:
        return None

    mid    = len(valid) // 2
    recent = valid[:mid]
    prior  = valid[mid:]

    if not recent or not prior:
        return None

    mean_recent = sum(recent) / len(recent)
    mean_prior  = sum(prior)  / len(prior)

    if mean_prior == 0:
        return None

    return round((mean_recent - mean_prior) / abs(mean_prior) * 100, 2)


# ── Normalisation thresholds ─────────────────────────────────

# Revenue: tighter bands (revenue is smoother / harder to manipulate)
_REV_THRESHOLDS = [
    (-10, 5), (-5, 20), (-2, 35), (0, 50),
    (2, 65),  (5, 80),  (10, 95),
]

# EPS: wider bands (noisier due to one-time items common in PH)
_EPS_THRESHOLDS = [
    (-15, 5), (-8, 20), (-3, 35), (0, 50),
    (3, 65),  (8, 80),  (15, 95),
]

# OCF: percentage-change scale (wider range needed)
_OCF_THRESHOLDS = [
    (-20, 10), (-10, 25), (-5, 40), (0, 50),
    (5, 60),   (10, 75),  (20, 90),
]


# ── Public API ───────────────────────────────────────────────

def compute_momentum_composite(metrics: dict) -> tuple:
    """
    Computes the Fundamental Momentum composite score (0-100).

    Combines three signals via _blend() (missing signals redistribute weight):
      - Revenue Momentum  40%
      - EPS Momentum      35%
      - OCF Momentum      25%

    Returns: (composite_score: float, detail: dict)
    detail keys: rev_delta, eps_delta, ocf_delta, rev_score, eps_score, ocf_score
    """
    # Revenue momentum (uses revenue_5y which can hold up to 10Y from DB)
    revenue_series = metrics.get('revenue_5y', [])
    rev_delta      = _momentum_delta(revenue_series)
    rev_score      = normalise(rev_delta, _REV_THRESHOLDS) if rev_delta is not None else None

    # EPS momentum (eps_5y can hold up to 10Y from DB)
    eps_series = metrics.get('eps_5y', [])
    eps_delta  = _momentum_delta(eps_series)
    eps_score  = normalise(eps_delta, _EPS_THRESHOLDS) if eps_delta is not None else None

    # Operating CF momentum (new field added to stock dict)
    ocf_series = metrics.get('operating_cf_history', [])
    ocf_delta  = _ocf_momentum(ocf_series)
    ocf_score  = normalise(ocf_delta, _OCF_THRESHOLDS) if ocf_delta is not None else None

    composite = _blend([
        (rev_score, 0.40),
        (eps_score, 0.35),
        (ocf_score, 0.25),
    ])

    detail = {
        'rev_delta': rev_delta,
        'eps_delta': eps_delta,
        'ocf_delta': ocf_delta,
        'rev_score': rev_score,
        'eps_score': eps_score,
        'ocf_score': ocf_score,
    }
    return round(composite, 1), detail


def explain_momentum(rev_delta, eps_delta, ocf_delta) -> str:
    """
    Plain-English explanation of the momentum signal for PDF reports.
    Follows the educational communication standard from CLAUDE.md section 7A:
    neutral, beginner-friendly, explains both strengths and risks.
    """
    lines = [
        "Fundamental Momentum measures whether growth is SPEEDING UP or SLOWING DOWN. "
        "It compares recent years to earlier years in the same company's history."
    ]

    if rev_delta is None and eps_delta is None and ocf_delta is None:
        lines.append(
            "Insufficient historical data to compute momentum. "
            "At least 4 years of financials are required."
        )
        return '  '.join(lines)

    # Revenue
    if rev_delta is not None:
        if rev_delta > 2:
            lines.append(
                f"Revenue growth is ACCELERATING (+{rev_delta:.1f}pp faster than earlier periods). "
                "This suggests improving demand or successful business expansion."
            )
        elif rev_delta < -2:
            lines.append(
                f"Revenue growth is SLOWING DOWN ({rev_delta:.1f}pp slower than earlier periods). "
                "While the company may still be growing, the pace is declining."
            )
        else:
            lines.append(
                f"Revenue growth is STABLE (delta {rev_delta:+.1f}pp). "
                "The company is maintaining a consistent pace of expansion."
            )

    # EPS
    if eps_delta is not None:
        if eps_delta > 3:
            lines.append(
                f"Earnings growth is ACCELERATING (+{eps_delta:.1f}pp). "
                "Improving profitability reinforces the positive revenue trend."
            )
        elif eps_delta < -3:
            lines.append(
                f"Earnings growth is SLOWING ({eps_delta:.1f}pp). "
                "Even if revenue is growing, profits may be under pressure from costs or one-time items."
            )
        else:
            lines.append(
                f"Earnings momentum is NEUTRAL ({eps_delta:+.1f}pp). "
                "Profitability trends are broadly stable."
            )

    # Mixed signal warning
    if (rev_delta is not None and eps_delta is not None
            and rev_delta > 2 and eps_delta < -3):
        lines.append(
            "NOTE: Revenue is accelerating but earnings are not keeping pace. "
            "This may indicate rising costs or margin compression."
        )

    # OCF
    if ocf_delta is not None:
        if ocf_delta > 5:
            lines.append(
                f"Operating cash flow is improving (+{ocf_delta:.1f}% vs prior period). "
                "Strong cash generation backs up the earnings trend."
            )
        elif ocf_delta < -5:
            lines.append(
                f"Operating cash flow has weakened ({ocf_delta:.1f}% vs prior period). "
                "This may warrant closer attention to earnings quality."
            )

    return '  '.join(lines)
