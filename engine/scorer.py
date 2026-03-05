# ============================================================
# scorer.py — Portfolio Scoring Engine (Institutional v2)
# PSE Quant SaaS — Phase 1
# ============================================================
#
# Institutional v2 improvements:
#
#   Pure Dividend (6 factors, equal-ish weights ~15-20%):
#     dividend_yield         20%  — how much cash income now
#     fcf_yield              20%  — real cash generation efficiency
#     roe                    15%  — quality of the business
#     eps_stability          15%  — consistent earnings = reliable dividend
#     leverage_coverage      15%  — composite: D/E + FCF coverage + interest coverage
#     relative_valuation     15%  — composite: P/E + EV/EBITDA (don't overpay)
#
#   Dividend Growth (6 factors):
#     dividend_cagr          20%  — how fast is the dividend growing?
#     eps_growth             20%  — earnings growth funds future dividends
#     roe                    15%  — business quality drives future growth
#     dividend_yield         15%  — starting income level
#     payout_ratio           15%  — low payout = room to raise the dividend
#     leverage_stability     15%  — composite: D/E + FCF coverage
#
#   Value (4 composite factors, near-equal weights):
#     valuation_composite    33%  — P/E + EV/EBITDA + FCF Yield
#     quality_composite      33%  — ROE + EPS stability
#     leverage_risk          17%  — D/E + interest coverage
#     revenue_growth         17%  — top-line growth fuels future value
#
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


# ── Plain English explanation generators ────────────────────

def explain_dividend_yield(value):
    if value is None:
        return "No dividend yield data available."
    if value > 12:
        return (
            f"Yield of {value:.1f}% is very high — this may signal "
            f"financial stress or an unsustainable payout. "
            f"We apply a caution penalty for yields above 12%."
        )
    elif value >= 9:
        return (
            f"Yield of {value:.1f}% is exceptional. For every ₱100 "
            f"invested, you receive ₱{value:.2f} per year in cash. "
            f"This is among the best income yields on the PSE."
        )
    elif value >= 7:
        return (
            f"Yield of {value:.1f}% is very strong. For every ₱100 "
            f"invested, you receive ₱{value:.2f} per year in cash. "
            f"Well above the PSE average."
        )
    elif value >= 5:
        return (
            f"Yield of {value:.1f}% is solid for an income stock. "
            f"For every ₱100 invested, you receive ₱{value:.2f} per year. "
            f"Meets the threshold for a meaningful dividend portfolio."
        )
    elif value >= 3:
        return (
            f"Yield of {value:.1f}% is moderate. For every ₱100 "
            f"invested, you receive only ₱{value:.2f} per year. "
            f"This stock is not primarily an income play."
        )
    else:
        return (
            f"Yield of {value:.1f}% is low for a dividend portfolio. "
            f"For every ₱100 invested, you receive only ₱{value:.2f} "
            f"per year — barely above a savings account."
        )


def explain_dividend_cagr(value):
    if value is None:
        return "No dividend growth history available."
    if value >= 10:
        return (
            f"Dividend grew at {value:.1f}% per year over 5 years — "
            f"excellent. At this rate, the dividend doubles roughly "
            f"every {round(72/value, 1)} years, well ahead of inflation."
        )
    elif value >= 5:
        return (
            f"Dividend grew at {value:.1f}% per year over 5 years — "
            f"solid. The company is consistently rewarding shareholders "
            f"with more cash over time."
        )
    elif value >= 0:
        return (
            f"Dividend grew at only {value:.1f}% per year over 5 years. "
            f"Growth is positive but slow — barely keeping pace "
            f"with inflation."
        )
    else:
        return (
            f"Dividend SHRANK at {abs(value):.1f}% per year over 5 years. "
            f"A declining dividend is a red flag — the company may be "
            f"under financial pressure."
        )


