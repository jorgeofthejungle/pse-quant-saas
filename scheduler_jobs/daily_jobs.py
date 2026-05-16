# scheduler_jobs/daily_jobs.py — Daily scoring pipeline (4 PM score + 6 PM report)
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # project root
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'reports'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'db'))

import database as db

try:
    from config import SCORE_CHANGE_THRESHOLD, CONGLOMERATE_DISCOUNT, IV_WEIGHTS
except ImportError:
    SCORE_CHANGE_THRESHOLD = 5.0
    CONGLOMERATE_DISCOUNT  = 0.20
    IV_WEIGHTS             = (0.30, 0.35, 0.35)

from scheduler_data import _load_stocks

from .state import (
    _check_price_freshness, _record_heartbeat,
    _load_signal_cache, _save_signal_cache, _signal_is_new,
    _write_pending_pdf, _read_pending_pdf, _clear_pending_pdf,
    _write_held_pdf, _read_held_pdf, _clear_held_pdf,
)

# Scraper import for price updates (PSE Edge)
try:
    from scraper.pse_edge_scraper import scrape_daily_prices
except ImportError:
    try:
        from pse_edge_scraper import scrape_daily_prices
    except ImportError:
        scrape_daily_prices = None

# Lock prevents concurrent runs of the scoring pipeline
_rescore_lock = threading.Lock()


def _top5_changed(old_top5: list, new_top5: list) -> bool:
    """
    Returns True if the top-5 changed in composition OR rank position.
    List equality is position-aware: [A,B,C,D,E] != [B,A,C,D,E].
    A rank swap within the top 5 (e.g. #1 and #2 swap) is meaningful
    and warrants a new report.
    """
    return old_top5 != new_top5


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


def detect_ranking_changes(
    old_top5:   list,
    old_scores: list,
    new_ranked: list,
    all_stocks: list,
) -> dict:
    """
    Single entry point for all change-detection logic.

    Returns a dict:
      {
        'should_send':       bool,
        'reason':            str,
        'changes':           list,   # rank/score deltas for send_rescore_notice
        'shortlist_changes': list,   # entry/exit events
      }

    reason values:
      'first run'
      'top-5 changed'
      f'score change >= {SCORE_CHANGE_THRESHOLD} pts in top-10'
      'no significant changes'
    """
    new_top5     = [s['ticker'] for s in new_ranked[:5]]
    is_first_run = not old_top5
    top5_changed = _top5_changed(old_top5, new_top5)
    score_moved  = bool(old_scores and _significant_score_change(old_scores, new_ranked))

    should_send = is_first_run or top5_changed or score_moved

    if should_send:
        if is_first_run:
            reason = 'first run'
        elif top5_changed:
            reason = 'top-5 changed'
        else:
            reason = f'score change >= {SCORE_CHANGE_THRESHOLD} pts in top-10'
    else:
        reason = 'no significant changes'

    changes           = _build_changes(new_ranked, old_scores) if old_scores else []
    shortlist_changes = _build_shortlist_changes(old_scores, new_ranked, all_stocks)

    return {
        'should_send':       should_send,
        'reason':            reason,
        'changes':           changes,
        'shortlist_changes': shortlist_changes,
    }


def _build_shortlist_changes(
    old_scores:     list,
    new_ranked:     list,
    all_stocks:     list,
    portfolio_type: str = 'unified',
) -> list:
    """
    Detects stocks that entered or left the qualifying shortlist.
    Uses the unified v2 filter for exit reason lookups.
    Finds the strongest scoring factor on entries.
    """
    from engine.filters_v2 import filter_unified

    old_tickers = {s['ticker'] for s in old_scores}
    new_tickers = {s['ticker'] for s in new_ranked}

    exited  = old_tickers - new_tickers
    entered = new_tickers - old_tickers

    if not exited and not entered:
        return []

    stock_by_tk  = {s['ticker']: s for s in all_stocks}
    old_by_tk    = {s['ticker']: s for s in old_scores}

    changes = []

    for ticker in sorted(exited):
        old   = old_by_tk.get(ticker, {})
        stock = stock_by_tk.get(ticker)
        if stock is None:
            reason = "No longer in the screening universe (data unavailable or stock inactive)."
        else:
            eligible, reason = filter_unified(stock)
            if eligible:
                reason = "Score dropped below qualifying stocks in the unified ranking."
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


