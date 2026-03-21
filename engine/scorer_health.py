# ============================================================
# scorer_health.py — Layer 1: Health Score
# PSE Quant SaaS — Phase 9B (v2 Unified Scorer)
# ============================================================
# Answers: "Is this company financially healthy today?"
#
# Evaluates current financial strength across 5 dimensions:
#   - ROE           (20%) — management efficiency
#   - OCF Margin    (20%) — cash generation quality
#   - D/E Ratio     (20%) — leverage risk (bank/REIT-adjusted)
#   - FCF Yield     (20%) — free cash flow generation
#   - EPS Stability (20%) — earnings consistency
#
# Sector-adjusted valuation (PE vs sector median) is applied as
# a bonus/penalty modifier on top of the raw health score.
#
# Returns: (score: float 0-100, breakdown: dict)
# ============================================================

from __future__ import annotations


def _score_with_sector_blend(absolute_score: float, value, sector_median,
                              higher_is_better: bool = True) -> float:
    """Blend absolute score 70% with sector-relative score 30%."""
    if sector_median is None or value is None:
        return absolute_score
    if higher_is_better:
        sector_score = 65.0 if value > sector_median else 35.0
    else:
        sector_score = 65.0 if value < sector_median else 35.0
    return round(absolute_score * 0.70 + sector_score * 0.30, 1)


def _normalise(value, thresholds: list) -> float:
    """
    Piecewise threshold normalisation.
    thresholds = [(max_value, score), ...] in ascending order.
    Returns the score for the first threshold where value <= max_value.
    """
    if value is None:
        return 0.0
    for max_val, score in thresholds:
        if value <= max_val:
            return float(score)
    return float(thresholds[-1][1])


def _blend(scores_weights: list) -> float:
    """
    Weighted average, redistributing weight from None sub-scores
    to the available ones proportionally.
    """
    valid = [(s, w) for s, w in scores_weights if s is not None]
    if not valid:
        return 0.0
    total_w = sum(w for _, w in valid)
    return round(sum(s * (w / total_w) for s, w in valid), 1)


# ── Sub-score functions ───────────────────────────────────────

def _score_roe(roe: float | None) -> float | None:
    """ROE % → 0-100. Higher is better. Bank/REIT-adjusted in caller."""
    return _normalise(roe, [
        (0,  10),
        (5,  25),
        (8,  40),
        (12, 60),
        (15, 75),
        (20, 88),
        (25, 96),
        (35, 100),
    ]) if roe is not None else None


def _score_ocf_margin(operating_cf, revenue) -> float | None:
    """
    Operating Cash Flow Margin = OCF / Revenue.
    Measures quality of earnings — how much cash the business generates
    from each peso of revenue.
    """
    if operating_cf is None or revenue is None or revenue <= 0:
        return None
    margin = (operating_cf / revenue) * 100
    return _normalise(margin, [
        (-20, 5),
        (-5,  15),
        (0,   30),
        (5,   50),
        (10,  65),
        (15,  80),
        (20,  90),
        (30,  100),
    ])


def _score_de_ratio(de_ratio: float | None,
                    is_bank: bool = False,
                    is_reit: bool = False) -> float | None:
    """
    D/E ratio → 0-100. Lower is better.
    Banks and REITs have structurally higher leverage — adjusted thresholds.
    """
    if de_ratio is None:
        return None
    if is_bank:
        return _normalise(de_ratio, [
            (3,  100), (5,  85), (7,  65),
            (9,  45),  (12, 25), (15, 10),
        ])
    if is_reit:
        return _normalise(de_ratio, [
            (0.5, 100), (1.0, 85), (1.5, 70),
            (2.0, 55),  (3.0, 35), (4.0, 15),
        ])
    # Standard non-financial company
    return _normalise(de_ratio, [
        (0.3, 100), (0.5, 92), (0.8, 80),
        (1.0, 70),  (1.5, 55), (2.0, 38),
        (2.5, 20),  (3.5, 8),
    ])


def _score_fcf_yield(fcf_yield: float | None) -> float | None:
    """
    FCF Yield % → 0-100. Higher is better.
    Negative FCF yield (cash-burning) scores very low.
    """
    if fcf_yield is None:
        return None
    return _normalise(fcf_yield, [
        (-10, 5),
        (-5,  15),
        (0,   30),
        (2,   45),
        (4,   60),
        (6,   75),
        (8,   87),
        (12,  96),
        (20,  100),
    ])