def explain_payout_ratio(value, is_reit=False):
    if value is None:
        return "No payout ratio data available."
    if is_reit:
        return (
            f"Payout ratio of {value:.1f}%. REITs are required by law "
            f"to distribute at least 90% of income — so this is "
            f"expected and normal for this type of company."
        )
    if value <= 30:
        return (
            f"Payout ratio of {value:.1f}% — very conservative. "
            f"The company retains most of its profits. "
            f"The dividend is very safe and has significant room to grow."
        )
    elif value <= 70:
        return (
            f"Payout ratio of {value:.1f}% — healthy sweet spot. "
            f"The company pays out a fair share while retaining "
            f"enough profit to grow the business and raise the dividend."
        )
    elif value <= 85:
        return (
            f"Payout ratio of {value:.1f}% — stretched. "
            f"The company is paying out most of its earnings. "
            f"Any dip in profit could put future dividend increases at risk."
        )
    else:
        return (
            f"Payout ratio of {value:.1f}% — danger zone. "
            f"The company is paying out nearly all its earnings as "
            f"dividends. One bad quarter could force a cut."
        )


def explain_fcf_coverage(value):
    if value is None:
        return "No free cash flow coverage data available."
    if value >= 2.0:
        return (
            f"FCF coverage of {value:.2f}x — excellent. "
            f"The company generates {value:.1f}x more real cash "
            f"than it pays in dividends. The dividend is very secure."
        )
    elif value >= 1.5:
        return (
            f"FCF coverage of {value:.2f}x — good. "
            f"The company has a healthy cushion of real cash "
            f"above what it needs to pay dividends."
        )
    elif value >= 1.0:
        return (
            f"FCF coverage of {value:.2f}x — adequate but thin. "
            f"The company can afford the dividend but has little "
            f"margin for error if cash flow drops."
        )
    else:
        return (
            f"FCF coverage of {value:.2f}x — warning. "
            f"The company does NOT generate enough real cash to "
            f"fully cover its dividend. The dividend may not be "
            f"sustainable long-term."
        )


def explain_eps_stability(net_income_3y, eps_vol_ratio=None):
    if eps_vol_ratio is not None:
        if eps_vol_ratio <= 0.3:
            return (
                f"EPS volatility ratio of {eps_vol_ratio:.2f} — very stable earnings. "
                f"Consistent profits are the foundation of a reliable dividend."
            )
        elif eps_vol_ratio <= 0.6:
            return (
                f"EPS volatility ratio of {eps_vol_ratio:.2f} — reasonably stable. "
                f"Some earnings variation, but not enough to threaten the dividend."
            )
        elif eps_vol_ratio <= 1.0:
            return (
                f"EPS volatility ratio of {eps_vol_ratio:.2f} — moderate volatility. "
                f"Earnings fluctuate noticeably. Monitor for trend deterioration."
            )
        else:
            return (
                f"EPS volatility ratio of {eps_vol_ratio:.2f} — highly erratic earnings. "
                f"Unreliable profits make the dividend unpredictable."
            )

    if not net_income_3y:
        return "No earnings history available."
    positive = sum(1 for n in net_income_3y if n > 0)
    if positive == 3:
        return (
            f"Profitable in all 3 of the last 3 years — excellent. "
            f"Consistent profitability is the foundation of a "
            f"reliable dividend."
        )
    elif positive == 2:
        return (
            f"Profitable in 2 of the last 3 years. "
            f"One year of losses is a yellow flag — worth monitoring "
            f"to see if the trend improves."
        )
    elif positive == 1:
        return (
            f"Only profitable in 1 of the last 3 years — concerning. "
            f"Inconsistent earnings make the dividend unreliable."
        )
    else:
        return (
            f"Not profitable in any of the last 3 years — "
            f"this stock should not be in a dividend portfolio."
        )


