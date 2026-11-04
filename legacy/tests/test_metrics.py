import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from metrics import (
    calculate_pe, calculate_pb, calculate_roe, calculate_de,
    calculate_dividend_yield, calculate_payout_ratio, calculate_fcf,
    calculate_fcf_yield, calculate_fcf_coverage, calculate_cagr,
    calculate_ev_ebitda,
)

price          = 11.50
eps            = 3.80
book_value     = 10.45
net_income     = 18500
equity         = 119000
total_debt     = 59500
cash           = 12000
ebitda         = 28000
market_cap     = 320000
dps            = 0.96
operating_cf   = 22000
capex          = 4500
dividends_paid = 9500
revenue_5y     = [42000, 45000, 48500, 51000, 54500]

print("=" * 50)
print("PSE QUANT SAAS - metrics.py Test")
print("Test Stock: DMC (DMCI Holdings)")
print("=" * 50)

pe = calculate_pe(price, eps)
print(f"P/E Ratio:         {pe}x")

pb = calculate_pb(price, book_value)
print(f"P/B Ratio:         {pb}x")

ev_ebitda = calculate_ev_ebitda(market_cap, total_debt, cash, ebitda)
print(f"EV/EBITDA:         {ev_ebitda}x")

roe = calculate_roe(net_income, equity)
print(f"ROE:               {roe}%")

de = calculate_de(total_debt, equity)
print(f"Debt/Equity:       {de}x")

div_yield = calculate_dividend_yield(dps, price)
print(f"Dividend Yield:    {div_yield}%")

payout = calculate_payout_ratio(dps, eps)
print(f"Payout Ratio:      {payout}%")

fcf = calculate_fcf(operating_cf, capex)
print(f"Free Cash Flow:    {fcf}")

fcf_yield = calculate_fcf_yield(fcf, market_cap)
print(f"FCF Yield:         {fcf_yield}%")

fcf_cov = calculate_fcf_coverage(fcf, dividends_paid)
print(f"FCF Coverage:      {fcf_cov}x")

rev_cagr = calculate_cagr(revenue_5y[0], revenue_5y[-1], years=4)
print(f"Revenue CAGR (4Y): {rev_cagr}%")

print("=" * 50)
print("All metrics calculated successfully!")
print("=" * 50)