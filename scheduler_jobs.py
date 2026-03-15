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
                          send_expiry_notification)
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
            db.save_scores(today, ranked, 'unified')   # legacy table (backward compat)
            db.save_scores_v2(today, ranked)            # new clean scores_v2 table
            print("  Scores saved to DB (scores + scores_v2).")
        except Exception as e:
            print(f"  DB save error: {e}")

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
        portfolio_type        = 'unified',
        ranked_stocks         = ranked,
        output_path           = pdf_path,
        total_stocks_screened = len(all_stocks),
    )

    webhook_url = WEBHOOKS.get('value', '')
    if webhook_url:
        print("  Sending PDF to Discord #pse-value...")
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

    print("\n[3/3]  Re-scoring all portfolios with fresh data...")
    run_daily_job()

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

    print(f"\n{'='*55}")
    print(f"  Weekly scrape complete.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")
