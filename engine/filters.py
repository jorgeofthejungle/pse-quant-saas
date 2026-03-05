# ============================================================
# filters.py — Portfolio Eligibility Filters
# PSE Quant SaaS — Phase 1 (Institutional v2)
# ============================================================
#
# Three portfolio strategies:
#
#   Pure Dividend   — highest current income, stable high-yield payers
#   Dividend Growth — growing income, dividends that rise year after year
#   Value           — underpriced businesses, no dividend requirement
#
# Key improvements in Institutional v2:
#   - 3-Year Normalized EPS replaces single-year NI check
#   - FCF-based payout replaces EPS-based payout ratio
#   - Interest coverage filter (graceful: skipped if data absent)
#   - Liquidity filter (graceful: skipped if data absent)
#   - EPS Volatility Ratio for Dividend Growth (graceful)
#   - Revenue consistency for Dividend Growth (graceful)
#
# New optional stock dict fields (pass None if unavailable):
#   'interest_coverage'  : float  — EBIT / Interest Expense
#   'avg_daily_value_6m' : float  — 6M avg daily value in PHP millions
#   'eps_5y'             : list   — 5 years of EPS, newest first
#   'revenue_5y'         : list   — 5 years of revenue in M PHP, newest first
# ============================================================

import statistics


def filter_pure_dividend_portfolio(stock: dict):
    """
    Pure Dividend: maximum current income from dividends.

    Requires:
    - 3Y Normalized EPS positive (average of last 3 years > 0)
    - Dividend paid at least 4 of the last 5 years
    - Current yield >= 3%
    - FCF/Dividend payout <= 85% non-REIT, <= 100% REIT
      (falls back to EPS payout ratio if FCF coverage unavailable)
    - Interest Coverage >= 3.0x  [skipped if data unavailable]
    - Avg Daily Traded Value >= PHP 5M  [skipped if data unavailable]
    - Debt/Equity <= 2.0x (non-bank) or <= 8.0x (bank)
    """
    ticker  = stock.get('ticker', 'UNKNOWN')
    is_reit = stock.get('is_reit', False)
    is_bank = stock.get('is_bank', False)

    # ── 3Y Normalized EPS must be positive ───────────────────
    # Uses average of last 3 years to smooth out one-off items.
    eps_3y = stock.get('eps_3y', [])
    if eps_3y and len(eps_3y) >= 3:
        valid_eps = [e for e in eps_3y[:3] if e is not None]
        if valid_eps:
            norm_eps = sum(valid_eps) / len(valid_eps)
            if norm_eps <= 0:
                return False, (
                    f"{ticker}: 3-year normalized EPS of {norm_eps:.2f} is negative "
                    f"— the company does not have consistent earnings to fund a dividend"
                )
        else:
            return False, f"{ticker}: No valid EPS data in the last 3 years"
    else:
        # Fallback: net income check if EPS not available
        net_income_3y = stock.get('net_income_3y', [])
        if len(net_income_3y) < 3:
            return False, f"{ticker}: Not enough earnings history (need 3 years)"
        if not all(n > 0 for n in net_income_3y[:3]):
            return False, f"{ticker}: Did not have positive net income for 3 consecutive years"

    # ── Must pay dividends consistently — 4 of last 5 years ──
    dividends_5y = stock.get('dividends_5y', [])
    paid_count = sum(1 for d in dividends_5y if d and d > 0)
    if paid_count < 4:
        return False, (
            f"{ticker}: Paid dividends only {paid_count}/5 years "
            f"(Pure Dividend requires at least 4/5)"
        )

    # ── Must offer meaningful income — minimum 3% yield ──────
    dividend_yield = stock.get('dividend_yield', None)
    if dividend_yield is None or dividend_yield < 3.0:
        y = f"{dividend_yield:.1f}%" if dividend_yield is not None else "N/A"
        return False, (
            f"{ticker}: Yield of {y} is too low for Pure Dividend portfolio (min 3%)"
        )

    # ── Payout sustainability ─────────────────────────────────
    # REITs use distributable income (net income + depreciation add-backs),
    # not FCF, as their payout base. FCF systematically understates REIT
    # distributable capacity, so we skip the FCF check for REITs entirely
    # and use the EPS payout ratio instead.
    # Non-REITs: FCF-based check (dividend/FCF <= 85%), EPS payout fallback.
    fcf_cov = stock.get('fcf_coverage')
    payout  = stock.get('payout_ratio')

    if is_reit:
        # REIT: EPS payout ratio must be <= 100%
        if payout is not None and payout > 100:
            return False, (
                f"{ticker}: Payout ratio {payout:.1f}% exceeds 100% — "
                f"dividend exceeds earnings even for a REIT"
            )
    else:
        if fcf_cov is not None:
            if fcf_cov > 0 and fcf_cov < 1.176:
                div_pct = round(100 / fcf_cov, 1)
                return False, (
                    f"{ticker}: Dividend/FCF of {div_pct:.1f}% exceeds 85% limit "
                    f"— the dividend is consuming too much of the company's real cash"
                )
        elif payout is not None:
            if payout > 90:
                return False, (
                    f"{ticker}: Payout ratio {payout:.1f}% exceeds 90% — "
                    f"unsustainable dividend (FCF data unavailable, using EPS payout)"
                )

    # ── Interest Coverage >= 3.0x ─────────────────────────────
    # Skipped gracefully if interest_coverage data is not yet available.
    interest_cov = stock.get('interest_coverage')
    if interest_cov is not None and interest_cov < 3.0:
        return False, (
            f"{ticker}: Interest coverage of {interest_cov:.1f}x is below the "
            f"minimum 3.0x — debt obligations may strain dividend capacity"
        )

    # ── Liquidity: Avg Daily Value >= PHP 5M ─────────────────
    # Skipped gracefully if liquidity data is not yet available.
    adv = stock.get('avg_daily_value_6m')
    if adv is not None and adv < 5.0:
        return False, (
            f"{ticker}: 6M avg daily traded value of ₱{adv:.1f}M is below "
            f"the minimum ₱5M — too illiquid for reliable position sizing"
        )

    # ── Leverage check ────────────────────────────────────────
    de_ratio = stock.get('de_ratio', None)
    if de_ratio is not None:
        if is_bank:
            if de_ratio > 8.0:
                return False, (
                    f"{ticker}: Debt/Equity {de_ratio:.1f}x too high even for a bank (max 8.0x)"
                )
        else:
            if de_ratio > 2.0:
                return False, (
                    f"{ticker}: Debt/Equity {de_ratio:.1f}x is too high (max 2.0x)"
                )

    return True, f"{ticker}: Passed all Pure Dividend Portfolio filters"


