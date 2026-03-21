# ============================================================
# routes_analytics.py — Analytics Chart Data Endpoints
# PSE Quant SaaS — Dashboard
# ============================================================

import sys
from pathlib import Path
from flask import Blueprint, render_template, jsonify

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

import database as db
from dashboard.db_members import (
    get_revenue_by_month, get_member_growth, get_plan_distribution,
)

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/')
def index():
    return render_template('analytics.html')


@analytics_bp.route('/revenue')
def revenue():
    """JSON: monthly revenue totals (for bar chart)."""
    data   = get_revenue_by_month()
    labels = [r['month'] for r in data]
    values = [r['revenue'] for r in data]
    return jsonify({'labels': labels, 'values': values})


@analytics_bp.route('/members')
def members():
    """JSON: cumulative member growth by month (for line chart)."""
    data   = get_member_growth()
    labels = [r['month'] for r in data]
    values = [r['cumulative'] for r in data]
    return jsonify({'labels': labels, 'values': values})


@analytics_bp.route('/plans')
def plans():
    """JSON: active member count by plan type (for doughnut chart)."""
    dist = get_plan_distribution()
    return jsonify({
        'labels': list(dist.keys()),
        'values': list(dist.values()),
    })


@analytics_bp.route('/scores')
def scores():
    """
    JSON: score trends for the top 5 dividend stocks over the last 10 runs.
    Used for the score trend line chart.
    """
    try:
        conn  = db.get_connection()

        # Get last 10 run dates
        dates = conn.execute("""
            SELECT DISTINCT run_date FROM scores_v2
            ORDER BY run_date DESC LIMIT 10
        """).fetchall()
        run_dates = [r['run_date'] for r in reversed(dates)]

        if not run_dates:
            conn.close()
            return jsonify({'labels': [], 'datasets': []})

        # Get top 5 tickers from most recent run (dividend portfolio)
        latest = run_dates[-1]
        top5_rows = conn.execute("""
            SELECT ticker FROM scores_v2
            WHERE run_date = ? AND portfolio_type = 'dividend'
              AND rank IS NOT NULL
            ORDER BY rank ASC LIMIT 5
        """, (latest,)).fetchall()
        top5 = [r['ticker'] for r in top5_rows]

        if not top5:
            # Fallback: top 5 by value portfolio
            top5_rows = conn.execute("""
                SELECT ticker FROM scores_v2
                WHERE run_date = ? AND portfolio_type = 'value'
                  AND rank IS NOT NULL
                ORDER BY rank ASC LIMIT 5
            """, (latest,)).fetchall()
            top5 = [r['ticker'] for r in top5_rows]

        # Build score series per ticker
        COLOURS = ['#1B4B6B', '#27AE60', '#E74C3C', '#F39C12', '#8E44AD']
        datasets = []
        for i, ticker in enumerate(top5):
            score_data = []
            for run_date in run_dates:
                row = conn.execute("""
                    SELECT score FROM scores_v2
                    WHERE ticker = ? AND run_date = ?
                      AND portfolio_type = 'dividend'
                """, (ticker, run_date)).fetchone()
                score_data.append(
                    round(row['score'], 1) if row and row['score'] else None
                )
            datasets.append({
                'label':           ticker,
                'data':            score_data,
                'borderColor':     COLOURS[i % len(COLOURS)],
                'backgroundColor': 'transparent',
                'tension':         0.3,
            })

        conn.close()
        return jsonify({'labels': run_dates, 'datasets': datasets})

    except Exception as e:
        return jsonify({'error': str(e), 'labels': [], 'datasets': []})
