# ============================================================
# routes_home.py — Home / Overview Page
# PSE Quant SaaS — Dashboard
# ============================================================

import sys
import os
import csv
import io
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, jsonify, Response
from dashboard.security import rate_limit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

import database as db
from db.db_settings import get_setting
from dashboard.db_members import (
    expire_overdue_members, get_member_stats,
    get_expiring_soon, get_recent_activity,
)
from dashboard.background import get_status as get_job_status

home_bp = Blueprint('home', __name__)


@home_bp.route('/')
def index():
    # Auto-expire overdue members on every page load
    expire_overdue_members()

    member_stats  = get_member_stats()
    expiring_soon = get_expiring_soon(days=7)
    activity      = get_recent_activity(limit=20)

    # Latest unified rankings (top 10)
    top10      = db.get_last_top5('unified') or []
    scores_raw = db.get_last_scores('unified') or []
    scores_map = {s['ticker']: s['score'] for s in scores_raw}
    unified_rankings = [
        {'ticker': t, 'score': round(scores_map.get(t, 0), 1)}
        for t in top10
    ]

    # Pricing for quick payment link card
    pm_configured = bool(os.getenv('PAYMONGO_SECRET_KEY', ''))
    pm_monthly    = int(get_setting('monthly_price_centavos',
                                     os.getenv('MONTHLY_PRICE_CENTAVOS', 29900))) / 100
    pm_annual     = int(get_setting('annual_price_centavos',
                                     os.getenv('ANNUAL_PRICE_CENTAVOS', 299900))) / 100

    context = {
        'member_stats':      member_stats,
        'expiring_soon':     expiring_soon,
        'activity':          activity,
        'unified_rankings':  unified_rankings,
        'now':               datetime.now().strftime('%Y-%m-%d %H:%M'),
        'pm_configured':     pm_configured,
        'pm_monthly':        pm_monthly,
        'pm_annual':         pm_annual,
    }
    return render_template('home.html', **context)


@home_bp.route('/api/status')
def api_status():
    """JSON endpoint: system health snapshot."""
    try:
        ticker_count = len(db.get_all_tickers())
    except Exception:
        ticker_count = 0

    db_path = db.DB_PATH
    try:
        db_size_kb = round(os.path.getsize(db_path) / 1024, 1)
    except Exception:
        db_size_kb = 0

    member_stats = get_member_stats()
    job          = get_job_status()

    # Last score run date from DB
    try:
        conn = db.get_connection()
        row  = conn.execute(
            "SELECT MAX(run_date) AS run_date FROM scores"
        ).fetchone()
        conn.close()
        last_run = row['run_date'] if row and row['run_date'] else 'Never'
    except Exception:
        last_run = 'Unknown'

    return jsonify({
        'stocks_tracked':  ticker_count,
        'db_size_kb':      db_size_kb,
        'last_score_run':  last_run,
        'active_members':  member_stats.get('active', 0),
        'expired_members': member_stats.get('expired', 0),
        'job':             job,
        'timestamp':       datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


@home_bp.route('/api/activity')
def api_activity():
    """JSON endpoint: recent activity log."""
    items = get_recent_activity(limit=30)
    return jsonify(items)


@home_bp.route('/api/rankings/export')
@rate_limit(limit=10)
def api_rankings_export():
    """CSV download of current unified rankings."""
    scores_raw = db.get_last_scores('unified') or []
    if not scores_raw:
        return jsonify({'error': 'No rankings available yet.'}), 404

    # Enrich with stock names
    conn = db.get_connection()
    name_map = {}
    try:
        rows = conn.execute("SELECT ticker, name, sector FROM stocks").fetchall()
        name_map = {r['ticker']: {'name': r['name'], 'sector': r['sector']} for r in rows}
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Rank', 'Ticker', 'Company', 'Sector', 'Score'])
    for i, s in enumerate(sorted(scores_raw, key=lambda x: x.get('score', 0), reverse=True), 1):
        t = s['ticker']
        info = name_map.get(t, {})
        writer.writerow([i, t, info.get('name', ''), info.get('sector', ''), s.get('score', '')])

    today = datetime.now().strftime('%Y-%m-%d')
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=pse_rankings_{today}.csv'},
    )


@home_bp.route('/api/health')
def api_health():
    """Health check: DB connectivity, last run, disk, scheduler."""
    from dashboard.background import get_scheduler_status

    db_ok = False
    last_run = 'Never'
    ticker_count = 0
    db_size_kb = 0

    try:
        conn = db.get_connection()
        row = conn.execute("SELECT MAX(run_date) AS run_date FROM scores").fetchone()
        conn.close()
        db_ok = True
        last_run = row['run_date'] if row and row['run_date'] else 'Never'
        ticker_count = len(db.get_all_tickers())
    except Exception as e:
        last_run = f'DB error: {e}'

    try:
        db_size_kb = round(os.path.getsize(db.DB_PATH) / 1024, 1)
    except Exception:
        pass

    sched = get_scheduler_status()

    return jsonify({
        'status':          'ok' if db_ok else 'degraded',
        'db_ok':           db_ok,
        'db_size_kb':      db_size_kb,
        'last_score_run':  last_run,
        'stocks_tracked':  ticker_count,
        'scheduler':       sched,
        'timestamp':       datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })
