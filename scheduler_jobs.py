# ============================================================
# scheduler_jobs.py — Daily Job Logic & Scoring Pipeline
# PSE Quant SaaS — scheduler sub-module
# ============================================================

import json
import os
import shutil
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'reports'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'scraper'))

from pdf_generator import generate_report
from publisher    import (WEBHOOKS, send_report, send_rescore_notice,
                          send_sentiment_signal, send_shortlist_change,
                          send_expiry_notification,
                          send_weekly_briefing, send_stock_of_week,
                          send_dividend_calendar, send_model_performance)
import database as db

try:
    from config import SCORE_CHANGE_THRESHOLD
except ImportError:
    SCORE_CHANGE_THRESHOLD = 5.0

# ── State file paths ─────────────────────────────────────────
# Stored in AppData (same dir as the DB) — Python can write there freely.
# Documents\ is write-restricted on this machine (see CLAUDE.md §16).
_STATE_DIR         = Path.home() / 'AppData' / 'Local' / 'pse_quant'
_PENDING_PDF_PATH  = _STATE_DIR / 'pending_pdf.json'
_SIGNAL_CACHE_PATH = _STATE_DIR / 'last_signals.json'

# Lock prevents concurrent runs of the scoring pipeline
_rescore_lock = threading.Lock()

from scheduler_data import (
    SCRAPER_AVAILABLE, _load_stocks,
)

# Scraper import for price updates (PSE Edge — replaces pse.com.ph which 403s)
try:
    from scraper.pse_edge_scraper import scrape_daily_prices
except ImportError:
    try:
        from pse_edge_scraper import scrape_daily_prices
    except ImportError:
        scrape_daily_prices = None


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
        old = old_by_tk.get(ticker, {})
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


# ── Sentiment dedup helpers ──────────────────────────────────

def _load_signal_cache() -> dict:
    """Loads last-sent sentiment signals from disk. Returns {} on any error."""
    try:
        with open(_SIGNAL_CACHE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_signal_cache(cache: dict):
    """Persists the sentiment signal cache to disk."""
    try:
        _SIGNAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_SIGNAL_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"  [signal cache] save failed: {e}")


def _signal_is_new(cache: dict, ticker: str, signal: str, score: float) -> bool:
    """
    Returns True if this signal should be sent.
    Skips if the same signal was already sent AND the sentiment score
    hasn't shifted more than 0.15 (on a -1.0 to 1.0 scale).
    """
    prev = cache.get(ticker, {})
    if prev.get('signal') != signal:
        return True
    return abs((prev.get('score') or 0.0) - score) >= 0.15


# ── Pending PDF helpers ───────────────────────────────────────