def _run_score_pipeline(
    portfolio_types: list | None = None,
) -> tuple[dict, list, list, list, list, dict]:
    """
    Loads stocks once, applies unified filter, then scores every portfolio type.

    Args:
        portfolio_types: List of portfolio type keys to score.  When None,
                         defaults to all keys in SCORER_WEIGHTS.

    Returns:
        (ranked_sections, all_stocks, old_top5, old_scores, eligible, fins_map)

        ranked_sections maps portfolio_type -> ranked list.  The 'unified'
        entry is the primary ranking used for change detection.
    Raises on critical failure.
    """
    from engine.filters_v2   import filter_unified_batch
    from engine.scorer_v2    import rank_stocks_v2
    from engine.sector_stats import compute_sector_stats
    from config import SCORER_WEIGHTS

    if portfolio_types is None:
        portfolio_types = list(SCORER_WEIGHTS.keys())

    all_stocks   = _load_stocks()
    sector_stats = compute_sector_stats(all_stocks)
    eligible, _  = filter_unified_batch(all_stocks)

    fins_map = {}
    for stock in eligible:
        try:
            fins_map[stock['ticker']] = db.get_financials(stock['ticker'], years=10)
        except Exception:
            fins_map[stock['ticker']] = []

    ranked_sections: dict[str, list] = {}
    for pt in portfolio_types:
        ranked_sections[pt] = rank_stocks_v2(
            eligible, sector_stats=sector_stats,
            financials_map=fins_map, portfolio_type=pt,
        )

    # Backward-compat: 'unified' is the primary ranking
    ranked = ranked_sections.get('unified', [])

    old_top5   = db.get_last_top5('unified')
    old_scores = db.get_last_scores('unified')
    return ranked_sections, all_stocks, old_top5, old_scores, eligible, fins_map


def run_daily_score():
    """
    Phase 1 — called by the scheduler at 4:00 PM PHT.

    1. Scrape latest prices
    2. Filter + score all stocks using unified 3-layer model
    3. Compare with previous run — detect rank/score changes
    4. Send rescore notices to #pse-alerts (Discord)
    5. Enrich top-10 with sentiment, send signals (deduped)
    6. Save scores to DB
    7. Write pending_pdf.json if a PDF should be sent at 6 PM

    Does NOT generate or send the PDF — that is run_daily_report().
    """
    from publisher import WEBHOOKS, send_rescore_notice, send_sentiment_signal, send_ops_alert

    if not _rescore_lock.acquire(blocking=False):
        print("  [run_daily_score] Already running — skipped.")
        return

    try:
        today = datetime.now().strftime('%Y-%m-%d')
        now   = datetime.now().strftime('%H:%M')

        print(f"\n{'='*55}")
        print(f"  PSE QUANT SAAS — 4 PM Scoring Run  {today}  {now}")
        print(f"{'='*55}")

        # ── Freshness gate: skip scoring if prices are stale ──
        if not _check_price_freshness():
            try:
                db.log_activity(
                    'pipeline', 'scoring_skipped',
                    'Stale price data — scoring aborted. Check price scraper.',
                    status='warn',
                )
            except Exception:
                pass
            print("  Scoring aborted due to stale price data.")
            return

        # ── Step 1: Scrape latest prices (from PSE Edge) ──────
        print("\n[1/3]  Scraping latest prices...")
        if scrape_daily_prices:
            prices = scrape_daily_prices()
            if prices:
                print(f"  {len(prices)} prices updated.")
            else:
                print("  Scrape returned no data — using existing DB prices.")
        else:
            print("  Scraper not available — skipping price update.")

        # ── Step 2: Load + score ───────────────────────────────
        print("\n[2/3]  Loading and scoring stocks...")
        try:
            ranked_sections, all_stocks, old_top5, old_scores, eligible, fins_map = _run_score_pipeline()
        except Exception as e:
            print(f"  Scoring failed: {e}")
            return

        ranked = ranked_sections.get('unified', [])
        print(f"  {len(all_stocks)} stocks available.")
        if not all_stocks:
            print("  No stock data available. Aborting run.")
            return
        print(f"  Ranked {len(ranked)} stock(s).")

        # ── Step 3: Detect changes ─────────────────────────────
        print("\n[3/3]  Checking for changes...")
        new_top5 = [s['ticker'] for s in ranked[:5]]
        print(f"  New top 5: {', '.join(new_top5)}")
        if old_top5:
            print(f"  Old top 5: {', '.join(old_top5)}")
        else:
            print("  Old top 5: (no previous run)")

        detection   = detect_ranking_changes(old_top5, old_scores, ranked, all_stocks)
        should_send = detection['should_send']
        reason      = detection['reason']
        changes     = detection['changes']

        if should_send:
            print(f"  PDF queued for 6 PM ({reason}).")
            _write_pending_pdf(ranked, reason, today)
        else:
            print("  No significant changes — no PDF queued.")
            _clear_pending_pdf()

        # ── Rank/score change notices ──────────────────────────
        if old_scores:
            if changes:
                print(f"  {len(changes)} rank/score change(s) detected.")
                alerts_url = WEBHOOKS.get('alerts', '')
                if alerts_url:
                    send_rescore_notice(alerts_url, 'unified', changes)
                    print("  Rescore notice sent to #pse-alerts.")
                else:
                    for c in changes:
                        print(f"    {c['ticker']}: #{c['old_rank']} -> "
                              f"#{c['new_rank']}  "
                              f"({c['old_score']:.1f} -> {c['new_score']:.1f})")
            else:
                print("  No significant rank changes.")

        # ── Sentiment enrichment + deduped signal alerts ───────
        try:
            from sentiment_engine import enrich_with_sentiment, classify_signal
            enrich_with_sentiment(ranked[:10])
            alerts_url    = WEBHOOKS.get('alerts', '')
            signal_cache  = _load_signal_cache()
            updated_cache = dict(signal_cache)

            for stock in ranked[:10]:
                sd = stock.get('sentiment_data')
                if not sd:
                    continue
                sig = classify_signal(sd, stock.get('mos_pct'), stock.get('score', 0))
                if sig['signal'] == 'monitor':
                    continue
                sent_score = sd.get('score') or 0.0
                if not _signal_is_new(signal_cache, stock['ticker'],
                                      sig['signal'], sent_score):
                    print(f"  [{sig['label']}] unchanged for "
                          f"{stock['ticker']} — skipped (dedup)")
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
                        portfolio_type    = 'unified',
                    )
                updated_cache[stock['ticker']] = {
                    'signal': sig['signal'],
                    'score':  sent_score,
                }
                print(f"  [{sig['label']}] signal sent for {stock['ticker']}")

            _save_signal_cache(updated_cache)
        except Exception as e:
            print(f"  [sentiment] skipped — {e}")

        # ── Save scores ────────────────────────────────────────
        try:
            db.save_scores(today, ranked, 'unified')              # legacy table (backward compat)

            for pt, ranked_pt in ranked_sections.items():
                try:
                    db.save_scores_v2(today, ranked_pt, portfolio_type=pt)
                    print(f"  Scores saved for portfolio_type={pt}.")
                except Exception as e:
                    print(f"  DB save error for portfolio_type={pt}: {e}")
                    send_ops_alert("Daily Score: portfolio save failed", str(e))

            print("  Scores saved to DB (scores + scores_v2 all portfolio types).")
        except Exception as e:
            print(f"  DB save error: {e}")
            send_ops_alert("Daily Score: DB save failed", str(e))

        _record_heartbeat('daily_score')

        print(f"\n{'='*55}")
        print(f"  4 PM scoring complete.  {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*55}\n")

    finally:
        _rescore_lock.release()