def filter_dividend_growth_portfolio(stock: dict):
    """
    Dividend Growth: income that grows faster than inflation.

    Requires:
    - Revenue positive in 4 of last 5 years  [falls back to 3Y NI if revenue_5y unavailable]
    - Dividend paid at least 3 of last 5 years
    - Dividend CAGR > 0% (dividend must actually be growing)
    - FCF/Dividend payout <= 75% non-REIT, <= 100% REIT
      (falls back to EPS payout ratio if FCF coverage unavailable)
    - EPS Volatility Ratio <= 1.0  [skipped if insufficient EPS history]
    - Interest Coverage >= 4.0x  [skipped if data unavailable]
    - Avg Daily Traded Value >= PHP 5M  [skipped if data unavailable]
    - Debt/Equity <= 2.0x (non-bank) or <= 8.0x (bank)
    """
    ticker  = stock.get('ticker', 'UNKNOWN')
    is_reit = stock.get('is_reit', False)
    is_bank = stock.get('is_bank', False)

    # ── REITs belong in Pure Dividend only ───────────────────
    if is_reit:
        return False, (
            f"{ticker}: REITs are excluded from the Dividend Growth Portfolio — "
            f"use Pure Dividend portfolio instead"
        )

    # ── Revenue positive 4 of last 5 years ───────────────────
    # Confirms consistent business growth, not just one good year.
    revenue_5y = stock.get('revenue_5y', [])
    if revenue_5y and len(revenue_5y) >= 5:
        positive_rev = sum(1 for r in revenue_5y[:5] if r is not None and r > 0)
        if positive_rev < 4:
            return False, (
                f"{ticker}: Revenue positive in only {positive_rev}/5 years "
                f"— needs consistent top-line growth to sustain dividend increases"
            )
    else:
        # Fallback: 3Y net income check when revenue_5y not yet available
        net_income_3y = stock.get('net_income_3y', [])
        if len(net_income_3y) < 3:
            return False, f"{ticker}: Not enough earnings history (need 3 years)"
        if not all(n > 0 for n in net_income_3y[:3]):
            return False, f"{ticker}: Did not maintain positive net income for 3 consecutive years"

    # ── Needs at least 3 years of dividend history ───────────
    dividends_5y = stock.get('dividends_5y', [])
    paid_count = sum(1 for d in dividends_5y if d and d > 0)
    if paid_count < 3:
        return False, (
            f"{ticker}: Only {paid_count}/5 years of dividend history — "
            f"insufficient to assess dividend growth (need at least 3)"
        )

    # ── The dividend must actually be growing ─────────────────
    dividend_cagr = stock.get('dividend_cagr_5y', None)
    if dividend_cagr is None:
        return False, f"{ticker}: No dividend CAGR data — cannot assess dividend growth"
    if dividend_cagr <= 0:
        return False, (
            f"{ticker}: Dividend CAGR of {dividend_cagr:.1f}%/yr — "
            f"dividend is flat or shrinking, not growing"
        )

    # ── Payout — room to raise the dividend ──────────────────
    # REITs: skip FCF check (distributable income ≠ FCF); use EPS payout <= 95%.
    # Non-REITs: FCF-based check (dividend/FCF <= 75%), EPS payout fallback.
    fcf_cov = stock.get('fcf_coverage')
    payout  = stock.get('payout_ratio')

    if is_reit:
        # REIT: payout ratio <= 95% (leave slight headroom for growth)
        if payout is not None and payout > 95:
            return False, (
                f"{ticker}: Payout ratio {payout:.1f}% leaves no room to raise "
                f"the dividend (max 95% for REITs)"
            )
    else:
        if fcf_cov is not None:
            if fcf_cov > 0 and fcf_cov < 1.333:
                div_pct = round(100 / fcf_cov, 1)
                return False, (
                    f"{ticker}: Dividend/FCF of {div_pct:.1f}% exceeds 75% — "
                    f"not enough cash headroom to sustain dividend growth"
                )
        elif payout is not None:
            if payout > 75:
                return False, (
                    f"{ticker}: Payout ratio {payout:.1f}% leaves little room to raise "
                    f"the dividend (max 75% for non-REITs)"
                )

    # ── EPS Volatility Ratio <= 1.0 ──────────────────────────
    # Erratic earnings cannot reliably fund dividend growth.
    # Volatility Ratio = StdDev(EPS) / Mean(EPS); <= 1.0 is stable.
    # Skipped if insufficient EPS history.
    eps_5y = stock.get('eps_5y', [])
    eps_3y = stock.get('eps_3y', [])
    eps_history = eps_5y if len(eps_5y) >= 4 else eps_3y
    if len(eps_history) >= 3:
        valid_eps = [e for e in eps_history if e is not None]
        if len(valid_eps) >= 3:
            mean_eps = sum(valid_eps) / len(valid_eps)
            if mean_eps > 0:
                stdev_eps = statistics.pstdev(valid_eps)
                eps_vol_ratio = stdev_eps / mean_eps
                if eps_vol_ratio > 1.0:
                    return False, (
                        f"{ticker}: EPS volatility ratio of {eps_vol_ratio:.2f} exceeds 1.0 "
                        f"— earnings are too erratic to sustain consistent dividend growth"
                    )

    # ── Interest Coverage >= 4.0x ─────────────────────────────
    interest_cov = stock.get('interest_coverage')
    if interest_cov is not None and interest_cov < 4.0:
        return False, (
            f"{ticker}: Interest coverage of {interest_cov:.1f}x is below the "
            f"minimum 4.0x — high debt service costs constrain dividend growth capacity"
        )

    # ── Liquidity: Avg Daily Value >= PHP 5M ─────────────────
    adv = stock.get('avg_daily_value_6m')
    if adv is not None and adv < 5.0:
        return False, (
            f"{ticker}: 6M avg daily traded value of ₱{adv:.1f}M is below "
            f"the minimum ₱5M — too illiquid for reliable position sizing"
        )

    # ── Leverage check ────────────────────────────────────────
    de_ratio = stock.get('de_ratio', None)
    if de_ratio is not None:
        if is_bank:
            if de_ratio > 8.0:
                return False, (
                    f"{ticker}: Debt/Equity {de_ratio:.1f}x too high even for a bank (max 8.0x)"
                )
        else:
            if de_ratio > 2.0:
                return False, (
                    f"{ticker}: Debt/Equity {de_ratio:.1f}x is too high (max 2.0x)"
                )

    return True, f"{ticker}: Passed all Dividend Growth Portfolio filters"


