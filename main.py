# ============================================================
# main.py — PSE Quant SaaS Pipeline Orchestrator
# PSE Quant SaaS — Phase 3
# ============================================================
# Runs the full pipeline:
#   Load stocks → Validate → Filter → Score → MoS → PDF → Discord
#
# Data source (auto-selected):
#   1. Real data  — loads from SQLite DB via pse_scraper.load_stocks_from_db()
#      Populate DB first: py scraper/pse_edge_scraper.py --ticker DMC
#   2. Sample data — used automatically if DB is empty (for testing)
#
# Usage:
#   py main.py                          # run all 3 portfolios
#   py main.py --portfolio pure_dividend # run one portfolio
#   py main.py --portfolio all --dry-run # generate PDFs only, no Discord
# ============================================================

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Path setup ────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'reports'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT / 'db'))

from filters      import (filter_pure_dividend_portfolio,
                          filter_dividend_growth_portfolio,
                          filter_value_portfolio)
from scorer       import score_pure_dividend, score_dividend_growth, score_value
from mos          import (calc_ddm, calc_two_stage_ddm, calc_eps_pe, calc_dcf,
                          calc_mos_price, calc_mos_pct,
                          calc_hybrid_intrinsic)
from validator    import validate_all, print_validation_summary
from pdf_generator import generate_report
from publisher    import WEBHOOKS, send_report


# ── Pipeline maps ─────────────────────────────────────────
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


# ── Data loader ────────────────────────────────────────────
# Tries live DB data first; falls back to sample data if DB is empty.
# To populate the DB run: py scraper/pse_edge_scraper.py --ticker DMC
# (or --sector Financials etc. for more coverage)

