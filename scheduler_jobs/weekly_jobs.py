# scheduler_jobs/weekly_jobs.py — Weekly scrape, digest, stock-of-week, briefing
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # project root
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'scraper'))

import database as db

try:
    from config import CONGLOMERATE_DISCOUNT, IV_WEIGHTS
except ImportError:
    CONGLOMERATE_DISCOUNT = 0.20
    IV_WEIGHTS            = (0.30, 0.35, 0.35)

from scheduler_data import SCRAPER_AVAILABLE

from .daily_jobs import run_daily_job
from .state import _record_heartbeat


def _backup_database():
    """PostgreSQL: no file-based backup. Use pg_dump externally."""
    print("  DB backup skipped — PostgreSQL backups handled via pg_dump.")


def run_weekly_scrape():
    """
    Sunday night full financial refresh for all PSE stocks.
    Called by the scheduler at 10:00 PM PHT every Sunday.

    Runs the full scraper to update financials, then triggers
    a full re-score so Monday morning rankings are fresh.
    """
    from publisher import WEBHOOKS, send_weekly_briefing

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
                for ticker in stale_tickers[:50]:  # cap at 50 per run (~10-15 min with 3s delays)
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

    # ── Step 2b: Auto-update conglomerate segments from DB ────
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

    # ── Step 4: Cleanup stale data ───────────────────────────
    print("\n[4/4]  Cleaning up stale data...")
    try:
        stats = db.cleanup_stale_data()
        print(f"  Pruned: {stats['prices_deleted']} price rows, "
              f"{stats['activity_deleted']} activity rows, "
              f"{stats['sentiment_deleted']} sentiment rows.")
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

    today    = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    week_str = ('Week of '
                + (datetime.now() - timedelta(days=6)).strftime('%b %d')
                + '–' + datetime.now().strftime('%b %d, %Y'))

    print(f"\n[weekly_digest]  {today}")

    # ── Get active members with a Discord ID ─────────────────
    try:
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
    current   = db.get_last_scores_v2() or []
    top5      = sorted(current, key=lambda x: x.get('score', 0) or 0, reverse=True)[:5]
    score_map = {s['ticker']: s.get('score', 0) or 0 for s in current}

    conn = db.get_connection()
    try:
        name_rows = conn.execute("SELECT ticker, name FROM stocks").fetchall()
        name_map  = {r['ticker']: r['name'] for r in name_rows}

        prev_row = conn.execute("""
            SELECT MAX(run_date) AS pd FROM scores_v2
            WHERE run_date < date('now', '-6 days')
        """).fetchone()
        prev_date = prev_row['pd'] if prev_row else None

        prev_scores = {}
        if prev_date:
            rows = conn.execute(
                "SELECT ticker, score FROM scores_v2 WHERE run_date = %s", (prev_date,)
            ).fetchall()
            prev_scores = {r['ticker']: r['score'] for r in rows}

        div_rows = conn.execute("""
            SELECT DISTINCT ticker, title, date FROM disclosures
            WHERE (LOWER(type) LIKE '%dividend%' OR LOWER(title) LIKE '%dividend%')
              AND date >= %s
            ORDER BY date DESC
            LIMIT 5
        """, (week_ago,)).fetchall()
        dividends = [dict(r) for r in div_rows]

        alert_rows = conn.execute("""
            SELECT detail, timestamp FROM activity_log
            WHERE action = 'price_alert'
              AND timestamp >= %s
            ORDER BY timestamp DESC
            LIMIT 5
        """, (week_ago + ' 00:00:00',)).fetchall()
        price_alerts = [dict(r) for r in alert_rows]
    finally:
        conn.close()

    def _grade(s):
        if s >= 80: return 'A'
        if s >= 65: return 'B'
        if s >= 50: return 'C'
        if s >= 35: return 'D'
        return 'F'

    medals = ['1.', '2.', '3.', '4.', '5.']
    top5_lines = []
    for i, s in enumerate(top5):
        t     = s['ticker']
        score = round(s.get('score', 0) or 0, 1)
        grade = _grade(score)
        medal = medals[i] if i < len(medals) else f'{i+1}.'
        top5_lines.append(f'{medal} **{t}** — {score} ({grade})')
    top5_text = '\n'.join(top5_lines) or 'No rankings available.'

    movers_lines = []
    if prev_scores:
        deltas = []
        for s in current:
            t    = s['ticker']
            prev = prev_scores.get(t)
            if prev is None:
                continue
            delta = (s.get('score') or 0) - prev
            if abs(delta) >= 1.0:
                deltas.append((t, delta))
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)
        for t, delta in deltas[:4]:
            arrow = 'up' if delta > 0 else 'down'
            movers_lines.append(f'[{arrow}] **{t}** {delta:+.1f} pts')
    movers_text = '\n'.join(movers_lines) or 'No significant changes this week.'

    if dividends:
        div_lines = [f'* **{d["ticker"]}** — {d["title"][:60]}' for d in dividends]
        div_text  = '\n'.join(div_lines)
    else:
        div_text = 'No dividend declarations this week.'

    if price_alerts:
        pa_lines = [a['detail'][:80] for a in price_alerts]
        pa_text  = '\n'.join(f'* {l}' for l in pa_lines)
    else:
        pa_text = 'No price alerts triggered this week.'

    base_fields = [
        {'name': 'Top 5 This Week',       'value': top5_text,   'inline': False},
        {'name': 'Biggest Movers',         'value': movers_text, 'inline': False},
        {'name': 'Dividends Declared',     'value': div_text,    'inline': False},
        {'name': 'Price Alerts Triggered', 'value': pa_text,     'inline': False},
    ]

    try:
        from db.db_watchlist import get_watchlist as _get_watchlist
        watchlists_available = True
    except ImportError:
        watchlists_available = False

    sent = 0
    failed = 0
    for member in members:
        discord_id = member['discord_id']
        name       = member.get('discord_name', 'Member')
        expiry_str = member.get('expiry_date', '')
        fields     = list(base_fields)

        if watchlists_available:
            try:
                wl_tickers = _get_watchlist(discord_id)
                if wl_tickers:
                    wl_lines = []
                    for wt in wl_tickers:
                        ws = score_map.get(wt)
                        wn = name_map.get(wt, wt)
                        if ws is not None:
                            wl_lines.append(f'* **{wt}** — {ws:.1f} ({_grade(ws)})  *  {wn}')
                        else:
                            wl_lines.append(f'* **{wt}** — not yet scored  *  {wn}')
                    fields.append({
                        'name':   f'Your Watchlist  ({len(wl_tickers)} stock(s))',
                        'value':  '\n'.join(wl_lines),
                        'inline': False,
                    })
            except Exception:
                pass

        try:
            from datetime import date as _date
            expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d').date()
            days_left = (expiry_dt - _date.today()).days
            if days_left <= 14:
                urgency = 'today' if days_left == 0 else f'in {days_left} day(s)'
                fields.append({
                    'name':   'Subscription Reminder',
                    'value':  (
                        f'Your subscription expires **{urgency}** ({expiry_str}).\n'
                        f'Use `/subscribe` in a DM with me to renew.'
                    ),
                    'inline': False,
                })
        except Exception:
            pass

        embed = {
            'title':       f'StockPilot PH — Weekly Digest  |  {week_str}',
            'description': (
                f'Hi **{name}**! Here\'s your weekly summary from StockPilot PH.\n\n'
                f'Rankings run daily. Use `/stock <ticker>` to analyse any PSE stock.'
            ),
            'color':     0x1B4B6B,
            'fields':    fields,
            'footer':    {
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
    from publisher         import WEBHOOKS, send_stock_of_week
    from engine.scorer_v2  import score_unified
    from engine.filters_v2 import filter_unified
    from engine.mos import (calc_ddm, calc_eps_pe, calc_dcf,
                             calc_hybrid_intrinsic, calc_mos_pct)

    deep_url = WEBHOOKS.get('deep_analysis', '')
    if not deep_url:
        print("  [SOTW] DISCORD_WEBHOOK_DEEP_ANALYSIS not set — skipping.")
        return

    current = db.get_last_scores_v2() or []
    if not current:
        print("  [SOTW] No scores in DB — run scoring first.")
        return
    current_sorted = sorted(current, key=lambda x: x.get('score', 0) or 0, reverse=True)

    conn = db.get_connection()
    try:
        row = conn.execute("""
            SELECT MAX(run_date) AS prev_date FROM scores_v2
            WHERE run_date < date('now', '-6 days')
        """).fetchone()
        prev_date = row['prev_date'] if row else None

        prev_by_ticker = {}
        if prev_date:
            prev_rows = conn.execute(
                "SELECT ticker, score FROM scores_v2 WHERE run_date = %s",
                (prev_date,)
            ).fetchall()
            prev_by_ticker = {r['ticker']: r['score'] for r in prev_rows}
    finally:
        conn.close()

    best_ticker = current_sorted[0]['ticker']
    best_delta  = None

    if prev_by_ticker:
        best_delta_val = None
        for s in current_sorted:
            t    = s['ticker']
            prev = prev_by_ticker.get(t)
            if prev is None:
                continue
            delta = (s.get('score') or 0) - prev
            if best_delta_val is None or delta > best_delta_val:
                best_delta_val = delta
                best_ticker    = t
                best_delta     = delta
        if best_delta is not None and best_delta < 0.5:
            best_ticker = current_sorted[0]['ticker']
            best_delta  = None

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
    score  = round(final_score, 1)

    def _grade(s):
        if s >= 80: return 'A'
        if s >= 65: return 'B'
        if s >= 50: return 'C'
        if s >= 35: return 'D'
        return 'F'

    grade  = _grade(score)
    layers = breakdown.get('layers', {})

    eps_3y    = [f['eps'] for f in fin_history if f.get('eps') is not None][:3]
    ddm_iv, _ = calc_ddm(stock.get('dps_last'), stock.get('dividend_cagr_5y'))
    eps_iv, _ = calc_eps_pe(eps_3y)
    dcf_iv, _ = calc_dcf(stock.get('fcf_per_share'), stock.get('revenue_cagr'))
    iv, _     = calc_hybrid_intrinsic(ddm_iv, eps_iv, dcf_iv, weights=IV_WEIGHTS)
    if stock.get('sector') == 'Holding Firms' and iv:
        iv = round(iv * (1 - CONGLOMERATE_DISCOUNT), 2)
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
    if best_delta is not None:
        print(f"  [SOTW] Stock of the Week: {best_ticker} (score {score}, delta {best_delta:+.1f})")
    else:
        print(f"  [SOTW] Stock of the Week: {best_ticker} (score {score}, rank #1 fallback)")
    print(f"  [SOTW] {'Posted to #deep-analysis.' if ok else 'Failed to post.'}")


def run_weekly_briefing():
    """
    Standalone function to send the weekly public briefing immediately.
    Used by CLI --run-briefing flag for testing without a full weekly scrape.
    """
    from publisher import WEBHOOKS, send_weekly_briefing
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