def _enrich_mos(stocks: list) -> list:
    """
    Adds intrinsic_value, mos_price, mos_pct to each stock dict.
    Called before PDF generation so MoS% appears in the report.
    """
    from engine.mos import (calc_ddm, calc_eps_pe, calc_dcf,
                             calc_hybrid_intrinsic, calc_mos_pct)

    for stock in stocks:
        try:
            fins   = db.get_financials(stock['ticker'], years=3)
            eps_3y = [f['eps'] for f in fins if f.get('eps') is not None][:3]
            ddm_iv, _ = calc_ddm(stock.get('dps_last'),
                                  stock.get('dividend_cagr_5y'))
            eps_iv, _ = calc_eps_pe(eps_3y)
            dcf_iv, _ = calc_dcf(stock.get('fcf_per_share'),
                                  stock.get('revenue_cagr'))
            is_holding = (stock.get('sector', '') == 'Holding Firms')
            iv, _      = calc_hybrid_intrinsic(ddm_iv, eps_iv, dcf_iv,
                                               weights=IV_WEIGHTS)
            if is_holding and iv:
                iv = round(iv * (1 - CONGLOMERATE_DISCOUNT), 2)
        except Exception:
            iv = None
        price = stock.get('current_price')
        stock['intrinsic_value'] = iv
        stock['mos_price']       = round(iv * 0.70, 2) if iv else None
        stock['mos_pct']         = calc_mos_pct(iv, price) if iv and price else None
    return stocks


