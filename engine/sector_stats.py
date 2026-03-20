# ============================================================
# sector_stats.py — Dynamic Sector Median Computation
# PSE Quant SaaS — Phase 9B (v2 Unified Scorer)
# ============================================================
# Computes sector median PE, PB, and EV/EBITDA from all stocks
# in the current universe. Used for sector-adjusted valuation
# in the Health scorer.
#
# Philippine sectors trade at very different valuation ranges:
#   Banks           → low PE (5-10x)
#   Mining          → low PE (3-8x)
#   Property        → mid PE (8-15x)
#   Holding Firms   → mid PE (8-18x)
#   Utilities       → mid PE (12-20x)
#   Consumer/Retail → higher PE (15-25x)
#   Services        → varies widely
#
# Fixed fallback thresholds are used when a sector has < 5 stocks
# with valid data.
# ============================================================

from __future__ import annotations

# ── Fallback sector benchmarks (manual, for small sectors) ────
# Format: sector_name (lowercase, partial match) → {median_pe, median_pb, median_ev_ebitda}
_FALLBACK_BENCHMARKS = {
    'financials':    {'median_pe': 8.0,  'median_pb': 1.2, 'median_ev_ebitda': 7.0},
    'banking':       {'median_pe': 8.0,  'median_pb': 1.2, 'median_ev_ebitda': 7.0},
    'mining':        {'median_pe': 6.0,  'median_pb': 0.9, 'median_ev_ebitda': 5.0},
    'holding':       {'median_pe': 12.0, 'median_pb': 1.0, 'median_ev_ebitda': 9.0},
    'property':      {'median_pe': 10.0, 'median_pb': 1.3, 'median_ev_ebitda': 12.0},
    'utilities':     {'median_pe': 15.0, 'median_pb': 1.5, 'median_ev_ebitda': 10.0},
    'industrial':    {'median_pe': 14.0, 'median_pb': 1.4, 'median_ev_ebitda': 9.0},
    'services':      {'median_pe': 16.0, 'median_pb': 2.0, 'median_ev_ebitda': 10.0},
    'consumer':      {'median_pe': 18.0, 'median_pb': 2.5, 'median_ev_ebitda': 12.0},
    'reit':          {'median_pe': 20.0, 'median_pb': 1.3, 'median_ev_ebitda': 18.0},
}

_MIN_SECTOR_SIZE = 5  # minimum stocks with valid data to use dynamic median


def _median(values: list) -> float | None:
    """Returns median of a list of numbers. Returns None if empty."""
    clean = sorted(v for v in values if v is not None and v > 0)
    if not clean:
        return None
    n = len(clean)
    mid = n // 2
    if n % 2 == 1:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2


