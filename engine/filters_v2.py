# ============================================================
# filters_v2.py — Unified Health Filter (Pass/Fail)
# PSE Quant SaaS — Phase 9B (v2 Unified Scorer)
# ============================================================
# Single gate for ALL stocks regardless of dividend status.
# Dividends are now a scoring signal, not a filter requirement.
#
# Hard requirements (any failure = rejected):
#   1. Minimum 2 years of EPS and Revenue data (confidence multiplier handles penalty)
#   2. 3-year normalized EPS > 0 (no persistent losses)
#   3. No persistent negative OCF (2+ consecutive negative years) — only if OCF available
#   4. D/E within sector-appropriate limits
#
# Soft requirements (warnings only, not rejection):
#   - Interest coverage < 2.5x → flagged but not rejected
#   - Stale price data → flagged but not rejected
#
# Returns: (eligible: bool, reason: str)
# ============================================================

from __future__ import annotations


def filter_unified(stock: dict) -> tuple[bool, str]:
    """
    Universal health filter for the v2 unified ranking system.
    Dividends are NOT required. Returns (eligible, reason).

    Evaluates:
      1. Data completeness (2+ years of EPS and Revenue)
      2. Earnings quality (3Y avg EPS > 0)
      3. Cash flow health (no 2+ consecutive negative OCF, only if OCF available)
      4. Leverage limits (sector-appropriate D/E cap)
    """
    ticker     = stock.get('ticker', '?')
    is_bank    = bool(stock.get('is_bank'))
    is_reit    = bool(stock.get('is_reit'))

    # ── 1. Data completeness ──────────────────────────────────
    eps_hist = stock.get('eps_5y') or stock.get('eps_3y') or []
    rev_hist = stock.get('revenue_5y') or []
    ocf_hist = stock.get('operating_cf_history') or []

    eps_vals = [v for v in eps_hist if v is not None]
    rev_vals = [v for v in rev_hist if v is not None]
    ocf_vals = [v for v in ocf_hist if v is not None]

    if len(eps_vals) < 2:
        return False, (f"{ticker}: insufficient EPS history "
                       f"({len(eps_vals)} year(s), need 2)")
    if len(rev_vals) < 2:
        return False, (f"{ticker}: insufficient revenue history "
                       f"({len(rev_vals)} year(s), need 2)")
    # OCF is optional — scraper may not populate it for all stocks.
    # If present, it is used for the negative-streak check below.

    # ── 2. Earnings quality — 3Y average EPS must be positive ─
    eps_3y_avg = sum(eps_vals[:3]) / 3
    if eps_3y_avg <= 0:
        return False, (f"{ticker}: persistent negative earnings "
                       f"(3Y avg EPS = {eps_3y_avg:.2f})")

    # ── 3. Cash flow health — no 2+ consecutive negative OCF ──
    # Only check this if we have at least 3 OCF years
    if len(ocf_vals) >= 3:
        consecutive_neg = 0
        max_consecutive_neg = 0
        for ocf in ocf_vals[:5]:  # check last 5 years max
            if ocf < 0:
                consecutive_neg += 1
                max_consecutive_neg = max(max_consecutive_neg, consecutive_neg)
            else:
                consecutive_neg = 0
        if max_consecutive_neg >= 2:
            return False, (f"{ticker}: persistent negative operating cash flow "
                           f"({max_consecutive_neg} consecutive years)")

    # ── 4. Leverage limits ────────────────────────────────────
    de = stock.get('de_ratio')
    if de is not None:
        if is_bank and de > 10.0:
            return False, (f"{ticker}: excessive leverage for a bank "
                           f"(D/E = {de:.1f}x, limit 10.0x)")
        elif is_reit and de > 4.0:
            return False, (f"{ticker}: excessive leverage for a REIT "
                           f"(D/E = {de:.1f}x, limit 4.0x)")
        elif not is_bank and not is_reit and de > 3.0:
            return False, (f"{ticker}: excessive leverage "
                           f"(D/E = {de:.1f}x, limit 3.0x for non-financial)")

    return True, f"{ticker}: passes all health filters"


def filter_unified_batch(stocks: list) -> tuple[list, list]:
    """
    Applies filter_unified to a list of stocks.
    Returns (eligible_stocks, rejected_stocks).
    Each rejected entry is {'stock': stock_dict, 'reason': str}.
    """
    eligible = []
    rejected = []
    for stock in stocks:
        ok, reason = filter_unified(stock)
        if ok:
            eligible.append(stock)
        else:
            rejected.append({'stock': stock, 'reason': reason})
    return eligible, rejected
