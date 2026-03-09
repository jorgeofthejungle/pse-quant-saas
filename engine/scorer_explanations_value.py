# ============================================================
# scorer_explanations_value.py — Value/quality explanations
# PSE Quant SaaS — engine sub-module
# ============================================================
# Plain-English explanations for value and shared quality factors:
#   ROE, EPS growth, P/E, P/B, EV/EBITDA, revenue CAGR, D/E,
#   leverage, valuation composite, quality composite,
#   cash flow quality, earnings yield spread, growth consistency.
# ============================================================


def explain_roe(value):
    if value is None:
        return "No ROE data available."
    if value >= 20:
        return (
            f"ROE of {value:.1f}% -- excellent management performance. "
            f"For every PHP100 of equity, the company earns PHP{value:.0f}. "
            f"Warren Buffett looks for ROE above 15% consistently."
        )
    elif value >= 15:
        return (
            f"ROE of {value:.1f}% -- strong. "
            f"Management is deploying capital efficiently. "
            f"Above the 15% threshold that signals a quality business."
        )
    elif value >= 10:
        return (
            f"ROE of {value:.1f}% -- moderate. "
            f"Management is generating acceptable but not outstanding "
            f"returns on shareholder equity."
        )
    elif value >= 5:
        return (
            f"ROE of {value:.1f}% -- below average. "
            f"Management is not generating strong returns. "
            f"A PSE index fund would likely outperform this."
        )
    else:
        return (
            f"ROE of {value:.1f}% -- poor capital allocation. "
            f"The business is barely earning anything on your money."
        )


def explain_eps_growth(value):
    if value is None:
        return "No EPS growth trend data available."
    if value >= 15:
        return (
            f"EPS growing at {value:.1f}% per year -- excellent. "
            f"Strong earnings growth is the engine that drives future dividend increases."
        )
    elif value >= 8:
        return (
            f"EPS growing at {value:.1f}% per year -- solid. "
            f"Consistent earnings growth supports sustained dividend raises."
        )
    elif value >= 3:
        return (
            f"EPS growing at {value:.1f}% per year -- modest. "
            f"Earnings are expanding but slowly. Dividend growth may "
            f"be limited to inflation-matching levels."
        )
    elif value >= 0:
        return (
            f"EPS growth of {value:.1f}% per year -- flat. "
            f"Stagnant earnings leave little room to grow the dividend meaningfully."
        )
    else:
        return (
            f"EPS DECLINING at {abs(value):.1f}% per year -- concerning. "
            f"Shrinking earnings make it difficult to maintain, let alone grow, the dividend."
        )


def explain_pe(value):
    if value is None:
        return "No P/E ratio data available."
    if value <= 8:
        return (
            f"P/E of {value:.1f}x -- deeply undervalued. "
            f"You are paying only PHP{value:.1f} for every PHP1 of annual "
            f"earnings. This is very cheap by any standard."
        )
    elif value <= 12:
        return (
            f"P/E of {value:.1f}x -- attractively valued. "
            f"You are paying PHP{value:.1f} for every PHP1 of annual "
            f"earnings. Below the PSE market average."
        )
    elif value <= 18:
        return (
            f"P/E of {value:.1f}x -- fairly valued. "
            f"You pay PHP{value:.1f} for every PHP1 of annual earnings. "
            f"Around the PSE market average."
        )
    elif value <= 28:
        return (
            f"P/E of {value:.1f}x -- moderately expensive. "
            f"You pay PHP{value:.1f} for every PHP1 of annual earnings. "
            f"Above average -- the stock needs strong growth to justify this."
        )
    else:
        return (
            f"P/E of {value:.1f}x -- expensive. "
            f"You pay PHP{value:.1f} for every PHP1 of annual earnings. "
            f"High P/E stocks carry more risk if growth disappoints."
        )


def explain_pb(value):
    if value is None:
        return "No P/B ratio data available."
    if value <= 0.8:
        return (
            f"P/B of {value:.2f}x -- trading below book value. "
            f"You are buying PHP1 of company assets for only "
            f"PHP{value:.2f}. Significant asset discount."
        )
    elif value <= 1.2:
        return (
            f"P/B of {value:.2f}x -- trading near book value. "
            f"The price is close to what the company actually owns. "
            f"Fair to slightly attractive."
        )
    elif value <= 2.0:
        return (
            f"P/B of {value:.2f}x -- modest premium to book value. "
            f"The market values the company above its assets, "
            f"likely due to brand or earnings power."
        )
    else:
        return (
            f"P/B of {value:.2f}x -- significant premium to book value. "
            f"The stock price is well above the company's net assets. "
            f"Justified only if earnings are consistently strong."
        )


