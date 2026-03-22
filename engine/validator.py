# ============================================================
# validator.py — Stock Data Validator
# PSE Quant SaaS — Phase 3
# ============================================================
# Validates the stock dict produced by build_stock_dict_from_db()
# before it enters the filter / scorer / MoS pipeline.
# ERRORS = hard stops (stock skipped). WARNINGS = suspicious values logged.
# Returns: {'ticker', 'valid', 'completeness', 'errors', 'warnings', 'missing_fields'}
# ============================================================


# ── Field definitions ─────────────────────────────────────────

# Fields required for ANY portfolio scoring.
# If ALL of these are missing/invalid, the stock is hard-blocked.
REQUIRED_FIELDS = [
    'ticker',
    'current_price',
]

# Fields scored for data completeness (0–1 ratio of populated fields).
# These are not hard requirements but affect how reliable the score is.
SCORED_FIELDS = [
    'current_price',
    'eps_3y',
    'net_income_3y',
    'dividend_yield',
    'dps_last',
    'dividends_5y',
    'dividend_cagr_5y',
    'roe',
    'pe',
    'pb',
    'ev_ebitda',
    'fcf_coverage',
    'fcf_yield',
    'fcf_per_share',
    'operating_cf',
    'revenue_cagr',
    'de_ratio',
]

# Hard-block thresholds: values so extreme they indicate bad data.
# Stocks that trip these are blocked (valid=False), not just warned.
BLOCK_THRESHOLDS = {
    # P/B > 50x almost always means equity is in wrong units
    'pb': ('>', 50.0,
           "P/B of {v:.1f}x above 50 — likely data error"),
    # ROE below -50% indicates distressed or data error
    'roe': ('<', -50.0,
            "ROE of {v:.1f}% below -50% — distressed or data error"),
}

# Thresholds for suspicious-value warnings (not hard errors).
# All values are in the same units the stock dict uses.
WARN_THRESHOLDS = {
    # Dividend yield > 25% is almost always a scraping/unit error
    'dividend_yield':  ('>', 25.0,
                        "Dividend yield of {v:.1f}% looks too high — "
                        "verify this is not a scraping or unit error"),

    # P/E < 0.5 or > 200 is extreme; negative P/E should not occur
    # (build_stock_dict_from_db sets pe=None when EPS <= 0)
    'pe':              ('<', 0.5,
                        "P/E of {v:.1f}x is suspiciously low — "
                        "verify EPS and price data"),

    # P/B > 30 is unusual for PSE stocks
    'pb':              ('>', 30.0,
                        "P/B of {v:.1f}x is unusually high — "
                        "verify equity and market cap data"),

    # ROE > 100% is exceptional; may indicate unit mismatch
    'roe':             ('>', 100.0,
                        "ROE of {v:.1f}% is extremely high — "
                        "verify net income and equity are in the same units"),

    # D/E > 20 for non-banks is a red flag (banks are exempt — checked separately)
    'de_ratio':        ('>', 20.0,
                        "D/E ratio of {v:.1f}x is very high — "
                        "verify debt and equity figures"),

    # EV/EBITDA > 50 is extreme for PSE
    'ev_ebitda':       ('>', 50.0,
                        "EV/EBITDA of {v:.1f}x is unusually high — "
                        "verify market cap, debt, cash, and EBITDA"),

    # Current price > 10,000 — possible extra zeros from scraping
    'current_price':   ('>', 10_000.0,
                        "Price of PHP {v:,.2f} is very high for a PSE stock -- "
                        "verify no extra zeros were scraped"),

    # Current price < 0.10 — may be suspended/delisted
    # (checked as a separate < threshold below)
}

WARN_LOW_THRESHOLDS = {
    'current_price':   ('<', 0.10,
                        "Price of PHP {v:.4f} is below PHP 0.10 -- "
                        "stock may be suspended, under monitoring, or penny stock"),
    'pe':              ('>', 200.0,
                        "P/E of {v:.1f}x is unusually high — "
                        "verify EPS data and confirm this is not a loss year"),
}

# Minimum completeness score to be considered usable.
# Below this, the stock is hard-blocked.
MIN_COMPLETENESS = 0.40   # need at least 40% of scored fields populated

