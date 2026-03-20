# ============================================================
# scorer_persistence.py — Layer 4: Persistence Score
# PSE Quant SaaS — Phase 9B (v2 Unified Scorer)
# ============================================================
# Answers: "Is the improvement consistent and sustainable?"
#
# Persistence is the most valuable signal for the Philippine market
# because most PSE stocks are erratic. Consistent multi-year
# improvement separates genuine quality from one-time spikes.
#
# Signals:
#   - Revenue Persistence     (35%) — consecutive positive YoY changes
#   - EPS Persistence         (30%) — consecutive positive YoY changes
#   - OCF Persistence         (20%) — consecutive positive YoY changes
#   - Direction Consistency   (15%) — all 3 metrics improve same year
#
# Scoring logic:
#   Score = (positive years / total years) → normalised 0-100
#   Consecutive positive runs weighted more than scattered positives.
#
# Returns: (score: float 0-100, breakdown: dict)
# ============================================================

from __future__ import annotations


def _blend(scores_weights: list) -> float:
    valid = [(s, w) for s, w in scores_weights if s is not None]
    if not valid:
        return 0.0
    total_w = sum(w for _, w in valid)
    return round(sum(s * (w / total_w) for s, w in valid), 1)


# ── Persistence helpers ───────────────────────────────────────

def _yoy_directions(series: list) -> list[int]:
    """
    Returns list of +1 (improvement) or -1 (decline) for each YoY change.
    Newest-first series → newest direction first.
    """
    clean = [v for v in series if v is not None]
    if len(clean) < 2:
        return []
    directions = []
    for i in range(len(clean) - 1):
        directions.append(1 if clean[i] > clean[i + 1] else -1)
    return directions


def _persistence_ratio(series: list, years: int = 5) -> tuple[float, int, int]:
    """
    Returns (ratio, positive_count, total_count).
    ratio = positive_changes / total_changes over last N years.
    Uses up to `years` most recent YoY comparisons.
    """
    directions = _yoy_directions(series)[:years]
    if not directions:
        return 0.0, 0, 0
    total    = len(directions)
    positive = sum(1 for d in directions if d > 0)
    return positive / total, positive, total


def _consecutive_streak(series: list) -> int:
    """
    Returns the length of the most recent consecutive positive streak.
    A streak of 4+ is rare and exceptional for PSE stocks.
    """
    directions = _yoy_directions(series)
    streak = 0
    for d in directions:
        if d > 0:
            streak += 1
        else:
            break
    return streak


def _score_single_persistence(series: list | None,
                               min_years: int = 2) -> float | None:
    """
    Scores persistence for a single metric series (0-100).
    Blended formula: direction (60pts) + magnitude (20pts) + streak (20pts).

    Magnitude scoring (avg positive YoY change):
        >= 15%  ->  20 pts
        10-15%  ->  15 pts
         5-10%  ->  10 pts
          1-5%  ->   5 pts
          < 1%  ->   2 pts
    """
    if not series:
        return None
    clean = [v for v in series if v is not None]
    if len(clean) < min_years + 1:
        return None

    ratio, pos, total = _persistence_ratio(series, years=5)
    streak = _consecutive_streak(series)

    # -- Direction score: 0-60 points --
    direction = ratio * 60

    # -- Magnitude score: 0-20 points --
    changes = []
    for i in range(len(clean) - 1):
        prior = clean[i + 1]
        curr  = clean[i]
        if prior != 0:
            pct = (curr - prior) / abs(prior) * 100
            if pct > 0:
                changes.append(pct)
    if changes:
        avg_positive = sum(changes) / len(changes)
        if avg_positive >= 15:
            magnitude = 20
        elif avg_positive >= 10:
            magnitude = 15
        elif avg_positive >= 5:
            magnitude = 10
        elif avg_positive >= 1:
            magnitude = 5
        else:
            magnitude = 2
    else:
        magnitude = 0

    # -- Streak bonus: 0-20 points --
    bonus = min(streak * 5, 20)

    raw_score = direction + magnitude + bonus

    # Penalty: if streak is 0 (most recent year declined), cap at 65
    if streak == 0 and raw_score > 65:
        raw_score = 65

    return round(min(raw_score, 100), 1)


def _direction_consistency(rev_series: list | None,
                            eps_series: list | None,
                            ocf_series: list | None,
                            years: int = 4) -> float | None:
    """
    Measures how often ALL three metrics improve in the same year.
    Returns score 0-100, or None if any series is missing.
    """
    if not rev_series or not eps_series or not ocf_series:
        return None

    rev_dirs = _yoy_directions(rev_series)[:years]
    eps_dirs = _yoy_directions(eps_series)[:years]
    ocf_dirs = _yoy_directions(ocf_series)[:years]

    n = min(len(rev_dirs), len(eps_dirs), len(ocf_dirs))
    if n < 2:
        return None

    all_positive = sum(
        1 for i in range(n)
        if rev_dirs[i] > 0 and eps_dirs[i] > 0 and ocf_dirs[i] > 0
    )
    ratio = all_positive / n
    return round(ratio * 100, 1)