def _cap_weighted_median(values: list, caps: list) -> float:
    """Compute market-cap weighted median."""
    if not values:
        return 0.0
    total_cap = sum(caps) if caps else 0
    if total_cap == 0:
        # Fallback to simple median if no cap data
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return sorted_vals[n // 2] if n % 2 else (sorted_vals[n//2-1] + sorted_vals[n//2]) / 2

    # Sort by value, accumulate cap weight
    paired = sorted(zip(values, caps), key=lambda x: x[0])
    cumulative = 0.0
    for val, cap in paired:
        cumulative += cap / total_cap
        if cumulative >= 0.5:
            return val
    return paired[-1][0]


def compute_sector_stats(all_stocks: list) -> dict:
    """
    Computes market-cap weighted medians for 8 metrics per sector.
    Filters: PE<50, PB<20, EV/EBITDA<50 to exclude outliers.
    Minimum sector size: 3 stocks with valid data.

    Returns: {sector: {pe, pb, ev_ebitda, roe, fcf_yield, dividend_yield, de_ratio, ocf_margin}}
    """
    from collections import defaultdict

    # Group valid data by sector
    sector_data = defaultdict(lambda: {
        'pe': [], 'pb': [], 'ev_ebitda': [], 'roe': [],
        'fcf_yield': [], 'dividend_yield': [], 'de_ratio': [], 'ocf_margin': [],
    })
    sector_caps = defaultdict(lambda: {
        'pe': [], 'pb': [], 'ev_ebitda': [], 'roe': [],
        'fcf_yield': [], 'dividend_yield': [], 'de_ratio': [], 'ocf_margin': [],
    })

    for s in all_stocks:
        sector = s.get('sector') or 'Unknown'
        cap = s.get('market_cap') or 0

        # PE: filter PE > 50 (outlier) and PE <= 0
        pe = s.get('pe')
        if pe and 0 < pe <= 50:
            sector_data[sector]['pe'].append(pe)
            sector_caps[sector]['pe'].append(cap)

        # PB: filter PB > 20
        pb = s.get('pb')
        if pb and 0 < pb <= 20:
            sector_data[sector]['pb'].append(pb)
            sector_caps[sector]['pb'].append(cap)

        # EV/EBITDA: filter > 50
        ev = s.get('ev_ebitda')
        if ev and 0 < ev <= 50:
            sector_data[sector]['ev_ebitda'].append(ev)
            sector_caps[sector]['ev_ebitda'].append(cap)

        # ROE: any value (can be negative for banks at times)
        roe = s.get('roe')
        if roe is not None:
            sector_data[sector]['roe'].append(roe)
            sector_caps[sector]['roe'].append(cap)

        # FCF Yield: positive only
        fcfy = s.get('fcf_yield')
        if fcfy and fcfy > 0:
            sector_data[sector]['fcf_yield'].append(fcfy)
            sector_caps[sector]['fcf_yield'].append(cap)

        # Dividend yield: positive only
        divy = s.get('dividend_yield')
        if divy and divy > 0:
            sector_data[sector]['dividend_yield'].append(divy)
            sector_caps[sector]['dividend_yield'].append(cap)

        # D/E: non-negative
        de = s.get('de_ratio')
        if de is not None and de >= 0:
            sector_data[sector]['de_ratio'].append(de)
            sector_caps[sector]['de_ratio'].append(cap)

        # OCF Margin: ocf / revenue (most recent year)
        ocf = s.get('operating_cf')
        rev_hist = s.get('revenue_5y') or []
        rev = rev_hist[0] if rev_hist else None
        if ocf is not None and rev and rev > 0:
            ocf_margin = (ocf / rev) * 100
            sector_data[sector]['ocf_margin'].append(ocf_margin)
            sector_caps[sector]['ocf_margin'].append(cap)

    # Compute cap-weighted medians (minimum 2 stocks per metric)
    result = {}
    for sector, metrics in sector_data.items():
        sector_result = {}
        for metric, values in metrics.items():
            caps = sector_caps[sector][metric]
            if len(values) >= 2:  # minimum 2 stocks with valid data
                sector_result[metric] = _cap_weighted_median(values, caps)
        if sector_result:
            result[sector] = sector_result

    return result


def get_sector_pe(sector: str, sector_stats: dict) -> float | None:
    """
    Returns the sector median PE for a given sector name.
    Tries dynamic stats first, then fallback benchmarks.
    Supports both new format (key: 'pe') and legacy format (key: 'median_pe').
    """
    if sector in sector_stats:
        stats = sector_stats[sector]
        # New format uses 'pe'; legacy format used 'median_pe'
        return stats.get('pe') or stats.get('median_pe')
    return _get_fallback_pe(sector)


def _get_fallback(sector: str) -> dict | None:
    """Returns fallback benchmark dict for a sector (case-insensitive partial match)."""
    s_lower = sector.lower()
    for key, bench in _FALLBACK_BENCHMARKS.items():
        if key in s_lower:
            return dict(bench)
    return None


def _get_fallback_pe(sector: str) -> float | None:
    """Returns fallback median PE for a sector."""
    fallback = _get_fallback(sector)
    return fallback.get('median_pe') if fallback else None