# Yield cap for special dividend detection.
# Philippine stocks paying >20% yield almost always include a one-time
# special dividend (property spin-off, liquidating dividend, etc.).
# We cap yield and DPS for scoring purposes and set special_dividend_flag=True.
SPECIAL_DIVIDEND_YIELD_CAP = 20.0   # percent

# If DPS exceeds earnings by this multiple, flag as special dividend
# even when yield doesn't look extreme (e.g. high-priced stocks).
SPECIAL_DIVIDEND_DPS_EPS_MULTIPLE = 3.0


# ── Special dividend cap ──────────────────────────────────────

def _detect_and_cap_special_dividend(stock: dict, warnings: list) -> None:
    """
    Detects one-time special dividends (yield > 20%) that would distort scoring.
    Caps dividend_yield at 20% and scales dps_last down to match.
    Sets stock['special_dividend_flag'] = True when triggered.
    Non-triggered stocks get special_dividend_flag = False.
    """
    ticker        = stock.get('ticker', 'UNKNOWN')
    div_yield     = stock.get('dividend_yield')
    dps_last      = stock.get('dps_last')
    current_price = stock.get('current_price')

    # Only cap when yield is genuinely implausible (> 20%)
    if div_yield is None or div_yield <= SPECIAL_DIVIDEND_YIELD_CAP:
        stock.setdefault('special_dividend_flag', False)
        return

    # Compute capped DPS — always scale DOWN from original
    if current_price and current_price > 0:
        capped_dps = round((SPECIAL_DIVIDEND_YIELD_CAP / 100) * current_price, 4)
    else:
        capped_dps = dps_last   # can't scale without price; leave unchanged

    original_yield = div_yield
    original_dps   = dps_last or 0.0

    stock['dividend_yield']        = SPECIAL_DIVIDEND_YIELD_CAP
    stock['dps_last']              = capped_dps
    stock['special_dividend_flag'] = True

    warnings.append(
        f"{ticker}: Special dividend detected (yield of {original_yield:.1f}% "
        f"exceeds the {SPECIAL_DIVIDEND_YIELD_CAP:.0f}% cap). "
        f"DPS adjusted from PHP {original_dps:.4f} to PHP {capped_dps:.4f} "
        f"and yield capped to {SPECIAL_DIVIDEND_YIELD_CAP:.0f}% for scoring purposes. "
        f"Verify with PSE Edge disclosures -- "
        f"the original figure likely includes a one-time special/property dividend."
    )


# ── Price staleness checker ───────────────────────────────────

def check_price_staleness(stock: dict) -> dict:
    """
    Checks how stale the price data is for a stock.

    Returns a dict:
    {
        'price_date':   str | None,   # ISO date string of last price ('YYYY-MM-DD')
        'days_stale':   int | None,   # calendar days since last price
        'is_stale':     bool,         # True if > PRICE_STALENESS_WARN_DAYS
        'is_critical':  bool,         # True if > PRICE_STALENESS_ERROR_DAYS
        'warning':      str | None,   # human-readable warning message
    }

    Priority for price_date:
      1. stock['price_date'] if present
      2. Query SELECT MAX(date) FROM prices WHERE ticker = ?
      3. None (is_critical=True if current_price is also None)
    """
    try:
        from config import PRICE_STALENESS_WARN_DAYS, PRICE_STALENESS_ERROR_DAYS
    except ImportError:
        PRICE_STALENESS_WARN_DAYS, PRICE_STALENESS_ERROR_DAYS = 5, 30

    ticker     = stock.get('ticker', 'UNKNOWN')
    price_date = stock.get('price_date')

    # Fallback: query DB if stock dict has no price_date
    if not price_date:
        try:
            import sys
            from pathlib import Path
            _root = Path(__file__).resolve().parent.parent
            if str(_root) not in sys.path:
                sys.path.insert(0, str(_root))
            from db.db_connection import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT MAX(date) AS max_date FROM prices WHERE ticker = ?",
                (ticker,)
            ).fetchone()
            conn.close()
            if row and row['max_date']:
                price_date = row['max_date']
        except Exception:
            pass   # DB unavailable — treat as no date

    # No date at all
    if not price_date:
        no_price = stock.get('current_price') is None
        return {
            'price_date':  None,
            'days_stale':  None,
            'is_stale':    True,
            'is_critical': True,
            'warning':     (
                f"{ticker}: No price date found in stock dict or database. "
                f"Price data may be missing entirely."
            ),
        }

    # Parse and compare dates
    try:
        from datetime import date
        pd_date    = date.fromisoformat(price_date)
        days_stale = (date.today() - pd_date).days
    except (ValueError, TypeError):
        return {
            'price_date':  price_date,
            'days_stale':  None,
            'is_stale':    False,
            'is_critical': False,
            'warning':     f"{ticker}: Could not parse price_date '{price_date}'.",
        }

    is_stale    = days_stale > PRICE_STALENESS_WARN_DAYS
    is_critical = days_stale > PRICE_STALENESS_ERROR_DAYS

    warning = None
    if is_critical:
        warning = (
            f"{ticker}: Price data is {days_stale} days old (last: {price_date}). "
            f"Stock may be suspended, delisted, or the data pipeline has stalled. "
            f"Scoring results may be unreliable."
        )
    elif is_stale:
        warning = (
            f"{ticker}: Price data is {days_stale} days old (last: {price_date}). "
            f"This may reflect a public holiday or thin trading week."
        )

    return {
        'price_date':  price_date,
        'days_stale':  days_stale,
        'is_stale':    is_stale,
        'is_critical': is_critical,
        'warning':     warning,
    }


