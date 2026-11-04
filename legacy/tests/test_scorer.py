import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from scorer import score_dividend, score_value, score_hybrid

# ============================================================
# Test stocks with real-world PSE numbers
# ============================================================

stocks = [
    {
        'name': 'DMC (DMCI Holdings)',
        'ticker': 'DMC',
        'is_reit': False,
        'dividend_yield':       8.35,
        'dividend_cagr_5y':     4.50,
        'payout_ratio':        25.26,
        'fcf_coverage':         1.84,
        'net_income_3y':       [16000, 17500, 18500],
        'eps_3y':              [1.20, 1.35, 1.45],
        'eps_5y':              [1.45, 1.35, 1.20, 1.05, 0.90],
        'revenue_5y':          [112000, 105000, 98000, 92000, 85000, 78000],
        'operating_cf':        20000,
        'operating_cf_history': [20000, 18000, 15000, 13000, 11000, 9000],
        'dividends_5y':        [0.96, 0.90, 0.85, 0.80, 0.75],
        'roe':                 15.55,
        'pe':                   3.03,
        'pb':                   1.10,
        'ev_ebitda':           13.12,
        'revenue_cagr':         6.73,
        'de_ratio':             0.50,
        'fcf_yield':            5.47,
        'interest_coverage':    8.5,
    },
    {
        'name': 'AREIT (Ayala REIT)',
        'ticker': 'AREIT',
        'is_reit': True,
        'dividend_yield':       6.20,
        'dividend_cagr_5y':     8.00,
        'payout_ratio':        93.00,
        'fcf_coverage':         1.20,
        'net_income_3y':       [3200, 3500, 3800],
        'eps_3y':              [0.80, 0.88, 0.95],
        'eps_5y':              [0.95, 0.88, 0.80, 0.72, 0.65],
        'revenue_5y':          [6600, 6000, 5500, 5000, 4500],
        'operating_cf':        3900,
        'operating_cf_history': [3900, 3500, 3100, 2800, 2500],
        'dividends_5y':        [2.17, 2.00, 1.85, 1.70, 1.55],
        'roe':                 10.50,
        'pe':                  16.00,
        'pb':                   1.40,
        'ev_ebitda':            9.50,
        'revenue_cagr':         9.20,
        'de_ratio':             0.30,
        'fcf_yield':            4.80,
        'interest_coverage':    5.0,
    },
    {
        'name': 'BDO (BDO Unibank)',
        'ticker': 'BDO',
        'is_reit': False,
        'dividend_yield':       2.80,
        'dividend_cagr_5y':     7.00,
        'payout_ratio':        35.00,
        'fcf_coverage':         2.50,
        'net_income_3y':       [42000, 48000, 55000],
        'eps_3y':              [3.50, 4.00, 4.60],
        'eps_5y':              [4.60, 4.00, 3.50, 3.20, 2.80],
        'revenue_5y':          [265000, 240000, 220000, 200000, 180000],
        'operating_cf':        58000,
        'operating_cf_history': [58000, 50000, 44000, 38000, 33000],
        'dividends_5y':        [4.50, 4.20, 3.80, 3.50, 3.20],
        'roe':                 14.20,
        'pe':                  10.50,
        'pb':                   1.20,
        'ev_ebitda':            8.20,
        'revenue_cagr':        11.50,
        'de_ratio':             7.20,
        'fcf_yield':            6.20,
        'interest_coverage':    4.0,
    },
]

# ============================================================
# Run all three scoring functions
# ============================================================

def print_breakdown(breakdown: dict):
    for metric, data in breakdown.items():
        sub   = data['score']
        wt    = data['weight']
        contrib = round(sub * wt, 1)
        bar   = '#' * int(sub / 10)
        print(f"    {metric:<20} {sub:>5.1f}/100  x{wt:.0%}  = {contrib:>4.1f}  {bar}")

for stock in stocks:
    print()
    print("=" * 60)
    print(f"  {stock['name']}")
    print("=" * 60)

    d_score, d_break = score_dividend(stock)
    v_score, v_break = score_value(stock)
    h_score, h_break = score_hybrid(stock)

    grade = lambda s: 'A' if s>=80 else 'B' if s>=65 else 'C' if s>=50 else 'D'

    print(f"\n  DIVIDEND SCORE:  {d_score}/100  [{grade(d_score)}]")
    print_breakdown(d_break)

    print(f"\n  VALUE SCORE:     {v_score}/100  [{grade(v_score)}]")
    print_breakdown(v_break)

    print(f"\n  HYBRID SCORE:    {h_score}/100  [{grade(h_score)}]")
    print_breakdown(h_break)

print()
print("=" * 60)
print("  All scoring tests completed!")
print("=" * 60)