def explain_ev_ebitda(value):
    if value is None:
        return "No EV/EBITDA data available."
    if value <= 5:
        return (
            f"EV/EBITDA of {value:.1f}x -- very cheap. "
            f"The entire business (including debt) costs only "
            f"{value:.1f}x its annual operating profit."
        )
    elif value <= 8:
        return (
            f"EV/EBITDA of {value:.1f}x -- attractive. "
            f"Below 8x is generally considered good value "
            f"in the Philippine market."
        )
    elif value <= 12:
        return (
            f"EV/EBITDA of {value:.1f}x -- fair. "
            f"Around the market average. Not cheap but not expensive."
        )
    else:
        return (
            f"EV/EBITDA of {value:.1f}x -- expensive. "
            f"Above 12x suggests the market is pricing in "
            f"significant future growth."
        )


def explain_revenue_cagr(value):
    if value is None:
        return "No revenue growth data available."
    if value >= 15:
        return (
            f"Revenue growing at {value:.1f}% per year -- exceptional. "
            f"At this rate revenues double roughly every "
            f"{round(72/value, 1)} years."
        )
    elif value >= 10:
        return (
            f"Revenue growing at {value:.1f}% per year -- strong. "
            f"The business is expanding meaningfully and increasing "
            f"future earnings potential."
        )
    elif value >= 5:
        return (
            f"Revenue growing at {value:.1f}% per year -- moderate. "
            f"Steady growth, roughly in line with a healthy economy."
        )
    elif value >= 0:
        return (
            f"Revenue growing at only {value:.1f}% per year -- slow. "
            f"The business is barely expanding. "
            f"Limited upside from revenue growth."
        )
    else:
        return (
            f"Revenue SHRINKING at {abs(value):.1f}% per year -- "
            f"concerning. A declining top line threatens future "
            f"earnings and dividends."
        )