def filter_value_portfolio(stock: dict):
    """
    Value: underpriced businesses trading below intrinsic value.
    No dividend requirement — focuses on earnings and cash flow quality.

    Requires:
    - 3Y Normalized EPS positive (average of last 3 years > 0)
    - Positive operating cash flow
    - Interest Coverage >= 2.5x  [skipped if data unavailable]
    - Avg Daily Traded Value >= PHP 5M  [skipped if data unavailable]
    - Debt/Equity <= 2.5x (non-bank) or <= 10.0x (bank)
    """
    ticker  = stock.get('ticker', 'UNKNOWN')
    is_reit = stock.get('is_reit', False)
    is_bank = stock.get('is_bank', False)

    # ── REITs belong in dividend portfolios only ──────────────
    if is_reit:
        return False, (
            f"{ticker}: REITs are excluded from the Value Portfolio — "
            f"use Pure Dividend or Dividend Growth portfolios instead"
        )

    # ── 3Y Normalized EPS must be positive ───────────────────
    eps_3y = stock.get('eps_3y', [])
    if eps_3y and len(eps_3y) >= 1:
        valid_eps = [e for e in eps_3y[:3] if e is not None]
        if valid_eps:
            norm_eps = sum(valid_eps) / len(valid_eps)
            if norm_eps <= 0:
                return False, (
                    f"{ticker}: 3-year normalized EPS of {norm_eps:.2f} is negative "
                    f"— company is not consistently profitable"
                )
        else:
            return False, f"{ticker}: No valid EPS data available"
    else:
        # Fallback: most recent net income check
        net_income_3y = stock.get('net_income_3y', [])
        if not net_income_3y:
            return False, f"{ticker}: No net income data available"
        if net_income_3y[0] <= 0:
            return False, f"{ticker}: Most recent net income is negative — company is loss-making"

    # ── Operating cash flow must be positive ─────────────────
    operating_cf = stock.get('operating_cf', None)
    if operating_cf is None:
        return False, f"{ticker}: No operating cash flow data available"
    if operating_cf <= 0:
        return False, f"{ticker}: Negative operating cash flow — earnings may not be real"

    # ── Interest Coverage >= 2.5x ─────────────────────────────
    interest_cov = stock.get('interest_coverage')
    if interest_cov is not None and interest_cov < 2.5:
        return False, (
            f"{ticker}: Interest coverage of {interest_cov:.1f}x is below the "
            f"minimum 2.5x — debt burden poses a financial risk"
        )

    # ── Liquidity: Avg Daily Value >= PHP 5M ─────────────────
    adv = stock.get('avg_daily_value_6m')
    if adv is not None and adv < 5.0:
        return False, (
            f"{ticker}: 6M avg daily traded value of ₱{adv:.1f}M is below "
            f"the minimum ₱5M — too illiquid for reliable position sizing"
        )

    # ── Leverage check ────────────────────────────────────────
    de_ratio = stock.get('de_ratio', None)
    if de_ratio is not None:
        if is_bank:
            if de_ratio > 10.0:
                return False, (
                    f"{ticker}: Debt/Equity {de_ratio:.1f}x too high even for a bank (max 10.0x)"
                )
        else:
            if de_ratio > 2.5:
                return False, (
                    f"{ticker}: Debt/Equity {de_ratio:.1f}x is too high (max 2.5x)"
                )

    return True, f"{ticker}: Passed all Value Portfolio filters"