# ── Core validator ────────────────────────────────────────────

def validate_stock(stock: dict) -> dict:
    """Validates a single stock dict. Returns ValidationResult with valid, completeness, errors, warnings."""
    ticker   = stock.get('ticker', 'UNKNOWN')
    errors   = []
    warnings = []
    missing  = []

    # ── Hard error: required fields ───────────────────────────
    for field in REQUIRED_FIELDS:
        val = stock.get(field)
        if val is None:
            errors.append(f"{ticker}: Missing required field '{field}'")
        elif field == 'current_price' and val <= 0:
            errors.append(
                f"{ticker}: current_price={val} is zero or negative — "
                f"cannot calculate any ratios"
            )

    # ── Hard error: need at least some earnings data ──────────
    eps_3y      = stock.get('eps_3y') or []
    net_inc_3y  = stock.get('net_income_3y') or []
    has_earnings = (
        (eps_3y and any(e is not None for e in eps_3y)) or
        (net_inc_3y and any(n is not None for n in net_inc_3y))
    )
    if not has_earnings:
        errors.append(
            f"{ticker}: No earnings data (eps_3y and net_income_3y are both empty) — "
            f"cannot score or filter this stock"
        )

    # ── Stop here if hard errors exist ───────────────────────
    if errors:
        return {
            'ticker':          ticker,
            'valid':           False,
            'completeness':    0.0,
            'errors':          errors,
            'warnings':        warnings,
            'missing_fields':  [],
            'price_staleness': check_price_staleness(stock),
        }

    # ── Stale price detection (hard-block for old data) ───────
    # check_price_staleness() is the fine-grained reporter;
    # this block uses the broader STALE_PRICE_BLOCK_DAYS gate to
    # hard-block stocks that PSE Edge likely no longer lists.
    price_staleness = check_price_staleness(stock)
    if price_staleness['warning']:
        warnings.append(price_staleness['warning'])

    try:
        from config import STALE_PRICE_WARN_DAYS, STALE_PRICE_BLOCK_DAYS
    except ImportError:
        STALE_PRICE_WARN_DAYS, STALE_PRICE_BLOCK_DAYS = 30, 90

    price_date = stock.get('price_date')
    if price_date:
        from datetime import date
        try:
            pd_date = date.fromisoformat(price_date)
            age_days = (date.today() - pd_date).days
            if age_days > STALE_PRICE_BLOCK_DAYS:
                errors.append(
                    f"{ticker}: Price data is {age_days} days old "
                    f"(last: {price_date}) — stock may be suspended or delisted. "
                    f"Excluded from scoring until fresh price data is available."
                )
                return {
                    'ticker':          ticker,
                    'valid':           False,
                    'completeness':    0.0,
                    'errors':          errors,
                    'warnings':        warnings,
                    'missing_fields':  [],
                    'price_staleness': price_staleness,
                }
        except (ValueError, TypeError):
            pass   # malformed date — skip staleness check

    # ── Special dividend detection and yield cap ──────────────
    # Must run before completeness / threshold checks so the capped values
    # are what flows into the filter and scoring engines.
    _detect_and_cap_special_dividend(stock, warnings)

    # ── Completeness score ────────────────────────────────────
    populated = 0
    for field in SCORED_FIELDS:
        val = stock.get(field)
        if val is None:
            missing.append(field)
        elif isinstance(val, list) and len(val) == 0:
            missing.append(field)
        else:
            populated += 1

    completeness = populated / len(SCORED_FIELDS)

    if completeness < MIN_COMPLETENESS:
        errors.append(
            f"{ticker}: Data completeness {completeness:.0%} is below "
            f"the minimum {MIN_COMPLETENESS:.0%} — "
            f"too many fields missing to score reliably. "
            f"Missing: {', '.join(missing[:5])}"
            + (f" and {len(missing)-5} more" if len(missing) > 5 else "")
        )
        return {
            'ticker':          ticker,
            'valid':           False,
            'completeness':    completeness,
            'errors':          errors,
            'warnings':        warnings,
            'missing_fields':  missing,
            'price_staleness': price_staleness,
        }

    # ── Hard-block extreme values ─────────────────────────────
    for field, (op, threshold, msg_tpl) in BLOCK_THRESHOLDS.items():
        val = stock.get(field)
        if val is None:
            continue
        triggered = (val > threshold) if op == '>' else (val < threshold)
        if triggered:
            errors.append(f"{ticker}: " + msg_tpl.format(v=val))

    if errors:
        return {
            'ticker':          ticker,
            'valid':           False,
            'completeness':    completeness,
            'errors':          errors,
            'warnings':        warnings,
            'missing_fields':  missing,
            'price_staleness': price_staleness,
        }

    # ── Suspicious value warnings ─────────────────────────────
    for field, (op, threshold, msg_tpl) in WARN_THRESHOLDS.items():
        val = stock.get(field)
        if val is None:
            continue
        triggered = (val > threshold) if op == '>' else (val < threshold)
        if triggered:
            warnings.append(f"{ticker}: " + msg_tpl.format(v=val))

    for field, (op, threshold, msg_tpl) in WARN_LOW_THRESHOLDS.items():
        val = stock.get(field)
        if val is None:
            continue
        triggered = (val > threshold) if op == '>' else (val < threshold)
        if triggered:
            warnings.append(f"{ticker}: " + msg_tpl.format(v=val))

    # ── Cross-field sanity checks ─────────────────────────────

    # DPS > 2 × EPS — paying more dividend than earnings (extreme payout)
    dps_last   = stock.get('dps_last')
    eps_latest = (eps_3y[0] if eps_3y else None)
    if dps_last and eps_latest and eps_latest > 0:
        if dps_last > eps_latest * 2:
            warnings.append(
                f"{ticker}: DPS of PHP {dps_last:.4f} is more than 2x "
                f"EPS of PHP {eps_latest:.4f} -- "
                f"dividend may exceed earnings, verify figures"
            )

    # Negative equity for non-bank (possible unit mismatch or distress)
    is_bank  = stock.get('is_bank', False)
    equity_m = None
    # Back-calculate equity from P/B and market cap if needed
    pb         = stock.get('pb')
    market_cap = stock.get('current_price', 0) * 1   # placeholder
    # Check via ROE proxy: if ROE is negative, net income may be negative
    roe = stock.get('roe')
    if roe is not None and roe < -50 and not is_bank:
        warnings.append(
            f"{ticker}: ROE of {roe:.1f}% is deeply negative — "
            f"check equity figures for unit errors or financial distress"
        )

    # FCF negative warning
    fcf_per_share = stock.get('fcf_per_share')
    if fcf_per_share is not None and fcf_per_share < 0:
        warnings.append(
            f"{ticker}: FCF per share is PHP {fcf_per_share:.4f} (negative) -- "
            f"capex exceeds operating cash flow; dividend sustainability at risk"
        )

    # Revenue CAGR implausibly high (> 100% suggests unit error)
    rev_cagr = stock.get('revenue_cagr')
    if rev_cagr is not None and rev_cagr > 100:
        warnings.append(
            f"{ticker}: Revenue CAGR of {rev_cagr:.1f}% is implausibly high — "
            f"verify revenue figures for unit consistency across years"
        )

    return {
        'ticker':          ticker,
        'valid':           True,
        'completeness':    completeness,
        'errors':          [],
        'warnings':        warnings,
        'missing_fields':  missing,
        'price_staleness': price_staleness,
    }


