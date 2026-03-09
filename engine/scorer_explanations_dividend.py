# ============================================================
# scorer_explanations_dividend.py — Dividend-focused explanations
# PSE Quant SaaS — engine sub-module
# ============================================================
# Plain-English explanations for dividend portfolio factors:
#   yield, CAGR, payout, FCF coverage, EPS stability,
#   FCF yield, dividend stability.
# ============================================================


def explain_dividend_yield(value):
    if value is None:
        return "No dividend yield data available."
    if value > 12:
        return (
            f"Yield of {value:.1f}% is very high -- this may signal "
            f"financial stress or an unsustainable payout. "
            f"We apply a caution penalty for yields above 12%."
        )
    elif value >= 9:
        return (
            f"Yield of {value:.1f}% is exceptional. For every PHP100 "
            f"invested, you receive PHP{value:.2f} per year in cash. "
            f"This is among the best income yields on the PSE."
        )
    elif value >= 7:
        return (
            f"Yield of {value:.1f}% is very strong. For every PHP100 "
            f"invested, you receive PHP{value:.2f} per year in cash. "
            f"Well above the PSE average."
        )
    elif value >= 5:
        return (
            f"Yield of {value:.1f}% is solid for an income stock. "
            f"For every PHP100 invested, you receive PHP{value:.2f} per year. "
            f"Meets the threshold for a meaningful dividend portfolio."
        )
    elif value >= 3:
        return (
            f"Yield of {value:.1f}% is moderate. For every PHP100 "
            f"invested, you receive only PHP{value:.2f} per year. "
            f"This stock is not primarily an income play."
        )
    else:
        return (
            f"Yield of {value:.1f}% is low for a dividend portfolio. "
            f"For every PHP100 invested, you receive only PHP{value:.2f} "
            f"per year -- barely above a savings account."
        )


def explain_dividend_cagr(value):
    if value is None:
        return "No dividend growth history available."
    if value >= 10:
        return (
            f"Dividend grew at {value:.1f}% per year over 5 years -- "
            f"excellent. At this rate, the dividend doubles roughly "
            f"every {round(72/value, 1)} years, well ahead of inflation."
        )
    elif value >= 5:
        return (
            f"Dividend grew at {value:.1f}% per year over 5 years -- "
            f"solid. The company is consistently rewarding shareholders "
            f"with more cash over time."
        )
    elif value >= 0:
        return (
            f"Dividend grew at only {value:.1f}% per year over 5 years. "
            f"Growth is positive but slow -- barely keeping pace "
            f"with inflation."
        )
    else:
        return (
            f"Dividend SHRANK at {abs(value):.1f}% per year over 5 years. "
            f"A declining dividend is a red flag -- the company may be "
            f"under financial pressure."
        )


def explain_payout_ratio(value, is_reit=False):
    if value is None:
        return "No payout ratio data available."
    if is_reit:
        return (
            f"Payout ratio of {value:.1f}%. REITs are required by law "
            f"to distribute at least 90% of income -- so this is "
            f"expected and normal for this type of company."
        )
    if value <= 30:
        return (
            f"Payout ratio of {value:.1f}% -- very conservative. "
            f"The company retains most of its profits. "
            f"The dividend is very safe and has significant room to grow."
        )
    elif value <= 70:
        return (
            f"Payout ratio of {value:.1f}% -- healthy sweet spot. "
            f"The company pays out a fair share while retaining "
            f"enough profit to grow the business and raise the dividend."
        )
    elif value <= 85:
        return (
            f"Payout ratio of {value:.1f}% -- stretched. "
            f"The company is paying out most of its earnings. "
            f"Any dip in profit could put future dividend increases at risk."
        )
    else:
        return (
            f"Payout ratio of {value:.1f}% -- danger zone. "
            f"The company is paying out nearly all its earnings as "
            f"dividends. One bad quarter could force a cut."
        )


