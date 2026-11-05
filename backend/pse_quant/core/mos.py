"""
pse_quant/core/mos.py — Intrinsic Value & Margin of Safety Valuation Engine
Computes intrinsic value estimates via:
  1. DDM (Dividend Discount Model) — Gordon Growth and Two-Stage DDM
  2. EPS x Target PE (Normalised earnings multiple with ROE premium/discount)
  3. DCF (Discounted Cash Flow — 10-year projection + terminal value)
  4. Hybrid Blend (Portfolio-specific weighting)
  5. Conglomerate Discount (20% for Holding Firms)
All discount rates are risk-adjusted by Philippine 10Y Bond + Damodaran ERP + Size Premium + Sector Premium.
"""

from __future__ import annotations
from typing import Any

from pse_quant.config import (
    PH_RISK_FREE_RATE,
    EQUITY_RISK_PREMIUM,
    DEFAULT_TARGET_PE,
    DDM_MAX_GROWTH_RATE,
    CONGLOMERATE_DISCOUNT,
    MOS_SIZE_PREMIUM,
    MOS_SECTOR_PREMIUM,
    MOS_SECTOR_PREMIUM_DEFAULT,
    IV_WEIGHTS,
    IV_WEIGHTS_DIVIDEND,
    IV_WEIGHTS_VALUE,
)

DEFAULT_REQUIRED_RETURN: float = PH_RISK_FREE_RATE + EQUITY_RISK_PREMIUM  # ~11.5%

_IV_WEIGHTS_BY_PORTFOLIO: dict[str, tuple[float, float, float]] = {
    "dividend": IV_WEIGHTS_DIVIDEND,
    "value":    IV_WEIGHTS_VALUE,
    "unified":  IV_WEIGHTS,
}


def calc_required_return(market_cap: float | None, sector: str | None) -> float:
    """
    Computes risk-adjusted required return for Philippine equities.
    Formula: Risk Free (~6.5%) + Equity Risk Premium (~5.0%) + Size Premium + Sector Premium.
    """
    base = PH_RISK_FREE_RATE + EQUITY_RISK_PREMIUM

    # Size premium based on market cap in PHP
    if market_cap is None or market_cap <= 0:
        size_prem = MOS_SIZE_PREMIUM["micro"]
    elif market_cap > 100e9:
        size_prem = MOS_SIZE_PREMIUM["large"]
    elif market_cap > 20e9:
        size_prem = MOS_SIZE_PREMIUM["mid"]
    elif market_cap > 5e9:
        size_prem = MOS_SIZE_PREMIUM["small"]
    else:
        size_prem = MOS_SIZE_PREMIUM["micro"]

    # Sector premium
    sector_prem = MOS_SECTOR_PREMIUM.get(sector or "", MOS_SECTOR_PREMIUM_DEFAULT)

    return round(base + (size_prem + sector_prem) / 100.0, 4)


def apply_conglomerate_discount(intrinsic_value: float | None, sector: str | None) -> float | None:
    """Applies a 20% holding-company discount for conglomerates ('Holding Firms')."""
    if intrinsic_value is None or intrinsic_value <= 0:
        return None
    if sector == "Holding Firms":
        return round(intrinsic_value * (1.0 - CONGLOMERATE_DISCOUNT), 2)
    return round(intrinsic_value, 2)


def calc_ddm(
    dps_last: float | None,
    dividend_cagr: float | None,
    required_return: float = DEFAULT_REQUIRED_RETURN,
) -> tuple[float | None, str]:
    """
    Gordon Growth Dividend Discount Model.
    Formula: Intrinsic Value = DPS1 / (r - g)
    """
    if dps_last is None or dps_last <= 0:
        return None, "DDM not applicable — no positive dividend history"

    cagr = dividend_cagr if dividend_cagr is not None else 0.03
    if cagr > 1.0:
        cagr = cagr / 100.0

    # Cap terminal growth rate
    g = max(0.0, min(cagr, DDM_MAX_GROWTH_RATE))
    denom = required_return - g
    if denom <= 0.015:
        g = max(0.0, required_return - 0.02)
        denom = max(required_return - g, 0.015)

    dps1 = dps_last * (1.0 + g)
    if denom <= 0:
        return None, "DDM invalid denominator"

    iv = dps1 / denom
    return round(iv, 2), f"DDM applied (DPS1={dps1:.2f}, g={g:.1%}, r={required_return:.1%})"


