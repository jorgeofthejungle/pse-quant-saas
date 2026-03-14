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


def compute_sector_stats(all_stocks: list) -> dict:
    """
    Computes dynamic sector medians from the full stock universe.
    Returns dict: sector_name → {median_pe, median_pb, median_ev_ebitda}.

    all_stocks: list of stock dicts (same format as engine stock dict).
    Each stock needs: sector, pe, pb, ev_ebitda.
    """
    # Group valid values by sector
    sector_data: dict[str, dict[str, list]] = {}
    for stock in all_stocks:
        sector = (stock.get('sector') or 'Unknown').strip()
        if sector not in sector_data:
            sector_data[sector] = {'pe': [], 'pb': [], 'ev_ebitda': []}
        pe       = stock.get('pe')
        pb       = stock.get('pb')
        ev_ebitda = stock.get('ev_ebitda')
        # Only include reasonable values (filter out extreme outliers)
        if pe is not None and 0 < pe < 200:
            sector_data[sector]['pe'].append(pe)
        if pb is not None and 0 < pb < 50:
            sector_data[sector]['pb'].append(pb)
        if ev_ebitda is not None and 0 < ev_ebitda < 200:
            sector_data[sector]['ev_ebitda'].append(ev_ebitda)

    result = {}
    for sector, data in sector_data.items():
        med_pe  = _median(data['pe'])
        med_pb  = _median(data['pb'])
        med_ev  = _median(data['ev_ebitda'])

        # Check if we have enough data points
        if len(data['pe']) >= _MIN_SECTOR_SIZE and med_pe is not None:
            result[sector] = {
                'median_pe':       med_pe,
                'median_pb':       med_pb,
                'median_ev_ebitda': med_ev,
                'n_stocks':        len(data['pe']),
                'source':          'dynamic',
            }
        else:
            # Fall back to fixed benchmarks
            fallback = _get_fallback(sector)
            if fallback:
                result[sector] = {**fallback, 'n_stocks': len(data['pe']),
                                   'source': 'fallback'}

    return result


def get_sector_pe(sector: str, sector_stats: dict) -> float | None:
    """
    Returns the sector median PE for a given sector name.
    Tries dynamic stats first, then fallback benchmarks.
    """
    if sector in sector_stats:
        return sector_stats[sector].get('median_pe')
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