def explain_roe(value):
    if value is None:
        return "No ROE data available."
    if value >= 20:
        return (
            f"ROE of {value:.1f}% — excellent management performance. "
            f"For every ₱100 of equity, the company earns ₱{value:.0f}. "
            f"Warren Buffett looks for ROE above 15% consistently."
        )
    elif value >= 15:
        return (
            f"ROE of {value:.1f}% — strong. "
            f"Management is deploying capital efficiently. "
            f"Above the 15% threshold that signals a quality business."
        )
    elif value >= 10:
        return (
            f"ROE of {value:.1f}% — moderate. "
            f"Management is generating acceptable but not outstanding "
            f"returns on shareholder equity."
        )
    elif value >= 5:
        return (
            f"ROE of {value:.1f}% — below average. "
            f"Management is not generating strong returns. "
            f"A PSE index fund would likely outperform this."
        )
    else:
        return (
            f"ROE of {value:.1f}% — poor capital allocation. "
            f"The business is barely earning anything on your money."
        )


def explain_eps_growth(value):
    if value is None:
        return "No EPS growth trend data available."
    if value >= 15:
        return (
            f"EPS growing at {value:.1f}% per year — excellent. "
            f"Strong earnings growth is the engine that drives future dividend increases."
        )
    elif value >= 8:
        return (
            f"EPS growing at {value:.1f}% per year — solid. "
            f"Consistent earnings growth supports sustained dividend raises."
        )
    elif value >= 3:
        return (
            f"EPS growing at {value:.1f}% per year — modest. "
            f"Earnings are expanding but slowly. Dividend growth may "
            f"be limited to inflation-matching levels."
        )
    elif value >= 0:
        return (
            f"EPS growth of {value:.1f}% per year — flat. "
            f"Stagnant earnings leave little room to grow the dividend meaningfully."
        )
    else:
        return (
            f"EPS DECLINING at {abs(value):.1f}% per year — concerning. "
            f"Shrinking earnings make it difficult to maintain, let alone grow, the dividend."
        )


def explain_pe(value):
    if value is None:
        return "No P/E ratio data available."
    if value <= 8:
        return (
            f"P/E of {value:.1f}x — deeply undervalued. "
            f"You are paying only ₱{value:.1f} for every ₱1 of annual "
            f"earnings. This is very cheap by any standard."
        )
    elif value <= 12:
        return (
            f"P/E of {value:.1f}x — attractively valued. "
            f"You are paying ₱{value:.1f} for every ₱1 of annual "
            f"earnings. Below the PSE market average."
        )
    elif value <= 18:
        return (
            f"P/E of {value:.1f}x — fairly valued. "
            f"You pay ₱{value:.1f} for every ₱1 of annual earnings. "
            f"Around the PSE market average."
        )
    elif value <= 28:
        return (
            f"P/E of {value:.1f}x — moderately expensive. "
            f"You pay ₱{value:.1f} for every ₱1 of annual earnings. "
            f"Above average — the stock needs strong growth to justify this."
        )
    else:
        return (
            f"P/E of {value:.1f}x — expensive. "
            f"You pay ₱{value:.1f} for every ₱1 of annual earnings. "
            f"High P/E stocks carry more risk if growth disappoints."
        )


def explain_pb(value):
    if value is None:
        return "No P/B ratio data available."
    if value <= 0.8:
        return (
            f"P/B of {value:.2f}x — trading below book value. "
            f"You are buying ₱1 of company assets for only "
            f"₱{value:.2f}. Significant asset discount."
        )
    elif value <= 1.2:
        return (
            f"P/B of {value:.2f}x — trading near book value. "
            f"The price is close to what the company actually owns. "
            f"Fair to slightly attractive."
        )
    elif value <= 2.0:
        return (
            f"P/B of {value:.2f}x — modest premium to book value. "
            f"The market values the company above its assets, "
            f"likely due to brand or earnings power."
        )
    else:
        return (
            f"P/B of {value:.2f}x — significant premium to book value. "
            f"The stock price is well above the company's net assets. "
            f"Justified only if earnings are consistently strong."
        )