def _score_reit_coverage(stock: dict) -> float:
    """
    REIT FCF exemption: score based on FFO yield when available.
    REITs must distribute 90%+ of income by law — near-zero FCF is
    structural, not a sign of financial weakness. We use FFO yield
    (Net Income + Depreciation relative to market cap) as the proxy.

    If FFO yield is available → score on FFO yield thresholds.
    If FFO data is not available (depreciation missing from DB) →
      return neutral 50/100 rather than penalising the REIT.
    """
    ffo_yield = stock.get('ffo_yield')
    if ffo_yield is not None:
        # FFO yield thresholds calibrated for typical PH REIT levels
        if ffo_yield >= 6:
            return 90.0
        if ffo_yield >= 4:
            return 70.0
        if ffo_yield >= 2:
            return 50.0
        return 30.0
    # FFO not computable (depreciation not in DB) — neutral score
    return 50.0


def _score_eps_stability(eps_history: list | None) -> float | None:
    """
    EPS Stability: Coefficient of Variation (StdDev / |Mean|).
    Lower CV = more stable. Penalises erratic or negative EPS.
    Requires at least 3 years of EPS data.
    """
    if not eps_history or len(eps_history) < 3:
        return None
    vals = [v for v in eps_history if v is not None]
    if len(vals) < 3:
        return None
    mean = sum(vals) / len(vals)
    if mean <= 0:
        return 10.0  # persistent negative/zero EPS = low score
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = variance ** 0.5
    cv = std / abs(mean)
    return _normalise(cv, [
        (0.05, 100), (0.10, 90), (0.20, 75),
        (0.35, 58),  (0.50, 42), (0.70, 25),
        (1.00, 12),  (1.50, 5),
    ])


def _score_pe_vs_sector(pe: float | None,
                         sector_median_pe: float | None) -> float | None:
    """
    Sector-relative PE scoring.
    Compares this stock's PE to its sector median.
    Below sector median = potential undervaluation (higher score).
    Above sector median = elevated valuation (lower score).
    Returns None if either PE is missing.
    """
    if pe is None or sector_median_pe is None or sector_median_pe <= 0:
        return None
    if pe <= 0:
        return None
    ratio = pe / sector_median_pe  # 1.0 = at sector median
    return _normalise(ratio, [
        (0.40, 100),
        (0.60, 90),
        (0.75, 80),
        (0.90, 70),
        (1.00, 60),  # at sector median
        (1.15, 48),
        (1.30, 35),
        (1.50, 22),
        (2.00, 10),
    ])


# ── Main scorer ───────────────────────────────────────────────

