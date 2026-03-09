import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from filters import (
    filter_pure_dividend_portfolio   as filter_dividend_portfolio,
    filter_value_portfolio,
    filter_dividend_growth_portfolio as filter_hybrid_portfolio,
)

# ============================================================
# Test stocks — some will pass, some will fail on purpose
# This proves the filters are working correctly
# ============================================================

stocks = [
    {
        'ticker': 'DMC',
        'is_reit': False,
        'is_bank': False,
        'net_income_3y': [16000, 17500, 18500],
        'dividends_5y': [0.80, 0.85, 0.90, 0.93, 0.96],
        'payout_ratio': 25.26,
        'de_ratio': 0.50,
        'operating_cf': 22000,
        'fcf_3y': [15000, 16500, 17500],
    },
    {
        'ticker': 'AREIT',
        'is_reit': True,
        'is_bank': False,
        'net_income_3y': [3200, 3500, 3800],
        'dividends_5y': [0.80, 0.85, 0.88, 0.90, 0.93],
        'payout_ratio': 93.0,
        'de_ratio': 0.30,
        'operating_cf': 4200,
        'fcf_3y': [3800, 4000, 4200],
    },
    {
        'ticker': 'BDO',
        'is_reit': False,
        'is_bank': True,
        'net_income_3y': [42000, 48000, 55000],
        'dividends_5y': [2.00, 2.20, 2.40, 2.60, 2.80],
        'payout_ratio': 35.0,
        'de_ratio': 7.20,
        'operating_cf': 65000,
        'fcf_3y': [58000, 61000, 65000],
    },
    {
        'ticker': 'BADSTOCK',
        'is_reit': False,
        'is_bank': False,
        'net_income_3y': [5000, -2000, -1000],
        'dividends_5y': [0.50, 0, 0, 0, 0],
        'payout_ratio': 95.0,
        'de_ratio': 3.50,
        'operating_cf': -1000,
        'fcf_3y': [1000, -500, -800],
    },
]

# ============================================================
# Run all three filters on all four stocks
# ============================================================

portfolios = [
    ('DIVIDEND', filter_dividend_portfolio),
    ('VALUE',    filter_value_portfolio),
    ('HYBRID',   filter_hybrid_portfolio),
]

for portfolio_name, filter_func in portfolios:
    print()
    print("=" * 55)
    print(f"  {portfolio_name} PORTFOLIO FILTER RESULTS")
    print("=" * 55)
    for stock in stocks:
        eligible, reason = filter_func(stock)
        status = "PASS" if eligible else "FAIL"
        print(f"  {status}  |  {reason}")

print()
print("=" * 55)
print("  All filter tests completed!")
print("=" * 55)