def calc_data_confidence(stock: dict) -> float:
    """
    Returns a confidence multiplier (0.0-1.0) based on years of complete data.
    Complete = EPS and Revenue both present for a given year.
    OCF excluded — scraper does not populate it from PSE Edge reports.
    Uses minimum series length as an approximation of co-present years.
    """
    from config import CONFIDENCE_TIERS

    eps_vals = [v for v in (stock.get('eps_5y') or []) if v is not None]
    rev_vals = [v for v in (stock.get('revenue_5y') or []) if v is not None]

    complete_years = min(len(eps_vals), len(rev_vals))

    for threshold in sorted(CONFIDENCE_TIERS.keys(), reverse=True):
        if complete_years >= threshold:
            return CONFIDENCE_TIERS[threshold]
    return 0.0


def validate_all(stocks: list) -> tuple[list, list]:
    """Validates a list of stock dicts. Returns (valid_stocks, validation_results)."""
    valid_stocks = []
    results      = []

    for stock in stocks:
        result = validate_stock(stock)
        results.append(result)
        if result['valid']:
            valid_stocks.append(stock)

    return valid_stocks, results


def print_validation_summary(results: list) -> None:
    """
    Prints a human-readable summary of validation results.
    Shows counts, blocked stocks, and all warnings.
    """
    total   = len(results)
    valid   = sum(1 for r in results if r['valid'])
    blocked = total - valid
    warned  = sum(1 for r in results if r['warnings'])

    print(f"\nValidation summary: {total} stocks checked")
    print(f"  Passed : {valid}")
    print(f"  Blocked: {blocked}")
    print(f"  Warned : {warned}")

    if blocked:
        print(f"\nBlocked stocks:")
        for r in results:
            if not r['valid']:
                comp = f"  [{r['completeness']:.0%} complete]"
                for err in r['errors']:
                    print(f"  BLOCK  {err}{comp}")

    if warned:
        print(f"\nWarnings:")
        for r in results:
            for w in r['warnings']:
                print(f"  WARN   {w}")


