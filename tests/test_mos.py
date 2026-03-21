import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mos import (
    calc_ddm,
    calc_eps_pe,
    calc_dcf,
    calc_mos_price,
    calc_mos_pct,
    calc_hybrid_intrinsic,
)

# ============================================================
# Test stocks with real-world PSE numbers
# ============================================================

stocks = [
    {
        'name':            'DMC (DMCI Holdings)',
        'ticker':          'DMC',
        'current_price':   11.50,
        'dps_last':         0.96,
        'dividend_cagr':    4.50,
        'eps_3y':          [3.50, 3.65, 3.80],
        'roe':             15.55,
        'fcf_per_share':    5.95,
        'revenue_cagr':     6.73,
    },
    {
        'name':            'AREIT (Ayala REIT)',
        'ticker':          'AREIT',
        'current_price':   35.00,
        'dps_last':         2.17,
        'dividend_cagr':    8.00,
        'eps_3y':          [2.10, 2.30, 2.50],
        'roe':             10.50,
        'fcf_per_share':    2.40,
        'revenue_cagr':     9.20,
    },
    {
        'name':            'BDO (BDO Unibank)',
        'ticker':          'BDO',
        'current_price':   130.00,
        'dps_last':         4.50,
        'dividend_cagr':    7.00,
        'eps_3y':          [11.20, 12.80, 14.50],
        'roe':             14.20,
        'fcf_per_share':    18.50,
        'revenue_cagr':    11.50,
    },
]

# ============================================================
# Run MoS calculations for all three portfolios
# ============================================================

for stock in stocks:
    print()
    print("=" * 60)
    print(f"  {stock['name']}")
    print(f"  Current Price: ₱{stock['current_price']}")
    print("=" * 60)

    # ── Method 1: DDM ──
    ddm_val, ddm_msg = calc_ddm(
        dps_last       = stock['dps_last'],
        dividend_cagr  = stock['dividend_cagr'],
    )
    print(f"\n  💰 DDM (Dividend Discount Model)")
    print(f"     {ddm_msg}")
    if ddm_val:
        print(f"     Intrinsic Value : ₱{ddm_val}")

    # ── Method 2: EPS-PE ──
    eps_val, eps_msg = calc_eps_pe(
        eps_3y    = stock['eps_3y'],
        roe       = stock['roe'],
    )
    print(f"\n  📊 EPS x Target PE")
    print(f"     {eps_msg}")
    if eps_val:
        print(f"     Intrinsic Value : ₱{eps_val}")

    # ── Method 3: DCF ──
    dcf_val, dcf_msg = calc_dcf(
        fcf_per_share = stock['fcf_per_share'],
        growth_rate   = stock['revenue_cagr'],
    )
    print(f"\n  📈 DCF (Discounted Cash Flow)")
    print(f"     {dcf_msg}")
    if dcf_val:
        print(f"     Intrinsic Value : ₱{dcf_val}")

    # ── Hybrid Blend ──
    hybrid_val, hybrid_msg = calc_hybrid_intrinsic(
        ddm_value    = ddm_val,
        eps_pe_value = eps_val,
        dcf_value    = dcf_val,
    )

    print(f"\n  ⚖️  Hybrid Blend: {hybrid_msg}")

    # ── MoS Summary ──
    print(f"\n  {'─' * 50}")
    print(f"  MARGIN OF SAFETY SUMMARY")
    print(f"  {'─' * 50}")

    for portfolio, iv in [
        ('pure_dividend',   ddm_val),
        ('value',           eps_val),
        ('dividend_growth', hybrid_val),
    ]:
        if iv is None:
            continue
        mos_price = calc_mos_price(iv, portfolio)
        mos_pct   = calc_mos_pct(iv, stock['current_price'])
        signal    = '🟢 BELOW IV' if mos_pct and mos_pct > 0 else '🔴 ABOVE IV'
        cushion   = '✓ BUY ZONE' if mos_price and stock['current_price'] <= mos_price else '✗ WAIT'

        print(f"\n  {portfolio.upper()} PORTFOLIO")
        print(f"     Intrinsic Value : ₱{iv}")
        print(f"     MoS Buy Price   : ₱{mos_price}  ({cushion})")
        print(f"     Current MoS     : {mos_pct}%  {signal}")

print()
print("=" * 60)
print("  All MoS calculations completed!")
print("=" * 60)
print()
print("  DISCLAIMER: These are mathematical computations only.")
print("  Not investment advice. Do your own due diligence.")
print("=" * 60)