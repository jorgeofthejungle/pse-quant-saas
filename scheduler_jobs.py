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
                          calc_mos_price, calc_mos_pct, calc_hybrid_intrinsic,
                          apply_conglomerate_discount, _sector_median_pe)
from pdf_generator import generate_report
from publisher    import WEBHOOKS, send_report, send_rescore_notice, send_sentiment_signal, send_shortlist_change
import database as db

try:
    from config import SCORE_CHANGE_THRESHOLD
except ImportError:
    SCORE_CHANGE_THRESHOLD = 5.0

from scheduler_data import (
    FILTERS, SCORERS, PORTFOLIO_NAMES,
    SCRAPER_AVAILABLE, _load_stocks,
)

# Portfolio-specific IV blend weights: (DDM, EPS-PE, DCF)
_IV_WEIGHTS = {
    'pure_dividend':   (0.50, 0.25, 0.25),
    'dividend_growth': (0.40, 0.30, 0.30),
    'value':           (0.20, 0.40, 0.40),
}

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

    # Pre-compute sector PE medians (cached per sector) from full stock universe
    sector_pe_cache = {}
    iv_weights = _IV_WEIGHTS.get(portfolio_type, (0.40, 0.40, 0.20))

    result = []
    for stock in passed:
        score, breakdown = score_fn(stock)

        sector = stock.get('sector', '')
        if sector not in sector_pe_cache:
            sector_pe_cache[sector] = _sector_median_pe(sector, stocks)
        sector_pe = sector_pe_cache[sector]

        # DDM: Two-Stage for dividend_growth (explicit 5yr + terminal), Gordon Growth for others
        if portfolio_type == 'dividend_growth':
            ddm_val, _ = calc_two_stage_ddm(
                stock.get('dps_last'),
                stock.get('revenue_cagr'),
            )
        else:
            ddm_val, _ = calc_ddm(
                stock.get('dps_last'),
                stock.get('dividend_cagr_5y'),
            )

        eps_val, _ = calc_eps_pe(
            stock.get('eps_3y', []),
            target_pe=sector_pe,
            roe=stock.get('roe'),
        )
        dcf_val, _ = calc_dcf(
            stock.get('fcf_per_share'),
            stock.get('revenue_cagr'),
        )

        iv, _ = calc_hybrid_intrinsic(ddm_val, eps_val, dcf_val, weights=iv_weights)
        iv = apply_conglomerate_discount(iv, sector)

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


def _significant_score_change(
    old_scores: list,
    new_ranked: list,
    threshold: float = None,
) -> bool:
    """
    Returns True if any top-10 stock's score changed by >= threshold points.
    Only considers stocks that appear in BOTH old and new lists.
    """
    if threshold is None:
        threshold = SCORE_CHANGE_THRESHOLD

    old_by_ticker = {s['ticker']: s['score'] for s in old_scores}
    for stock in new_ranked[:10]:
        ticker    = stock['ticker']
        new_score = stock['score']
        old_score = old_by_ticker.get(ticker)
        if old_score is not None and abs(new_score - old_score) >= threshold:
            return True
    return False


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