def load_stocks():
    """
    Returns stock data for pipeline processing.

    Priority:
      1. Real data from SQLite DB (via pse_scraper.load_stocks_from_db)
         — used when DB has at least one stock with price + financials
      2. Built-in sample data — fallback for first-run / testing

    To populate the DB:
      py scraper/pse_edge_scraper.py --ticker DMC
      py scraper/pdf_parser.py --ticker DMC --edge-no <edge_no>
    """
    try:
        from pse_scraper import load_stocks_from_db
        live = load_stocks_from_db()
        if live:
            print(f"       Using live DB data: {len(live)} stock(s)")
            return live
        else:
            print("       DB empty — using sample data")
    except Exception as e:
        print(f"       DB load failed ({e}) — using sample data")

    # ── Fallback: built-in sample data ───────────────────────
    return [
        {
            # Identity
            'ticker':           'DMC',
            'name':             'DMCI Holdings',
            'sector':           'Holdings',
            'is_reit':          False,
            'is_bank':          False,
            # Price
            'current_price':    11.50,
            # Dividends
            'dividend_yield':    8.35,
            'dividend_cagr_5y':  4.50,
            'payout_ratio':     25.26,
            'dps_last':          0.96,
            'dividends_5y':     [0.96, 0.90, 0.85, 0.80, 0.75],
            # Earnings
            'eps_3y':           [3.50, 3.65, 3.80],
            'net_income_3y':    [16000, 17500, 18500],
            'roe':              15.55,
            # Cash flow
            'operating_cf':     22000,
            'fcf_coverage':      1.84,
            'fcf_yield':         5.47,
            'fcf_per_share':     5.95,
            'fcf_3y':           [18000, 20000, 22000],
            # Valuation
            'pe':                3.03,
            'pb':                1.10,
            'ev_ebitda':        13.12,
            # Growth & leverage
            'revenue_cagr':      6.73,
            'de_ratio':          0.50,
        },
        {
            'ticker':           'AREIT',
            'name':             'Ayala REIT',
            'sector':           'Real Estate',
            'is_reit':          True,
            'is_bank':          False,
            'current_price':    35.00,
            'dividend_yield':    6.20,
            'dividend_cagr_5y':  8.00,
            'payout_ratio':     93.00,
            'dps_last':          2.17,
            'dividends_5y':     [2.17, 2.00, 1.85, 1.70, 1.55],
            'eps_3y':           [2.10, 2.30, 2.50],
            'net_income_3y':    [3200, 3500, 3800],
            'roe':              10.50,
            'operating_cf':      4500,
            'fcf_coverage':      1.20,
            'fcf_yield':         4.80,
            'fcf_per_share':     2.40,
            'fcf_3y':           [3800, 4000, 4200],
            'pe':               16.00,
            'pb':                1.40,
            'ev_ebitda':         9.50,
            'revenue_cagr':      9.20,
            'de_ratio':          0.30,
        },
        {
            'ticker':           'BDO',
            'name':             'BDO Unibank',
            'sector':           'Banking',
            'is_reit':          False,
            'is_bank':          True,
            'current_price':   130.00,
            'dividend_yield':    2.80,
            'dividend_cagr_5y':  7.00,
            'payout_ratio':     35.00,
            'dps_last':          4.50,
            'dividends_5y':     [4.50, 4.20, 3.80, 3.50, 3.20],
            'eps_3y':           [11.20, 12.80, 14.50],
            'net_income_3y':    [42000, 48000, 55000],
            'roe':              14.20,
            'operating_cf':     65000,
            'fcf_coverage':      2.50,
            'fcf_yield':         6.20,
            'fcf_per_share':    18.50,
            'fcf_3y':           [50000, 55000, 60000],
            'pe':               10.50,
            'pb':                1.20,
            'ev_ebitda':         8.20,
            'revenue_cagr':     11.50,
            'de_ratio':          7.20,
        },
        {
            'ticker':           'MER',
            'name':             'Manila Electric Company',
            'sector':           'Utilities',
            'is_reit':          False,
            'is_bank':          False,
            'current_price':   385.00,
            'dividend_yield':    4.20,
            'dividend_cagr_5y':  5.50,
            'payout_ratio':     62.00,
            'dps_last':         16.20,
            'dividends_5y':     [16.20, 15.00, 14.00, 13.00, 12.00],
            'eps_3y':           [24.50, 26.00, 28.50],
            'net_income_3y':    [22000, 24000, 26500],
            'roe':              18.20,
            'operating_cf':     30000,
            'fcf_coverage':      1.65,
            'fcf_yield':         4.10,
            'fcf_per_share':    15.80,
            'fcf_3y':           [25000, 27000, 30000],
            'pe':               14.50,
            'pb':                2.60,
            'ev_ebitda':        10.20,
            'revenue_cagr':      7.80,
            'de_ratio':          1.20,
        },
        {
            'ticker':           'JFC',
            'name':             'Jollibee Foods Corporation',
            'sector':           'Food & Beverage',
            'is_reit':          False,
            'is_bank':          False,
            'current_price':   215.00,
            'dividend_yield':    1.40,
            'dividend_cagr_5y':  3.20,
            'payout_ratio':     45.00,
            'dps_last':          3.00,
            'dividends_5y':     [3.00, 2.80, 2.60, 2.40, 2.20],
            'eps_3y':           [6.20, 7.80, 9.50],
            'net_income_3y':    [4800, 6200, 7800],
            'roe':              12.80,
            'operating_cf':      9500,
            'fcf_coverage':      1.30,
            'fcf_yield':         2.80,
            'fcf_per_share':     6.00,
            'fcf_3y':           [7000, 8000, 9500],
            'pe':               27.50,
            'pb':                3.20,
            'ev_ebitda':        15.80,
            'revenue_cagr':     12.40,
            'de_ratio':          1.80,
        },
    ]


# ── Pipeline steps ─────────────────────────────────────────

def filter_stocks(stocks, portfolio_type):
    """
    Runs each stock through the portfolio's eligibility filter.
    Returns (passed_list, rejected_list).
    rejected_list contains (ticker, reason) tuples for logging.
    """
    filter_fn = FILTERS[portfolio_type]
    passed   = []
    rejected = []
    for stock in stocks:
        eligible, reason = filter_fn(stock)
        if eligible:
            passed.append(stock)
        else:
            rejected.append((stock.get('ticker', '?'), reason))
    return passed, rejected