def explain_fcf_coverage(value):
    if value is None:
        return "No free cash flow coverage data available."
    if value >= 2.0:
        return (
            f"FCF coverage of {value:.2f}x -- excellent. "
            f"The company generates {value:.1f}x more real cash "
            f"than it pays in dividends. The dividend is very secure."
        )
    elif value >= 1.5:
        return (
            f"FCF coverage of {value:.2f}x -- good. "
            f"The company has a healthy cushion of real cash "
            f"above what it needs to pay dividends."
        )
    elif value >= 1.0:
        return (
            f"FCF coverage of {value:.2f}x -- adequate but thin. "
            f"The company can afford the dividend but has little "
            f"margin for error if cash flow drops."
        )
    else:
        return (
            f"FCF coverage of {value:.2f}x -- warning. "
            f"The company does NOT generate enough real cash to "
            f"fully cover its dividend. The dividend may not be "
            f"sustainable long-term."
        )


def explain_eps_stability(net_income_3y, eps_vol_ratio=None):
    if eps_vol_ratio is not None:
        if eps_vol_ratio <= 0.3:
            return (
                f"EPS volatility ratio of {eps_vol_ratio:.2f} -- very stable earnings. "
                f"Consistent profits are the foundation of a reliable dividend."
            )
        elif eps_vol_ratio <= 0.6:
            return (
                f"EPS volatility ratio of {eps_vol_ratio:.2f} -- reasonably stable. "
                f"Some earnings variation, but not enough to threaten the dividend."
            )
        elif eps_vol_ratio <= 1.0:
            return (
                f"EPS volatility ratio of {eps_vol_ratio:.2f} -- moderate volatility. "
                f"Earnings fluctuate noticeably. Monitor for trend deterioration."
            )
        else:
            return (
                f"EPS volatility ratio of {eps_vol_ratio:.2f} -- highly erratic earnings. "
                f"Unreliable profits make the dividend unpredictable."
            )

    if not net_income_3y:
        return "No earnings history available."
    positive = sum(1 for n in net_income_3y if n > 0)
    if positive == 3:
        return (
            f"Profitable in all 3 of the last 3 years -- excellent. "
            f"Consistent profitability is the foundation of a "
            f"reliable dividend."
        )
    elif positive == 2:
        return (
            f"Profitable in 2 of the last 3 years. "
            f"One year of losses is a yellow flag -- worth monitoring "
            f"to see if the trend improves."
        )
    elif positive == 1:
        return (
            f"Only profitable in 1 of the last 3 years -- concerning. "
            f"Inconsistent earnings make the dividend unreliable."
        )
    else:
        return (
            f"Not profitable in any of the last 3 years -- "
            f"this stock should not be in a dividend portfolio."
        )


def explain_fcf_yield(value):
    if value is None:
        return "No FCF yield data available."
    if value >= 10:
        return (
            f"FCF yield of {value:.1f}% -- exceptional cash generation. "
            f"For every PHP100 of market cap, the company generates "
            f"PHP{value:.1f} in real free cash. Very efficient business."
        )
    elif value >= 7:
        return (
            f"FCF yield of {value:.1f}% -- strong. "
            f"The company converts a high percentage of its market "
            f"value into real cash each year."
        )
    elif value >= 4:
        return (
            f"FCF yield of {value:.1f}% -- moderate. "
            f"Decent cash generation relative to market cap."
        )
    else:
        return (
            f"FCF yield of {value:.1f}% -- low. "
            f"The company generates relatively little free cash "
            f"compared to what the market values it at."
        )


def explain_dividend_stability(cv):
    if cv is None:
        return "Not enough dividend history to assess payment stability."
    if cv <= 0.10:
        return (
            f"Dividend stability: excellent (CV {cv:.2f}). "
            f"Dividend payments have been remarkably consistent year to year. "
            f"A predictable income stream is the core promise of an income stock."
        )
    elif cv <= 0.20:
        return (
            f"Dividend stability: good (CV {cv:.2f}). "
            f"Dividend payments have been relatively steady with only minor variation. "
            f"Shareholders can plan around this income with reasonable confidence."
        )
    elif cv <= 0.35:
        return (
            f"Dividend stability: moderate (CV {cv:.2f}). "
            f"Dividend payments show some variation between years. "
            f"The company pays consistently but the amount fluctuates noticeably."
        )
    elif cv <= 0.50:
        return (
            f"Dividend stability: below average (CV {cv:.2f}). "
            f"Dividend payments are uneven. Income investors should be cautious -- "
            f"a variable dividend makes financial planning difficult."
        )
    else:
        return (
            f"Dividend stability: poor (CV {cv:.2f}). "
            f"Dividend payments are highly erratic. The company has cut or varied "
            f"its dividend significantly, making it unreliable as an income source."
        )
