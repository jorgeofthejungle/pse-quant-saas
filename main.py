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
from pipeline     import score_and_rank
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
# Sample data lives in scheduler_data.py (single source of truth).

def load_stocks():
    """
    Returns stock data for pipeline processing.
    Tries live DB first; falls back to sample data for testing.
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

    from scheduler_data import load_sample_stocks
    return load_sample_stocks()


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
    ranked = score_and_rank(passed, portfolio_type, SCORERS[portfolio_type], all_stocks=all_stocks)
    for i, s in enumerate(ranked[:5], 1):
        print(f"       #{i}  {s['ticker']:6}  {s['score']}/100")

    # ── Step 3b: Sentiment enrichment (all ranked stocks — shown in PDF) ──
    _try_enrich_with_sentiment(ranked)

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