def score_health(stock: dict, sector_median_pe: float | None = None,
                 sector_medians: dict | None = None) -> tuple[float, dict]:
    """
    Layer 1 — Health Score.
    Evaluates current financial strength. Returns (score 0-100, breakdown).

    Required stock dict keys:
        roe, operating_cf, revenue_5y, de_ratio, fcf_yield,
        eps_3y or eps_5y, is_bank, is_reit
    Optional:
        sector_median_pe — PE median for this stock's sector (backward compat)
        sector_medians   — dict with sector medians for roe, ocf_margin,
                           fcf_yield, de_ratio; used for 70/30 absolute/sector blend
    """
    is_bank = bool(stock.get('is_bank'))
    is_reit = bool(stock.get('is_reit'))
    sm = sector_medians or {}

    # ── Compute sub-scores ────────────────────────────────────
    roe_raw   = _score_roe(stock.get('roe'))
    de_s      = _score_de_ratio(stock.get('de_ratio'), is_bank, is_reit)

    # FCF yield: REITs use FFO-based scoring to avoid penalising mandatory
    # dividend distributions. Non-REITs use standard FCF yield scoring.
    if is_reit:
        fcfy_raw = _score_reit_coverage(stock)
        fcfy_s   = fcfy_raw  # no sector blend for REIT FFO proxy
    else:
        fcfy_raw = _score_fcf_yield(stock.get('fcf_yield'))
        fcfy_s   = None  # computed in sector-blend block below

    # OCF margin uses most recent revenue
    rev_hist = stock.get('revenue_5y') or []
    rev_curr = rev_hist[0] if rev_hist else None
    ocf_raw = _score_ocf_margin(stock.get('operating_cf'), rev_curr)
    ocf_margin_val = (
        round(stock.get('operating_cf') / rev_curr * 100, 1)
        if stock.get('operating_cf') is not None and rev_curr else None
    )

    # EPS stability — prefer 5y, fall back to 3y
    eps_hist = stock.get('eps_5y') or stock.get('eps_3y') or []
    eps_s = _score_eps_stability(eps_hist)

    # Sector-adjusted PE (optional modifier — backward compat)
    pe_vs_sector_s = _score_pe_vs_sector(
        stock.get('pe'), sector_median_pe
    )

    # ── Apply 70/30 sector blend where sector medians are available ───
    roe_s  = _score_with_sector_blend(
        roe_raw, stock.get('roe'), sm.get('roe'),
        higher_is_better=True
    ) if roe_raw is not None else None

    ocf_s  = _score_with_sector_blend(
        ocf_raw, ocf_margin_val, sm.get('ocf_margin'),
        higher_is_better=True
    ) if ocf_raw is not None else None

    # For non-REITs: apply sector blend to FCF yield
    if not is_reit:
        fcfy_s = _score_with_sector_blend(
            fcfy_raw, stock.get('fcf_yield'), sm.get('fcf_yield'),
            higher_is_better=True
        ) if fcfy_raw is not None else None

    # D/E: apply blend only if sector median available (lower is better)
    if de_s is not None and sm.get('de_ratio') is not None:
        de_s = _score_with_sector_blend(
            de_s, stock.get('de_ratio'), sm.get('de_ratio'),
            higher_is_better=False
        )

    # ── Weighted blend ────────────────────────────────────────
    # Base 5 factors (equal weight within layer 1)
    base_score = _blend([
        (roe_s,  0.20),
        (ocf_s,  0.20),
        (de_s,   0.20),
        (fcfy_s, 0.20),
        (eps_s,  0.20),
    ])

    # Sector PE modifier: blend in at 15% if available
    if pe_vs_sector_s is not None:
        final_score = round(base_score * 0.85 + pe_vs_sector_s * 0.15, 1)
    else:
        final_score = base_score

    breakdown = {
        'roe': {
            'score':       roe_s,
            'weight':      0.20,
            'value':       stock.get('roe'),
            'explanation': _explain_roe(stock.get('roe'), is_bank),
        },
        'ocf_margin': {
            'score':       ocf_s,
            'weight':      0.20,
            'value':       ocf_margin_val,
            'explanation': _explain_ocf_margin(stock.get('operating_cf'), rev_curr),
        },
        'de_ratio': {
            'score':       de_s,
            'weight':      0.20,
            'value':       stock.get('de_ratio'),
            'explanation': _explain_de(stock.get('de_ratio'), is_bank, is_reit),
        },
        'fcf_yield': {
            'score':       fcfy_s,
            'weight':      0.20,
            'value':       stock.get('ffo_yield') if is_reit else stock.get('fcf_yield'),
            'explanation': (
                _explain_reit_ffo(stock.get('ffo_yield'))
                if is_reit else _explain_fcf_yield(stock.get('fcf_yield'))
            ),
        },
        'eps_stability': {
            'score':       eps_s,
            'weight':      0.20,
            'value':       len([v for v in eps_hist if v is not None]),
            'explanation': _explain_eps_stability(eps_hist),
        },
        'pe_vs_sector': {
            'score':       pe_vs_sector_s,
            'weight':      0.15,  # modifier on top of base
            'value':       stock.get('pe'),
            'explanation': _explain_pe_sector(
                stock.get('pe'), sector_median_pe,
                stock.get('sector', '')
            ),
        },
    }

    return final_score, breakdown


# ── Plain-English explanations ────────────────────────────────

def _explain_roe(roe, is_bank):
    if roe is None:
        return "ROE data not available."
    bank_note = " (bank — higher leverage is normal)" if is_bank else ""
    if roe >= 20:
        return (f"ROE of {roe:.1f}%{bank_note} — excellent. "
                f"Management generates PHP{roe:.0f} for every PHP100 of equity.")
    if roe >= 15:
        return (f"ROE of {roe:.1f}%{bank_note} — strong. "
                f"Our rule-based model rates 15%+ as a quality threshold.")
    if roe >= 10:
        return f"ROE of {roe:.1f}%{bank_note} — moderate. Acceptable but not outstanding."
    if roe >= 5:
        return f"ROE of {roe:.1f}%{bank_note} — below average. Weak capital deployment."
    return f"ROE of {roe:.1f}%{bank_note} — poor. Capital is barely working for shareholders."


