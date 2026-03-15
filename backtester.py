# ============================================================
# backtester.py — Historical Fundamental Score Simulation
# PSE Quant SaaS — Phase 7
# ============================================================
# Reruns the scoring model for each historical year using only
# the annual financials available at that point in time.
# Uses current prices (no multi-year price archive).
# Educational only — not a price-return backtest.
#
# CLI: py backtester.py --years 2022 2023 2024 2025           (unified, default)
#      py backtester.py --mode legacy --portfolio value --years 2022 2023 2024 2025
# ============================================================

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'engine'))

import database as db
from metrics import (calculate_roe, calculate_de, calculate_dividend_yield,
                     calculate_payout_ratio, calculate_cagr, calculate_fcf,
                     calculate_fcf_yield, calculate_fcf_coverage,
                     calculate_ev_ebitda)

# ── Legacy scorer imports (kept for --mode legacy) ────────────
from filters import (filter_pure_dividend_portfolio,
                     filter_dividend_growth_portfolio,
                     filter_value_portfolio)
from scorer import score_dividend, score_value, score_hybrid

# ── Unified v2 scorer imports ─────────────────────────────────
from engine.filters_v2   import filter_unified
from engine.scorer_v2    import score_unified
from engine.sector_stats import compute_sector_stats


# ── Constants ─────────────────────────────────────────────────

PORTFOLIO_FILTERS = {
    'pure_dividend':   filter_pure_dividend_portfolio,
    'dividend_growth': filter_dividend_growth_portfolio,
    'value':           filter_value_portfolio,
}

PORTFOLIO_SCORERS = {
    'pure_dividend':   score_dividend,
    'dividend_growth': score_dividend,   # uses same scorer as pure_dividend
    'value':           score_value,
}

DISCLAIMER = (
    "DISCLAIMER: This is a mathematical simulation for educational use only.\n"
    "Historical fundamental quality does not guarantee future price performance.\n"
    "Intrinsic value figures are estimates, not price targets. Not investment advice."
)

DEFAULT_YEARS = [2022, 2023, 2024, 2025]


# ── Metric builder (historical) ───────────────────────────────

