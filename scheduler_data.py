# ============================================================
# scheduler_data.py — Stock Loading & Pipeline Config Maps
# PSE Quant SaaS — scheduler sub-module
# ============================================================

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'db'))

from filters import (filter_pure_dividend_portfolio,
                     filter_dividend_growth_portfolio,
                     filter_value_portfolio)
from scorer  import score_pure_dividend, score_dividend_growth, score_value

# Try importing the scraper (may fail if dependencies not set up yet)
try:
    from scraper.pse_scraper import load_stocks_from_db
    SCRAPER_AVAILABLE = True
except ImportError:
    try:
        sys.path.insert(0, str(ROOT / 'scraper'))
        from pse_scraper import load_stocks_from_db
        SCRAPER_AVAILABLE = True
    except ImportError:
        SCRAPER_AVAILABLE = False
        print("WARNING: pse_scraper not available — will use sample data.")

# ── Pipeline lookup maps ───────────────────────────────────────
FILTERS = {
    'pure_dividend':   filter_pure_dividend_portfolio,
    'dividend_growth': filter_dividend_growth_portfolio,
    'value':           filter_value_portfolio,
}

SCORERS = {
    'pure_dividend':   score_pure_dividend,
    'dividend_growth': score_dividend_growth,
    'value':           score_value,
}

PORTFOLIO_NAMES = {
    'pure_dividend':   'Pure Dividend',
    'dividend_growth': 'Dividend Growth',
    'value':           'Value',
}


def load_sample_stocks():
    """Sample data fallback — used when DB is not yet populated."""
    return [
        {
            'ticker': 'DMC', 'name': 'DMCI Holdings',
            'sector': 'Holdings', 'is_reit': False, 'is_bank': False,
            'current_price': 11.50, 'dividend_yield': 8.35,
            'dividend_cagr_5y': 4.50, 'payout_ratio': 25.26,
            'dps_last': 0.96, 'dividends_5y': [0.96, 0.90, 0.85, 0.80, 0.75],
            'eps_3y': [3.50, 3.65, 3.80], 'net_income_3y': [16000, 17500, 18500],
            'roe': 15.55, 'operating_cf': 22000, 'fcf_coverage': 1.84,
            'fcf_yield': 5.47, 'fcf_per_share': 5.95,
            'fcf_3y': [18000, 20000, 22000], 'pe': 3.03, 'pb': 1.10,
            'ev_ebitda': 13.12, 'revenue_cagr': 6.73, 'de_ratio': 0.50,
        },
        {
            'ticker': 'AREIT', 'name': 'Ayala REIT',
            'sector': 'Real Estate', 'is_reit': True, 'is_bank': False,
            'current_price': 35.00, 'dividend_yield': 6.20,
            'dividend_cagr_5y': 8.00, 'payout_ratio': 93.00,
            'dps_last': 2.17, 'dividends_5y': [2.17, 2.00, 1.85, 1.70, 1.55],
            'eps_3y': [2.10, 2.30, 2.50], 'net_income_3y': [3200, 3500, 3800],
            'roe': 10.50, 'operating_cf': 4500, 'fcf_coverage': 1.20,
            'fcf_yield': 4.80, 'fcf_per_share': 2.40,
            'fcf_3y': [3800, 4000, 4200], 'pe': 16.00, 'pb': 1.40,
            'ev_ebitda': 9.50, 'revenue_cagr': 9.20, 'de_ratio': 0.30,
        },
        {
            'ticker': 'BDO', 'name': 'BDO Unibank',
            'sector': 'Banking', 'is_reit': False, 'is_bank': True,
            'current_price': 130.00, 'dividend_yield': 2.80,
            'dividend_cagr_5y': 7.00, 'payout_ratio': 35.00,
            'dps_last': 4.50, 'dividends_5y': [4.50, 4.20, 3.80, 3.50, 3.20],
            'eps_3y': [11.20, 12.80, 14.50], 'net_income_3y': [42000, 48000, 55000],
            'roe': 14.20, 'operating_cf': 65000, 'fcf_coverage': 2.50,
            'fcf_yield': 6.20, 'fcf_per_share': 18.50,
            'fcf_3y': [50000, 55000, 60000], 'pe': 10.50, 'pb': 1.20,
            'ev_ebitda': 8.20, 'revenue_cagr': 11.50, 'de_ratio': 7.20,
        },
        {
            'ticker': 'MER', 'name': 'Manila Electric Company',
            'sector': 'Utilities', 'is_reit': False, 'is_bank': False,
            'current_price': 385.00, 'dividend_yield': 4.20,
            'dividend_cagr_5y': 5.50, 'payout_ratio': 62.00,
            'dps_last': 16.20, 'dividends_5y': [16.20, 15.00, 14.00, 13.00, 12.00],
            'eps_3y': [24.50, 26.00, 28.50], 'net_income_3y': [22000, 24000, 26500],
            'roe': 18.20, 'operating_cf': 30000, 'fcf_coverage': 1.65,
            'fcf_yield': 4.10, 'fcf_per_share': 15.80,
            'fcf_3y': [25000, 27000, 30000], 'pe': 14.50, 'pb': 2.60,
            'ev_ebitda': 10.20, 'revenue_cagr': 7.80, 'de_ratio': 1.20,
        },
        {
            'ticker': 'JFC', 'name': 'Jollibee Foods Corporation',
            'sector': 'Food & Beverage', 'is_reit': False, 'is_bank': False,
            'current_price': 215.00, 'dividend_yield': 1.40,
            'dividend_cagr_5y': 3.20, 'payout_ratio': 45.00,
            'dps_last': 3.00, 'dividends_5y': [3.00, 2.80, 2.60, 2.40, 2.20],
            'eps_3y': [6.20, 7.80, 9.50], 'net_income_3y': [4800, 6200, 7800],
            'roe': 12.80, 'operating_cf': 9500, 'fcf_coverage': 1.30,
            'fcf_yield': 2.80, 'fcf_per_share': 6.00,
            'fcf_3y': [7000, 8000, 9500], 'pe': 27.50, 'pb': 3.20,
            'ev_ebitda': 15.80, 'revenue_cagr': 12.40, 'de_ratio': 1.80,
        },
    ]


def _load_stocks() -> list:
    """
    Loads stock data. Uses live DB data if available, falls back
    to sample data if DB is not yet populated.
    """
    if SCRAPER_AVAILABLE:
        stocks = load_stocks_from_db()
        if stocks:
            return stocks
    print("  Using sample data (DB not yet populated with real PSE data).")
    return load_sample_stocks()