def _explain_ocf_margin(ocf, revenue):
    if ocf is None or revenue is None or revenue <= 0:
        return "Operating cash flow or revenue data not available."
    margin = (ocf / revenue) * 100
    if margin >= 20:
        return f"OCF margin of {margin:.1f}% — excellent. Strong cash conversion."
    if margin >= 10:
        return f"OCF margin of {margin:.1f}% — healthy. Business generates real cash."
    if margin >= 0:
        return f"OCF margin of {margin:.1f}% — thin. Low cash relative to revenue."
    return f"OCF margin of {margin:.1f}% — negative. Business consuming more cash than it generates."


def _explain_de(de, is_bank, is_reit):
    if de is None:
        return "Debt-to-equity data not available."
    if is_bank:
        return (f"D/E of {de:.2f}x (bank). Banks operate with high leverage by nature. "
                f"Evaluated against bank-specific thresholds.")
    if is_reit:
        return (f"D/E of {de:.2f}x (REIT). REITs use debt to fund property acquisitions. "
                f"Evaluated against REIT-specific thresholds.")
    if de <= 0.5:
        return f"D/E of {de:.2f}x — very low leverage. Strong balance sheet."
    if de <= 1.0:
        return f"D/E of {de:.2f}x — moderate leverage. Manageable debt level."
    if de <= 2.0:
        return f"D/E of {de:.2f}x — elevated leverage. Monitor debt service capacity."
    return f"D/E of {de:.2f}x — high leverage. Significant financial risk."


def _explain_fcf_yield(fcfy):
    if fcfy is None:
        return "FCF yield data not available."
    if fcfy >= 8:
        return f"FCF yield of {fcfy:.1f}% — excellent. Stock generates strong free cash."
    if fcfy >= 4:
        return f"FCF yield of {fcfy:.1f}% — healthy. Business is cash-generative."
    if fcfy >= 0:
        return f"FCF yield of {fcfy:.1f}% — thin. Limited free cash generation."
    return f"FCF yield of {fcfy:.1f}% — negative. Business burning cash."


def _explain_reit_ffo(ffo_yield):
    """
    Plain-English explanation for the REIT FFO yield sub-score.
    REITs must distribute 90%+ of income by law, so standard FCF
    (which deducts dividends) is structurally near zero — this is
    normal and healthy for a REIT, not a warning sign.
    """
    if ffo_yield is not None:
        if ffo_yield >= 6:
            return (f"FFO yield of {ffo_yield:.1f}% — strong. "
                    f"This REIT generates ample funds from operations relative to its price.")
        if ffo_yield >= 4:
            return (f"FFO yield of {ffo_yield:.1f}% — adequate. "
                    f"FFO (net income + depreciation) supports dividend distributions.")
        if ffo_yield >= 2:
            return (f"FFO yield of {ffo_yield:.1f}% — below average for a REIT. "
                    f"Dividend sustainability may be tighter.")
        return (f"FFO yield of {ffo_yield:.1f}% — low. "
                f"Limited FFO relative to market price.")
    return ("FFO data not available (depreciation not scraped). "
            "REITs must distribute 90%+ of income by law — "
            "near-zero FCF is structurally expected, not a red flag. "
            "Scored as neutral until FFO data becomes available.")


def _explain_eps_stability(eps_hist):
    if not eps_hist or len([v for v in eps_hist if v is not None]) < 3:
        return "Insufficient EPS history for stability analysis (need 3+ years)."
    vals = [v for v in eps_hist if v is not None]
    positives = sum(1 for v in vals if v > 0)
    return (f"EPS over {len(vals)} years: {positives}/{len(vals)} positive years. "
            f"{'Consistent earnings.' if positives == len(vals) else 'Some earnings volatility detected.'}")


def _explain_pe_sector(pe, sector_median, sector):
    if pe is None:
        return "P/E ratio not available."
    if sector_median is None:
        return f"P/E of {pe:.1f}x — sector median not available for comparison."
    ratio = pe / sector_median
    sector_str = f" ({sector})" if sector else ""
    if ratio <= 0.75:
        return (f"P/E of {pe:.1f}x vs sector{sector_str} median of {sector_median:.1f}x. "
                f"Trading at a significant discount to peers.")
    if ratio <= 1.0:
        return (f"P/E of {pe:.1f}x vs sector{sector_str} median of {sector_median:.1f}x. "
                f"Moderately priced relative to peers.")
    if ratio <= 1.3:
        return (f"P/E of {pe:.1f}x vs sector{sector_str} median of {sector_median:.1f}x. "
                f"Slight premium to sector peers.")
    return (f"P/E of {pe:.1f}x vs sector{sector_str} median of {sector_median:.1f}x. "
            f"Significant premium — price implies high growth expectations.")
