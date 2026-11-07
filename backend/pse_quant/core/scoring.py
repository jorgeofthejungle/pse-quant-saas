"""
pse_quant/core/scoring.py — Unified 3-Layer Fundamental Scoring Engine
Deterministic, sector-aware fundamental scoring:
  - Layer 1: Health (ROE, Net Margin, D/E, EPS stability, P/B, Dividend Yield, FCF Yield)
  - Layer 2: Improvement (Smoothed YoY deltas: Revenue, EPS, ROE, DPS, and momentum bonus)
  - Layer 3: Persistence (Growth consistency, direction alignment, and streak bonuses)
"""

from __future__ import annotations
import statistics as stats
from typing import Any

from pse_quant.config import (
    SCORER_WEIGHTS,
    MIN_SCORE_THRESHOLD,
    MIN_SUBSCORES_PER_LAYER,
    IMPROVEMENT_RECENCY_WEIGHTS,
    CONFIDENCE_TIERS,
)
from pse_quant.core.sector_groups import get_scoring_group, get_layer_config

# ── Health Layer Threshold Tables ─────────────────────────────
_ROE_STD = [
    (0.0, 10), (5.0, 25), (8.0, 40), (12.0, 60),
    (15.0, 75), (20.0, 88), (25.0, 96), (35.0, 100),
]
_ROE_BANK = [
    (5.0, 10), (8.0, 25), (10.0, 40), (13.0, 60),
    (16.0, 75), (20.0, 88), (25.0, 96), (30.0, 100),
]

_NI_MARGIN_STD = [
    (-20.0, 5), (-5.0, 15), (0.0, 30), (3.0, 45),
    (6.0, 60), (10.0, 72), (15.0, 83), (20.0, 92), (30.0, 100),
]
_NI_MARGIN_BANK = [
    (-10.0, 5), (-3.0, 15), (0.0, 30), (5.0, 50),
    (10.0, 65), (15.0, 80), (20.0, 92), (25.0, 100),
]

_DE_STD = [
    (0.3, 100), (0.5, 92), (0.8, 80), (1.0, 70),
    (1.5, 55), (2.0, 38), (2.5, 20), (3.5, 8),
]
_DE_REIT = [
    (0.5, 100), (1.0, 85), (1.5, 70),
    (2.0, 55), (3.0, 35), (4.0, 15),
]

_EPS_CV = [
    (0.05, 100), (0.10, 90), (0.20, 75), (0.35, 58),
    (0.50, 42), (0.70, 25), (1.00, 12),
]

_PB = [
    (0.5, 100), (0.8, 90), (1.0, 80), (1.3, 70),
    (1.5, 58), (2.0, 42), (2.5, 25), (3.0, 12),
]

_DIV_YIELD = [
    (2.0, 5), (3.0, 20), (4.0, 40), (5.0, 60),
    (6.0, 75), (7.0, 87), (8.0, 95), (10.0, 100),
]

_FCF_YIELD = [
    (-10.0, 5), (-5.0, 15), (0.0, 30), (2.0, 45),
    (4.0, 60), (6.0, 75), (8.0, 87), (12.0, 96), (20.0, 100),
]

# ── Improvement Layer Threshold Tables ─────────────────────────
_REV_THRESHOLDS = [
    (-20.0, 5), (-10.0, 15), (-5.0, 25), (-2.0, 38),
    (0.0, 50), (2.0, 62), (5.0, 75), (10.0, 88), (999.0, 100),
]
_EPS_THRESHOLDS = [
    (-30.0, 5), (-20.0, 12), (-10.0, 22), (-5.0, 35),
    (0.0, 50), (5.0, 64), (10.0, 78), (20.0, 90), (999.0, 100),
]
_ROE_DELTA_THRESHOLDS = [
    (-10.0, 5), (-5.0, 18), (-3.0, 32), (-1.0, 45),
    (0.0, 55), (1.0, 65), (3.0, 78), (5.0, 88), (999.0, 100),
]
_DPS_THRESHOLDS = [
    (-20.0, 5), (-10.0, 15), (-5.0, 28), (-2.0, 42),
    (0.0, 55), (2.0, 68), (5.0, 80), (10.0, 92), (999.0, 100),
]

