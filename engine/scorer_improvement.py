# ============================================================
# scorer_improvement.py — Layer 2: Improvement Score
# PSE Quant SaaS — Phase 9B (v2 Unified Scorer)
# ============================================================
# Answers: "Are the company's fundamentals improving?"
#
# Uses 3-year smoothed deltas (not raw YoY) to reduce noise from
# one-time items, COVID base effects, and Philippine conglomerate
# segment mix-shifts.
#
# Signals:
#   - Revenue Delta  (30%) — demand growth
#   - EPS Delta      (25%) — profitability improvement
#   - OCF Delta      (25%) — real cash generation improvement
#   - ROE Delta      (20%) — management efficiency trend
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


# ── Delta computation ─────────────────────────────────────────

def _yoy_changes(series: list) -> list[float]:
    """
    Computes year-over-year % changes from a newest-first series.
    Returns changes in newest-first order (most recent change first).
    Skips None values and avoids division by zero.
    """
    clean = [v for v in series if v is not None]
    if len(clean) < 2:
        return []
    changes = []
    # series[0] is newest. changes[0] = (series[0]-series[1])/|series[1]|
    for i in range(len(clean) - 1):
        prior = clean[i + 1]
        curr  = clean[i]
        if prior == 0:
            continue
        changes.append((curr - prior) / abs(prior) * 100)
    return changes


def _smoothed_delta(series: list, years: int = 3) -> float | None:
    """
    Computes the average of the most recent N year-over-year changes.
    Using the average reduces sensitivity to one-time events.
    Returns None if fewer than 2 data points are available.
    """
    changes = _yoy_changes(series)
    if not changes:
        return None
    recent = changes[:years]  # newest changes first
    return sum(recent) / len(recent)


def _roe_delta(roe_current: float | None,
               financials_history: list) -> float | None:
    """
    Computes ROE delta = current ROE - ROE 3 years ago.
    Uses financials_history (list of annual rows, newest first).
    Each row must have 'net_income' and 'equity' fields.
    """
    if roe_current is None:
        return None
    if not financials_history or len(financials_history) < 4:
        return None
    # Try to get ROE from 3 years ago
    row_3y = financials_history[3] if len(financials_history) > 3 else None
    if row_3y is None:
        return None
    ni_3y  = row_3y.get('net_income')
    eq_3y  = row_3y.get('equity')
    if ni_3y is None or eq_3y is None or eq_3y <= 0:
        return None
    roe_3y = (ni_3y / eq_3y) * 100
    return roe_current - roe_3y


# ── Sub-score functions ───────────────────────────────────────

# Revenue delta thresholds (% change smoothed over 3Y)
# Tighter bands — revenue is the hardest metric to manipulate
_REV_THRESHOLDS = [
    (-20, 5), (-10, 15), (-5, 25), (-2, 38),
    (0,  50), (2,  62),  (5, 75),  (10, 88), (20, 100),
]

# REIT-adjusted revenue thresholds.
# REITs grow rental income at 2-6% annually by design — that is excellent
# performance for a property trust, not "flat" growth for an industrial firm.
_REIT_REV_THRESHOLDS = [
    (-10, 5), (-5, 15), (-2, 28), (0,  42),
    (2,  58), (3,  70), (5, 83),  (8, 94), (12, 100),
]

# EPS delta thresholds — wider bands because EPS is noisier
# (one-time items, forex, revaluations common in Philippines)
_EPS_THRESHOLDS = [
    (-30, 5), (-20, 12), (-10, 22), (-5, 35),
    (0,  50), (5,  64),  (10, 78),  (20, 90), (35, 100),
]

# REIT-adjusted EPS thresholds.
# REITs are legally required to distribute 90%+ of income — retained earnings
# that drive EPS growth are structurally limited. A 5% EPS improvement in a
# REIT is equivalent to 15%+ for an industrial company.
_REIT_EPS_THRESHOLDS = [
    (-20, 5), (-10, 15), (-5, 28), (-2, 42),
    (0,  55), (3,  68),  (5, 80),  (10, 92), (18, 100),
]

# OCF delta thresholds — similar to EPS, can swing due to working capital
_OCF_THRESHOLDS = [
    (-30, 5), (-15, 15), (-8, 28), (-3, 42),
    (0,  52), (5,  65),  (10, 78), (20, 90), (30, 100),
]

# ROE delta thresholds (percentage points change, not %)
_ROE_DELTA_THRESHOLDS = [
    (-10, 5), (-5, 18), (-3, 32), (-1, 45),
    (0,  55), (1, 65),  (3, 78),  (5, 88), (10, 100),
]


def _score_revenue_delta(revenue_5y: list | None,
                          thresholds: list | None = None) -> float | None:
    if not revenue_5y or len([v for v in revenue_5y if v is not None]) < 2:
        return None
    delta = _smoothed_delta(revenue_5y, years=3)
    if delta is None:
        return None
    return _normalise(delta, thresholds or _REV_THRESHOLDS)


def _score_eps_delta(eps_5y: list | None,
                     thresholds: list | None = None) -> float | None:
    if not eps_5y or len([v for v in eps_5y if v is not None]) < 2:
        return None
    delta = _smoothed_delta(eps_5y, years=3)
    if delta is None:
        return None
    return _normalise(delta, thresholds or _EPS_THRESHOLDS)