# ── Main scorer ───────────────────────────────────────────────

def score_persistence(stock: dict) -> tuple[float, dict]:
    """
    Layer 4 — Persistence Score.
    Evaluates whether improvement is consistent and reliable.
    Returns (score 0-100, breakdown).

    Required stock dict keys:
        revenue_5y, eps_5y, operating_cf_history
    """
    rev_series = stock.get('revenue_5y') or []
    eps_series = stock.get('eps_5y') or []
    ocf_series = stock.get('operating_cf_history') or []

    rev_s = _score_single_persistence(rev_series)
    eps_s = _score_single_persistence(eps_series)
    ocf_s = _score_single_persistence(ocf_series)
    dir_s = _direction_consistency(rev_series, eps_series, ocf_series)

    score = _blend([
        (rev_s, 0.35),
        (eps_s, 0.30),
        (ocf_s, 0.20),
        (dir_s, 0.15),
    ])

    # Compute summary metrics for display
    rev_ratio, rev_pos, rev_total = _persistence_ratio(rev_series)
    eps_ratio, eps_pos, eps_total = _persistence_ratio(eps_series)
    ocf_ratio, ocf_pos, ocf_total = _persistence_ratio(ocf_series)
    rev_streak = _consecutive_streak(rev_series)
    eps_streak = _consecutive_streak(eps_series)

    breakdown = {
        'revenue_persistence': {
            'score':       rev_s,
            'weight':      0.35,
            'value':       f"{rev_pos}/{rev_total}" if rev_total > 0 else None,
            'explanation': _explain_persistence(
                'Revenue', rev_pos, rev_total, rev_streak),
        },
        'eps_persistence': {
            'score':       eps_s,
            'weight':      0.30,
            'value':       f"{eps_pos}/{eps_total}" if eps_total > 0 else None,
            'explanation': _explain_persistence(
                'EPS', eps_pos, eps_total, eps_streak),
        },
        'ocf_persistence': {
            'score':       ocf_s,
            'weight':      0.20,
            'value':       f"{ocf_pos}/{ocf_total}" if ocf_total > 0 else None,
            'explanation': _explain_persistence(
                'Operating Cash Flow',
                *(_persistence_ratio(ocf_series)[:2]),
                _consecutive_streak(ocf_series)),
        },
        'direction_consistency': {
            'score':       dir_s,
            'weight':      0.15,
            'value':       round(dir_s, 1) if dir_s is not None else None,
            'explanation': _explain_direction_consistency(dir_s),
        },
    }

    return score, breakdown


# ── Plain-English explanations ────────────────────────────────

def _explain_persistence(metric: str, positive: int, total: int,
                          streak: int) -> str:
    if total == 0:
        return f"{metric} persistence data not available."
    pct = positive / total * 100
    streak_note = (f" Current streak: {streak} consecutive positive year(s)."
                   if streak > 0 else " Most recent year showed a decline.")
    if pct >= 80:
        return (f"{metric} improved in {positive}/{total} of the last {total} years "
                f"({pct:.0f}% consistency) — highly reliable growth.{streak_note}")
    if pct >= 60:
        return (f"{metric} improved in {positive}/{total} years "
                f"({pct:.0f}%) — generally improving with occasional dips.{streak_note}")
    if pct >= 40:
        return (f"{metric} improved in {positive}/{total} years "
                f"({pct:.0f}%) — mixed results, limited consistency.{streak_note}")
    return (f"{metric} improved in only {positive}/{total} years "
            f"({pct:.0f}%) — erratic or declining trend.{streak_note}")


def _explain_direction_consistency(score: float | None) -> str:
    if score is None:
        return ("Direction consistency requires revenue, EPS, and OCF data. "
                "One or more series unavailable.")
    if score >= 75:
        return (f"All three key metrics (revenue, EPS, cash flow) improved "
                f"together in {score:.0f}% of measured years — highly coordinated growth.")
    if score >= 50:
        return (f"All three key metrics improved together in {score:.0f}% of years. "
                f"Growth is broad-based but not always synchronized.")
    if score >= 25:
        return (f"All three key metrics improved together in only {score:.0f}% of years. "
                f"Growth is inconsistent or driven by only one or two metrics.")
    return (f"All three metrics rarely improve in the same year ({score:.0f}%). "
            f"Suggests uneven or volatile business fundamentals.")