def calc_two_stage_ddm(
    dps_last: float | None,
    eps_growth_rate: float | None,
    terminal_growth: float = 0.05,
    required_return: float = DEFAULT_REQUIRED_RETURN,
    stage1_years: int = 5,
) -> tuple[float | None, str]:
    """Two-stage DDM for dividend growth stocks."""
    if dps_last is None or dps_last <= 0:
        return None, "Two-stage DDM not applicable — no positive dividend history"

    growth = eps_growth_rate if eps_growth_rate is not None else 5.0
    if growth > 1.0:
        growth = growth / 100.0
    if terminal_growth > 1.0:
        terminal_growth = terminal_growth / 100.0

    # Stage 1: dividend growth capped at 60% of earnings growth or 10%
    stage1_g = max(0.0, min(growth * 0.60, 0.10))
    terminal_g = min(terminal_growth, DDM_MAX_GROWTH_RATE)
    if terminal_g >= required_return:
        terminal_g = required_return - 0.02

    pv_dividends = 0.0
    dps = dps_last
    for t in range(1, stage1_years + 1):
        dps = dps * (1.0 + stage1_g)
        pv_dividends += dps / ((1.0 + required_return) ** t)

    dps_terminal = dps * (1.0 + terminal_g)
    terminal_value = dps_terminal / (required_return - terminal_g)
    pv_terminal = terminal_value / ((1.0 + required_return) ** stage1_years)

    iv = pv_dividends + pv_terminal
    return round(iv, 2), f"Two-Stage DDM (Stage 1 g={stage1_g:.1%}, Terminal g={terminal_g:.1%})"


def calc_eps_pe(
    eps_3y: list[float | None] | None,
    target_pe: float | None = None,
    roe: float | None = None,
) -> tuple[float | None, str]:
    """Normalised EPS x Target PE with ROE quality multiple adjustments."""
    if not eps_3y:
        return None, "EPS-PE not applicable — missing EPS history"

    valid_eps = [e for e in eps_3y if e is not None]
    if not valid_eps:
        return None, "EPS-PE not applicable — no valid EPS"

    normalised_eps = sum(valid_eps) / len(valid_eps)
    if normalised_eps <= 0:
        return None, f"EPS-PE not applicable — negative normalised EPS ({normalised_eps:.2f})"

    pe_multiple = target_pe if target_pe is not None else DEFAULT_TARGET_PE
    if roe is not None:
        if roe >= 20.0:
            pe_multiple *= 1.30  # 30% premium for high ROE
        elif roe >= 15.0:
            pe_multiple *= 1.15  # 15% premium
        elif roe < 10.0:
            pe_multiple *= 0.85  # 15% discount for weak ROE

    iv = normalised_eps * pe_multiple
    return round(iv, 2), f"EPS-PE applied (EPS={normalised_eps:.2f}, Multiple={pe_multiple:.1f}x)"


def calc_dcf(
    fcf_per_share: float | None,
    growth_rate: float | None,
    required_return: float = DEFAULT_REQUIRED_RETURN,
    years: int = 10,
    terminal_growth: float = 0.03,
) -> tuple[float | None, str]:
    """10-Year Discounted Cash Flow valuation with Gordon Growth terminal value."""
    if fcf_per_share is None or fcf_per_share <= 0:
        return None, "DCF not applicable — non-positive FCF per share"

    g = growth_rate if growth_rate is not None else 0.05
    if g > 1.0:
        g = g / 100.0
    g = min(g, 0.15)  # conservative cap

    pv_fcf = 0.0
    fcf = fcf_per_share
    for y in range(1, years + 1):
        fcf = fcf * (1.0 + g)
        pv_fcf += fcf / ((1.0 + required_return) ** y)

    t_growth = min(terminal_growth, max(0.0, required_return - 0.02))
    t_denom = max(required_return - t_growth, 0.02)
    terminal_fcf = fcf * (1.0 + t_growth)
    terminal_val = terminal_fcf / t_denom
    pv_terminal = terminal_val / ((1.0 + required_return) ** years)

    iv = pv_fcf + pv_terminal
    return round(iv, 2), f"DCF applied ({years}yr, g={g:.1%}, r={required_return:.1%})"