def _build_metrics_as_of(ticker: str, as_of_year: int, conn) -> dict | None:
    """Builds stock metrics dict using financials up to as_of_year + current price."""
    stock_row = conn.execute(
        "SELECT ticker, name, sector, is_reit, is_bank FROM stocks WHERE ticker = ?",
        (ticker,)
    ).fetchone()
    if not stock_row:
        return None

    # Current price (we use latest available — see module docstring)
    price_row = conn.execute(
        "SELECT close, market_cap FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    if not price_row:
        return None

    current_price = price_row['close']
    market_cap    = price_row['market_cap']

    # Historical financials up to as_of_year
    fin_rows = conn.execute("""
        SELECT year, revenue, net_income, equity, total_debt, cash,
               operating_cf, capex, ebitda, eps, dps
        FROM financials
        WHERE ticker = ? AND year <= ?
        ORDER BY year DESC LIMIT 10
    """, (ticker, as_of_year)).fetchall()

    if not fin_rows:
        return None

    fins = [dict(r) for r in fin_rows]

    # Most recent year with actual financial data
    f0 = next(
        (f for f in fins
         if f.get('net_income') is not None or f.get('eps') is not None
            or f.get('revenue') is not None),
        fins[0]
    )

    shares = (market_cap / current_price) if (market_cap and current_price) else None

    # Multi-year lists (newest first)
    eps_3y     = [f['eps']        for f in fins if f['eps']        is not None][:3]
    eps_5y     = [f['eps']        for f in fins if f['eps']        is not None]
    net_inc_3y = [f['net_income'] for f in fins if f['net_income'] is not None][:3]
    dps_vals   = [f['dps']        for f in fins if f['dps']        is not None]
    rev_vals   = [f['revenue']    for f in fins if f['revenue']    is not None]
    revenue_5y = rev_vals[:]
    operating_cf_history = [f['operating_cf'] for f in fins if f['operating_cf'] is not None]

    # DPS: prefer completed-year data (no partial-year current entries)
    completed_dps = [(f['year'], f['dps']) for f in fins
                     if f['dps'] is not None and f['year'] < as_of_year]
    dps_last = (completed_dps[0][1] if completed_dps
                else (dps_vals[0] if dps_vals else None))

    # Ratios
    eps_latest = f0.get('eps')
    pe = (current_price / eps_latest) if (eps_latest and eps_latest > 0) else None

    equity_m = f0.get('equity')
    pb = None
    if market_cap and equity_m and equity_m > 0:
        pb = round(market_cap / (equity_m * 1_000_000), 2)

    roe      = calculate_roe(f0.get('net_income'), equity_m)
    td       = f0.get('total_debt')
    de_ratio = calculate_de(td, equity_m) if td is not None else None

    div_yield    = calculate_dividend_yield(dps_last, current_price) if dps_last else None
    payout_ratio = calculate_payout_ratio(dps_last, eps_latest) if dps_last else None

    dividend_cagr = None
    if len(completed_dps) >= 2:
        ny, nd = completed_dps[0]; oy, od = completed_dps[-1]
        span = ny - oy
        if span > 0 and od and od > 0:
            dividend_cagr = calculate_cagr(od, nd, span)
    elif len(dps_vals) >= 2:
        dividend_cagr = calculate_cagr(dps_vals[-1], dps_vals[0], len(dps_vals) - 1)

    revenue_cagr = None
    if len(rev_vals) >= 2:
        revenue_cagr = calculate_cagr(rev_vals[-1], rev_vals[0], len(rev_vals) - 1)

    cf_row = next((f for f in fins if f.get('operating_cf') is not None), None)
    op_cf  = cf_row.get('operating_cf') if cf_row else None
    capex  = cf_row.get('capex')        if cf_row else None

    fcf_m = calculate_fcf(op_cf, capex) if (op_cf is not None and capex is not None) else None

    fcf_yield_val = None
    fcf_per_share = None
    fcf_coverage  = None

    if fcf_m is not None:
        if market_cap:
            fcf_yield_val = calculate_fcf_yield(fcf_m * 1_000_000, market_cap)
        if shares:
            fcf_per_share = round(fcf_m * 1_000_000 / shares, 4)
        if dps_last and shares:
            div_paid_m = dps_last * shares / 1_000_000
            fcf_coverage = calculate_fcf_coverage(fcf_m, div_paid_m)

    ebitda     = f0.get('ebitda')
    total_debt = f0.get('total_debt')
    cash       = f0.get('cash')
    ev_ebitda  = None
    if market_cap and total_debt is not None and cash is not None:
        ev_ebitda = calculate_ev_ebitda(
            market_cap / 1_000_000, total_debt, cash, ebitda
        )

    return {
        'ticker':               stock_row['ticker'],
        'name':                 stock_row['name'],
        'sector':               stock_row['sector'],
        'is_reit':              bool(stock_row['is_reit']),
        'is_bank':              bool(stock_row['is_bank']),
        'current_price':        current_price,
        'dividend_yield':       div_yield,
        'dividend_cagr_5y':     dividend_cagr,
        'payout_ratio':         payout_ratio,
        'dps_last':             dps_last,
        'dividends_5y':         dps_vals[:5],
        'eps_3y':               eps_3y,
        'eps_5y':               eps_5y,
        'net_income_3y':        net_inc_3y,
        'roe':                  roe,
        'operating_cf':         op_cf,
        'operating_cf_history': operating_cf_history,
        'fcf_coverage':         fcf_coverage,
        'fcf_yield':            fcf_yield_val,
        'fcf_per_share':        fcf_per_share,
        'fcf_3y':               [],
        'pe':                   pe,
        'pb':                   pb,
        'ev_ebitda':            ev_ebitda,
        'revenue_cagr':         revenue_cagr,
        'revenue_5y':           revenue_5y,
        'de_ratio':             de_ratio,
        'interest_coverage':    None,
        'avg_daily_value_6m':   None,
        'special_dividend_flag': False,
    }


# ── Simulation runner ─────────────────────────────────────────

def run_simulation(portfolio_type: str, as_of_year: int) -> list:
    """
    Scores all tickers using financials up to as_of_year.
    Returns a ranked list of dicts: {ticker, name, score, rank, eligible}.
    """
    conn        = db.get_connection()
    tickers     = [r['ticker'] for r in conn.execute(
        "SELECT ticker FROM stocks ORDER BY ticker"
    ).fetchall()]

    filt_fn  = PORTFOLIO_FILTERS[portfolio_type]
    score_fn = PORTFOLIO_SCORERS[portfolio_type]

    eligible = []
    for ticker in tickers:
        metrics = _build_metrics_as_of(ticker, as_of_year, conn)
        if not metrics:
            continue
        ok, _ = filt_fn(metrics)
        if not ok:
            continue
        score, breakdown = score_fn(metrics)
        metrics['score']     = round(score, 1)
        metrics['breakdown'] = breakdown
        eligible.append(metrics)

    conn.close()

    eligible.sort(key=lambda x: x['score'], reverse=True)
    for rank, s in enumerate(eligible, 1):
        s['rank'] = rank

    return eligible


def run_simulation_v2(as_of_year: int) -> list:
    """
    Unified 4-layer backtest simulation for a given year.
    Uses filter_unified + score_unified (v2 engine).
    Returns a ranked list: [{ticker, name, score, rank, category, breakdown}].
    """
    conn    = db.get_connection()
    tickers = [r['ticker'] for r in conn.execute(
        "SELECT ticker FROM stocks WHERE status = 'active' ORDER BY ticker"
    ).fetchall()]
    conn.close()

    all_metrics = []
    conn = db.get_connection()
    for ticker in tickers:
        metrics = _build_metrics_as_of(ticker, as_of_year, conn)
        if metrics:
            all_metrics.append(metrics)
    conn.close()

    # Compute sector stats from this snapshot (for PE normalisation)
    sector_stats = compute_sector_stats(all_metrics)

    eligible = []
    for metrics in all_metrics:
        ok, _ = filter_unified(metrics)
        if not ok:
            continue
        # Build financial history as a list of dicts (for improvement/acceleration layers)
        fin_history = []
        raw_conn = db.get_connection()
        rows = raw_conn.execute(
            """SELECT year, revenue, net_income, equity, total_debt, cash,
                      operating_cf, capex, ebitda, eps, dps
               FROM financials
               WHERE ticker = ? AND year <= ?
               ORDER BY year DESC LIMIT 10""",
            (metrics['ticker'], as_of_year)
        ).fetchall()
        raw_conn.close()
        fin_history = [dict(r) for r in rows]

        score, breakdown = score_unified(
            metrics,
            sector_stats=sector_stats,
            financials_history=fin_history,
        )
        metrics['score']     = round(score, 1)
        metrics['breakdown'] = breakdown
        eligible.append(metrics)

    eligible.sort(key=lambda x: x['score'], reverse=True)
    for rank, s in enumerate(eligible, 1):
        s['rank'] = rank

    return eligible


# ── Analysis functions ────────────────────────────────────────

def _rank_map(results: list) -> dict:
    """Returns {ticker: rank} for a simulation result list."""
    return {s['ticker']: s['rank'] for s in results}


def analyse_consistency(simulations: dict) -> dict:
    """Analyses rank consistency. Returns top5_by_year, consistent_top5, turnover, rank_corr."""
    years = sorted(simulations.keys())
    if not years:
        return {}

    top5_by_year = {y: [s['ticker'] for s in simulations[y][:5]] for y in years}

    # Consistent top-5: appeared in top-5 in ALL years
    consistent = set(top5_by_year[years[0]])
    for y in years[1:]:
        consistent &= set(top5_by_year[y])

    # Turnover: % of top-5 new each year vs prior
    turnover = {}
    for i in range(1, len(years)):
        prev = set(top5_by_year[years[i - 1]])
        curr = set(top5_by_year[years[i]])
        changed = len(curr - prev)
        turnover[years[i]] = round(changed / 5 * 100)

    # Spearman rank correlation between consecutive years
    rank_corr = {}
    for i in range(1, len(years)):
        y1, y2 = years[i - 1], years[i]
        rm1 = _rank_map(simulations[y1])
        rm2 = _rank_map(simulations[y2])
        common = [t for t in rm1 if t in rm2]
        if len(common) < 3:
            continue
        r1 = [rm1[t] for t in common]
        r2 = [rm2[t] for t in common]
        n  = len(common)
        d2 = sum((a - b) ** 2 for a, b in zip(r1, r2))
        rho = 1 - (6 * d2) / (n * (n ** 2 - 1)) if n > 2 else None
        if rho is not None:
            rank_corr[f'{y1}->{y2}'] = round(rho, 3)

    return {
        'top5_by_year':    top5_by_year,
        'consistent_top5': sorted(consistent),
        'turnover_by_year': turnover,
        'rank_corr':        rank_corr,
    }


def score_trajectory(ticker: str, simulations: dict) -> dict:
    """
    Returns {year: score} for a given ticker across all simulations.
    Returns {} if ticker not found in any simulation.
    """
    result = {}
    for year, ranked in simulations.items():
        for s in ranked:
            if s['ticker'] == ticker:
                result[year] = s['score']
                break
    return result


# ── Report printer ────────────────────────────────────────────

def _bar(score: float, width: int = 20) -> str:
    filled = int(score / 100 * width)
    return '#' * filled + '.' * (width - filled)


def _grade(score: float) -> str:
    if score >= 80: return 'A'
    if score >= 65: return 'B'
    if score >= 50: return 'C'
    return 'D'


def print_report(simulations: dict, portfolio_type: str, summary_only: bool = False):
    """Prints the full backtest report to stdout."""
    years = sorted(simulations.keys())
    label = portfolio_type.replace('_', ' ').upper()
    w     = 65

    print()
    print("=" * w)
    print(f"  PSE QUANT SAAS — FUNDAMENTAL BACKTEST")
    print(f"  Portfolio: {label}")
    print(f"  Simulation years: {', '.join(str(y) for y in years)}")
    print(f"  Note: Current prices used with historical fundamentals")
    print("=" * w)

    # ── Year-by-year top-10 ───────────────────────────────────
    if not summary_only:
        for year in years:
            ranked = simulations[year]
            n = len(ranked)
            print()
            print(f"  [{year}]  {n} stocks passed filters")
            print(f"  {'Rank':<5} {'Ticker':<8} {'Score':>6}  {'Grade'}  {'Bar'}")
            print(f"  {'-'*4}  {'-'*7}  {'-'*5}  {'-'*5}  {'-'*20}")
            for s in ranked[:10]:
                print(f"  #{s['rank']:<4} {s['ticker']:<8} {s['score']:>5.1f}  "
                      f"  [{_grade(s['score'])}]  {_bar(s['score'])}")
            if n > 10:
                print(f"  ... and {n - 10} more")

    # ── Consistency analysis ──────────────────────────────────
    analysis = analyse_consistency(simulations)

    print()
    print("=" * w)
    print("  CONSISTENCY ANALYSIS")
    print("=" * w)

    # Top-5 each year
    print()
    print("  Top-5 by year:")
    for year in years:
        tickers = analysis['top5_by_year'].get(year, [])
        print(f"    {year}: {', '.join(tickers) if tickers else '(none)'}")

    # Consistent picks
    consistent = analysis['consistent_top5']
    print()
    if consistent:
        print(f"  Stocks in top-5 EVERY year: {', '.join(consistent)}")
    else:
        print("  No stocks appeared in top-5 every simulated year.")

    # Portfolio turnover
    print()
    print("  Portfolio turnover (% of top-5 that changed vs prior year):")
    for year, pct in sorted(analysis['turnover_by_year'].items()):
        bar = '#' * (pct // 10)
        print(f"    {year}: {pct:>3}%  {bar}")

    # Rank correlation
    print()
    print("  Rank correlation (Spearman) between consecutive years:")
    if analysis['rank_corr']:
        for pair, rho in sorted(analysis['rank_corr'].items()):
            quality = ('Very stable' if rho >= 0.85
                       else 'Stable' if rho >= 0.70
                       else 'Moderate' if rho >= 0.50
                       else 'Low stability')
            print(f"    {pair}: rho={rho:+.3f}  [{quality}]")
    else:
        print("    Insufficient overlapping data to compute.")

    # ── Score trajectories for top stocks ────────────────────
    print()
    print("=" * w)
    print("  SCORE TRAJECTORIES (top stocks across all years)")
    print("=" * w)

    # Union of top-5 across all years
    all_top5 = set()
    for year in years:
        for s in simulations[year][:5]:
            all_top5.add(s['ticker'])

    print()
    header = '  ' + f"{'Ticker':<10}" + ''.join(f"{y:>8}" for y in years) + '   Trend'
    print(header)
    print('  ' + '-' * (10 + 8 * len(years) + 10))

    for ticker in sorted(all_top5):
        traj = score_trajectory(ticker, simulations)
        row = f"  {ticker:<10}"
        scores_in_order = []
        for year in years:
            if year in traj:
                row += f"{traj[year]:>7.1f} "
                scores_in_order.append(traj[year])
            else:
                row += f"{'  N/A':>7} "

        # Simple trend
        if len(scores_in_order) >= 2:
            diff = scores_in_order[-1] - scores_in_order[0]
            trend = (f'+{diff:.1f} (improving)' if diff > 3
                     else f'{diff:.1f} (declining)' if diff < -3
                     else '~stable')
        else:
            trend = 'insufficient data'
        row += f"  {trend}"
        print(row)

    # ── Coverage note ─────────────────────────────────────────
    print()
    print("=" * w)
    print("  DATA COVERAGE")
    print("=" * w)
    print()
    for year in years:
        n = len(simulations[year])
        print(f"  {year}: {n} stocks passed filters (at current prices + {year} financials)")

    # ── Disclaimer ────────────────────────────────────────────
    print()
    print("=" * w)
    for line in DISCLAIMER.split('\n'):
        print(f"  {line}")
    print("=" * w)
    print()


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='PSE Quant SaaS — Fundamental Backtest Simulator'
    )
    parser.add_argument('--mode',
        choices=['unified', 'legacy'], default='unified',
        help='unified = 4-layer v2 scorer (default); legacy = 3-portfolio scorer')
    parser.add_argument('--portfolio',
        choices=['pure_dividend', 'dividend_growth', 'value'], default='pure_dividend',
        help='Only used when --mode legacy')
    parser.add_argument('--years', nargs='+', type=int, default=DEFAULT_YEARS)
    parser.add_argument('--summary-only', action='store_true')
    args = parser.parse_args()

    db.init_db()

    mode_label = ('UNIFIED (4-Layer v2)' if args.mode == 'unified'
                  else f'LEGACY ({args.portfolio.replace("_", " ").upper()})')

    print()
    print(f"  Mode: {mode_label}")
    print(f"  Running simulations for years: {args.years}")

    simulations = {}
    for year in sorted(args.years):
        print(f"  Scoring [{year}]...", end='', flush=True)
        if args.mode == 'unified':
            results = run_simulation_v2(year)
        else:
            results = run_simulation(args.portfolio, year)
        simulations[year] = results
        print(f" {len(results)} stocks passed.")

    label = 'unified' if args.mode == 'unified' else args.portfolio
    print_report(simulations, label, summary_only=args.summary_only)


if __name__ == '__main__':
    main()