def explain_ev_ebitda(value):
    if value is None:
        return "No EV/EBITDA data available."
    if value <= 5:
        return (
            f"EV/EBITDA of {value:.1f}x — very cheap. "
            f"The entire business (including debt) costs only "
            f"{value:.1f}x its annual operating profit."
        )
    elif value <= 8:
        return (
            f"EV/EBITDA of {value:.1f}x — attractive. "
            f"Below 8x is generally considered good value "
            f"in the Philippine market."
        )
    elif value <= 12:
        return (
            f"EV/EBITDA of {value:.1f}x — fair. "
            f"Around the market average. Not cheap but not expensive."
        )
    else:
        return (
            f"EV/EBITDA of {value:.1f}x — expensive. "
            f"Above 12x suggests the market is pricing in "
            f"significant future growth."
        )


def explain_revenue_cagr(value):
    if value is None:
        return "No revenue growth data available."
    if value >= 15:
        return (
            f"Revenue growing at {value:.1f}% per year — exceptional. "
            f"At this rate revenues double roughly every "
            f"{round(72/value, 1)} years."
        )
    elif value >= 10:
        return (
            f"Revenue growing at {value:.1f}% per year — strong. "
            f"The business is expanding meaningfully and increasing "
            f"future earnings potential."
        )
    elif value >= 5:
        return (
            f"Revenue growing at {value:.1f}% per year — moderate. "
            f"Steady growth, roughly in line with a healthy economy."
        )
    elif value >= 0:
        return (
            f"Revenue growing at only {value:.1f}% per year — slow. "
            f"The business is barely expanding. "
            f"Limited upside from revenue growth."
        )
    else:
        return (
            f"Revenue SHRINKING at {abs(value):.1f}% per year — "
            f"concerning. A declining top line threatens future "
            f"earnings and dividends."
        )


def explain_de_ratio(value):
    if value is None:
        return "No debt data available."
    if value <= 0.3:
        return (
            f"Debt/Equity of {value:.2f}x — very low debt. "
            f"The company is largely self-funded and highly resilient "
            f"to economic downturns."
        )
    elif value <= 0.7:
        return (
            f"Debt/Equity of {value:.2f}x — manageable debt. "
            f"The company uses modest leverage without taking "
            f"excessive financial risk."
        )
    elif value <= 1.2:
        return (
            f"Debt/Equity of {value:.2f}x — moderate debt. "
            f"The company carries meaningful debt. "
            f"Monitor if interest rates rise."
        )
    elif value <= 2.0:
        return (
            f"Debt/Equity of {value:.2f}x — elevated debt. "
            f"High leverage increases financial risk. "
            f"A revenue decline could strain debt repayments."
        )
    else:
        return (
            f"Debt/Equity of {value:.2f}x — high debt. "
            f"This level of leverage is a significant risk factor. "
            f"The company must generate strong cash flow to service it."
        )


def explain_fcf_yield(value):
    if value is None:
        return "No FCF yield data available."
    if value >= 10:
        return (
            f"FCF yield of {value:.1f}% — exceptional cash generation. "
            f"For every ₱100 of market cap, the company generates "
            f"₱{value:.1f} in real free cash. Very efficient business."
        )
    elif value >= 7:
        return (
            f"FCF yield of {value:.1f}% — strong. "
            f"The company converts a high percentage of its market "
            f"value into real cash each year."
        )
    elif value >= 4:
        return (
            f"FCF yield of {value:.1f}% — moderate. "
            f"Decent cash generation relative to market cap."
        )
    else:
        return (
            f"FCF yield of {value:.1f}% — low. "
            f"The company generates relatively little free cash "
            f"compared to what the market values it at."
        )


def explain_leverage_coverage(de, fcf_cov, interest_cov):
    parts = []
    if de is not None:
        parts.append(f"D/E {de:.2f}x")
    if fcf_cov is not None:
        parts.append(f"FCF coverage {fcf_cov:.2f}x")
    if interest_cov is not None:
        parts.append(f"interest coverage {interest_cov:.1f}x")
    if not parts:
        return "No leverage or coverage data available."
    summary = ", ".join(parts)
    return (
        f"Composite leverage and coverage score based on {summary}. "
        f"Lower debt and higher coverage ratios indicate a more financially "
        f"resilient dividend payer."
    )