def score_and_rank(stocks, portfolio_type):
    """
    Scores each stock, calculates intrinsic value and MoS,
    then returns the list sorted by score (highest first).
    """
    score_fn = SCORERS[portfolio_type]
    result   = []

    for stock in stocks:
        score, breakdown = score_fn(stock)

        ddm_val, _ = calc_ddm(
            stock.get('dps_last'),
            stock.get('dividend_cagr_5y'),
        )
        eps_val, _ = calc_eps_pe(
            stock.get('eps_3y', []),
            roe=stock.get('roe'),
        )
        dcf_val, _ = calc_dcf(
            stock.get('fcf_per_share'),
            stock.get('revenue_cagr'),
        )

        if portfolio_type == 'pure_dividend':
            iv = ddm_val   # Gordon Growth DDM — best for stable high-yield payers
        elif portfolio_type == 'dividend_growth':
            # Two-Stage DDM: conservative Stage 1 growth + terminal at PH GDP rate
            eps_growth = stock.get('revenue_cagr')   # proxy until eps CAGR available
            iv, _ = calc_two_stage_ddm(
                stock.get('dps_last'),
                eps_growth,
            )
        elif portfolio_type == 'value':
            iv = eps_val
        else:
            iv, _ = calc_hybrid_intrinsic(ddm_val, eps_val, dcf_val)

        mos_price = calc_mos_price(iv, portfolio_type)
        mos_pct   = calc_mos_pct(iv, stock.get('current_price'))

        result.append({
            **stock,
            'score':           score,
            'score_breakdown': breakdown,
            'intrinsic_value': iv,
            'mos_price':       mos_price,
            'mos_pct':         mos_pct,
        })

    result.sort(key=lambda x: x['score'], reverse=True)
    return result


# ── Sentiment helpers ──────────────────────────────────────

def _try_enrich_with_sentiment(stocks):
    """
    Enriches stock dicts in-place with 'sentiment_data' key.
    Silently skips if ANTHROPIC_API_KEY is missing or fetch fails.
    """
    try:
        from sentiment_engine import enrich_with_sentiment
        enrich_with_sentiment(stocks)
        enriched = sum(1 for s in stocks if s.get('sentiment_data'))
        if enriched:
            print(f"       [sentiment] enriched {enriched} stock(s) with news data")
        else:
            print(f"       [sentiment] no headlines found (API key set? News sources reachable?)")
    except Exception as e:
        print(f"       [sentiment] skipped — {e}")


def _send_opportunistic_alerts(ranked_stocks):
    """
    Sends opportunistic watch alerts to Discord for any ranked stock
    that has opportunistic_flag=1 in its sentiment data.
    """
    try:
        from publisher import send_opportunistic_alert
        alerts_webhook = WEBHOOKS.get('alerts', '')
        opp_stocks = [
            s for s in ranked_stocks
            if s.get('sentiment_data', {}) and
               s['sentiment_data'].get('opportunistic_flag')
        ]
        for stock in opp_stocks:
            sd = stock['sentiment_data']
            send_opportunistic_alert(
                stock['ticker'],
                stock.get('name', stock['ticker']),
                sd.get('summary', ''),
                alerts_webhook,
            )
    except Exception as e:
        print(f"       [sentiment] opportunistic alerts failed — {e}")


# ── Main pipeline ──────────────────────────────────────────

