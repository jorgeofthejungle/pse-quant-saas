# ============================================================
# routes_home.py — Home / Overview Page
# PSE Quant SaaS — Dashboard
# ============================================================

import sys
import os
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, jsonify

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

import database as db
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

    # Latest top-5 for each portfolio
    portfolios = {}
    for pt in ['pure_dividend', 'dividend_growth', 'value']:
        portfolios[pt] = db.get_last_top5(pt) or []

    context = {
        'member_stats':   member_stats,
        'expiring_soon':  expiring_soon,
        'activity':       activity,
        'portfolios':     portfolios,
        'now':            datetime.now().strftime('%Y-%m-%d %H:%M'),
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
