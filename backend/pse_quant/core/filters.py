"""
pse_quant/core/filters.py — Fundamental Health Filter Gate
Evaluates baseline data completeness, earnings quality, and solvency.
Dividends are a scoring signal, NOT a filter requirement.
"""

from __future__ import annotations
from typing import Any


def filter_unified(stock: dict[str, Any]) -> tuple[bool, str]:
    """
    Universal health filter for PSE equities.
    Returns (eligible: bool, reason: str).

    Checks:
      1. Minimum 2 years of EPS and Revenue data.
      2. 3-year normalized EPS > 0 (excludes chronic money-losers).
      3. No persistent negative Operating Cash Flow (2+ consecutive years, if OCF available).
      4. Sector-appropriate leverage limits (D/E <= 10x for banks, <= 4x for REITs, <= 3x for others).
    """
    ticker = stock.get("ticker", "?")
    is_bank = bool(stock.get("is_bank"))
    is_reit = bool(stock.get("is_reit"))

    # 1. Minimum historical data completeness
    eps_hist = stock.get("eps_5y") or stock.get("eps_3y") or []
    rev_hist = stock.get("revenue_5y") or []
    ocf_hist = stock.get("operating_cf_history") or []

    eps_vals = [v for v in eps_hist if v is not None]
    rev_vals = [v for v in rev_hist if v is not None]
    ocf_vals = [v for v in ocf_hist if v is not None]

    if len(eps_vals) < 2:
        return False, f"{ticker}: insufficient EPS history ({len(eps_vals)} year(s), minimum 2 required)"
    if len(rev_vals) < 2:
        return False, f"{ticker}: insufficient Revenue history ({len(rev_vals)} year(s), minimum 2 required)"

    # 2. Earnings quality (3Y normalized EPS must be positive)
    eps_3y_avg = sum(eps_vals[:3]) / min(len(eps_vals), 3)
    if eps_3y_avg <= 0:
        return False, f"{ticker}: persistent negative earnings (3Y normalized EPS = {eps_3y_avg:.2f})"

    # 3. Operating Cash Flow Health (no 2+ consecutive negative OCF years)
    if len(ocf_vals) >= 3:
        consecutive_neg = 0
        max_consecutive_neg = 0
        for ocf in ocf_vals[:5]:
            if ocf < 0:
                consecutive_neg += 1
                max_consecutive_neg = max(max_consecutive_neg, consecutive_neg)
            else:
                consecutive_neg = 0
        if max_consecutive_neg >= 2:
            return False, f"{ticker}: persistent negative operating cash flow ({max_consecutive_neg} consecutive years)"

    # 4. Solvency / Leverage Check
    de = stock.get("de_ratio")
    if de is not None:
        if is_bank and de > 10.0:
            return False, f"{ticker}: excessive leverage for a bank (D/E = {de:.1f}x, max 10.0x)"
        elif is_reit and de > 4.0:
            return False, f"{ticker}: excessive leverage for a REIT (D/E = {de:.1f}x, max 4.0x)"
        elif not is_bank and not is_reit and de > 3.0:
            return False, f"{ticker}: excessive leverage (D/E = {de:.1f}x, max 3.0x for non-financials)"

    return True, f"{ticker}: eligible"


def filter_unified_batch(stocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Filters a list of stocks.
    Returns (eligible_stocks, rejected_records).
    """
    eligible = []
    rejected = []
    for stock in stocks:
        passed, reason = filter_unified(stock)
        if passed:
            eligible.append(stock)
        else:
            rejected.append({"ticker": stock.get("ticker", "?"), "reason": reason, "stock": stock})
    return eligible, rejected