def explain_relative_valuation(pe, ev_ebitda):
    parts = []
    if pe is not None:
        parts.append(f"P/E {pe:.1f}x")
    if ev_ebitda is not None:
        parts.append(f"EV/EBITDA {ev_ebitda:.1f}x")
    if not parts:
        return "No valuation data available for relative valuation composite."
    return (
        f"Composite valuation score based on {' and '.join(parts)}. "
        f"Even in an income portfolio, buying at a reasonable price "
        f"protects against valuation risk if dividends are cut."
    )


def explain_valuation_composite(pe, ev_ebitda, fcf_yield):
    parts = []
    if pe is not None:
        parts.append(f"P/E {pe:.1f}x")
    if ev_ebitda is not None:
        parts.append(f"EV/EBITDA {ev_ebitda:.1f}x")
    if fcf_yield is not None:
        parts.append(f"FCF yield {fcf_yield:.1f}%")
    if not parts:
        return "No valuation data available for composite scoring."
    return (
        f"Composite valuation using {', '.join(parts)}. "
        f"Lower multiples and higher FCF yield signal a stock trading "
        f"below its intrinsic worth. All three metrics must agree for "
        f"high conviction."
    )


def explain_quality_composite(roe, positive_years, total_years=3):
    roe_str = f"ROE {roe:.1f}%" if roe is not None else "ROE unavailable"
    return (
        f"Quality composite: {roe_str}, profitable {positive_years}/{total_years} years. "
        f"High ROE + earnings consistency is the hallmark of a durable, "
        f"compounding business."
    )


# ── Helper: compute EPS CAGR from history ───────────────────

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


# ── Scoring functions ────────────────────────────────────────