# ── Scoring Categories ────────────────────────────────────────
CATEGORIES = [
    (75.0, "Highest Quality", "Healthy, improving, and consistently growing."),
    (55.0, "Strong Growth",   "Fundamentally healthy with improving trends."),
    (35.0, "Watchlist",       "Healthy today but growth momentum is limited."),
    (0.0,  "Weak",            "Multiple red flags in health or trend metrics."),
]


def _normalise(value: float | None, table: list[tuple[float, int]]) -> float | None:
    if value is None:
        return None
    for max_val, score in table:
        if value <= max_val:
            return float(score)
    return float(table[-1][1])


def _blend_checked(scores_weights: list[tuple[float | None, float]], min_subscores: int = 2) -> float | None:
    valid = [(s, w) for s, w in scores_weights if s is not None]
    if len(valid) < min_subscores:
        return None
    total_w = sum(w for _, w in valid)
    if total_w <= 0:
        return None
    return sum(s * (w / total_w) for s, w in valid)


def _yoy_changes(series: list[float | None]) -> list[float]:
    valid = [v for v in series if v is not None]
    changes = []
    for i in range(len(valid) - 1):
        curr, prev = valid[i], valid[i + 1]
        if prev and prev != 0:
            raw_change = ((curr - prev) / abs(prev)) * 100.0
            # Clamp percentage changes to [-100%, +300%] to prevent micro-base growth explosions
            clamped = max(-100.0, min(raw_change, 300.0))
            changes.append(clamped)
    return changes


# ── Sub-score Calculators (Layer 1: Health) ────────────────────

def _score_roe(stock: dict[str, Any], group: str) -> float | None:
    roe = stock.get("roe")
    if roe is None:
        ni = stock.get("net_income")
        eq = stock.get("equity")
        if (ni is not None and ni < 0) or (eq is not None and eq <= 0):
            return 5.0
    table = _ROE_BANK if group == "bank" else _ROE_STD
    return _normalise(roe, table)


def _score_ni_margin(stock: dict[str, Any], group: str) -> float | None:
    ni_list = stock.get("net_income_3y") or []
    rev_list = stock.get("revenue_5y") or []
    ni = next((v for v in ni_list if v is not None), None)
    rev = next((v for v in rev_list if v is not None), None)
    if ni is not None and rev is not None and rev != 0:
        margin = (ni / rev) * 100.0
    elif stock.get("net_margin") is not None:
        margin = float(stock["net_margin"])
    else:
        return None
    table = _NI_MARGIN_BANK if group == "bank" else _NI_MARGIN_STD
    return _normalise(margin, table)


def _score_de_ratio(stock: dict[str, Any], group: str) -> float | None:
    if group == "bank":
        return None  # Leverage is the business model for banks
    de = stock.get("de_ratio")
    if de is None:
        eq = stock.get("equity")
        if eq is not None and eq <= 0:
            return 5.0
    table = _DE_REIT if group == "reit" else _DE_STD
    return _normalise(de, table)


def _score_eps_stability(stock: dict[str, Any], _group: str) -> float | None:
    eps_hist = stock.get("eps_5y") or stock.get("eps_3y") or []
    valid = [float(e) for e in eps_hist if e is not None]
    if len(valid) < 3:
        return None
    mean_eps = sum(valid) / len(valid)
    if mean_eps <= 0:
        shrinking = all(valid[i] > valid[i + 1] for i in range(len(valid) - 1))
        return 15.0 if shrinking else 5.0
    cv = stats.pstdev(valid) / mean_eps
    return _normalise(cv, _EPS_CV)


def _score_pb(stock: dict[str, Any], _group: str) -> float | None:
    return _normalise(stock.get("pb"), _PB)


def _score_dividend_yield(stock: dict[str, Any], _group: str) -> float | None:
    return _normalise(stock.get("dividend_yield"), _DIV_YIELD)


def _score_fcf_yield(stock: dict[str, Any], _group: str) -> float | None:
    return _normalise(stock.get("fcf_yield"), _FCF_YIELD)


_HEALTH_SUBSCORERS = {
    "roe": _score_roe,
    "ni_margin": _score_ni_margin,
    "de_ratio": _score_de_ratio,
    "eps_stability": _score_eps_stability,
    "pb": _score_pb,
    "dividend_yield": _score_dividend_yield,
    "fcf_yield": _score_fcf_yield,
}