def _write_pending_pdf(ranked: list, reason: str, today: str):
    """Records that a PDF should be sent at the 6 PM report run."""
    try:
        _PENDING_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'date':   today,
            'reason': reason,
            'tickers': [s['ticker'] for s in ranked],
        }
        with open(_PENDING_PDF_PATH, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
    except Exception as e:
        print(f"  [pending pdf] write failed: {e}")


def _read_pending_pdf() -> dict | None:
    """Returns pending PDF info if it exists and was written today."""
    try:
        with open(_PENDING_PDF_PATH, encoding='utf-8') as f:
            data = json.load(f)
        today = datetime.now().strftime('%Y-%m-%d')
        if data.get('date') == today:
            return data
    except Exception:
        pass
    return None


def _clear_pending_pdf():
    try:
        _PENDING_PDF_PATH.unlink(missing_ok=True)
    except Exception:
        pass


# ── Shared scoring pipeline ───────────────────────────────────

def _run_score_pipeline() -> tuple[list, list, list, list]:
    """
    Loads stocks, applies unified filter, scores, enriches sentiment.
    Returns (ranked, all_stocks, old_top5, old_scores).
    Raises on critical failure.
    """
    from engine.filters_v2   import filter_unified_batch
    from engine.scorer_v2    import rank_stocks_v2
    from engine.sector_stats import compute_sector_stats

    all_stocks   = _load_stocks()
    sector_stats = compute_sector_stats(all_stocks)
    eligible, _  = filter_unified_batch(all_stocks)

    fins_map = {}
    for stock in eligible:
        try:
            fins_map[stock['ticker']] = db.get_financials(stock['ticker'], years=10)
        except Exception:
            fins_map[stock['ticker']] = []

    ranked = rank_stocks_v2(eligible, sector_stats=sector_stats,
                             financials_map=fins_map)

    old_top5   = db.get_last_top5('unified')
    old_scores = db.get_last_scores('unified')
    return ranked, all_stocks, old_top5, old_scores


def run_daily_score():
    """
    Phase 1 — called by the scheduler at 4:00 PM PHT.

    1. Scrape latest prices
    2. Filter + score all stocks using unified 4-layer model
    3. Compare with previous run — detect rank/score changes
    4. Send rescore notices to #pse-alerts (Discord)
    5. Enrich top-10 with sentiment, send signals (deduped)
    6. Save scores to DB
    7. Write pending_pdf.json if a PDF should be sent at 6 PM

    Does NOT generate or send the PDF — that is run_daily_report().
    """
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
        all_stocks = _load_stocks()
        print(f"  {len(all_stocks)} stocks available.")
        if not all_stocks:
            print("  No stock data available. Aborting run.")
            return

        try:
            ranked, all_stocks, old_top5, old_scores = _run_score_pipeline()
        except Exception as e:
            print(f"  Scoring failed: {e}")
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

        is_first_run = not old_top5
        top5_changed = _top5_changed(old_top5, new_top5)
        score_moved  = bool(old_scores and _significant_score_change(old_scores, ranked))
        should_send  = is_first_run or top5_changed or score_moved

        if should_send:
            if is_first_run:
                reason = 'first run'
            elif top5_changed:
                reason = 'top-5 changed'
            else:
                reason = f'score change >= {SCORE_CHANGE_THRESHOLD} pts in top-10'
            print(f"  PDF queued for 6 PM ({reason}).")
            _write_pending_pdf(ranked, reason, today)
        else:
            print("  No significant changes — no PDF queued.")
            _clear_pending_pdf()

        # ── Rank/score change notices ──────────────────────────
        if old_scores:
            changes = _build_changes(ranked, old_scores)
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
            alerts_url   = WEBHOOKS.get('alerts', '')
            signal_cache = _load_signal_cache()
            updated_cache = dict(signal_cache)

            for stock in ranked[:10]:
                sd = stock.get('sentiment_data')
                if not sd:
                    continue
                sig   = classify_signal(sd, stock.get('mos_pct'), stock.get('score', 0))
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
            from engine.filters_v2   import filter_unified_batch
            from engine.scorer_v2    import rank_stocks_v2
            from engine.sector_stats import compute_sector_stats
            from config import SCORER_WEIGHTS

            db.save_scores(today, ranked, 'unified')              # legacy table (backward compat)
            db.save_scores_v2(today, ranked, portfolio_type='unified')  # new clean scores_v2 table

            # Also score and save each portfolio type (pure_dividend, dividend_growth, value)
            _all_stocks_pt  = _load_stocks()
            _sector_stats   = compute_sector_stats(_all_stocks_pt)
            _eligible_pt, _ = filter_unified_batch(_all_stocks_pt)
            _fins_map = {}
            for _s in _eligible_pt:
                try:
                    _fins_map[_s['ticker']] = db.get_financials(_s['ticker'], years=10)
                except Exception:
                    _fins_map[_s['ticker']] = []

            for pt in [p for p in SCORER_WEIGHTS.keys() if p != 'unified']:
                try:
                    ranked_pt = rank_stocks_v2(
                        _eligible_pt, sector_stats=_sector_stats,
                        financials_map=_fins_map, portfolio_type=pt,
                    )
                    db.save_scores_v2(today, ranked_pt, portfolio_type=pt)
                    print(f"  Scores saved for portfolio_type={pt}.")
                except Exception as e:
                    print(f"  DB save error for portfolio_type={pt}: {e}")

            print("  Scores saved to DB (scores + scores_v2 all portfolio types).")
        except Exception as e:
            print(f"  DB save error: {e}")

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
    _IV_WEIGHTS = (0.30, 0.35, 0.35)

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
                                               weights=_IV_WEIGHTS)
            if is_holding and iv:
                iv = round(iv * 0.80, 2)
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

    # Re-load ranked data from DB (fresh from the 4 PM save)
    old_scores = db.get_last_scores('unified')
    if not old_scores:
        print("  No scored stocks in DB. Aborting report.")
        return

    # Rebuild ranked list from DB scores for PDF generation
    # (We need the full enriched stock dicts, so re-run a light score)
    try:
        ranked, all_stocks, _, _ = _run_score_pipeline()
    except Exception as e:
        print(f"  Could not rebuild rankings for PDF: {e}")
        return

    # Enrich with MoS before generating PDF
    ranked = _enrich_mos(ranked)
    enriched = sum(1 for s in ranked if s.get('mos_pct') is not None)
    print(f"  MoS enriched: {enriched}/{len(ranked)} stocks")

    DESKTOP  = os.path.join(os.path.expanduser('~'), 'Desktop')
    filename = f"PSE_UNIFIED_RANKINGS_{today}.pdf"
    pdf_path = os.path.join(DESKTOP, filename)

    generate_report(
        ranked_sections        = {'unified': ranked},
        output_path            = pdf_path,
        total_stocks_screened  = len(all_stocks),
    )

    webhook_url = WEBHOOKS.get('rankings', '')
    if webhook_url:
        print("  Sending PDF to Discord #rankings...")
        send_report(
            webhook_url    = webhook_url,
            pdf_path       = pdf_path,
            portfolio_type = 'unified',
            ranked_stocks  = ranked,
        )
    else:
        print(f"  No webhook set — PDF saved at: {pdf_path}")

    _clear_pending_pdf()

    print(f"\n{'='*55}")
    print(f"  6 PM report complete.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")


def run_daily_job():
    """
    Backward-compatible entry point: runs scoring + report immediately.
    Used by run_weekly_scrape() and CLI --run-now.
    For the live scheduler, use run_daily_score() (4 PM) + run_daily_report() (6 PM).
    """
    run_daily_score()
    run_daily_report()


def _backup_database():
    """
    Copies the SQLite DB to a timestamped backup file in the same directory.
    Prunes backups older than 4 weeks to avoid disk accumulation.
    """
    db_path = Path(db.DB_PATH)
    if not db_path.exists():
        return
    backup_dir = db_path.parent
    today_str  = datetime.now().strftime('%Y-%m-%d')
    backup_path = backup_dir / f'pse_quant_backup_{today_str}.db'
    try:
        shutil.copy2(str(db_path), str(backup_path))
        print(f"  DB backup saved: {backup_path.name}")
    except Exception as e:
        print(f"  DB backup failed: {e}")
        return

    # Prune backups older than 28 days
    cutoff = datetime.now() - timedelta(days=28)
    for old_backup in backup_dir.glob('pse_quant_backup_*.db'):
        try:
            date_str = old_backup.stem.replace('pse_quant_backup_', '')
            backup_date = datetime.strptime(date_str, '%Y-%m-%d')
            if backup_date < cutoff:
                old_backup.unlink()
                print(f"  Pruned old backup: {old_backup.name}")
        except Exception:
            pass