def calc_hybrid_intrinsic(
    ddm_value: float | None,
    eps_pe_value: float | None,
    dcf_value: float | None,
    portfolio_type: str = "unified",
) -> tuple[float | None, str]:
    """
    Weighted combination of applicable valuation models.
    Redistributes weights proportionally when a model is not applicable.
    """
    weights = _IV_WEIGHTS_BY_PORTFOLIO.get(portfolio_type, IV_WEIGHTS)
    ddm_w, eps_w, dcf_w = weights

    models: list[tuple[float, float]] = []
    if ddm_value is not None and ddm_value > 0:
        models.append((ddm_value, ddm_w))
    if eps_pe_value is not None and eps_pe_value > 0:
        models.append((eps_pe_value, eps_w))
    if dcf_value is not None and dcf_value > 0:
        models.append((dcf_value, dcf_w))

    if not models:
        return None, "No valuation methods applicable"

    total_w = sum(w for _, w in models)
    iv = sum(val * (w / total_w) for val, w in models)
    return round(iv, 2), f"Hybrid blend of {len(models)} method(s)"


def calc_mos_pct(intrinsic_value: float | None, current_price: float | None) -> float | None:
    """Margin of Safety (%) = (Intrinsic Value - Current Price) / Intrinsic Value * 100."""
    if intrinsic_value is None or intrinsic_value <= 0 or current_price is None or current_price <= 0:
        return None
    return round(((intrinsic_value - current_price) / intrinsic_value) * 100.0, 1)


def calc_mos_price(intrinsic_value: float | None, target_margin: float = 0.25) -> float | None:
    """Target entry price providing the specified safety cushion (e.g. 25% or 30%)."""
    if intrinsic_value is None or intrinsic_value <= 0:
        return None
    return round(intrinsic_value * (1.0 - target_margin), 2)


def enrich_stock_valuation(
    stock: dict[str, Any],
    portfolio_type: str = "unified",
) -> dict[str, Any]:
    """
    Enriches a stock dictionary with full intrinsic value estimates and MoS metrics.
    Pure function — returns an updated copy without side effects.
    """
    out = dict(stock)
    market_cap = stock.get("market_cap")
    sector = stock.get("sector")
    price = stock.get("current_price")

    req_return = calc_required_return(market_cap, sector)

    # 1. DDM
    dps = stock.get("dps_last")
    div_cagr = stock.get("dividend_cagr_5y")
    ddm_val, ddm_msg = calc_ddm(dps, div_cagr, required_return=req_return)

    # 2. EPS-PE
    eps_3y = stock.get("eps_3y") or []
    roe = stock.get("roe")
    eps_val, eps_msg = calc_eps_pe(eps_3y, roe=roe)

    # 3. DCF
    fcf_share = stock.get("fcf_per_share")
    rev_cagr = stock.get("revenue_cagr")
    dcf_val, dcf_msg = calc_dcf(fcf_share, rev_cagr, required_return=req_return)

    # 4. Hybrid
    raw_iv, hybrid_msg = calc_hybrid_intrinsic(ddm_val, eps_val, dcf_val, portfolio_type=portfolio_type)

    # 5. Conglomerate Discount
    final_iv = apply_conglomerate_discount(raw_iv, sector)

    # 6. MoS
    mos_pct = calc_mos_pct(final_iv, price)
    mos_entry = calc_mos_price(final_iv, target_margin=0.25 if portfolio_type == "dividend" else 0.30)

    out["required_return"] = req_return
    out["valuation"] = {
        "ddm": {"value": ddm_val, "status": ddm_msg},
        "eps_pe": {"value": eps_val, "status": eps_msg},
        "dcf": {"value": dcf_val, "status": dcf_msg},
        "hybrid_raw": raw_iv,
        "conglomerate_discount_applied": (sector == "Holding Firms" and raw_iv is not None),
        "status": hybrid_msg,
    }
    out["intrinsic_value"] = final_iv
    out["mos_pct"] = mos_pct
    out["mos_target_price"] = mos_entry

    return out
