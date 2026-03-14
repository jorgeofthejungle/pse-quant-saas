# ============================================================
# mos.py — Margin of Safety Calculator
# PSE Quant SaaS — Phase 1
# ============================================================
# Calculates the intrinsic value of a stock and the price
# at which it offers a sufficient Margin of Safety.
#
# Three methods are used depending on portfolio type:
#
# 1. DDM  — Dividend Discount Model (Dividend Portfolio)
#    Best for stable dividend-paying companies.
#    Intrinsic Value = DPS1 / (r - g)
#
# 2. EPS-PE — Normalised Earnings x Target PE (Value Portfolio)
#    Best for profitable non-dividend companies.
#    Intrinsic Value = Normalised EPS x Target PE
#
# 3. DCF — Discounted Cash Flow (all portfolios as cross-check)
#    Best for cash-generative businesses.
#    Intrinsic Value = sum of discounted future FCF + terminal value
#
# IMPORTANT: All outputs are mathematical computations only.
# They are NOT buy/sell recommendations.
# ============================================================

# Philippine 10-year Treasury Bond rate (risk-free rate)
# Update this periodically to reflect current PH rates
PH_RISK_FREE_RATE = 0.065   # 6.5%

# Equity Risk Premium for Philippine market
EQUITY_RISK_PREMIUM = 0.05  # 5.0%

# Default required rate of return
DEFAULT_REQUIRED_RETURN = PH_RISK_FREE_RATE + EQUITY_RISK_PREMIUM  # 11.5%

# Maximum growth rate allowed in DDM to prevent model explosion
DDM_MAX_GROWTH_RATE = 0.07  # 7.0%

# Default target PE multiple for Philippine market
DEFAULT_TARGET_PE = 15.0

# Conglomerate IV discount (Holding Firms sector)
CONGLOMERATE_DISCOUNT = 0.20

# Margin of Safety targets per portfolio
MOS_TARGET = {
    'pure_dividend':   0.25,   # 25% — income investors are conservative
    'dividend_growth': 0.20,   # 20% — growth companies command a premium
    'value':           0.30,   # 30% — value investors demand the most cushion
}