def score_health(stock: dict[str, Any], scoring_group: str) -> tuple[float | None, dict[str, Any]]:
    layer_cfg = get_layer_config(scoring_group, "health")
    if not layer_cfg:
        return None, {"error": f"No health config for group={scoring_group}"}

    scores_weights: list[tuple[float | None, float]] = []
    factors: dict[str, float | None] = {}

    for sub_name, weight in layer_cfg.items():
        fn = _HEALTH_SUBSCORERS.get(sub_name)
        s = fn(stock, scoring_group) if fn else None
        scores_weights.append((s, weight))
        factors[sub_name] = round(s, 1) if s is not None else None

    score = _blend_checked(scores_weights, min_subscores=MIN_SUBSCORES_PER_LAYER)
    return score, {
        "score": round(score, 1) if score is not None else None,
        "group": scoring_group,
        "factors": factors,
    }


# ── Sub-score Calculators (Layer 2: Improvement) ──────────────

def _smoothed_delta(series: list[float | None]) -> float | None:
    changes = _yoy_changes(series)
    if not changes:
        return None
    weights = IMPROVEMENT_RECENCY_WEIGHTS
    recent = changes[:len(weights)]
    if not recent:
        return None
    w_slice = weights[:len(recent)]
    total_w = sum(w_slice)
    return sum(c * w for c, w in zip(recent, w_slice)) / total_w


def _momentum_bonus(series: list[float | None]) -> float:
    changes = _yoy_changes(series)
    if len(changes) < 4:
        return 0.0
    recent_avg = sum(changes[:2]) / 2.0
    prior_avg = sum(changes[2:4]) / 2.0
    if recent_avg > prior_avg + 1.0:
        return 8.0
    if recent_avg < prior_avg - 1.0:
        return -8.0
    return 0.0


def _score_roe_delta(stock: dict[str, Any], financials_history: list[dict[str, Any]]) -> float | None:
    roe_now = stock.get("roe")
    if roe_now is None or not financials_history:
        return None
    valid_rows = [r for r in financials_history if r.get("equity") and r.get("net_income") is not None]
    if len(valid_rows) < 4:
        return None
    row_3y = valid_rows[3]
    eq = row_3y.get("equity")
    ni = row_3y.get("net_income")
    if not eq or eq == 0:
        return None
    roe_3y_ago = (ni / eq) * 100.0
    delta = roe_now - roe_3y_ago
    return _normalise(delta, _ROE_DELTA_THRESHOLDS)


def score_improvement(
    stock: dict[str, Any],
    financials_history: list[dict[str, Any]],
    scoring_group: str,
) -> tuple[float | None, dict[str, Any]]:
    layer_cfg = get_layer_config(scoring_group, "improvement")
    if not layer_cfg:
        return None, {"error": f"No improvement config for group={scoring_group}"}

    scores_weights: list[tuple[float | None, float]] = []
    factors: dict[str, float | None] = {}

    for sub_name, weight in layer_cfg.items():
        if sub_name == "revenue_delta":
            delta = _smoothed_delta(stock.get("revenue_5y") or [])
            s = _normalise(delta, _REV_THRESHOLDS)
        elif sub_name == "eps_delta":
            delta = _smoothed_delta(stock.get("eps_5y") or stock.get("eps_3y") or [])
            s = _normalise(delta, _EPS_THRESHOLDS)
        elif sub_name == "roe_delta":
            s = _score_roe_delta(stock, financials_history)
        elif sub_name == "dps_delta":
            paying = [d for d in (stock.get("dividends_5y") or []) if d and d > 0]
            delta = _smoothed_delta(paying) if len(paying) >= 2 else None
            s = _normalise(delta, _DPS_THRESHOLDS)
        else:
            s = None

        scores_weights.append((s, weight))
        factors[sub_name] = round(s, 1) if s is not None else None

    # Momentum bonus for tickers with 5+ years of data
    bonus = 0.0
    eps_series = [v for v in (stock.get("eps_5y") or []) if v is not None]
    rev_series = [v for v in (stock.get("revenue_5y") or []) if v is not None]
    if len(eps_series) >= 5:
        bonus = _momentum_bonus(eps_series)
    elif len(rev_series) >= 5:
        bonus = _momentum_bonus(rev_series)

    score = _blend_checked(scores_weights, min_subscores=MIN_SUBSCORES_PER_LAYER)
    if score is not None and bonus != 0.0:
        score = max(0.0, min(100.0, score + bonus))

    factors["_momentum_bonus"] = bonus if bonus != 0.0 else None

    return score, {
        "score": round(score, 1) if score is not None else None,
        "group": scoring_group,
        "factors": factors,
    }


