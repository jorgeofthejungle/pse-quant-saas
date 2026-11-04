import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'reports'))

from scorer import score_pure_dividend, score_dividend_growth, score_value
from mos import calc_ddm, calc_eps_pe, calc_dcf, calc_mos_price, calc_mos_pct, calc_hybrid_intrinsic
from pdf_generator import generate_report

# ============================================================
# Sample PSE stocks
# ============================================================

raw_stocks = [
    {
        'ticker':          'DMC',
        'name':            'DMCI Holdings',
        'current_price':   11.50,
        'is_reit':         False,
        'is_bank':         False,
        'dividend_yield':   8.35,
        'dividend_cagr_5y': 4.50,
        'payout_ratio':    25.26,
        'fcf_coverage':     1.84,
        'net_income_3y':   [16000, 17500, 18500],
        'roe':             15.55,
        'pe':               3.03,
        'pb':               1.10,
        'ev_ebitda':       13.12,
        'revenue_cagr':     6.73,
        'de_ratio':         0.50,
        'fcf_yield':        5.47,
        'dps_last':         0.96,
        'eps_3y':          [3.50, 3.65, 3.80],
        'fcf_per_share':    5.95,
    },
    {
        'ticker':          'AREIT',
        'name':            'Ayala REIT',
        'current_price':   35.00,
        'is_reit':         True,
        'is_bank':         False,
        'dividend_yield':   6.20,
        'dividend_cagr_5y': 8.00,
        'payout_ratio':    93.00,
        'fcf_coverage':     1.20,
        'net_income_3y':   [3200, 3500, 3800],
        'roe':             10.50,
        'pe':              16.00,
        'pb':               1.40,
        'ev_ebitda':        9.50,
        'revenue_cagr':     9.20,
        'de_ratio':         0.30,
        'fcf_yield':        4.80,
        'dps_last':         2.17,
        'eps_3y':          [2.10, 2.30, 2.50],
        'fcf_per_share':    2.40,
    },
    {
        'ticker':          'BDO',
        'name':            'BDO Unibank',
        'current_price':   130.00,
        'is_reit':         False,
        'is_bank':         True,
        'dividend_yield':   2.80,
        'dividend_cagr_5y': 7.00,
        'payout_ratio':    35.00,
        'fcf_coverage':     2.50,
        'net_income_3y':   [42000, 48000, 55000],
        'roe':             14.20,
        'pe':              10.50,
        'pb':               1.20,
        'ev_ebitda':        8.20,
        'revenue_cagr':    11.50,
        'de_ratio':         7.20,
        'fcf_yield':        6.20,
        'dps_last':         4.50,
        'eps_3y':          [11.20, 12.80, 14.50],
        'fcf_per_share':   18.50,
    },
    {
        'ticker':          'MER',
        'name':            'Manila Electric Company',
        'current_price':   385.00,
        'is_reit':         False,
        'is_bank':         False,
        'dividend_yield':   4.20,
        'dividend_cagr_5y': 5.50,
        'payout_ratio':    62.00,
        'fcf_coverage':     1.65,
        'net_income_3y':   [22000, 24000, 26500],
        'roe':             18.20,
        'pe':              14.50,
        'pb':               2.60,
        'ev_ebitda':       10.20,
        'revenue_cagr':     7.80,
        'de_ratio':         1.20,
        'fcf_yield':        4.10,
        'dps_last':        16.20,
        'eps_3y':          [24.50, 26.00, 28.50],
        'fcf_per_share':   15.80,
    },
    {
        'ticker':          'JFC',
        'name':            'Jollibee Foods Corporation',
        'current_price':   215.00,
        'is_reit':         False,
        'is_bank':         False,
        'dividend_yield':   1.40,
        'dividend_cagr_5y': 3.20,
        'payout_ratio':    45.00,
        'fcf_coverage':     1.30,
        'net_income_3y':   [4800, 6200, 7800],
        'roe':             12.80,
        'pe':              27.50,
        'pb':               3.20,
        'ev_ebitda':       15.80,
        'revenue_cagr':    12.40,
        'de_ratio':         1.80,
        'fcf_yield':        2.80,
        'dps_last':         3.00,
        'eps_3y':          [6.20, 7.80, 9.50],
        'fcf_per_share':    6.00,
    },
]

# ============================================================
# Score and calculate MoS for all stocks
# ============================================================

def process_stocks(raw_stocks, portfolio_type):
    processed = []
    for s in raw_stocks:
        if portfolio_type == 'pure_dividend':
            score, breakdown = score_pure_dividend(s)
        elif portfolio_type == 'value':
            score, breakdown = score_value(s)
        else:
            score, breakdown = score_dividend_growth(s)

        ddm_val, _ = calc_ddm(s['dps_last'], s['dividend_cagr_5y'])
        eps_val, _ = calc_eps_pe(s['eps_3y'], roe=s['roe'])
        dcf_val, _ = calc_dcf(s['fcf_per_share'], s['revenue_cagr'])

        if portfolio_type in ('pure_dividend', 'dividend_growth'):
            iv = ddm_val
        elif portfolio_type == 'value':
            iv = eps_val
        else:
            iv, _ = calc_hybrid_intrinsic(ddm_val, eps_val, dcf_val)

        mos_price = calc_mos_price(iv, portfolio_type)
        mos_pct   = calc_mos_pct(iv, s['current_price'])

        processed.append({
            **s,
            'score':           score,
            'score_breakdown': breakdown,
            'intrinsic_value': iv,
            'mos_price':       mos_price,
            'mos_pct':         mos_pct,
        })

    processed.sort(key=lambda x: x['score'], reverse=True)
    return processed

# ============================================================
# Generate reports — saving directly to Desktop for now
# ============================================================

# Save to Desktop so we can easily find and open the PDFs
DESKTOP = os.path.join(os.path.expanduser('~'), 'Desktop')

portfolios = ['pure_dividend', 'dividend_growth', 'value']

for portfolio in portfolios:
    print(f"Generating {portfolio.upper()} report...")
    ranked = process_stocks(raw_stocks, portfolio)

    output_path = os.path.join(
        DESKTOP,
        f'PSE_{portfolio.upper()}_REPORT.pdf'
    )

    generate_report(
        portfolio_type        = portfolio,
        ranked_stocks         = ranked,
        output_path           = output_path,
        total_stocks_screened = len(raw_stocks),
    )

print()
print("=" * 50)
print("All 3 reports generated!")
print(f"Check your Desktop for the PDF files.")
print("=" * 50)