def _score_ocf_delta(ocf_history: list | None) -> float | None:
    if not ocf_history or len([v for v in ocf_history if v is not None]) < 2:
        return None
    delta = _smoothed_delta(ocf_history, years=3)
    if delta is None:
        return None
    return _normalise(delta, _OCF_THRESHOLDS)


def _score_roe_delta(roe: float | None,
                     financials_history: list | None) -> float | None:
    if not financials_history:
        return None
    delta = _roe_delta(roe, financials_history)
    if delta is None:
        return None
    return _normalise(delta, _ROE_DELTA_THRESHOLDS)


# ── Main scorer ───────────────────────────────────────────────

def score_improvement(stock: dict,
                       financials_history: list | None = None
                       ) -> tuple[float, dict]:
    """
    Layer 2 — Improvement Score.
    Evaluates whether fundamentals are improving using 3-year smoothed deltas.
    Returns (score 0-100, breakdown).

    Required stock dict keys:
        revenue_5y, eps_5y, operating_cf_history, roe
    Optional:
        financials_history — list of annual DB rows (newest first)
                              used for ROE delta computation
    """
    is_reit = bool(stock.get('is_reit'))
    rev_thresholds = _REIT_REV_THRESHOLDS if is_reit else _REV_THRESHOLDS
    eps_thresholds = _REIT_EPS_THRESHOLDS if is_reit else _EPS_THRESHOLDS

    rev_s = _score_revenue_delta(stock.get('revenue_5y'), rev_thresholds)
    eps_s = _score_eps_delta(stock.get('eps_5y'), eps_thresholds)
    ocf_s = _score_ocf_delta(stock.get('operating_cf_history'))
    roe_s = _score_roe_delta(stock.get('roe'), financials_history)

    score = _blend([
        (rev_s, 0.30),
        (eps_s, 0.25),
        (ocf_s, 0.25),
        (roe_s, 0.20),
    ])

    # Compute raw delta values for display
    rev_delta = _smoothed_delta(stock.get('revenue_5y') or [], 3)
    eps_delta = _smoothed_delta(stock.get('eps_5y') or [], 3)
    ocf_delta = _smoothed_delta(stock.get('operating_cf_history') or [], 3)
    roe_delta = _roe_delta(stock.get('roe'), financials_history or [])

    breakdown = {
        'revenue_delta': {
            'score':       rev_s,
            'weight':      0.30,
            'value':       round(rev_delta, 1) if rev_delta is not None else None,
            'explanation': _explain_delta('Revenue', rev_delta, 'revenue'),
        },
        'eps_delta': {
            'score':       eps_s,
            'weight':      0.25,
            'value':       round(eps_delta, 1) if eps_delta is not None else None,
            'explanation': _explain_delta('EPS', eps_delta, 'eps'),
        },
        'ocf_delta': {
            'score':       ocf_s,
            'weight':      0.25,
            'value':       round(ocf_delta, 1) if ocf_delta is not None else None,
            'explanation': _explain_delta('Operating Cash Flow', ocf_delta, 'ocf'),
        },
        'roe_delta': {
            'score':       roe_s,
            'weight':      0.20,
            'value':       round(roe_delta, 2) if roe_delta is not None else None,
            'explanation': _explain_roe_delta(roe_delta),
        },
    }

    return score, breakdown


# ── Plain-English explanations ────────────────────────────────

def _explain_delta(metric_name: str, delta: float | None,
                   metric_type: str) -> str:
    if delta is None:
        return f"{metric_name} improvement data not available (insufficient history)."
    unit = 'pp' if metric_type == 'roe' else '%'
    if delta >= 10:
        return (f"{metric_name} growing at {delta:+.1f}%{unit} avg (3-year) — "
                f"strong improvement trend.")
    if delta >= 3:
        return (f"{metric_name} growing at {delta:+.1f}%{unit} avg (3-year) — "
                f"moderate improvement.")
    if delta >= -3:
        return (f"{metric_name} roughly flat at {delta:+.1f}%{unit} avg (3-year) — "
                f"no clear improvement direction.")
    if delta >= -10:
        return (f"{metric_name} declining at {delta:+.1f}%{unit} avg (3-year) — "
                f"deteriorating trend.")
    return (f"{metric_name} falling sharply at {delta:+.1f}%{unit} avg (3-year) — "
            f"significant fundamental deterioration.")


def _explain_roe_delta(delta: float | None) -> str:
    if delta is None:
        return "ROE trend not available (need 4+ years of data)."
    if delta >= 5:
        return f"ROE improved by {delta:+.1f}pp over 3 years — management becoming more efficient."
    if delta >= 1:
        return f"ROE improved by {delta:+.1f}pp over 3 years — modest efficiency gains."
    if delta >= -1:
        return f"ROE roughly stable ({delta:+.1f}pp) — management efficiency unchanged."
    if delta >= -5:
        return f"ROE declined by {delta:+.1f}pp over 3 years — efficiency slipping."
    return f"ROE fell sharply by {delta:+.1f}pp over 3 years — significant decline in capital efficiency."