# ── Sub-score Calculators (Layer 3: Persistence) ──────────────

def _single_persistence(series: list[float | None]) -> float | None:
    changes = _yoy_changes(series)
    if not changes:
        return None

    pos = [c for c in changes if c > 0]
    direction = (len(pos) / len(changes)) * 60.0

    if pos:
        avg_pos = sum(pos) / len(pos)
        if avg_pos >= 15.0:   magnitude = 20.0
        elif avg_pos >= 10.0: magnitude = 15.0
        elif avg_pos >= 5.0:  magnitude = 10.0
        elif avg_pos >= 1.0:  magnitude = 5.0
        else:                 magnitude = 2.0
    else:
        magnitude = 0.0

    streak = 0
    for c in changes:
        if c > 0:
            streak += 1
        else:
            break
    bonus = min(streak * 5.0, 20.0)

    raw = direction + magnitude + bonus
    if streak == 0 and raw > 65.0:
        raw = 65.0
    return min(float(raw), 100.0)


def _score_direction(stock: dict[str, Any]) -> float | None:
    rev_valid = [v for v in (stock.get("revenue_5y") or []) if v is not None]
    eps_valid = [v for v in (stock.get("eps_5y") or stock.get("eps_3y") or []) if v is not None]
    years = min(len(rev_valid), len(eps_valid))
    if years < 3:
        return None

    credit = 0.0
    total = 0
    for i in range(min(years - 1, 4)):
        rev_up = (rev_valid[i] - rev_valid[i + 1]) > 0
        eps_up = (eps_valid[i] - eps_valid[i + 1]) > 0
        total += 1
        if rev_up and eps_up:
            credit += 1.0
        elif rev_up or eps_up:
            credit += 0.5

    if total == 0:
        return None
    return (credit / total) * 100.0


def score_persistence(stock: dict[str, Any], scoring_group: str) -> tuple[float | None, dict[str, Any]]:
    layer_cfg = get_layer_config(scoring_group, "persistence")
    if not layer_cfg:
        return None, {"error": f"No persistence config for group={scoring_group}"}

    scores_weights: list[tuple[float | None, float]] = []
    factors: dict[str, float | None] = {}

    for sub_name, weight in layer_cfg.items():
        if sub_name == "revenue":
            s = _single_persistence(stock.get("revenue_5y") or [])
        elif sub_name == "eps":
            s = _single_persistence(stock.get("eps_5y") or stock.get("eps_3y") or [])
        elif sub_name == "dps":
            paying = [d for d in (stock.get("dividends_5y") or []) if d and d > 0]
            s = _single_persistence(paying) if len(paying) >= 2 else None
        elif sub_name == "direction":
            s = _score_direction(stock)
        else:
            s = None

        scores_weights.append((s, weight))
        factors[sub_name] = round(s, 1) if s is not None else None

    score = _blend_checked(scores_weights, min_subscores=MIN_SUBSCORES_PER_LAYER)
    return score, {
        "score": round(score, 1) if score is not None else None,
        "group": scoring_group,
        "factors": factors,
    }


# ── Data Confidence Multiplier ─────────────────────────────────

def calc_data_confidence(stock: dict[str, Any]) -> float:
    eps_vals = [v for v in (stock.get("eps_5y") or []) if v is not None]
    rev_vals = [v for v in (stock.get("revenue_5y") or []) if v is not None]
    complete_years = min(len(eps_vals), len(rev_vals))

    for threshold in sorted(CONFIDENCE_TIERS.keys(), reverse=True):
        if complete_years >= threshold:
            return CONFIDENCE_TIERS[threshold]
    return 0.0