def score_pure_dividend(metrics: dict):
    """
    Pure Dividend portfolio scoring.
    Primary goal: maximum current income that is safe and sustainable.

    Weights (Institutional v2):
      dividend_yield       20%  — how much cash income now
      fcf_yield            20%  — real cash generation efficiency
      roe                  15%  — quality of the business
      eps_stability        15%  — consistent earnings = reliable dividend
      leverage_coverage    15%  — composite: D/E + FCF coverage + interest cov
      relative_valuation   15%  — composite: P/E + EV/EBITDA (avoid overpaying)
    """
    is_reit = metrics.get('is_reit', False)

    # ── Dividend Yield (20%) ─────────────────────────────────
    div_yield = metrics.get('dividend_yield')
    yield_score = normalise(div_yield, [
        (3, 20), (5, 55), (7, 80), (9, 95), (12, 100),
    ])
    if div_yield and div_yield > 12:
        yield_score = 50   # yield trap warning — too high may be unsustainable

    # ── FCF Yield (20%) ──────────────────────────────────────
    fcf_yield = metrics.get('fcf_yield')
    fcf_yield_score = normalise(fcf_yield, [
        (2, 15), (4, 40), (6, 65), (8, 85), (10, 100),
    ])

    # ── ROE (15%) ────────────────────────────────────────────
    roe = metrics.get('roe')
    roe_score = normalise(roe, [
        (5, 10), (10, 40), (15, 65), (20, 85), (25, 100),
    ])

    # ── EPS Stability (15%) ──────────────────────────────────
    # Use EPS volatility ratio if multi-year EPS available; else count positive years.
    eps_5y = metrics.get('eps_5y', [])
    eps_3y = metrics.get('eps_3y', [])
    eps_history = eps_5y if len(eps_5y) >= 3 else eps_3y
    vol_ratio = _eps_vol_ratio(eps_history)

    if vol_ratio is not None:
        # Lower volatility = higher score
        stability_score = normalise(vol_ratio, [
            (0.2, 100), (0.4, 85), (0.6, 70), (0.8, 55), (1.0, 35), (1.5, 15),
        ])
        stability_explanation = explain_eps_stability([], eps_vol_ratio=vol_ratio)
    else:
        net_income_3y = metrics.get('net_income_3y', [])
        positive_years = sum(1 for n in net_income_3y if n and n > 0)
        stability_score = [0, 20, 60, 100][min(positive_years, 3)]
        stability_explanation = explain_eps_stability(net_income_3y)

    # ── Leverage & Coverage Composite (15%) ─────────────────
    # Blends D/E + FCF coverage + interest coverage (if available)
    de = metrics.get('de_ratio')
    fcf_cov = metrics.get('fcf_coverage')
    interest_cov = metrics.get('interest_coverage')

    de_score = normalise(de, [
        (0.3, 100), (0.7, 80), (1.2, 60), (2.0, 35), (3.0, 10),
    ]) if de is not None else None

    fcf_cov_score = normalise(fcf_cov, [
        (0.5, 10), (1.0, 40), (1.5, 75), (2.0, 90), (3.0, 100),
    ]) if fcf_cov is not None else None

    int_cov_score = normalise(interest_cov, [
        (1.5, 10), (3.0, 50), (5.0, 75), (8.0, 90), (12.0, 100),
    ]) if interest_cov is not None else None

    lev_score = _blend([
        (de_score,      0.40),
        (fcf_cov_score, 0.40),
        (int_cov_score, 0.20),
    ])
    lev_explanation = explain_leverage_coverage(de, fcf_cov, interest_cov)

    # ── Relative Valuation Composite (15%) ──────────────────
    pe = metrics.get('pe')
    ev = metrics.get('ev_ebitda')

    pe_score = normalise(pe, [
        (8, 100), (12, 85), (18, 65), (28, 35), (40, 15),
    ]) if pe is not None else None

    ev_score = normalise(ev, [
        (5, 100), (8, 80), (12, 55), (18, 30), (25, 10),
    ]) if ev is not None else None

    val_score = _blend([
        (pe_score, 0.50),
        (ev_score, 0.50),
    ])
    val_explanation = explain_relative_valuation(pe, ev)

    breakdown = {
        'dividend_yield': {
            'score': yield_score, 'weight': 0.20,
            'value': div_yield,
            'explanation': explain_dividend_yield(div_yield),
        },
        'fcf_yield': {
            'score': fcf_yield_score, 'weight': 0.20,
            'value': fcf_yield,
            'explanation': explain_fcf_yield(fcf_yield),
        },
        'roe': {
            'score': roe_score, 'weight': 0.15,
            'value': roe,
            'explanation': explain_roe(roe),
        },
        'eps_stability': {
            'score': stability_score, 'weight': 0.15,
            'value': vol_ratio,
            'explanation': stability_explanation,
        },
        'leverage_coverage': {
            'score': lev_score, 'weight': 0.15,
            'value': de,
            'explanation': lev_explanation,
        },
        'relative_valuation': {
            'score': val_score, 'weight': 0.15,
            'value': pe,
            'explanation': val_explanation,
        },
    }

    final_score = sum(v['score'] * v['weight'] for v in breakdown.values())
    return round(final_score, 1), breakdown