def _sector_median_pe(sector: str, all_stocks: list) -> float:
    """
    Computes median PE for a sector from the current stock universe.
    Falls back to DEFAULT_TARGET_PE if sector has fewer than 3 stocks.

    Filters out PE outliers (< 0 or > 100) to get a realistic median.
    """
    sector_pes = [
        s['pe'] for s in all_stocks
        if s.get('sector') == sector
        and s.get('pe') is not None
        and 0 < s['pe'] < 100
    ]
    if len(sector_pes) < 3:
        return DEFAULT_TARGET_PE
    sorted_pes = sorted(sector_pes)
    return round(sorted_pes[len(sorted_pes) // 2], 1)


def apply_conglomerate_discount(intrinsic_value: float, sector: str) -> float:
    """
    Applies a structural discount to intrinsic value for conglomerates.
    Philippine holding companies (Holding Firms sector) trade at a discount
    due to cross-holding complexity and limited segment-level reporting.

    Discount: 20% (configurable via config.py CONGLOMERATE_DISCOUNT)
    Applied only to 'Holding Firms' sector.
    Returns intrinsic_value unchanged for all other sectors.
    Returns None if intrinsic_value is None.
    """
    if intrinsic_value is None:
        return None
    if sector == 'Holding Firms':
        try:
            from config import CONGLOMERATE_DISCOUNT as _disc
        except ImportError:
            _disc = CONGLOMERATE_DISCOUNT
        return round(intrinsic_value * (1 - _disc), 2)
    return intrinsic_value


def calc_ddm(
    dps_last: float,
    dividend_cagr: float,
    required_return: float = DEFAULT_REQUIRED_RETURN,
):
    """
    Dividend Discount Model.
    Calculates intrinsic value based on future dividend stream.

    Formula: Intrinsic Value = DPS1 / (r - g)

    Where:
      DPS1 = next expected dividend (DPS_last x (1 + g))
      r    = required rate of return
      g    = perpetual dividend growth rate (capped at 7%)

    Returns intrinsic value per share, or None if not applicable.
    """
    if dps_last is None or dps_last <= 0:
        return None, "DDM not applicable — no dividend history"

    if dividend_cagr is None:
        dividend_cagr = 0.03    # assume 3% growth if unknown

    # Convert percentage to decimal if needed
    if dividend_cagr > 1:
        dividend_cagr = dividend_cagr / 100

    # Cap growth rate to prevent model explosion; floor at 0 so shrinking
    # dividends don't inflate the DDM denominator (negative g widens r-g)
    g = max(min(dividend_cagr, DDM_MAX_GROWTH_RATE), 0.0)

    # Growth rate must be below required return
    if g >= required_return:
        g = required_return - 0.02

    # Next year expected dividend
    dps1 = dps_last * (1 + g)

    # Gordon Growth Model formula
    intrinsic_value = dps1 / (required_return - g)

    return round(intrinsic_value, 2), "DDM applied successfully"


def calc_eps_pe(
    eps_3y: list,
    target_pe: float = None,
    roe: float = None,
):
    """
    EPS x Target PE Method.
    Calculates intrinsic value based on normalised earnings.

    Formula: Intrinsic Value = Normalised EPS x Target PE

    Normalised EPS = 3-year average EPS (smooths out one-off items)
    Target PE is adjusted upward for high-ROE companies.

    Returns intrinsic value per share, or None if not applicable.
    """
    if not eps_3y or len(eps_3y) < 1:
        return None, "EPS-PE not applicable — no EPS data"

    # Use available years — prefer 3 year average
    normalised_eps = sum(eps_3y) / len(eps_3y)

    if normalised_eps <= 0:
        return None, "EPS-PE not applicable — negative normalised EPS"

    # Use provided sector-median PE, else fall back to default
    if target_pe is None:
        target_pe = DEFAULT_TARGET_PE

    # Adjust target PE upward for high quality businesses
    # High ROE companies deserve a premium multiple
    adjusted_pe = target_pe
    if roe is not None:
        if roe >= 20:
            adjusted_pe = target_pe * 1.30   # 30% premium
        elif roe >= 15:
            adjusted_pe = target_pe * 1.15   # 15% premium
        elif roe < 10:
            adjusted_pe = target_pe * 0.85   # 15% discount

    intrinsic_value = normalised_eps * adjusted_pe

    return round(intrinsic_value, 2), f"EPS-PE applied (Norm. EPS={round(normalised_eps,2)}, Target PE={round(adjusted_pe,1)}x)"


def calc_dcf(
    fcf_per_share: float,
    growth_rate: float,
    required_return: float = DEFAULT_REQUIRED_RETURN,
    years: int = 10,
    terminal_growth: float = 0.03,
):
    """
    Simplified Discounted Cash Flow Model.
    Projects Free Cash Flow forward and discounts back to today.

    Formula:
      Year 1-10: FCF x (1+g)^n discounted at required return
      Terminal:  FCF_year10 x (1+tg) / (r - tg) discounted back

    Returns intrinsic value per share, or None if not applicable.
    """
    if fcf_per_share is None or fcf_per_share <= 0:
        return None, "DCF not applicable — negative or missing FCF per share"

    # Convert percentages to decimals if needed
    if growth_rate and growth_rate > 1:
        growth_rate = growth_rate / 100
    if growth_rate is None:
        growth_rate = 0.05   # assume 5% if unknown

    # Cap growth rate conservatively
    growth_rate = min(growth_rate, 0.15)

    # Project and discount future FCF
    pv_fcf = 0
    fcf = fcf_per_share

    for year in range(1, years + 1):
        fcf = fcf * (1 + growth_rate)
        pv  = fcf / ((1 + required_return) ** year)
        pv_fcf += pv

    # Terminal value — what the business is worth beyond year 10
    terminal_fcf   = fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (required_return - terminal_growth)
    pv_terminal    = terminal_value / ((1 + required_return) ** years)

    intrinsic_value = pv_fcf + pv_terminal

    return round(intrinsic_value, 2), f"DCF applied ({years}yr projection, g={growth_rate:.1%}, r={required_return:.1%})"


def calc_mos_price(intrinsic_value: float, portfolio: str = 'value'):
    """
    Calculates the Margin of Safety buy price.

    MoS Price = Intrinsic Value x (1 - MoS Target %)

    Example: Intrinsic Value = 18.50, MoS Target = 25%
             MoS Price = 18.50 x 0.75 = 13.88

    This is the price at which the stock offers sufficient
    safety cushion based on the portfolio strategy.
    """
    if intrinsic_value is None or intrinsic_value <= 0:
        return None

    mos_pct = MOS_TARGET.get(portfolio, 0.25)
    mos_price = intrinsic_value * (1 - mos_pct)

    return round(mos_price, 2)


def calc_mos_pct(intrinsic_value: float, current_price: float):
    """
    Calculates the current Margin of Safety percentage.

    MoS % = (Intrinsic Value - Current Price) / Intrinsic Value x 100

    Positive = stock is trading BELOW intrinsic value (good)
    Negative = stock is trading ABOVE intrinsic value (expensive)
    """
    if intrinsic_value is None or intrinsic_value <= 0:
        return None
    if current_price is None or current_price <= 0:
        return None

    mos_pct = ((intrinsic_value - current_price) / intrinsic_value) * 100

    return round(mos_pct, 1)


def calc_two_stage_ddm(
    dps_last: float,
    eps_growth_rate: float,
    terminal_growth: float = 0.05,
    required_return: float = DEFAULT_REQUIRED_RETURN,
    stage1_years: int = 5,
):
    """
    Two-Stage Dividend Discount Model for the Dividend Growth portfolio.

    Stage 1 (explicit, years 1–5):
      Dividend grows at a conservative rate = min(eps_growth_rate * 0.6, 10%)
      This reflects that dividends typically grow slower than earnings.

    Stage 2 (terminal, year 6+):
      Gordon Growth at terminal_growth rate (default 5%, capped at PH GDP ~6%)

    Formula:
      IV = sum(DPS_t / (1+r)^t for t=1..5) + TV / (1+r)^5
      TV = DPS_5 * (1 + terminal_growth) / (r - terminal_growth)

    Returns intrinsic value per share, or None if not applicable.
    """
    if dps_last is None or dps_last <= 0:
        return None, "Two-Stage DDM not applicable — no dividend history"

    if eps_growth_rate is None:
        eps_growth_rate = 5.0   # assume 5% if unknown

    # Convert to decimal if given as percentage
    if eps_growth_rate > 1:
        eps_growth_rate = eps_growth_rate / 100
    if terminal_growth > 1:
        terminal_growth = terminal_growth / 100

    # Stage 1: conservative dividend growth = 60% of earnings growth, capped at 10%
    stage1_growth = min(eps_growth_rate * 0.6, 0.10)
    stage1_growth = max(stage1_growth, 0.0)   # floor at 0%

    # Terminal growth must be below required return
    terminal_growth = min(terminal_growth, DDM_MAX_GROWTH_RATE)
    if terminal_growth >= required_return:
        terminal_growth = required_return - 0.02

    # Stage 1: discount each year's expected dividend
    pv_dividends = 0.0
    dps = dps_last
    for t in range(1, stage1_years + 1):
        dps = dps * (1 + stage1_growth)
        pv_dividends += dps / ((1 + required_return) ** t)

    # Stage 2: Gordon Growth terminal value at end of Stage 1
    dps_terminal = dps * (1 + terminal_growth)
    terminal_value = dps_terminal / (required_return - terminal_growth)
    pv_terminal = terminal_value / ((1 + required_return) ** stage1_years)

    intrinsic_value = pv_dividends + pv_terminal

    return round(intrinsic_value, 2), (
        f"Two-Stage DDM: Stage 1 g={stage1_growth:.1%} ({stage1_years}yr), "
        f"Terminal g={terminal_growth:.1%}"
    )


def calc_hybrid_intrinsic(
    ddm_value: float,
    eps_pe_value: float,
    dcf_value: float,
    weights: tuple = (0.40, 0.40, 0.20),
):
    """
    Hybrid Intrinsic Value — weighted blend of all three methods.

    Default weights: DDM 40%, EPS-PE 40%, DCF 20%.
    Pass custom weights tuple (ddm_w, eps_w, dcf_w) per portfolio:
      pure_dividend:   (0.50, 0.25, 0.25) — income focus
      dividend_growth: (0.40, 0.30, 0.30) — balanced
      value:           (0.20, 0.40, 0.40) — fundamentals focus

    If a method returns None (not applicable),
    the weight is redistributed to available methods.
    """
    ddm_w, eps_w, dcf_w = weights
    values  = []
    blend_w = []

    if ddm_value is not None and ddm_value > 0:
        values.append(ddm_value)
        blend_w.append(ddm_w)

    if eps_pe_value is not None and eps_pe_value > 0:
        values.append(eps_pe_value)
        blend_w.append(eps_w)

    if dcf_value is not None and dcf_value > 0:
        values.append(dcf_value)
        blend_w.append(dcf_w)

    if not values:
        return None, "No intrinsic value methods applicable"

    # Normalise weights to sum to 1.0
    total_weight = sum(blend_w)
    normalised   = [w / total_weight for w in blend_w]

    intrinsic_value = sum(v * w for v, w in zip(values, normalised))

    return round(intrinsic_value, 2), f"Hybrid blend of {len(values)} method(s)"