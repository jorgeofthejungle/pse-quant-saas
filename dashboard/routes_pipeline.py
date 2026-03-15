# ============================================================
# routes_pipeline.py — Pipeline Controls
# PSE Quant SaaS — Dashboard
# ============================================================

import sys
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, jsonify, request, redirect, url_for

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

import database as db
from dashboard.background import (
    run_scoring, run_alerts, get_status, is_running,
    start_scheduler, stop_scheduler, get_scheduler_status,
    start_bot, stop_bot, get_bot_status,
)
from config import DAILY_ALERT_HOUR, DAILY_ALERT_MINUTE

pipeline_bp = Blueprint('pipeline', __name__)


@pipeline_bp.route('/')
def index():
    job = get_status()

    # Last 5 score run dates from DB
    try:
        conn      = db.get_connection()
        run_dates = conn.execute("""
            SELECT DISTINCT run_date FROM scores
            ORDER BY run_date DESC LIMIT 5
        """).fetchall()
        conn.close()
        recent_runs = [r['run_date'] for r in run_dates]
    except Exception:
        recent_runs = []

    # Latest unified rankings (top 10)
    rankings = {}
    top5       = db.get_last_top5('unified') or []
    scores_raw = db.get_last_scores('unified') or []
    scores_map = {s['ticker']: s['score'] for s in scores_raw}
    rankings['unified'] = [
        {'ticker': t, 'score': round(scores_map.get(t, 0), 1)}
        for t in top5
    ]

    return render_template('pipeline.html',
                           job=job,
                           recent_runs=recent_runs,
                           rankings=rankings,
                           scheduler=get_scheduler_status(),
                           bot=get_bot_status(),
                           alert_time=f"{DAILY_ALERT_HOUR:02d}:{DAILY_ALERT_MINUTE:02d}",
                           now=datetime.now().strftime('%Y-%m-%d %H:%M'))


@pipeline_bp.route('/run', methods=['POST'])
def trigger_run():
    """Start the full scoring pipeline in background."""
    dry_run = request.form.get('dry_run') == '1'
    started, msg = run_scoring(portfolio='all', dry_run=dry_run)
    return jsonify({'started': started, 'message': msg})


@pipeline_bp.route('/alerts', methods=['POST'])
def trigger_alerts():
    """Start the alert check in background."""
    dry_run = request.form.get('dry_run') == '1'
    started, msg = run_alerts(dry_run=dry_run)
    return jsonify({'started': started, 'message': msg})


@pipeline_bp.route('/status')
def job_status():
    """JSON: current background job state (polled by frontend)."""
    return jsonify(get_status())


@pipeline_bp.route('/scheduler/start', methods=['POST'])
def scheduler_start():
    ok, msg = start_scheduler()
    return jsonify({'ok': ok, 'message': msg})


@pipeline_bp.route('/scheduler/stop', methods=['POST'])
def scheduler_stop():
    ok, msg = stop_scheduler()
    return jsonify({'ok': ok, 'message': msg})


@pipeline_bp.route('/scheduler/status')
def scheduler_status():
    return jsonify(get_scheduler_status())


@pipeline_bp.route('/history')
def history():
    """JSON: recent score run dates and top-5 tickers per portfolio."""
    try:
        conn  = db.get_connection()
        dates = conn.execute("""
            SELECT DISTINCT run_date FROM scores
            ORDER BY run_date DESC LIMIT 10
        """).fetchall()
        conn.close()
        run_dates = [r['run_date'] for r in dates]
    except Exception:
        run_dates = []

    result = []
    for run_date in run_dates:
        entry = {'run_date': run_date, 'portfolios': {}}
        for pt in ['pure_dividend', 'dividend_growth', 'value']:
            try:
                conn = db.get_connection()
                rows = conn.execute("""
                    SELECT ticker, COALESCE(pure_dividend_rank,
                           dividend_growth_rank, value_rank) AS rnk
                    FROM scores
                    WHERE run_date = ?
                      AND (
                        (? = 'pure_dividend'   AND pure_dividend_rank   IS NOT NULL) OR
                        (? = 'dividend_growth' AND dividend_growth_rank IS NOT NULL) OR
                        (? = 'value'           AND value_rank           IS NOT NULL)
                      )
                    ORDER BY rnk ASC LIMIT 5
                """, (run_date, pt, pt, pt)).fetchall()
                conn.close()
                entry['portfolios'][pt] = [r['ticker'] for r in rows]
            except Exception:
                entry['portfolios'][pt] = []
        result.append(entry)

    return jsonify(result)


@pipeline_bp.route('/bot/start', methods=['POST'])
def bot_start():
    ok, msg = start_bot()
    return jsonify({'ok': ok, 'message': msg})


@pipeline_bp.route('/bot/stop', methods=['POST'])
def bot_stop():
    ok, msg = stop_bot()
    return jsonify({'ok': ok, 'message': msg})


@pipeline_bp.route('/bot/status')
def bot_status():
    return jsonify(get_bot_status())
