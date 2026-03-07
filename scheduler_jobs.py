# ============================================================
# scheduler_jobs.py — Daily Job Logic & Scoring Pipeline
# PSE Quant SaaS — scheduler sub-module
# ============================================================

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'reports'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'scraper'))

from mos          import (calc_ddm, calc_two_stage_ddm, calc_eps_pe, calc_dcf,
                          calc_mos_price, calc_mos_pct, calc_hybrid_intrinsic)
from pdf_generator import generate_report
from publisher    import WEBHOOKS, send_report, send_rescore_notice
import database as db

from scheduler_data import (
    FILTERS, SCORERS, PORTFOLIO_NAMES,
    SCRAPER_AVAILABLE, _load_stocks,
)

# Scraper import for price updates
try:
    from pse_scraper import scrape_and_save
except ImportError:
    scrape_and_save = None


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
    if SCRAPER_AVAILABLE and scrape_and_save:
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

        old_top5   = db.get_last_top5(portfolio_type)
        old_scores = db.get_last_scores(portfolio_type)

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
                        print(f"    {c['ticker']}: #{c['old_rank']} -> #{c['new_rank']}  "
                              f"({c['old_score']:.1f} -> {c['new_score']:.1f})")
            else:
                print(f"  No significant rank changes.")

        try:
            db.save_scores(today, ranked, portfolio_type)
            print(f"  Scores saved to DB ({portfolio_type}).")
        except Exception as e:
            print(f"  DB save error: {e}")

    print(f"\n{'='*55}")
    print(f"  Daily run complete.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")