def _build_shortlist_changes(
    old_scores:     list,
    new_ranked:     list,
    all_stocks:     list,
    portfolio_type: str,
) -> list:
    """
    Detects stocks that entered or left the portfolio's qualifying shortlist.
    Re-runs filters on exits for plain-English reason; finds strongest factor on entries.
    """
    old_tickers = {s['ticker'] for s in old_scores}
    new_tickers = {s['ticker'] for s in new_ranked}

    exited  = old_tickers - new_tickers
    entered = new_tickers - old_tickers

    if not exited and not entered:
        return []

    filter_fn    = FILTERS[portfolio_type]
    stock_by_tk  = {s['ticker']: s for s in all_stocks}
    old_by_tk    = {s['ticker']: s for s in old_scores}

    changes = []

    for ticker in sorted(exited):
        old = old_by_tk.get(ticker, {})
        stock = stock_by_tk.get(ticker)
        if stock is None:
            reason = "No longer in the screening universe (data unavailable or stock inactive)."
        else:
            eligible, reason = filter_fn(stock)
            if eligible:
                reason = "Score dropped below qualifying stocks in this portfolio."
        changes.append({
            'type':      'exit',
            'ticker':    ticker,
            'name':      stock.get('name', ticker) if stock else ticker,
            'reason':    reason,
            'old_score': old.get('score'),
            'old_rank':  old.get('rank'),
        })

    for rank_idx, stock in enumerate(new_ranked, 1):
        if stock['ticker'] in entered:
            breakdown = stock.get('score_breakdown', {})
            strongest_factor = ''
            strongest_score  = None
            if breakdown:
                best = max(breakdown.items(),
                           key=lambda x: x[1].get('score', 0) * x[1].get('weight', 0))
                strongest_factor = best[0]
                strongest_score  = best[1].get('score', 0)
            changes.append({
                'type':             'entry',
                'ticker':           stock['ticker'],
                'name':             stock.get('name', stock['ticker']),
                'score':            stock['score'],
                'rank':             rank_idx,
                'strongest_factor': strongest_factor,
                'strongest_score':  strongest_score,
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
        print(f"\n  -- {name} --")

        old_top5   = db.get_last_top5(portfolio_type)
        old_scores = db.get_last_scores(portfolio_type)

        ranked = _score_and_rank(all_stocks, portfolio_type)
        if not ranked:
            print(f"  No stocks passed {name} filters. Skipping.")
            continue

        # Sentiment enrichment (top 10 only — shown in PDF)
        try:
            from sentiment_engine import enrich_with_sentiment, classify_signal
            enrich_with_sentiment(ranked[:10])

            # Classify and send educational signals for enriched stocks
            alerts_url = WEBHOOKS.get('alerts', '')
            for stock in ranked[:10]:
                sd = stock.get('sentiment_data')
                if not sd:
                    continue
                sig = classify_signal(
                    sd,
                    stock.get('mos_pct'),
                    stock.get('score', 0),
                )
                if sig['signal'] == 'monitor':
                    continue
                if alerts_url:
                    send_sentiment_signal(
                        webhook_url       = alerts_url,
                        ticker            = stock['ticker'],
                        company           = stock.get('name', stock['ticker']),
                        signal            = sig['signal'],
                        reasoning         = sig['reasoning'],
                        sentiment_summary = sd.get('summary', ''),
                        key_events        = sd.get('key_events', []),
                        mos_pct           = stock.get('mos_pct'),
                        overall_score     = stock.get('score', 0),
                        portfolio_type    = portfolio_type,
                    )
                    print(f"  [{sig['label']}] signal sent for {stock['ticker']}")
                else:
                    print(f"  [{sig['label']}] {stock['ticker']} — no alerts webhook set")
        except Exception as e:
            print(f"  [sentiment] skipped for {name} — {e}")

        # ── Shortlist membership change alert ──
        if old_scores:
            shortlist_changes = _build_shortlist_changes(
                old_scores, ranked, all_stocks, portfolio_type
            )
            if shortlist_changes:
                alerts_url = WEBHOOKS.get('alerts', '')
                if alerts_url:
                    send_shortlist_change(alerts_url, portfolio_type, shortlist_changes)
                    print(f"  Shortlist change alert sent ({len(shortlist_changes)} change(s)).")
                else:
                    for c in shortlist_changes:
                        sym = 'X' if c['type'] == 'exit' else '+'
                        print(f"    [{sym}] {c['ticker']}: {c.get('reason', 'new entry')}")

        new_top5 = [s['ticker'] for s in ranked[:5]]

        print(f"  Ranked {len(ranked)} stock(s).")
        print(f"  New top 5: {', '.join(new_top5)}")
        if old_top5:
            print(f"  Old top 5: {', '.join(old_top5)}")
        else:
            print(f"  Old top 5: (no previous run)")

        is_first_run      = not old_top5
        top5_changed      = _top5_changed(old_top5, new_top5)
        score_moved       = old_scores and _significant_score_change(old_scores, ranked)
        should_send       = is_first_run or top5_changed or score_moved

        if should_send:
            if is_first_run:
                reason = 'first run'
            elif top5_changed:
                reason = 'top-5 changed'
            else:
                reason = f'score change >= {SCORE_CHANGE_THRESHOLD} pts in top-10'
            print(f"  PDF TRIGGER ({reason}) — generating PDF...")

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


def run_weekly_scrape():
    """
    Sunday night full financial refresh for all PSE stocks.
    Called by the scheduler at 10:00 PM PHT every Sunday.

    Runs the full scraper to update financials, then triggers
    a full re-score so Monday morning rankings are fresh.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    now   = datetime.now().strftime('%H:%M')

    print(f"\n{'='*55}")
    print(f"  PSE QUANT SAAS — Weekly Financial Scrape  {today}  {now}")
    print(f"{'='*55}")

    if not SCRAPER_AVAILABLE or not scrape_and_save:
        print("  Scraper not available — weekly refresh skipped.")
        print(f"{'='*55}\n")
        return

    print("\n[1/2]  Running full financial scrape (this may take several hours)...")
    try:
        # Full scrape — updates prices AND full financials for all stocks
        results = scrape_and_save(full=True)
        count = len(results) if results else 0
        print(f"  Full scrape complete: {count} stock(s) updated.")
    except TypeError:
        # Scraper may not support full=True flag — fall back to standard call
        try:
            results = scrape_and_save()
            count = len(results) if results else 0
            print(f"  Scrape complete (standard mode): {count} stock(s) updated.")
        except Exception as e:
            print(f"  Scrape failed: {e}")
            print(f"{'='*55}\n")
            return
    except Exception as e:
        print(f"  Full scrape failed: {e}")
        print(f"{'='*55}\n")
        return

    # ── Step 1b: Force-refresh stale financial data ──────────
    print("\n[1b/2]  Checking for stale financial data (>90 days since last update)...")
    try:
        stale_tickers = db.get_stale_financials_tickers(days=90)
        if stale_tickers:
            print(f"  {len(stale_tickers)} ticker(s) have stale financials. Re-fetching...")
            try:
                sys.path.insert(0, str(ROOT / 'scraper'))
                from pse_edge_scraper import scrape_one as _scrape_one
                for ticker in stale_tickers[:20]:   # cap at 20 per run to avoid rate limits
                    try:
                        print(f"  Re-fetching {ticker}...")
                        _scrape_one(ticker)
                    except Exception as e:
                        print(f"  {ticker}: re-fetch failed — {e}")
            except ImportError:
                print("  PSE Edge scraper not available — skipping stale re-fetch.")
        else:
            print("  All financial data is fresh.")
    except Exception as e:
        print(f"  Stale financials check failed: {e}")

    print("\n[2/2]  Re-scoring all portfolios with fresh data...")
    run_daily_job()

    print(f"\n{'='*55}")
    print(f"  Weekly scrape complete.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")