def score_dividend_growth(metrics: dict):
    """
    Dividend Growth portfolio scoring.
    Primary goal: income that grows faster than inflation year after year.

    Weights (Institutional v2):
      dividend_cagr        20%  — how fast is the dividend growing?
      eps_growth           20%  — earnings growth funds future dividend raises
      roe                  15%  — business quality drives long-term growth
      dividend_yield       15%  — starting income level (moderate is ideal)
      payout_ratio         15%  — low payout = more room to raise the dividend
      leverage_stability   15%  — composite: D/E + FCF coverage
    """
    is_reit = metrics.get('is_reit', False)  # used in payout_ratio block below

    # ── Dividend CAGR (20%) ──────────────────────────────────
    cagr = metrics.get('dividend_cagr_5y')
    cagr_score = normalise(cagr, [
        (0, 10), (3, 40), (5, 60), (8, 80), (12, 95), (20, 100),
    ])

    # ── EPS Growth (20%) ────────────────────────────────────
    # Compute CAGR from EPS history; fall back to revenue_cagr if unavailable.
    eps_5y = metrics.get('eps_5y', [])
    eps_3y = metrics.get('eps_3y', [])
    eps_history = eps_5y if len(eps_5y) >= 3 else eps_3y
    eps_growth = _eps_cagr(eps_history)

    # Volatility-adjust: penalise erratic growers (high vol_ratio = lower score)
    vol_ratio = _eps_vol_ratio(eps_history)
    if eps_growth is not None and vol_ratio is not None and vol_ratio > 0.5:
        eps_growth = eps_growth * (1.0 - min(vol_ratio - 0.5, 0.5))

    if eps_growth is None:
        # Fallback: revenue CAGR as proxy for earnings growth potential
        eps_growth = metrics.get('revenue_cagr')

    eps_growth_score = normalise(eps_growth, [
        (0, 10), (3, 30), (8, 60), (12, 80), (18, 95), (25, 100),
    ])

    # ── ROE (15%) ────────────────────────────────────────────
    roe = metrics.get('roe')
    roe_score = normalise(roe, [
        (5, 10), (10, 40), (15, 65), (20, 85), (25, 100),
    ])

    # ── Dividend Yield (15%) ─────────────────────────────────
    # Moderate starting yield is ideal — very high yield signals slow growth ahead
    div_yield = metrics.get('dividend_yield')
    yield_score = normalise(div_yield, [
        (1, 10), (2, 30), (3, 55), (5, 80), (7, 90), (9, 75), (12, 55),
    ])
    if div_yield and div_yield > 12:
        yield_score = 30   # very high yield = likely mature/slow growth stock

    # ── Payout Ratio (15%) — lower is better for future raises ──
    payout = metrics.get('payout_ratio')
    if payout is None:
        payout_score = 0
    elif is_reit and payout <= 100:
        payout_score = 65   # REITs must pay out high %; limited room to grow beyond income growth
    elif payout <= 25:
        payout_score = 100  # excellent room to raise the dividend
    elif payout <= 40:
        payout_score = 90   # great room
    elif payout <= 60:
        payout_score = 70   # good balance
    elif payout <= 75:
        payout_score = 50   # getting tight
    elif payout <= 85:
        payout_score = 25   # very little room
    else:
        payout_score = 10   # almost no room to raise the dividend further

    # ── Leverage & Stability Composite (15%) ────────────────
    de = metrics.get('de_ratio')
    fcf_cov = metrics.get('fcf_coverage')

    de_score = normalise(de, [
        (0.3, 100), (0.7, 80), (1.2, 60), (2.0, 35), (3.0, 10),
    ]) if de is not None else None

    fcf_cov_score = normalise(fcf_cov, [
        (0.5, 10), (1.0, 40), (1.5, 75), (2.0, 90), (3.0, 100),
    ]) if fcf_cov is not None else None

    lev_score = _blend([
        (de_score,      0.50),
        (fcf_cov_score, 0.50),
    ])

    breakdown = {
        'dividend_cagr': {
            'score': cagr_score, 'weight': 0.20,
            'value': cagr,
            'explanation': explain_dividend_cagr(cagr),
        },
        'eps_growth': {
            'score': eps_growth_score, 'weight': 0.20,
            'value': eps_growth,
            'explanation': explain_eps_growth(eps_growth),
        },
        'roe': {
            'score': roe_score, 'weight': 0.15,
            'value': roe,
            'explanation': explain_roe(roe),
        },
        'dividend_yield': {
            'score': yield_score, 'weight': 0.15,
            'value': div_yield,
            'explanation': explain_dividend_yield(div_yield),
        },
        'payout_ratio': {
            'score': payout_score, 'weight': 0.15,
            'value': payout,
            'explanation': explain_payout_ratio(payout, is_reit),
        },
        'leverage_stability': {
            'score': lev_score, 'weight': 0.15,
            'value': de,
            'explanation': explain_leverage_coverage(de, fcf_cov, None),
        },
    }

    final_score = sum(v['score'] * v['weight'] for v in breakdown.values())
    return round(final_score, 1), breakdown


