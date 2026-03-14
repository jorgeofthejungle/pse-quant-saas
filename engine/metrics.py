# ============================================================
# metrics.py — Financial Ratio Calculator
# PSE Quant SaaS — Phase 1
# ============================================================
# This file takes raw financial numbers and turns them into
# the ratios we need to score PSE stocks.
# ============================================================


def calculate_pe(price: float, eps: float):
    """
    Price to Earnings Ratio.
    How much you pay for every peso of profit.
    Lower is better for value investing.
    Example: Price=10, EPS=1 → P/E = 10x
    """
    if eps is None or eps <= 0:
        return None
    return round(price / eps, 2)


def calculate_pb(price: float, book_value_per_share: float):
    """
    Price to Book Ratio.
    How much you pay vs what the company owns.
    Below 1.0 means buying assets at a discount.
    Example: Price=10, Book=8 → P/B = 1.25x
    """
    if book_value_per_share is None or book_value_per_share <= 0:
        return None
    return round(price / book_value_per_share, 2)


def calculate_roe(net_income: float, equity: float):
    """
    Return on Equity.
    How efficiently the company makes profit from your money.
    ROE above 15% is considered a quality threshold.
    Example: Net Income=15, Equity=100 → ROE = 15%
    """
    if net_income is None or equity is None or equity <= 0:
        return None
    return round((net_income / equity) * 100, 2)


def calculate_de(total_debt: float, equity: float):
    """
    Debt to Equity Ratio.
    How much debt the company carries vs what it owns.
    Lower is safer. Above 2.0 is a red flag.
    Example: Debt=50, Equity=100 → D/E = 0.5x
    """
    if equity is None or equity <= 0:
        return None
    return round(total_debt / equity, 2)


def calculate_dividend_yield(dps: float, price: float):
    """
    Dividend Yield.
    Annual dividend as a percentage of the stock price.
    Example: DPS=0.50, Price=10 → Yield = 5%
    """
    if price is None or price <= 0:
        return None
    return round((dps / price) * 100, 2)


def calculate_payout_ratio(dps: float, eps: float):
    """
    Payout Ratio.
    What percentage of earnings is paid out as dividends.
    Sweet spot is 30-70%. Above 90% is dangerous.
    Example: DPS=0.50, EPS=1.00 → Payout = 50%
    """
    if eps is None or eps <= 0:
        return None
    return round((dps / eps) * 100, 2)


def calculate_fcf(operating_cash_flow: float, capex: float):
    """
    Free Cash Flow.
    Real cash left over after maintaining the business.
    This is the most honest measure of profitability.
    Example: Operating CF=100, CapEx=30 → FCF = 70
    """
    return round(operating_cash_flow - capex, 2)


def calculate_fcf_yield(fcf: float, market_cap: float):
    """
    Free Cash Flow Yield.
    FCF as a percentage of market cap.
    Higher means the company generates more real cash.
    Example: FCF=70, Market Cap=1000 → FCF Yield = 7%
    """
    if market_cap is None or market_cap <= 0:
        return None
    return round((fcf / market_cap) * 100, 2)


def calculate_fcf_coverage(fcf: float, dividends_paid: float):
    """
    FCF Coverage Ratio.
    How many times FCF covers the dividend payment.
    Above 1.5x means the dividend is safe.
    Below 1.0x means the company cannot afford its dividend.
    Example: FCF=70, Dividends Paid=35 → Coverage = 2.0x
    """
    if dividends_paid is None or dividends_paid <= 0:
        return None
    return round(fcf / dividends_paid, 2)


def calculate_cagr(value_start: float, value_end: float, years: int):
    """
    Compound Annual Growth Rate.
    The steady annual growth rate over a number of years.
    Used for Revenue Growth and Dividend Growth calculations.
    Example: Start=100, End=161, Years=5 → CAGR = 10%
    """
    if value_start is None or value_start <= 0:
        return None
    if years <= 0:
        return None
    return round(((value_end / value_start) ** (1 / years) - 1) * 100, 2)


def calculate_ev_ebitda(
    market_cap: float,
    total_debt: float,
    cash: float,
    ebitda: float
):
    """
    EV/EBITDA — Enterprise Value to EBITDA.
    A valuation metric that works even for companies with debt.
    Lower is better. Below 8x is generally attractive.
    Example: Market Cap=1000, Debt=200, Cash=50, EBITDA=150
             EV = 1000+200-50 = 1150 → EV/EBITDA = 7.67x
    """
    if ebitda is None or ebitda <= 0:
        return None
    ev = market_cap + total_debt - cash
    return round(ev / ebitda, 2)