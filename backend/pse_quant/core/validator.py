"""
pse_quant/core/validator.py — Financial Data Validator & Hygiene Checks
Audits scraped company records before they enter the scoring and valuation engine.
Separates critical blockers (missing price, extreme anomalies) from non-fatal warnings.
"""

from __future__ import annotations
from typing import Any

REQUIRED_FIELDS = [
    "ticker",
    "current_price",
]

SCORED_FIELDS = [
    "current_price",
    "eps_3y",
    "net_income_3y",
    "dividend_yield",
    "dps_last",
    "dividends_5y",
    "dividend_cagr_5y",
    "roe",
    "pe",
    "pb",
    "ev_ebitda",
    "fcf_coverage",
    "fcf_yield",
    "fcf_per_share",
    "operating_cf",
    "revenue_cagr",
    "de_ratio",
]

BLOCK_THRESHOLDS: dict[str, tuple[str, float, str]] = {
    "pb": (">", 50.0, "P/B of {v:.1f}x exceeds 50.0 — likely equity unit mismatch"),
    "roe": ("<", -50.0, "ROE of {v:.1f}% below -50.0% — severe distress or unit error"),
}

WARN_THRESHOLDS: dict[str, tuple[str, float, str]] = {
    "dividend_yield": (">", 25.0, "Dividend yield of {v:.1f}% is unusually high"),
    "pe": ("<", 0.5, "P/E of {v:.1f}x is suspiciously low"),
    "pb": (">", 30.0, "P/B of {v:.1f}x is unusually high"),
    "roe": (">", 100.0, "ROE of {v:.1f}% is unusually high"),
    "de_ratio": (">", 20.0, "D/E ratio of {v:.1f}x is very high"),
    "ev_ebitda": (">", 50.0, "EV/EBITDA of {v:.1f}x is unusually high"),
    "current_price": (">", 10_000.0, "Price of PHP {v:,.2f} is unusually high"),
}

WARN_LOW_THRESHOLDS: dict[str, tuple[str, float, str]] = {
    "current_price": ("<", 0.10, "Price of PHP {v:.4f} is below PHP 0.10 (penny stock or under monitoring)"),
    "pe": (">", 200.0, "P/E of {v:.1f}x is unusually high"),
}

SPECIAL_DIVIDEND_YIELD_CAP: float = 20.0  # Capped for ongoing run-rate scoring


def validate_financial_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Validates and cleans a scraped annual financial record.
    Returns cleaned dictionary.
    """
    out = dict(record)
    year = out.get("year")
    if not year or not isinstance(year, int) or year < 1990 or year > 2100:
        return {}

    # Ensure numeric fields are clean floats
    numeric_keys = [
        "revenue", "net_income", "equity", "total_debt", "cash",
        "operating_cash_flow", "capital_expenditures", "ebitda",
        "eps", "dps", "depreciation", "amortization", "book_value_per_share",
    ]
    for k in numeric_keys:
        v = out.get(k)
        if v is not None:
            try:
                out[k] = float(v)
            except (ValueError, TypeError):
                out[k] = None

    return out


def detect_and_cap_special_dividend(stock: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Detects one-time special dividends (yield > 20%) that distort baseline scoring.
    Returns (updated_stock_dict, warnings).
    """
    out = dict(stock)
    warnings = []
    div_yield = out.get("dividend_yield")
    price = out.get("current_price")
    dps_last = out.get("dps_last")

    if div_yield and div_yield > SPECIAL_DIVIDEND_YIELD_CAP:
        capped_dps = round((SPECIAL_DIVIDEND_YIELD_CAP / 100.0) * price, 4) if price else dps_last
        warnings.append(
            f"Special dividend detected: yield {div_yield:.1f}% capped to {SPECIAL_DIVIDEND_YIELD_CAP:.0f}% "
            f"(DPS adjusted from {dps_last} to {capped_dps}) for baseline fundamental scoring."
        )
        out["dividend_yield"] = SPECIAL_DIVIDEND_YIELD_CAP
        out["dps_last"] = capped_dps
        out["special_dividend_flag"] = True
    else:
        out.setdefault("special_dividend_flag", False)

    return out, warnings


def validate_stock(stock: dict[str, Any]) -> dict[str, Any]:
    """
    Validates a single stock record.
    Returns audit report: valid (bool), completeness (float), errors (list), warnings (list).
    """
    ticker = stock.get("ticker", "UNKNOWN")
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Required fields
    for field_name in REQUIRED_FIELDS:
        val = stock.get(field_name)
        if val is None or (isinstance(val, (int, float)) and val <= 0):
            errors.append(f"{ticker}: missing or invalid required field '{field_name}'")

    # 2. Hard-block threshold checks
    for metric, (op, threshold, msg) in BLOCK_THRESHOLDS.items():
        v = stock.get(metric)
        if v is not None:
            if op == ">" and v > threshold:
                errors.append(msg.format(v=v))
            elif op == "<" and v < threshold:
                errors.append(msg.format(v=v))

    # 3. Warning threshold checks
    for metric, (op, threshold, msg) in WARN_THRESHOLDS.items():
        v = stock.get(metric)
        if v is not None and op == ">" and v > threshold:
            warnings.append(msg.format(v=v))

    for metric, (op, threshold, msg) in WARN_LOW_THRESHOLDS.items():
        v = stock.get(metric)
        if v is not None:
            if op == "<" and v < threshold:
                warnings.append(msg.format(v=v))
            elif op == ">" and v > threshold:
                warnings.append(msg.format(v=v))

    # 4. Completeness ratio
    populated = sum(1 for f in SCORED_FIELDS if stock.get(f) is not None)
    completeness = round(populated / len(SCORED_FIELDS), 2)

    return {
        "ticker": ticker,
        "valid": len(errors) == 0,
        "completeness": completeness,
        "errors": errors,
        "warnings": warnings,
    }


def validate_all(stocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validates a collection of stocks, returning (valid_stocks, audit_results)."""
    valid_stocks = []
    audit_results = []
    for stock in stocks:
        stock_capped, special_warns = detect_and_cap_special_dividend(stock)
        res = validate_stock(stock_capped)
        res["warnings"].extend(special_warns)
        audit_results.append(res)
        if res["valid"]:
            valid_stocks.append(stock_capped)
    return valid_stocks, audit_results