def run_expiry_notifications():
    """
    Daily job (9:00 AM PHT) — sends Discord alerts for subscriptions
    expiring in 7 days, 1 day, or today.

    Uses DISCORD_WEBHOOK_ALERTS channel so notifications go to the
    admin's alerts channel. Admin can then forward renewal links to
    members via Discord DM.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n[expiry_notifications]  {today}")

    try:
        sys.path.insert(0, str(ROOT / 'dashboard'))
        from dashboard.db_members import get_expiring_soon, log_activity
    except ImportError:
        try:
            from db_members import get_expiring_soon, log_activity
        except ImportError as e:
            print(f"  [expiry] db_members import failed: {e}")
            return

    alerts_url = WEBHOOKS.get('alerts', '')
    if not alerts_url:
        print("  [expiry] DISCORD_WEBHOOK_ALERTS not set — skipping.")
        return

    notified = 0
    for days_left in (7, 1, 0):
        expiring = get_expiring_soon(days=days_left)
        # Filter to only members expiring exactly on that day
        target_date = (datetime.now() + timedelta(days=days_left)).strftime('%Y-%m-%d')
        on_day = [m for m in expiring if m.get('expiry_date') == target_date]

        for member in on_day:
            try:
                send_expiry_notification(
                    webhook_url = alerts_url,
                    member_name = member['discord_name'],
                    expiry_date = member['expiry_date'],
                    days_left   = days_left,
                )
                log_activity(
                    'member', 'expiry_notification_sent',
                    f"{member['discord_name']} — {days_left}d remaining",
                )
                notified += 1
                print(f"  [expiry] Notified: {member['discord_name']} ({days_left}d)")
            except Exception as e:
                print(f"  [expiry] Failed for {member.get('discord_name', '?')}: {e}")

    print(f"  [expiry] {notified} notification(s) sent.")


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

    # ── Backup DB before any scraping overwrites data ─────────
    print("\n[0/2]  Backing up database...")
    _backup_database()

    if not SCRAPER_AVAILABLE:
        print("  Scraper not available — weekly refresh skipped.")
        print(f"{'='*55}\n")
        return

    print("\n[1/3]  Running full financial scrape (this may take several hours)...")
    try:
        from scraper.pse_edge_scraper import scrape_all_and_save
        scrape_all_and_save()
        count = len(db.get_all_tickers())
        print(f"  Full scrape complete: {count} stock(s) in DB.")
    except ImportError:
        try:
            from pse_edge_scraper import scrape_all_and_save
            scrape_all_and_save()
            count = len(db.get_all_tickers())
            print(f"  Full scrape complete: {count} stock(s) in DB.")
        except ImportError as e:
            print(f"  Scrape failed: {e}")
            print(f"{'='*55}\n")
            return
    except Exception as e:
        print(f"  Full scrape failed: {e}")
        print(f"{'='*55}\n")
        return

    # ── Step 1b: Force-refresh stale financial data ──────────
    print("\n[2/3]  Checking for stale financial data (>90 days since last update)...")
    try:
        stale_tickers = db.get_stale_financials_tickers(days=90)
        if stale_tickers:
            print(f"  {len(stale_tickers)} ticker(s) have stale financials. Re-fetching...")
            try:
                sys.path.insert(0, str(ROOT / 'scraper'))
                from pse_edge_scraper import scrape_one as _scrape_one
                for ticker in stale_tickers[:50]:   # cap at 50 per run (3s delay between requests = ~10-15 min)
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

    # ── Step 2b: Auto-update conglomerate segments from DB ────────
    print("\n[2b/3] Auto-updating conglomerate segment data from DB...")
    try:
        from engine.conglomerate_autofill import autofill_segments_from_db
        results = autofill_segments_from_db(verbose=False)
        total   = sum(results.values())
        print(f"  {total} listed-subsidiary segments refreshed across "
              f"{len(results)} conglomerates.")
    except Exception as e:
        print(f"  Conglomerate autofill failed: {e}")

    # ── Step 2c: Auto-clean bad DPS values ───────────────────
    print("\n[2c/3] Auto-cleaning implausible DPS values...")
    try:
        from db.db_maintenance import clean_bad_dps
        result = clean_bad_dps(dry_run=False)
        if result['nulled'] > 0:
            print(f"  Nulled {result['nulled']} bad DPS row(s) across: "
                  f"{', '.join(result['tickers_affected'])}")
            db.log_activity('pipeline', 'dps_auto_clean',
                            f"Nulled {result['nulled']} bad DPS row(s): "
                            f"{', '.join(result['tickers_affected'])}")
        else:
            print("  No implausible DPS values found.")
    except Exception as e:
        print(f"  DPS auto-clean failed: {e}")

    # ── Step 2d: Data quality audit ───────────────────────────
    print("\n[2d/3] Running data quality audit...")
    try:
        from db.db_data_quality import run_audit
        issues   = run_audit()
        errors   = [i for i in issues if i['severity'] == 'ERROR']
        warnings = [i for i in issues if i['severity'] == 'WARN']
        infos    = [i for i in issues if i['severity'] == 'INFO']
        print(f"  Audit complete: {len(errors)} ERROR(s), "
              f"{len(warnings)} WARN(s), {len(infos)} INFO(s)")
        for issue in errors:
            print(f"  ERROR [{issue['ticker']}] FY{issue['year']}: "
                  f"{issue['check']} — {issue['detail']}")
        if issues:
            db.log_activity(
                'pipeline', 'data_quality_audit',
                f"{len(errors)} ERROR(s), {len(warnings)} WARN(s), "
                f"{len(infos)} INFO(s) found post-scrape",
                status='warn' if errors else 'ok',
            )
    except Exception as e:
        print(f"  Data quality audit failed: {e}")

    print("\n[3/3]  Re-scoring all portfolios with fresh data...")
    run_daily_job()

    # ── Step 3b: Weekly public briefing (top 3 grades → #daily-briefing) ──
    briefing_url = WEBHOOKS.get('daily_briefing', '')
    if briefing_url:
        try:
            date_display = 'Week of ' + datetime.now().strftime('%b %d, %Y')
            ranked_now   = db.get_last_scores_v2() or []
            ranked_now   = sorted(ranked_now, key=lambda x: x.get('score', 0) or 0, reverse=True)
            if ranked_now:
                send_weekly_briefing(briefing_url, ranked_now, date_display)
                print("  Weekly briefing sent to #daily-briefing.")
            else:
                print("  Weekly briefing skipped (no ranked stocks in DB).")
        except Exception as e:
            print(f"  [weekly briefing] failed: {e}")

    # ── Step 4: Cleanup stale data + VACUUM ───────────────────
    print("\n[4/4]  Cleaning up stale data and vacuuming database...")
    try:
        stats = db.cleanup_stale_data()
        print(f"  Pruned: {stats['prices_deleted']} price rows, "
              f"{stats['activity_deleted']} activity rows, "
              f"{stats['sentiment_deleted']} sentiment rows.")
        print("  VACUUM complete — disk space reclaimed.")
    except Exception as e:
        print(f"  Cleanup failed: {e}")

    _record_heartbeat('weekly_scrape')

    print(f"\n{'='*55}")
    print(f"  Weekly scrape complete.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")


def run_weekly_digest():
    """
    Sends a personalized Weekly Digest DM to every active premium member.
    Runs every Friday at 5:00 PM PHT.
    CLI: py scheduler.py --run-digest

    Digest includes:
      - Top 5 rankings with scores
      - Biggest score movers vs last week
      - Dividends declared in the past 7 days
      - Price alerts triggered this week
      - Subscription expiry reminder (if < 14 days remaining)
    """
    from discord.discord_dm import send_dm_embed

    today     = datetime.now().strftime('%Y-%m-%d')
    week_ago  = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    week_str  = 'Week of ' + (datetime.now() - timedelta(days=6)).strftime('%b %d') \
                + '–' + datetime.now().strftime('%b %d, %Y')

    print(f"\n[weekly_digest]  {today}")

    # ── Get active members with a Discord ID ─────────────────
    try:
        sys.path.insert(0, str(ROOT / 'dashboard'))
        from dashboard.db_members import get_all_members
    except ImportError:
        try:
            from db_members import get_all_members
        except ImportError as e:
            print(f"  [digest] db_members import failed: {e}")
            return

    members = [
        m for m in get_all_members(status_filter='active')
        if m.get('discord_id')
    ]
    if not members:
        print("  [digest] No active members with Discord IDs — skipping.")
        return
    print(f"  [digest] Sending to {len(members)} active member(s)...")

    # ── Gather shared data (queried once, reused for all DMs) ─

    # Top 5 current rankings
    current    = db.get_last_scores_v2() or []
    top5       = sorted(current, key=lambda x: x.get('score', 0) or 0, reverse=True)[:5]
    score_map  = {s['ticker']: s.get('score', 0) or 0 for s in current}

    conn = db.get_connection()

    # Name map
    name_rows = conn.execute("SELECT ticker, name FROM stocks").fetchall()
    name_map  = {r['ticker']: r['name'] for r in name_rows}

    # Last week's scores for movers
    prev_row = conn.execute("""
        SELECT MAX(run_date) AS pd FROM scores_v2
        WHERE run_date < date('now', '-6 days')
    """).fetchone()
    prev_date = prev_row['pd'] if prev_row else None

    prev_scores = {}
    if prev_date:
        rows = conn.execute(
            "SELECT ticker, score FROM scores_v2 WHERE run_date = ?", (prev_date,)
        ).fetchall()
        prev_scores = {r['ticker']: r['score'] for r in rows}

    # Dividends declared this week
    div_rows = conn.execute("""
        SELECT DISTINCT ticker, title, date FROM disclosures
        WHERE (LOWER(type) LIKE '%dividend%' OR LOWER(title) LIKE '%dividend%')
          AND date >= ?
        ORDER BY date DESC
        LIMIT 5
    """, (week_ago,)).fetchall()
    dividends = [dict(r) for r in div_rows]

    # Price alerts from activity_log this week
    alert_rows = conn.execute("""
        SELECT detail, timestamp FROM activity_log
        WHERE action = 'price_alert'
          AND timestamp >= ?
        ORDER BY timestamp DESC
        LIMIT 5
    """, (week_ago + ' 00:00:00',)).fetchall()
    price_alerts = [dict(r) for r in alert_rows]

    conn.close()

    # ── Build grade helper ────────────────────────────────────
    def _grade(s):
        if s >= 80: return 'A'
        if s >= 65: return 'B'
        if s >= 50: return 'C'
        if s >= 35: return 'D'
        return 'F'

    # ── Top 5 field ───────────────────────────────────────────
    medals = ['🥇', '🥈', '🥉', '4.', '5.']
    top5_lines = []
    for i, s in enumerate(top5):
        t     = s['ticker']
        score = round(s.get('score', 0) or 0, 1)
        grade = _grade(score)
        medal = medals[i] if i < len(medals) else f'{i+1}.'
        top5_lines.append(f'{medal} **{t}** — {score} ({grade})')
    top5_text = '\n'.join(top5_lines) or 'No rankings available.'

    # ── Movers field ──────────────────────────────────────────
    movers_lines = []
    if prev_scores:
        deltas = []
        for s in current:
            t     = s['ticker']
            prev  = prev_scores.get(t)
            if prev is None:
                continue
            delta = (s.get('score') or 0) - prev
            if abs(delta) >= 1.0:
                deltas.append((t, delta))
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)
        for t, delta in deltas[:4]:
            arrow = '▲' if delta > 0 else '▼'
            movers_lines.append(f'{arrow} **{t}** {delta:+.1f} pts')
    movers_text = '\n'.join(movers_lines) or 'No significant changes this week.'

    # ── Dividends field ───────────────────────────────────────
    if dividends:
        div_lines = [
            f'• **{d["ticker"]}** — {d["title"][:60]}' for d in dividends
        ]
        div_text = '\n'.join(div_lines)
    else:
        div_text = 'No dividend declarations this week.'

    # ── Price alerts field ────────────────────────────────────
    if price_alerts:
        pa_lines = [a['detail'][:80] for a in price_alerts]
        pa_text  = '\n'.join(f'• {l}' for l in pa_lines)
    else:
        pa_text = 'No price alerts triggered this week.'

    # ── Build embed (same for all members + expiry suffix) ───
    base_fields = [
        {'name': '🏆 Top 5 This Week',          'value': top5_text,   'inline': False},
        {'name': '📈 Biggest Movers',            'value': movers_text, 'inline': False},
        {'name': '💰 Dividends Declared',        'value': div_text,    'inline': False},
        {'name': '📉 Price Alerts Triggered',    'value': pa_text,     'inline': False},
    ]

    # ── Pre-load watchlist data ───────────────────────────────
    try:
        sys.path.insert(0, str(ROOT / 'db'))
        from db.db_watchlist import get_watchlist as _get_watchlist
        watchlists_available = True
    except ImportError:
        watchlists_available = False

    # ── DM each member ────────────────────────────────────────
    sent = 0
    failed = 0
    for member in members:
        discord_id  = member['discord_id']
        name        = member.get('discord_name', 'Member')
        expiry_str  = member.get('expiry_date', '')
        fields      = list(base_fields)   # shallow copy — expiry field is member-specific

        # Personalised watchlist section
        if watchlists_available:
            try:
                wl_tickers = _get_watchlist(discord_id)
                if wl_tickers:
                    wl_lines = []
                    for wt in wl_tickers:
                        ws = score_map.get(wt)
                        wn = name_map.get(wt, wt)
                        if ws is not None:
                            wl_lines.append(f'• **{wt}** — {ws:.1f} ({_grade(ws)})  ·  {wn}')
                        else:
                            wl_lines.append(f'• **{wt}** — not yet scored  ·  {wn}')
                    fields.append({
                        'name':   f'📌 Your Watchlist  ({len(wl_tickers)} stock(s))',
                        'value':  '\n'.join(wl_lines),
                        'inline': False,
                    })
            except Exception:
                pass

        # Personalised expiry reminder
        try:
            from datetime import date as _date
            expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d').date()
            days_left = (expiry_dt - _date.today()).days
            if days_left <= 14:
                urgency = 'today' if days_left == 0 else f'in {days_left} day(s)'
                fields.append({
                    'name':   '⚠️ Subscription Reminder',
                    'value':  (
                        f'Your subscription expires **{urgency}** ({expiry_str}).\n'
                        f'Use `/subscribe` in a DM with me to renew.'
                    ),
                    'inline': False,
                })
        except Exception:
            pass

        embed = {
            'title':       f'📊 StockPilot PH — Weekly Digest  |  {week_str}',
            'description': (
                f'Hi **{name}**! Here\'s your weekly summary from StockPilot PH.\n\n'
                f'Rankings run daily. Use `/stock <ticker>` to analyse any PSE stock.'
            ),
            'color':   0x1B4B6B,
            'fields':  fields,
            'footer':  {
                'text': (
                    'StockPilot PH · Scores are educational rankings, not investment advice. '
                    'Data sourced from PSE Edge.'
                )
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }

        ok, err = send_dm_embed(discord_id, embed)
        if ok:
            sent += 1
            print(f"  [digest] OK  {name} ({discord_id})")
        else:
            failed += 1
            print(f"  [digest] ERR {name} ({discord_id}): {err}")

    print(f"  [digest] Done — {sent} sent, {failed} failed.")


def run_stock_of_week():
    """
    Picks the stock with the biggest score improvement vs last week
    (fallback: current #1 ranked stock) and posts a full analysis embed
    to the premium #deep-analysis channel.

    Runs every Monday morning at 8:00 AM PHT via the scheduler.
    Can also be triggered manually: py scheduler.py --run-sotw
    """
    from engine.scorer_v2 import score_unified
    from engine.filters_v2 import filter_unified
    from engine.mos import (calc_ddm, calc_eps_pe, calc_dcf,
                             calc_hybrid_intrinsic, calc_mos_pct)

    deep_url = WEBHOOKS.get('deep_analysis', '')
    if not deep_url:
        print("  [SOTW] DISCORD_WEBHOOK_DEEP_ANALYSIS not set — skipping.")
        return

    # ── Get current top rankings ──────────────────────────────
    current = db.get_last_scores_v2() or []
    if not current:
        print("  [SOTW] No scores in DB — run scoring first.")
        return
    current_sorted = sorted(current, key=lambda x: x.get('score', 0) or 0, reverse=True)

    # ── Get last week's scores for delta calculation ──────────
    conn = db.get_connection()
    row = conn.execute("""
        SELECT MAX(run_date) AS prev_date FROM scores_v2
        WHERE run_date < date('now', '-6 days')
    """).fetchone()
    prev_date = row['prev_date'] if row else None

    prev_by_ticker = {}
    if prev_date:
        prev_rows = conn.execute(
            "SELECT ticker, score FROM scores_v2 WHERE run_date = ?",
            (prev_date,)
        ).fetchall()
        prev_by_ticker = {r['ticker']: r['score'] for r in prev_rows}
    conn.close()

    # ── Pick the stock: biggest positive delta, fallback #1 ──
    best_ticker = current_sorted[0]['ticker']
    best_delta  = None

    if prev_by_ticker:
        best_delta_val = None
        for s in current_sorted:
            t     = s['ticker']
            prev  = prev_by_ticker.get(t)
            if prev is None:
                continue
            delta = (s.get('score') or 0) - prev
            if best_delta_val is None or delta > best_delta_val:
                best_delta_val = delta
                best_ticker    = t
                best_delta     = delta
        # Only use delta if it's actually positive
        if best_delta is not None and best_delta < 0.5:
            best_ticker = current_sorted[0]['ticker']
            best_delta  = None

    # ── Load stock data and run full analysis ─────────────────
    try:
        from scraper.pse_stock_builder import build_stock_dict_from_db
    except ImportError:
        try:
            sys.path.insert(0, str(ROOT / 'scraper'))
            from pse_stock_builder import build_stock_dict_from_db
        except ImportError as e:
            print(f"  [SOTW] Cannot import build_stock_dict_from_db: {e}")
            return

    stock = build_stock_dict_from_db(best_ticker)
    if not stock:
        print(f"  [SOTW] No stock data for {best_ticker}.")
        return

    fin_history  = db.get_financials(best_ticker, years=10)
    final_score, breakdown = score_unified(stock, financials_history=fin_history)
    score = round(final_score, 1)

    def _grade(s):
        if s >= 80: return 'A'
        if s >= 65: return 'B'
        if s >= 50: return 'C'
        if s >= 35: return 'D'
        return 'F'

    grade  = _grade(score)
    layers = breakdown.get('layers', {})

    # MoS calculation
    eps_3y = [f['eps'] for f in fin_history if f.get('eps') is not None][:3]
    ddm_iv, _ = calc_ddm(stock.get('dps_last'), stock.get('dividend_cagr_5y'))
    eps_iv, _ = calc_eps_pe(eps_3y)
    dcf_iv, _ = calc_dcf(stock.get('fcf_per_share'), stock.get('revenue_cagr'))
    iv, _     = calc_hybrid_intrinsic(ddm_iv, eps_iv, dcf_iv, weights=(0.30, 0.35, 0.35))
    if stock.get('sector') == 'Holding Firms' and iv:
        iv = round(iv * 0.80, 2)
    price   = stock.get('current_price')
    mos_pct = calc_mos_pct(iv, price) if iv and price else None

    week_str = 'Week of ' + datetime.now().strftime('%b %d, %Y')

    ok = send_stock_of_week(
        webhook_url = deep_url,
        ticker      = best_ticker,
        name        = stock.get('name', best_ticker),
        sector      = stock.get('sector', ''),
        score       = score,
        grade       = grade,
        price       = price,
        iv          = round(iv, 2) if iv else None,
        mos_pct     = round(mos_pct, 1) if mos_pct is not None else None,
        layers      = layers,
        roe         = stock.get('roe'),
        de_ratio    = stock.get('de_ratio'),
        div_yield   = stock.get('dividend_yield'),
        score_delta = round(best_delta, 1) if best_delta is not None else None,
        week_str    = week_str,
    )
    print(f"  [SOTW] Stock of the Week: {best_ticker} (score {score}, "
          f"delta {best_delta:+.1f})" if best_delta is not None
          else f"  [SOTW] Stock of the Week: {best_ticker} (score {score}, rank #1 fallback)")
    if ok:
        print("  [SOTW] Posted to #deep-analysis.")
    else:
        print("  [SOTW] Failed to post.")


def run_weekly_briefing():
    """
    Standalone function to send the weekly public briefing immediately.
    Used by CLI --run-briefing flag for testing without a full weekly scrape.
    """
    import os as _os
    briefing_url = WEBHOOKS.get('daily_briefing', '')
    if not briefing_url:
        print("  DISCORD_WEBHOOK_DAILY_BRIEFING not set in .env — skipping.")
        return
    ranked_now = db.get_last_scores_v2() or []
    ranked_now = sorted(ranked_now, key=lambda x: x.get('score', 0) or 0, reverse=True)
    if not ranked_now:
        print("  No ranked stocks in DB — run scoring first.")
        return
    date_display = 'Week of ' + datetime.now().strftime('%b %d, %Y')
    ok = send_weekly_briefing(briefing_url, ranked_now, date_display)
    print(f"  Weekly briefing {'sent' if ok else 'FAILED'}.")


# ── Monthly jobs (1st of each month) ─────────────────────────

def run_monthly_dividend_calendar():
    """
    Posts the monthly dividend calendar to #deep-analysis.
    Shows top dividend-paying stocks by yield + recent PSE Edge announcements.
    Runs on the 1st of each month.
    """
    from db.db_connection import get_connection

    month_str = datetime.now().strftime('%B %Y')
    print(f"\n[monthly_calendar] Building dividend calendar for {month_str}...")

    conn = get_connection()

    # Top 15 dividend payers from latest COMPLETED year financials × current prices.
    # Rules:
    #   1. year < current_year — exclude FY2026+ (partial data, PDF parser errors,
    #      ex-div dates from early 2026 mis-bucketed as FY2026)
    #   2. yield 0.3–20% — removes inflated DPS from PDF parser misreads
    import datetime as _dt
    current_year = _dt.date.today().year

    payer_rows = conn.execute("""
        SELECT f.ticker,
               s.name,
               f.dps,
               f.year,
               p.close AS price,
               round(f.dps / p.close * 100.0, 2) AS yield_pct
        FROM financials f
        JOIN (
            SELECT ticker, MAX(year) AS max_year
            FROM financials
            WHERE dps > 0 AND year < ?
            GROUP BY ticker
        ) latest ON f.ticker = latest.ticker AND f.year = latest.max_year
        JOIN stocks s ON f.ticker = s.ticker
        JOIN (
            SELECT t.ticker, p2.close
            FROM (SELECT ticker, MAX(date) AS max_date FROM prices GROUP BY ticker) t
            JOIN prices p2 ON p2.ticker = t.ticker AND p2.date = t.max_date
        ) p ON f.ticker = p.ticker
        WHERE f.dps > 0
          AND s.status = 'active'
          AND p.close > 0
          AND f.year < ?
          AND (f.dps / p.close * 100.0) BETWEEN 0.5 AND 20.0
          AND (
              -- REITs: always allowed (legitimate high payouts by law)
              s.is_reit = 1
              -- Has positive EPS: validate payout ratio (must be <= 200%)
              OR (f.eps > 0 AND (f.dps / f.eps) <= 2.0)
              -- Negative EPS: allow (paying dividends from retained earnings)
              OR (f.eps IS NOT NULL AND f.eps <= 0)
              -- EPS unknown: allow ONLY if yield <= 10% (low risk without validation)
              OR (f.eps IS NULL AND (f.dps / p.close * 100.0) <= 10.0)
              -- EPS unknown, yield > 10%: require at least 1 prior year of DPS
              -- history to confirm this is not a scraper error (e.g. LFM FY2025)
              OR (
                  f.eps IS NULL
                  AND (f.dps / p.close * 100.0) > 10.0
                  AND EXISTS (
                      SELECT 1 FROM financials f2
                      WHERE f2.ticker = f.ticker
                        AND f2.dps > 0
                        AND f2.year < f.year
                        AND f2.year >= f.year - 4
                  )
              )
          )
        ORDER BY yield_pct DESC
        LIMIT 15
    """, (current_year, current_year)).fetchall()

    payers = [dict(r) for r in payer_rows]

    # Dividend disclosures from the last 45 days
    cutoff = (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d')
    disc_rows = conn.execute("""
        SELECT ticker, date, title FROM disclosures
        WHERE (type LIKE '%dividend%' OR title LIKE '%dividend%')
        AND date >= ?
        ORDER BY date DESC
        LIMIT 10
    """, (cutoff,)).fetchall()

    recent_disc = [dict(r) for r in disc_rows]
    conn.close()

    url = WEBHOOKS.get('deep_analysis', '')
    ok  = send_dividend_calendar(url, month_str, payers, recent_disc)
    print(f"  Dividend calendar {'sent' if ok else 'FAILED'} for {month_str}.")


def run_monthly_model_performance():
    """
    Compares current vs last month's unified scores and posts a
    performance snapshot to #deep-analysis.
    Runs on the 1st of each month.
    """
    from db.db_connection import get_connection

    month_str = datetime.now().strftime('%B %Y')
    print(f"\n[monthly_perf] Building model performance for {month_str}...")

    conn = get_connection()

    # All distinct run dates, newest first
    date_rows = conn.execute(
        "SELECT DISTINCT run_date FROM scores_v2 ORDER BY run_date DESC LIMIT 60"
    ).fetchall()

    if not date_rows:
        print("  [monthly_perf] No scores_v2 data — run scoring first.")
        conn.close()
        return

    latest_date = date_rows[0]['run_date']
    latest_dt   = datetime.strptime(latest_date, '%Y-%m-%d')
    target_prior = latest_dt - timedelta(days=28)

    # Find closest run_date at or before 28 days ago
    prior_date = None
    for row in date_rows[1:]:
        dt = datetime.strptime(row['run_date'], '%Y-%m-%d')
        if dt <= target_prior:
            prior_date = row['run_date']
            break

    # Current top 20 with stock names
    curr_rows = conn.execute("""
        SELECT sv.ticker, sv.score, sv.rank, sv.category, s.name
        FROM scores_v2 sv
        LEFT JOIN stocks s ON sv.ticker = s.ticker
        WHERE sv.run_date = ? AND sv.rank IS NOT NULL
        ORDER BY sv.rank
        LIMIT 20
    """, (latest_date,)).fetchall()

    current = [dict(r) for r in curr_rows]

    # Prior month scores for comparison
    prior = {}
    if prior_date:
        prior_rows = conn.execute(
            "SELECT ticker, score, rank FROM scores_v2 WHERE run_date = ? AND rank IS NOT NULL",
            (prior_date,)
        ).fetchall()
        prior = {r['ticker']: {'score': r['score'], 'rank': r['rank']} for r in prior_rows}

    conn.close()

    url = WEBHOOKS.get('deep_analysis', '')
    ok  = send_model_performance(url, month_str, current, prior, latest_date, prior_date)
    print(f"  Model performance {'sent' if ok else 'FAILED'} for {month_str}.")


def run_monthly_jobs():
    """
    Runs both monthly reports on the 1st of each month:
      1. Dividend Calendar  → #deep-analysis
      2. Model Performance  → #deep-analysis
    """
    print(f"\n{'='*55}")
    print(f"  Monthly Reports — {datetime.now().strftime('%B %Y')}")
    print(f"{'='*55}")
    run_monthly_dividend_calendar()
    run_monthly_model_performance()
    print(f"\n  Monthly reports complete.")


def run_backfill():
    """One-time historical backfill: fetch 2018-2023 financials for all active tickers."""
    from scraper.pse_financial_reports import backfill_historical_financials
    from scraper.pse_session import make_session
    from db.database import get_all_tickers, get_all_cmpy_ids

    tickers = get_all_tickers(active_only=True)
    cmpy_ids = get_all_cmpy_ids()
    session = make_session()

    total = len(tickers)
    cumulative = {'fetched': 0, 'skipped': 0, 'errors': 0}
    for i, ticker in enumerate(tickers):
        cmpy_id = cmpy_ids.get(ticker)
        if not cmpy_id:
            cumulative['skipped'] += 1
            continue
        stats = backfill_historical_financials(session, cmpy_id, ticker)
        for k in cumulative:
            cumulative[k] += stats.get(k, 0)
        if (i + 1) % 10 == 0 or (i + 1) == total:
            print(f"  Backfill progress: {i+1}/{total} tickers "
                  f"(total fetched={cumulative['fetched']}, "
                  f"skipped={cumulative['skipped']}, "
                  f"errors={cumulative['errors']})")

    print(f"  Backfill complete: {total} tickers processed, "
          f"{cumulative['fetched']} years fetched")


# ── Alert check wrapper with heartbeat ───────────────────────

def run_alert_check_with_heartbeat(dry_run: bool = False):
    """
    Thin wrapper around run_alert_check() that records a scheduler heartbeat
    on successful completion. Used by the live scheduler so we can track
    that the alert job is still running.
    """
    try:
        from alerts.alert_engine import run_alert_check
    except ImportError:
        try:
            from alert_engine import run_alert_check
        except ImportError as e:
            print(f"  [alert_check] import failed: {e}")
            return
    try:
        run_alert_check(dry_run=dry_run)
    finally:
        _record_heartbeat('alert_check')


# ── Heartbeat & Freshness Gate ────────────────────────────────

def _record_heartbeat(job_name: str):
    """
    Write job completion timestamp to the settings table.
    Non-fatal — any DB or import error is silently logged to console.
    key: 'scheduler_heartbeat_{job_name}'
    value: ISO-format datetime of successful completion
    """
    try:
        from db.db_connection import get_connection
        ts = datetime.now().isoformat()
        key = f'scheduler_heartbeat_{job_name}'
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, ts, ts),
        )
        conn.commit()
        conn.close()
        print(f"  [heartbeat] {job_name} recorded at {ts[:19]}")
    except Exception as e:
        print(f"  [heartbeat] write failed for {job_name}: {e}")


def _check_price_freshness() -> bool:
    """
    Returns True if price data is fresh enough to score.
    Queries: SELECT COUNT(*) FROM prices WHERE date >= date('now', '-N days')
    If count == 0, prices are stale — sends admin DM and returns False.
    N is PRICE_STALENESS_ERROR_DAYS from config.py.
    """
    try:
        from config import PRICE_STALENESS_ERROR_DAYS
    except ImportError:
        PRICE_STALENESS_ERROR_DAYS = 30

    try:
        from db.db_connection import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM prices WHERE date >= date('now', ?)",
            (f'-{PRICE_STALENESS_ERROR_DAYS} days',),
        ).fetchone()
        conn.close()
        count = row['cnt'] if row else 0
    except Exception as e:
        print(f"  [freshness] DB query failed — skipping gate: {e}")
        return True  # fail-open: don't block scoring on a DB error

    if count == 0:
        msg = (
            f"[PSE Quant] STALE PRICE DATA — no prices updated in the last "
            f"{PRICE_STALENESS_ERROR_DAYS} days. Scoring skipped. "
            f"Check PSE Edge scraper or price pipeline."
        )
        print(f"  [freshness] {msg}")
        try:
            admin_id = os.environ.get('ADMIN_DISCORD_ID', '')
            if admin_id:
                from discord.discord_dm import send_dm_text
                send_dm_text(admin_id, msg)
        except Exception as dm_err:
            print(f"  [freshness] admin DM failed: {dm_err}")
        return False

    return True


def check_scheduler_health() -> dict:
    """
    Returns a status dict showing the last heartbeat time for each scheduled job.
    Used by the dashboard to display scheduler health at a glance.

    Return format:
    {
        'daily_score':   {'last_run': '2026-03-19T17:30:00', 'hours_ago': 23.5, 'ok': True},
        'weekly_scrape': {'last_run': None, 'hours_ago': None, 'ok': False},
        'alert_check':   {'last_run': '2026-03-19T06:30:00', 'hours_ago': 11.0, 'ok': True},
    }
    'ok' is True if last_run is within SCHEDULER_HEARTBEAT_WARN_HOURS hours (or never run yet
    for weekly_scrape, which is tolerated for up to 8 days).
    """
    try:
        from config import SCHEDULER_HEARTBEAT_WARN_HOURS
    except ImportError:
        SCHEDULER_HEARTBEAT_WARN_HOURS = 26

    JOB_WARN_HOURS = {
        'daily_score':   SCHEDULER_HEARTBEAT_WARN_HOURS,
        'weekly_scrape': 24 * 8,   # 8 days — runs once a week
        'alert_check':   SCHEDULER_HEARTBEAT_WARN_HOURS,
    }

    result = {}
    try:
        from db.db_connection import get_connection
        conn = get_connection()
        for job_name, warn_hours in JOB_WARN_HOURS.items():
            key = f'scheduler_heartbeat_{job_name}'
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row and row['value']:
                last_run = row['value']
                try:
                    dt = datetime.fromisoformat(last_run)
                    hours_ago = (datetime.now() - dt).total_seconds() / 3600
                    ok = hours_ago <= warn_hours
                except Exception:
                    hours_ago = None
                    ok = False
            else:
                last_run = None
                hours_ago = None
                ok = (job_name == 'weekly_scrape')  # never run yet is OK for weekly

            result[job_name] = {
                'last_run':  last_run,
                'hours_ago': round(hours_ago, 1) if hours_ago is not None else None,
                'ok':        ok,
            }
        conn.close()
    except Exception as e:
        print(f"  [check_scheduler_health] DB query failed: {e}")
        for job_name in JOB_WARN_HOURS:
            result.setdefault(job_name, {'last_run': None, 'hours_ago': None, 'ok': False})

    return result
