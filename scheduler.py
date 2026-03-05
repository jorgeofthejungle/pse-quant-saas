# ============================================================
# scheduler.py — Daily Automation Orchestrator
# PSE Quant SaaS — Phase 4
# ============================================================
# Runs every weekday at 4:00 PM PHT (after market close).
#
# Each day:
#   1. Scrapes latest prices from PSE → updates DB
#   2. Re-scores all stocks for all 3 portfolios
#   3. Compares new top-5 to last sent top-5 per portfolio
#   4. If top-5 changed → sends new PDF to Discord
#   5. If any ranks changed → sends rescore notice to #pse-alerts
#   6. Saves new scores to DB (always)
#
# Usage:
#   py scheduler.py              # starts live scheduler (blocking)
#   py scheduler.py --run-now    # runs one cycle immediately (for testing)
# ============================================================

import sys
import os
import argparse
from datetime import datetime
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'reports'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'scraper'))

from filters      import (filter_pure_dividend_portfolio,
                          filter_dividend_growth_portfolio,
                          filter_value_portfolio)
from scorer       import score_pure_dividend, score_dividend_growth, score_value
from mos          import (calc_ddm, calc_two_stage_ddm, calc_eps_pe, calc_dcf,
                          calc_mos_price, calc_mos_pct,
                          calc_hybrid_intrinsic)
from pdf_generator import generate_report
from publisher    import WEBHOOKS, send_report, send_rescore_notice
import database as db

# Try importing the scraper (may fail if dependencies not set up yet)
try:
    from pse_scraper import scrape_and_save, load_stocks_from_db
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False
    print("WARNING: pse_scraper not available — will use sample data.")

# ── Pipeline maps ─────────────────────────────────────────────
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


# ── Fallback sample data ──────────────────────────────────────
# Used when the DB has no data yet (Phase 3 scraper not set up).
# Remove this once real data is flowing from pse_scraper.py.

def load_sample_stocks():
    """Sample data fallback — same stocks as main.py."""
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


# ── Core pipeline functions ───────────────────────────────────

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


def _score_and_rank(stocks: list, portfolio_type: str) -> list:
    """
    Filters, scores, and ranks stocks for a given portfolio.
    Returns sorted list with score, intrinsic value, and MoS added.
    """
    filter_fn = FILTERS[portfolio_type]
    score_fn  = SCORERS[portfolio_type]

    passed = [s for s in stocks if filter_fn(s)[0]]

    result = []
    for stock in passed:
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
            iv = ddm_val
        elif portfolio_type == 'dividend_growth':
            eps_growth = stock.get('revenue_cagr')
            iv, _ = calc_two_stage_ddm(stock.get('dps_last'), eps_growth)
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


def _top5_changed(old_top5: list, new_top5: list) -> bool:
    """
    Returns True if the SET of top-5 tickers has changed —
    i.e. a stock entered or left the top 5.
    Order within the top 5 does not trigger a resend.
    """
    return set(old_top5) != set(new_top5)


def _build_changes(new_ranked: list, old_scores: list) -> list:
    """
    Compares new rankings to old scores and returns a list of changes
    for send_rescore_notice().

    Format: [{'ticker', 'old_rank', 'new_rank', 'old_score', 'new_score'}, ...]
    Only includes stocks where rank or score actually changed.
    """
    old_by_ticker = {s['ticker']: s for s in old_scores}
    changes = []

    for stock in new_ranked:
        ticker    = stock['ticker']
        new_rank  = new_ranked.index(stock) + 1
        new_score = stock['score']
        old       = old_by_ticker.get(ticker)

        if old is None:
            # New stock that wasn't ranked before
            changes.append({
                'ticker':    ticker,
                'old_rank':  '—',
                'new_rank':  new_rank,
                'old_score': 0,
                'new_score': new_score,
            })
        elif old['rank'] != new_rank or abs(old['score'] - new_score) >= 1.0:
            changes.append({
                'ticker':    ticker,
                'old_rank':  old['rank'],
                'new_rank':  new_rank,
                'old_score': old['score'],
                'new_score': new_score,
            })

    return changes


# ── Main daily job ────────────────────────────────────────────