def explain_de_ratio(value):
    if value is None:
        return "No debt data available."
    if value <= 0.3:
        return (
            f"Debt/Equity of {value:.2f}x -- very low debt. "
            f"The company is largely self-funded and highly resilient "
            f"to economic downturns."
        )
    elif value <= 0.7:
        return (
            f"Debt/Equity of {value:.2f}x -- manageable debt. "
            f"The company uses modest leverage without taking "
            f"excessive financial risk."
        )
    elif value <= 1.2:
        return (
            f"Debt/Equity of {value:.2f}x -- moderate debt. "
            f"The company carries meaningful debt. "
            f"Monitor if interest rates rise."
        )
    elif value <= 2.0:
        return (
            f"Debt/Equity of {value:.2f}x -- elevated debt. "
            f"High leverage increases financial risk. "
            f"A revenue decline could strain debt repayments."
        )
    else:
        return (
            f"Debt/Equity of {value:.2f}x -- high debt. "
            f"This level of leverage is a significant risk factor. "
            f"The company must generate strong cash flow to service it."
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


def explain_valuation_composite(pe, ev_ebitda, fcf_yield, ey_spread=None):
    parts = []
    if pe is not None:
        parts.append(f"P/E {pe:.1f}x")
    if ev_ebitda is not None:
        parts.append(f"EV/EBITDA {ev_ebitda:.1f}x")
    if fcf_yield is not None:
        parts.append(f"FCF yield {fcf_yield:.1f}%")
    if ey_spread is not None:
        parts.append(f"earnings yield spread {ey_spread:+.1f}% vs bonds")
    if not parts:
        return "No valuation data available for composite scoring."
    return (
        f"Composite valuation using {', '.join(parts)}. "
        f"Lower multiples, higher FCF yield, and a positive earnings yield "
        f"spread over the risk-free rate all signal a stock trading "
        f"below its intrinsic worth."
    )


def explain_quality_composite(roe, positive_years, total_years=3, cf_quality=None, div_stability_cv=None):
    roe_str = f"ROE {roe:.1f}%" if roe is not None else "ROE unavailable"
    cf_str  = f", cash flow quality {cf_quality:.2f}x" if cf_quality is not None else ""
    div_str = f", dividend stability CV {div_stability_cv:.2f}" if div_stability_cv is not None else ""
    return (
        f"Quality composite: {roe_str}{cf_str}{div_str}, profitable {positive_years}/{total_years} years. "
        f"High ROE, earnings backed by real cash, and consistent profitability "
        f"are the hallmarks of a durable, compounding business."
    )


def explain_cash_flow_quality(cf_ratio):
    if cf_ratio is None:
        return "No cash flow quality data available."
    if cf_ratio >= 1.3:
        return (
            f"Cash flow quality of {cf_ratio:.2f}x -- excellent. "
            f"For every PHP1 of reported profit, the company collects "
            f"PHP{cf_ratio:.2f} in actual cash. Earnings are real and reliable."
        )
    elif cf_ratio >= 1.0:
        return (
            f"Cash flow quality of {cf_ratio:.2f}x -- good. "
            f"Reported earnings are broadly backed by real operating cash. "
            f"The business is converting profit into cash effectively."
        )
    elif cf_ratio >= 0.7:
        return (
            f"Cash flow quality of {cf_ratio:.2f}x -- moderate. "
            f"Only about {cf_ratio*100:.0f}% of reported earnings are converted "
            f"into real cash. Some gap between accounting profit and cash reality."
        )
    elif cf_ratio >= 0.5:
        return (
            f"Cash flow quality of {cf_ratio:.2f}x -- below average. "
            f"Reported earnings are significantly higher than actual cash collected. "
            f"Watch for working capital issues or accounting adjustments."
        )
    else:
        return (
            f"Cash flow quality of {cf_ratio:.2f}x -- poor. "
            f"The company reports profits but generates little real cash. "
            f"This gap between earnings and cash is a red flag worth investigating."
        )


def explain_earnings_yield_spread(ey, bond_rate, spread):
    if ey is None or spread is None:
        return "No earnings yield data available for bond comparison."
    bond_pct = bond_rate * 100
    if spread >= 8:
        return (
            f"Earnings yield of {ey:.1f}% is {spread:.1f}% above the PH 10Y bond rate "
            f"of {bond_pct:.1f}%. You are being compensated very well for the extra "
            f"risk of owning this stock over a government bond."
        )
    elif spread >= 5:
        return (
            f"Earnings yield of {ey:.1f}% is {spread:.1f}% above the PH 10Y bond rate "
            f"of {bond_pct:.1f}%. A solid risk premium -- the stock earnings "
            f"meaningfully beat what a risk-free bond would pay."
        )
    elif spread >= 2:
        return (
            f"Earnings yield of {ey:.1f}% is {spread:.1f}% above the PH 10Y bond rate "
            f"of {bond_pct:.1f}%. A modest risk premium. "
            f"The stock earns more than bonds, but not by a wide margin."
        )
    elif spread >= 0:
        return (
            f"Earnings yield of {ey:.1f}% barely exceeds the PH 10Y bond rate "
            f"of {bond_pct:.1f}% (spread: {spread:.1f}%). "
            f"At this price, you are taking equity risk for very little extra reward."
        )
    else:
        return (
            f"Earnings yield of {ey:.1f}% is BELOW the PH 10Y bond rate of {bond_pct:.1f}% "
            f"(spread: {spread:.1f}%). A risk-free government bond currently pays more "
            f"than this stock earns per peso of price. The stock appears overvalued."
        )


def explain_growth_consistency(cv):
    if cv is None:
        return "Not enough revenue history to assess growth consistency."
    if cv <= 0.10:
        return (
            f"Growth consistency score: excellent (CV {cv:.2f}). "
            f"Revenue has grown in a remarkably steady, predictable pattern. "
            f"Consistent growth is far more valuable than boom-bust cycles."
        )
    elif cv <= 0.20:
        return (
            f"Growth consistency score: good (CV {cv:.2f}). "
            f"Revenue growth has been relatively stable with only minor variation "
            f"year to year. A reliable upward trend."
        )
    elif cv <= 0.35:
        return (
            f"Growth consistency score: moderate (CV {cv:.2f}). "
            f"Revenue growth shows noticeable variation between years. "
            f"The business cycles through good and less-good periods."
        )
    elif cv <= 0.50:
        return (
            f"Growth consistency score: below average (CV {cv:.2f}). "
            f"Revenue growth is uneven. Strong years are offset by weak ones, "
            f"making future growth hard to predict with confidence."
        )
    else:
        return (
            f"Growth consistency score: poor (CV {cv:.2f}). "
            f"Revenue is highly erratic. The business lacks a stable growth "
            f"trajectory, which increases forecasting risk significantly."
        )