def score_value(metrics: dict):
    """
    Value portfolio scoring.
    Primary goal: find underpriced businesses trading below intrinsic value.

    Weights (Institutional v2):
      valuation_composite  33%  — P/E + EV/EBITDA + FCF Yield (equal weight)
      quality_composite    33%  — ROE + EPS stability
      leverage_risk        17%  — D/E + interest coverage
      revenue_growth       17%  — growing businesses are better value
    """
    # ── Valuation Composite (33%) ────────────────────────────
    pe = metrics.get('pe')
    ev = metrics.get('ev_ebitda')
    fcf_yield = metrics.get('fcf_yield')

    pe_score = normalise(pe, [
        (8, 100), (12, 85), (18, 65), (28, 35), (40, 15),
    ]) if pe is not None else None

    ev_score = normalise(ev, [
        (5, 100), (8, 80), (12, 55), (18, 30), (25, 10),
    ]) if ev is not None else None

    fcf_y_score = normalise(fcf_yield, [
        (2, 15), (4, 40), (6, 65), (8, 85), (10, 100),
    ]) if fcf_yield is not None else None

    val_composite = _blend([
        (pe_score,   0.333),
        (ev_score,   0.333),
        (fcf_y_score, 0.334),
    ])
    val_explanation = explain_valuation_composite(pe, ev, fcf_yield)

    # ── Quality Composite (33%) ──────────────────────────────
    roe = metrics.get('roe')
    roe_score = normalise(roe, [
        (5, 10), (10, 40), (15, 65), (20, 85), (25, 100),
    ]) if roe is not None else None

    eps_5y = metrics.get('eps_5y', [])
    eps_3y = metrics.get('eps_3y', [])
    eps_history = eps_5y if len(eps_5y) >= 3 else eps_3y
    vol_ratio = _eps_vol_ratio(eps_history)
    net_income_3y = metrics.get('net_income_3y', [])

    if vol_ratio is not None:
        # Inverted: lower volatility = higher score
        stab_score = normalise(vol_ratio, [
            (0.2, 100), (0.4, 85), (0.6, 70), (0.8, 55), (1.0, 35), (1.5, 15),
        ])
    else:
        positive_years = sum(1 for n in net_income_3y if n and n > 0)
        stab_score = [0, 20, 60, 100][min(positive_years, 3)]

    quality_composite = _blend([
        (roe_score,  0.60),
        (stab_score, 0.40),
    ])
    positive_years_display = sum(1 for n in net_income_3y if n and n > 0)
    quality_explanation = explain_quality_composite(roe, positive_years_display)

    # ── Leverage & Financial Risk (17%) ─────────────────────
    de = metrics.get('de_ratio')
    interest_cov = metrics.get('interest_coverage')

    de_score = normalise(de, [
        (0.3, 100), (0.7, 80), (1.2, 55), (2.0, 30), (3.0, 10),
    ]) if de is not None else None

    int_cov_score = normalise(interest_cov, [
        (1.5, 10), (2.5, 35), (4.0, 60), (6.0, 80), (10.0, 100),
    ]) if interest_cov is not None else None

    lev_risk = _blend([
        (de_score,      0.60),
        (int_cov_score, 0.40),
    ])
    lev_explanation = explain_leverage_coverage(de, None, interest_cov)

    # ── Revenue Growth (17%) ─────────────────────────────────
    rev = metrics.get('revenue_cagr')
    rev_score = normalise(rev, [
        (0, 10), (3, 30), (5, 50), (10, 70), (15, 85), (20, 100),
    ])

    breakdown = {
        'valuation_composite': {
            'score': val_composite, 'weight': 0.33,
            'value': pe,
            'explanation': val_explanation,
        },
        'quality_composite': {
            'score': quality_composite, 'weight': 0.33,
            'value': roe,
            'explanation': quality_explanation,
        },
        'leverage_risk': {
            'score': lev_risk, 'weight': 0.17,
            'value': de,
            'explanation': lev_explanation,
        },
        'revenue_growth': {
            'score': rev_score, 'weight': 0.17,
            'value': rev,
            'explanation': explain_revenue_cagr(rev),
        },
    }

    final_score = sum(v['score'] * v['weight'] for v in breakdown.values())
    return round(final_score, 1), breakdown