def run_pipeline(portfolio_type, dry_run=False):
    """
    Runs the full pipeline for one portfolio type.
    Returns True if the run completed successfully, False otherwise.
    """
    print(f"\n{'='*55}")
    print(f"  PSE QUANT SAAS — {portfolio_type.upper()} PORTFOLIO")
    print(f"{'='*55}")

    # ── Step 1: Load ──
    print("\n[1/5]  Loading stock data...")
    all_stocks = load_stocks()
    print(f"       {len(all_stocks)} stocks loaded")

    # ── Step 1b: Validate ──
    all_stocks, val_results = validate_all(all_stocks)
    blocked = sum(1 for r in val_results if not r['valid'])
    warned  = sum(1 for r in val_results if r['warnings'])
    if blocked:
        print(f"       Validation blocked {blocked} stock(s)")
    if warned:
        for r in val_results:
            for w in r['warnings']:
                print(f"       WARN  {w}")
    print(f"       {len(all_stocks)} stock(s) passed validation")

    if not all_stocks:
        print(f"\n  No stocks passed validation.")
        return False

    # ── Step 2: Filter ──
    print(f"\n[2/5]  Filtering for {portfolio_type} portfolio...")
    passed, rejected = filter_stocks(all_stocks, portfolio_type)
    print(f"       Passed : {len(passed)}")
    print(f"       Skipped: {len(rejected)}")
    for ticker, reason in rejected:
        print(f"         SKIP  {reason}")

    if not passed:
        print(f"\n  No stocks passed the {portfolio_type} filters.")
        return False

    # ── Step 3: Score & rank ──
    print(f"\n[3/5]  Scoring and ranking {len(passed)} stock(s)...")
    ranked = score_and_rank(passed, portfolio_type)
    for i, s in enumerate(ranked[:5], 1):
        print(f"       #{i}  {s['ticker']:6}  {s['score']}/100")

    # ── Step 3b: Sentiment enrichment (top 10 only — shown in PDF) ──
    _try_enrich_with_sentiment(ranked[:10])

    # ── Step 4: Generate PDF ──
    print(f"\n[4/5]  Generating PDF report...")
    # Save to Desktop (always writable, easy to find)
    # Phase 3: move to REPORTS_DIR once the data pipeline is set up
    DESKTOP  = os.path.join(os.path.expanduser('~'), 'Desktop')
    run_date = datetime.now().strftime('%Y-%m-%d')
    filename = f"PSE_{portfolio_type.upper()}_REPORT_{run_date}.pdf"
    pdf_path = os.path.join(DESKTOP, filename)

    generate_report(
        portfolio_type        = portfolio_type,
        ranked_stocks         = ranked,
        output_path           = pdf_path,
        total_stocks_screened = len(all_stocks),
    )
    print(f"       Saved: {pdf_path}")

    # ── Step 5: Send to Discord ──
    print(f"\n[5/5]  Discord delivery...")
    if dry_run:
        print(f"\n  [DRY RUN] Skipping Discord delivery.")
        return True

    webhook_url = WEBHOOKS.get(portfolio_type, '')
    if not webhook_url:
        print(f"\n  No Discord webhook set for '{portfolio_type}'. "
              f"Add DISCORD_WEBHOOK_{portfolio_type.upper()} to .env to enable delivery.")
        return True

    print(f"\n  Sending to Discord #{portfolio_type}...")
    success = send_report(
        webhook_url    = webhook_url,
        pdf_path       = pdf_path,
        portfolio_type = portfolio_type,
        ranked_stocks  = ranked,
    )
    if success:
        print(f"  Delivered to #{portfolio_type} channel.")
    else:
        print(f"  Discord delivery failed. PDF saved locally at:\n  {pdf_path}")

    # ── Step 5b: Opportunistic alerts ──
    _send_opportunistic_alerts(ranked)

    return True


# ── Entry point ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='PSE Quant SaaS — Portfolio Report Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  py main.py                           # run all 3 portfolios\n'
            '  py main.py --portfolio dividend      # dividend only\n'
            '  py main.py --portfolio all --dry-run # generate PDFs, no Discord\n'
        )
    )
    parser.add_argument(
        '--portfolio',
        choices=['pure_dividend', 'dividend_growth', 'value', 'all'],
        default='all',
        help='Portfolio to run (default: all)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate PDF reports but do not send to Discord',
    )
    args = parser.parse_args()

    portfolios = (
        ['pure_dividend', 'dividend_growth', 'value']
        if args.portfolio == 'all'
        else [args.portfolio]
    )

    if args.dry_run:
        print("\nDRY RUN mode — PDFs will be generated but NOT sent to Discord.")

    for portfolio in portfolios:
        run_pipeline(portfolio, dry_run=args.dry_run)

    print(f"\n{'='*55}")
    print(f"  All done.")
    print(f"{'='*55}\n")


if __name__ == '__main__':
    main()