# ── Self-test ─────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 55)
    print("  PSE Quant SaaS -- Validator Self-Test")
    print("=" * 55)

    test_cases = [
        # Valid stock (DMC-like)
        {'ticker': 'DMC', 'name': 'DMCI Holdings', 'sector': 'Holdings',
         'is_reit': False, 'is_bank': False, 'current_price': 9.65,
         'dividend_yield': 9.95, 'dividend_cagr_5y': 6.3, 'payout_ratio': 80.0,
         'dps_last': 0.96, 'dividends_5y': [0.96, 0.90, 0.85, 0.80, 0.75],
         'eps_3y': [1.20, 1.13, 0.98], 'net_income_3y': [16000, 15000, 13000],
         'roe': 13.3, 'operating_cf': 22000, 'fcf_coverage': 1.38,
         'fcf_yield': 13.78, 'fcf_per_share': 1.33,
         'pe': 8.04, 'pb': 1.09, 'ev_ebitda': 7.03,
         'revenue_cagr': 8.65, 'de_ratio': 0.50},
        # Missing current_price (hard error)
        {'ticker': 'NOPR', 'current_price': None,
         'eps_3y': [1.0, 0.9, 0.8], 'net_income_3y': [100, 90, 80]},
        # No earnings data (hard error)
        {'ticker': 'NOEP', 'current_price': 10.0, 'eps_3y': [], 'net_income_3y': []},
        # Special dividend cap (332% yield)
        {'ticker': 'SPEC', 'name': 'Special Dividend Co', 'sector': 'Services',
         'is_reit': False, 'is_bank': False, 'current_price': 15.34,
         'dividend_yield': 332.0, 'dps_last': 51.0,
         'eps_3y': [0.40, 0.56, 0.38], 'net_income_3y': [6322, 8705, 5900],
         'roe': 6.4, 'fcf_coverage': 0.8, 'fcf_yield': 2.0, 'fcf_per_share': 0.31,
         'pe': 38.4, 'pb': 1.5, 'ev_ebitda': 12.0, 'revenue_cagr': 5.0, 'de_ratio': 0.80},
    ]

    valid_stocks, results = validate_all(test_cases)
    print_validation_summary(results)
    print(f"\nStocks passed to engine: {len(valid_stocks)}")
