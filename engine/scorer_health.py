# ============================================================
# scorer_health.py — Health Layer Scorer (Sector-Specific)
# PSE Quant SaaS
# ============================================================
# Evaluates current financial strength.
# Sub-scores and weights are driven by SECTOR_SCORING_CONFIG
# in config.py — each sector group scores different metrics.
#
# Available sub-scores:
#   roe           — Return on Equity (%)
#   ni_margin     — Net Income / Revenue (%) — universal efficiency proxy
#   de_ratio      — Debt-to-Equity ratio
#   eps_stability — EPS Coefficient of Variation (lower = more stable)
#   pb            — Price-to-Book ratio (banks and holding firms)
#   dividend_yield— Dividend yield % (REITs)
#   fcf_yield     — FCF Yield % (optional — only when OCF data is available)
#
# Entry: score_health(stock, scoring_group) → (score: float | None, breakdown: dict)
# ============================================================

from __future__ import annotations
import statistics as _stats
from engine.scorer_utils import _blend_checked
from engine.sector_groups import get_layer_config
from config import MIN_SUBSCORES_PER_LAYER


# ── Threshold tables ─────────────────────────────────────
# Each table: list of (upper_bound, score) pairs, ascending.

_ROE_STD = [
    (0,   10), (5,  25), (8,  40), (12, 60),
    (15,  75), (20, 88), (25, 96), (35, 100),
]
_ROE_BANK = [           # Banks have structurally higher ROE from leverage
    (5,   10), (8,  25), (10, 40), (13, 60),
    (16,  75), (20, 88), (25, 96), (30, 100),
]

_NI_MARGIN_STD = [
    (-20,  5), (-5, 15), (0,  30), (3,  45),
    ( 6,  60), (10, 72), (15, 83), (20, 92), (30, 100),
]
_NI_MARGIN_BANK = [     # Banks have structurally lower NI margins
    (-10,  5), (-3, 15), (0,  30), (5,  50),
    (10,  65), (15, 80), (20, 92), (25, 100),
]

_DE_STD = [
    (0.3, 100), (0.5, 92), (0.8, 80), (1.0, 70),
    (1.5,  55), (2.0, 38), (2.5, 20), (3.5,  8),
]
_DE_REIT = [
    (0.5, 100), (1.0, 85), (1.5, 70),
    (2.0,  55), (3.0, 35), (4.0, 15),
]

_EPS_CV = [             # Lower CV = more stable (inverted scale)
    (0.05, 100), (0.10, 90), (0.20, 75), (0.35, 58),
    (0.50,  42), (0.70, 25), (1.00, 12),
]
_EPS_CV_FLOOR = 5.0     # Score floor when mean EPS <= 0

_PB = [                 # Lower P/B preferred for banks/holdings (NAV discount)
    (0.5, 100), (0.8, 90), (1.0, 80), (1.3, 70),
    (1.5,  58), (2.0, 42), (2.5, 25), (3.0, 12),
]

_DIV_YIELD = [          # For REITs — higher distribution is better
    (2,   5), (3,  20), (4,  40), (5,  60),
    (6,  75), (7,  87), (8,  95), (10, 100),
]

_FCF_YIELD = [
    (-10, 5), (-5, 15), (0,  30), (2,  45),
    ( 4, 60), ( 6, 75), (8,  87), (12, 96), (20, 100),
]


def _normalise(value, table: list) -> float | None:
    """Map a raw value to 0-100 using a threshold table. Returns None if value is None."""
    if value is None:
        return None
    for max_val, score in table:
        if value <= max_val:
            return float(score)
    return float(table[-1][1])


# ── Sub-score functions ───────────────────────────────────

def _score_roe(stock: dict, group: str) -> float | None:
    roe = stock.get('roe')
    table = _ROE_BANK if group == 'bank' else _ROE_STD
    return _normalise(roe, table)


def _score_ni_margin(stock: dict, group: str) -> float | None:
    ni_list  = stock.get('net_income_3y') or []
    rev_list = stock.get('revenue_5y') or []
    ni  = next((v for v in ni_list if v is not None), None)
    rev = next((v for v in rev_list if v is not None), None)
    if ni is None or rev is None or rev == 0:
        return None
    margin = (ni / rev) * 100
    table = _NI_MARGIN_BANK if group == 'bank' else _NI_MARGIN_STD
    return _normalise(margin, table)


def _score_de_ratio(stock: dict, group: str) -> float | None:
    de = stock.get('de_ratio')
    if group == 'bank':
        return None   # D/E excluded for banks — leverage IS the business
    table = _DE_REIT if group == 'reit' else _DE_STD
    return _normalise(de, table)


def _score_eps_stability(stock: dict, _group: str) -> float | None:
    eps_hist = stock.get('eps_5y') or stock.get('eps_3y') or []
    valid = [e for e in eps_hist if e is not None]
    if len(valid) < 3:
        return None
    mean_eps = sum(valid) / len(valid)
    if mean_eps <= 0:
        return _EPS_CV_FLOOR
    cv = _stats.pstdev(valid) / mean_eps
    return _normalise(cv, _EPS_CV)


def _score_pb(stock: dict, _group: str) -> float | None:
    return _normalise(stock.get('pb'), _PB)


def _score_dividend_yield(stock: dict, _group: str) -> float | None:
    return _normalise(stock.get('dividend_yield'), _DIV_YIELD)


def _score_fcf_yield(stock: dict, _group: str) -> float | None:
    """Optional — only fires when FCF yield data is available."""
    return _normalise(stock.get('fcf_yield'), _FCF_YIELD)


# ── Sub-score dispatcher ──────────────────────────────────

_SUBSCORERS: dict = {
    'roe':            _score_roe,
    'ni_margin':      _score_ni_margin,
    'de_ratio':       _score_de_ratio,
    'eps_stability':  _score_eps_stability,
    'pb':             _score_pb,
    'dividend_yield': _score_dividend_yield,
    'fcf_yield':      _score_fcf_yield,
}


# ── Main entry ────────────────────────────────────────────

def score_health(stock: dict, scoring_group: str,
                 sector_medians: dict | None = None) -> tuple[float | None, dict]:
    """
    Score the Health layer for this stock using sector-specific config.

    Args:
        stock:          canonical stock dict
        scoring_group:  from engine.sector_groups.get_scoring_group()
        sector_medians: unused (retained for backward-compat call signature)

    Returns:
        (score: float | None, breakdown: dict)
        score is None if fewer than MIN_SUBSCORES_PER_LAYER are available.
    """
    layer_cfg = get_layer_config(scoring_group, 'health')
    if not layer_cfg:
        return None, {'error': f'No health config for group={scoring_group}'}

    scores_weights = []
    factors: dict = {}

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