def run_daily_report():
    """
    Phase 2 — called by the scheduler at 6:00 PM PHT.

    Reads pending_pdf.json written by run_daily_score().
    If present and from today, generates the PDF and sends to Discord.
    If nothing is pending, prints a note and exits silently.
    """
    from publisher import WEBHOOKS, send_report, send_ops_alert

    today = datetime.now().strftime('%Y-%m-%d')
    now   = datetime.now().strftime('%H:%M')

    print(f"\n{'='*55}")
    print(f"  PSE QUANT SAAS — 6 PM Report Run  {today}  {now}")
    print(f"{'='*55}")

    pending = _read_pending_pdf()
    if not pending:
        print("  No pending PDF — rankings unchanged since 4 PM. Nothing sent.")
        print(f"{'='*55}\n")
        return

    reason = pending.get('reason', 'rankings changed')
    print(f"  Pending PDF found ({reason}) — generating report...")

    # Rebuild ranked data for all portfolios — single pass (dividend + value for PDF)
    try:
        _ranked_sections_raw, all_stocks, _old_top5, _old_scores, eligible, fins_map = (
            _run_score_pipeline()
        )
    except Exception as e:
        print(f"  Could not rebuild rankings for PDF: {e}")
        return

    ranked_sections = {}
    bad_pdf_sections = []
    for pt in ['dividend', 'value']:
        try:
            ranked_sections[pt] = _enrich_mos(_ranked_sections_raw.get(pt, []))
        except Exception as e:
            print(f"  Score error for {pt}: {e}")
            ranked_sections[pt] = []
            bad_pdf_sections.append(pt)

    print(f"  MoS enriched: dividend={len(ranked_sections['dividend'])}, value={len(ranked_sections['value'])} stocks")

    from pdf_generator import generate_report
    from config import REPORTS_DIR
    _desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    _out_dir = os.environ.get('PDF_OUTPUT_DIR',
                              _desktop if os.path.isdir(_desktop) else REPORTS_DIR)
    os.makedirs(_out_dir, exist_ok=True)
    filename = f"StockPilot_PH_Rankings_{today}.pdf"
    pdf_path = os.path.join(_out_dir, filename)

    generate_report(
        ranked_sections        = ranked_sections,
        output_path            = pdf_path,
        total_stocks_screened  = len(all_stocks),
    )

    if bad_pdf_sections:
        _write_held_pdf(
            pdf_path,
            f"Empty sections: {', '.join(bad_pdf_sections)}",
            ranked_sections.get('dividend', []),
        )
        send_ops_alert(
            "Daily Report: portfolio scoring failed",
            f"Sections empty: {', '.join(bad_pdf_sections)}. "
            f"PDF held at {pdf_path}. "
            f"Approve with: python scheduler.py --approve-pdf",
        )
        _clear_pending_pdf()
        print(f"  Bad PDF detected ({', '.join(bad_pdf_sections)} empty) — held for review.")
        print(f"  Approve with: python scheduler.py --approve-pdf")
        return

    webhook_url = WEBHOOKS.get('rankings', '')
    if webhook_url:
        print("  Sending PDF to Discord #rankings...")
        send_report(
            webhook_url    = webhook_url,
            pdf_path       = pdf_path,
            portfolio_type = 'unified',
            ranked_stocks  = ranked_sections.get('dividend', []),
        )
    else:
        print(f"  No webhook set — PDF saved at: {pdf_path}")

    _clear_pending_pdf()

    print(f"\n{'='*55}")
    print(f"  6 PM report complete.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")


def run_approve_pdf():
    """
    Sends a held PDF that was blocked by the bad-PDF fail switch.
    The PDF was generated but not sent because one or more portfolio
    sections were empty due to a scoring failure.

    Usage: python scheduler.py --approve-pdf
    """
    from publisher import WEBHOOKS, send_report

    held = _read_held_pdf()
    if not held:
        print("  No held PDF found. Nothing to approve.")
        return

    pdf_path       = held.get('pdf_path', '')
    ranked_preview = held.get('ranked_preview', [])
    reason         = held.get('reason', 'unknown')
    held_at        = held.get('held_at', '')[:19]

    print(f"  Held PDF found (held at {held_at})")
    print(f"  Reason: {reason}")
    print(f"  File:   {pdf_path}")

    if not os.path.exists(pdf_path):
        print(f"  File no longer on disk — clearing hold.")
        _clear_held_pdf()
        return

    webhook_url = WEBHOOKS.get('rankings', '')
    if not webhook_url:
        print("  DISCORD_WEBHOOK_RANKINGS not set — cannot send. Clearing hold.")
        _clear_held_pdf()
        return

    print("  Sending held PDF to Discord #rankings...")
    success = send_report(
        webhook_url    = webhook_url,
        pdf_path       = pdf_path,
        portfolio_type = 'unified',
        ranked_stocks  = ranked_preview,
    )
    if success:
        print("  Held PDF delivered to Discord.")
    else:
        print("  Held PDF delivery failed — check webhook URL.")
    _clear_held_pdf()


def run_daily_job():
    """
    Backward-compatible entry point: runs scoring + report immediately.
    Used by run_weekly_scrape() and CLI --run-now.
    For the live scheduler, use run_daily_score() (4 PM) + run_daily_report() (6 PM).
    """
    run_daily_score()
    run_daily_report()