def run_daily_job():
    """
    The full daily pipeline — called by the scheduler at 4:00 PM PHT.

    For each portfolio:
    1. Get last top-5 (before this run) from DB
    2. Load and score all stocks
    3. Compare top-5 sets → send PDF if changed
    4. Detect rank/score changes → send rescore notice to #pse-alerts
    5. Save new scores to DB
    """
    today = datetime.now().strftime('%Y-%m-%d')
    now   = datetime.now().strftime('%H:%M')

    print(f"\n{'='*55}")
    print(f"  PSE QUANT SAAS — Daily Run  {today}  {now}")
    print(f"{'='*55}")

    # ── Step 1: Scrape latest prices ──
    print("\n[1/3]  Scraping latest prices...")
    if SCRAPER_AVAILABLE:
        prices = scrape_and_save()
        if prices:
            print(f"  {len(prices)} prices updated.")
        else:
            print("  Scrape returned no data — using existing DB prices.")
    else:
        print("  Scraper not available — skipping price update.")

    # ── Step 2: Load stocks ──
    print("\n[2/3]  Loading stock data...")
    all_stocks = _load_stocks()
    print(f"  {len(all_stocks)} stocks available.")

    if not all_stocks:
        print("  No stock data available. Aborting run.")
        return

    # ── Step 3: Score and compare for each portfolio ──
    print("\n[3/3]  Scoring portfolios and checking for changes...")

    for portfolio_type in ['pure_dividend', 'dividend_growth', 'value']:
        name = PORTFOLIO_NAMES[portfolio_type]
        print(f"\n  ── {name} ──")

        # Get previous state BEFORE this run
        old_top5   = db.get_last_top5(portfolio_type)
        old_scores = db.get_last_scores(portfolio_type)

        # Score and rank
        ranked = _score_and_rank(all_stocks, portfolio_type)
        if not ranked:
            print(f"  No stocks passed {name} filters. Skipping.")
            continue

        # Sentiment enrichment (top 10 only — shown in PDF)
        try:
            from sentiment_engine import enrich_with_sentiment
            enrich_with_sentiment(ranked[:10])
        except Exception as e:
            print(f"  [sentiment] skipped for {name} — {e}")

        new_top5 = [s['ticker'] for s in ranked[:5]]

        print(f"  Ranked {len(ranked)} stock(s).")
        print(f"  New top 5: {', '.join(new_top5)}")
        if old_top5:
            print(f"  Old top 5: {', '.join(old_top5)}")
        else:
            print(f"  Old top 5: (no previous run)")

        # ── Check if top-5 changed → send PDF ──
        is_first_run = not old_top5
        should_send  = is_first_run or _top5_changed(old_top5, new_top5)

        if should_send:
            reason = 'first run' if is_first_run else 'top-5 changed'
            print(f"  TOP-5 CHANGED ({reason}) — generating PDF...")

            DESKTOP  = os.path.join(os.path.expanduser('~'), 'Desktop')
            filename = f"PSE_{portfolio_type.upper()}_REPORT_{today}.pdf"
            pdf_path = os.path.join(DESKTOP, filename)

            generate_report(
                portfolio_type        = portfolio_type,
                ranked_stocks         = ranked,
                output_path           = pdf_path,
                total_stocks_screened = len(all_stocks),
            )

            webhook_url = WEBHOOKS.get(portfolio_type, '')
            if webhook_url:
                print(f"  Sending to Discord #{portfolio_type}...")
                send_report(
                    webhook_url    = webhook_url,
                    pdf_path       = pdf_path,
                    portfolio_type = portfolio_type,
                    ranked_stocks  = ranked,
                )
            else:
                print(f"  No webhook for {portfolio_type} — PDF saved at: {pdf_path}")
        else:
            print(f"  Top-5 unchanged — no PDF sent.")

        # ── Check for any rank/score changes → send rescore notice ──
        if old_scores:
            changes = _build_changes(ranked, old_scores)
            if changes:
                print(f"  {len(changes)} rank/score change(s) detected.")
                alerts_url = WEBHOOKS.get('alerts', '')
                if alerts_url:
                    send_rescore_notice(alerts_url, portfolio_type, changes)
                    print(f"  Rescore notice sent to #pse-alerts.")
                else:
                    print(f"  No alerts webhook set — rescore notice skipped.")
                    for c in changes:
                        print(f"    {c['ticker']}: #{c['old_rank']} → #{c['new_rank']}  "
                              f"({c['old_score']:.1f} → {c['new_score']:.1f})")
            else:
                print(f"  No significant rank changes.")

        # ── Save scores to DB (always) ──
        try:
            db.save_scores(today, ranked, portfolio_type)
            print(f"  Scores saved to DB ({portfolio_type}).")
        except Exception as e:
            print(f"  DB save error: {e}")

    print(f"\n{'='*55}")
    print(f"  Daily run complete.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")


# ── Scheduler setup ───────────────────────────────────────────

def start_scheduler():
    """
    Starts the APScheduler background scheduler.
    Runs run_daily_job() every weekday at 4:00 PM PHT.
    Blocks until interrupted (Ctrl+C).
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("APScheduler not installed. Run: py -m pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone='Asia/Manila')
    scheduler.add_job(
        run_daily_job,
        CronTrigger(day_of_week='mon-fri', hour=16, minute=0),
        id='daily_pse_run',
        name='PSE Daily Score & Report',
        misfire_grace_time=600,   # 10 min grace if job starts late
    )

    print("=" * 55)
    print("  PSE QUANT SAAS — Scheduler Started")
    print("  Runs every weekday at 4:00 PM PHT")
    print("  Press Ctrl+C to stop")
    print("=" * 55)

    next_run = scheduler.get_jobs()[0].next_run_time
    print(f"  Next scheduled run: {next_run}")
    print()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


# ── Entry point ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='PSE Quant SaaS — Daily Scheduler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  py scheduler.py              # start live scheduler\n'
            '  py scheduler.py --run-now    # run one cycle immediately\n'
        )
    )
    parser.add_argument(
        '--run-now',
        action='store_true',
        help='Run one full cycle immediately (for testing)',
    )
    args = parser.parse_args()

    # Always ensure DB is initialised
    db.init_db()

    if args.run_now:
        print("Running one full daily cycle now...")
        run_daily_job()
    else:
        start_scheduler()


if __name__ == '__main__':
    main()