def get_category(score: float) -> tuple[str, str]:
    for threshold, label, desc in CATEGORIES:
        if score >= threshold:
            return label, desc
    return "Weak", "Multiple red flags in health or trend metrics."


# ── Master Scorer & Ranker ────────────────────────────────────

def score_unified(
    stock: dict[str, Any],
    financials_history: list[dict[str, Any]] | None = None,
    portfolio_type: str = "unified",
) -> tuple[float, dict[str, Any]]:
    """
    Computes deterministic 3-layer score (0-100) for a single stock.
    Returns (final_score, breakdown_dict).
    """
    scoring_group = get_scoring_group(stock)
    weights = SCORER_WEIGHTS.get(portfolio_type, SCORER_WEIGHTS["unified"])

    h_score, h_breakdown = score_health(stock, scoring_group)
    i_score, i_breakdown = score_improvement(stock, financials_history or [], scoring_group)
    p_score, p_breakdown = score_persistence(stock, scoring_group)

    # Weighted blend across valid layers
    layers = [
        (h_score, weights["health"]),
        (i_score, weights["improvement"]),
        (p_score, weights["persistence"]),
    ]
    valid_layers = [(s, w) for s, w in layers if s is not None]
    if valid_layers:
        total_w = sum(w for _, w in valid_layers)
        raw_score = sum(s * (w / total_w) for s, w in valid_layers)
    else:
        raw_score = 0.0

    confidence = calc_data_confidence(stock)
    final_score = round(raw_score * confidence, 1)

    category, desc = get_category(final_score)

    breakdown = {
        "final_score": final_score,
        "raw_score": round(raw_score, 1),
        "confidence": confidence,
        "category": category,
        "category_description": desc,
        "portfolio_type": portfolio_type,
        "scoring_group": scoring_group,
        "layers": {
            "health": h_breakdown,
            "improvement": i_breakdown,
            "persistence": p_breakdown,
        },
    }
    return final_score, breakdown


def rank_stocks(
    stocks: list[dict[str, Any]],
    financials_map: dict[str, list[dict[str, Any]]] | None = None,
    portfolio_type: str = "unified",
) -> list[dict[str, Any]]:
    """
    Scores and ranks a list of pre-filtered stocks.
    Filters out stocks below dynamic threshold (mean + 0.5 SD with hard floor at MIN_SCORE_THRESHOLD).
    """
    scored = []
    for stock in stocks:
        # Exclude REITs from Value portfolio
        if portfolio_type == "value" and stock.get("is_reit"):
            continue

        fins = (financials_map or {}).get(stock.get("ticker", ""), [])
        score, breakdown = score_unified(stock, financials_history=fins, portfolio_type=portfolio_type)

        enriched = dict(stock)
        enriched["score"] = score
        enriched["category"] = breakdown["category"]
        enriched["breakdown"] = breakdown
        enriched["confidence"] = breakdown["confidence"]
        enriched["scoring_group"] = breakdown["scoring_group"]
        scored.append(enriched)

    scored.sort(key=lambda s: s["score"], reverse=True)

    # Compute dynamic threshold: max(MIN_SCORE_THRESHOLD, mean + 0.5 * SD)
    if scored:
        all_scores = [s["score"] for s in scored]
        mean_score = sum(all_scores) / len(all_scores)
        sd_score = stats.pstdev(all_scores) if len(all_scores) > 1 else 0.0
        dyn_cutoff = max(MIN_SCORE_THRESHOLD, mean_score + 0.5 * sd_score)
    else:
        dyn_cutoff = MIN_SCORE_THRESHOLD

    qualifying = [s for s in scored if s["score"] >= dyn_cutoff]

    # If qualifying stocks is fewer than 10 (e.g. during small demo/seed universes),
    # ensure top candidates scoring above MIN_SCORE_THRESHOLD are included up to 10
    if len(qualifying) < 10:
        qualifying = [s for idx, s in enumerate(scored) if s["score"] >= dyn_cutoff or (s["score"] >= MIN_SCORE_THRESHOLD and idx < 10)]

    # Assign 1-based ranks
    for rank, stock in enumerate(qualifying, start=1):
        stock["rank"] = rank

    return qualifying
