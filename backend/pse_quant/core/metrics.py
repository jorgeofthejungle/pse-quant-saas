"""
pse_quant/core/metrics.py — Financial Ratio Calculator
Deterministic, pure mathematical financial ratio computations for PSE equities.
"""

from __future__ import annotations


def calculate_pe(price: float | None, eps: float | None) -> float | None:
    """Price to Earnings Ratio. Returns None if price or eps is invalid or non-positive."""
    if price is None or eps is None or eps <= 0 or price <= 0:
        return None
    return round(price / eps, 2)


def calculate_pb(price: float | None, book_value_per_share: float | None) -> float | None:
    """Price to Book Ratio. Returns None if inputs are non-positive."""
    if price is None or book_value_per_share is None or book_value_per_share <= 0 or price <= 0:
        return None
    return round(price / book_value_per_share, 2)


def calculate_roe(net_income: float | None, equity: float | None) -> float | None:
    """Return on Equity (%). Returns None if equity is non-positive or inputs missing."""
    if net_income is None or equity is None or equity <= 0:
        return None
    return round((net_income / equity) * 100.0, 2)


def calculate_de(total_debt: float | None, equity: float | None) -> float | None:
    """Debt to Equity Ratio (x). Returns None if equity is non-positive."""
    if total_debt is None or equity is None or equity <= 0:
        return None
    return round(total_debt / equity, 2)


def calculate_dividend_yield(dps: float | None, price: float | None) -> float | None:
    """Dividend Yield (%). Annual dividend as percentage of current price."""
    if dps is None or price is None or price <= 0 or dps < 0:
        return None
    return round((dps / price) * 100.0, 2)


def calculate_payout_ratio(dps: float | None, eps: float | None) -> float | None:
    """Dividend Payout Ratio (%). Returns None if EPS is non-positive."""
    if dps is None or eps is None or eps <= 0 or dps < 0:
        return None
    return round((dps / eps) * 100.0, 2)


def calculate_fcf(operating_cash_flow: float | None, capex: float | None) -> float | None:
    """Free Cash Flow = Operating Cash Flow - Capital Expenditures."""
    if operating_cash_flow is None or capex is None:
        return None
    return round(operating_cash_flow - capex, 2)


def calculate_fcf_yield(fcf: float | None, market_cap: float | None) -> float | None:
    """Free Cash Flow Yield (%). FCF relative to market capitalization."""
    if fcf is None or market_cap is None or market_cap <= 0:
        return None
    return round((fcf / market_cap) * 100.0, 2)


def calculate_fcf_coverage(fcf: float | None, dividends_paid: float | None) -> float | None:
    """FCF Coverage Ratio (x). How many times FCF covers the total dividend payout."""
    if fcf is None or dividends_paid is None or dividends_paid <= 0:
        return None
    return round(fcf / dividends_paid, 2)


def calculate_cagr(value_start: float | None, value_end: float | None, years: int) -> float | None:
    """Compound Annual Growth Rate (%)."""
    if value_start is None or value_end is None or value_start <= 0 or value_end <= 0 or years <= 0:
        return None
    return round(((value_end / value_start) ** (1.0 / years) - 1.0) * 100.0, 2)


def calculate_ev_ebitda(
    market_cap: float | None,
    total_debt: float | None,
    cash: float | None,
    ebitda: float | None,
) -> float | None:
    """Enterprise Value to EBITDA. EV = Market Cap + Debt - Cash."""
    if market_cap is None or total_debt is None or cash is None or ebitda is None or ebitda <= 0:
        return None
    ev = market_cap + total_debt - cash
    return round(ev / ebitda, 2)


# ── REIT Specific Metrics (Funds From Operations) ─────────────

def calc_ffo(
    net_income: float | None,
    depreciation: float | None,
    gains_on_sale: float | None = None,
) -> float | None:
    """
    FFO = Net Income + Depreciation - Gains on Property Sales.
    Key profitability and cash-generation metric for REITs.
    """
    if net_income is None or depreciation is None:
        return None
    gains = gains_on_sale or 0.0
    return round(net_income + depreciation - gains, 2)


def calc_ffo_yield(ffo: float | None, market_cap: float | None) -> float | None:
    """FFO Yield (%) = FFO / Market Cap * 100."""
    if ffo is None or market_cap is None or market_cap <= 0:
        return None
    return round((ffo / market_cap) * 100.0, 2)


def calc_ffo_payout(dps: float | None, shares_outstanding: float | None, ffo: float | None) -> float | None:
    """FFO Payout Ratio (%) = (DPS * Shares) / FFO * 100."""
    if dps is None or shares_outstanding is None or ffo is None or ffo <= 0:
        return None
    return round(((dps * shares_outstanding) / ffo) * 100.0, 2)
