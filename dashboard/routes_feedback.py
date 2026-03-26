# ============================================================
# routes_feedback.py — Feedback Loop Dashboard
# PSE Quant SaaS — Dashboard
# ============================================================

import sys
import json
from pathlib import Path
from flask import Blueprint, render_template, jsonify, request as flask_request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

from db.db_connection import get_connection

feedback_bp = Blueprint('feedback', __name__)


@feedback_bp.route('/')
def index():
    return render_template('feedback.html')


@feedback_bp.route('/api/monthly')
def api_monthly():
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute("""
            SELECT month, portfolio_type, top10_avg_return, top10_vs_index,
                   hit_rate_positive, mos_direction_accuracy, spearman_correlation,
                   total_matched, confidence_level, score_change_flag_count,
                   score_change_minor_count, score_change_major_count
            FROM feedback_monthly
            ORDER BY month DESC, portfolio_type
            LIMIT 24
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])
    finally:
        if conn is not None:
            conn.close()


@feedback_bp.route('/api/quarterly')
def api_quarterly():
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute("""
            SELECT quarter, portfolio_type, avg_monthly_top10_return, avg_monthly_hit_rate,
                   avg_spearman, blind_spot_count, blind_spot_tickers, sectors_flagged,
                   sectors_skipped, band_inversion_flag, total_stocks_evaluated,
                   confidence_level, corrections_applied_json, corrections_blocked_json
            FROM feedback_quarterly
            ORDER BY quarter DESC, portfolio_type
            LIMIT 8
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])
    finally:
        if conn is not None:
            conn.close()


@feedback_bp.route('/api/corrections')
def api_corrections():
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT key, value, updated_at FROM settings WHERE key LIKE 'feedback_correction_%'"
        ).fetchall()
        _PREFIX = 'feedback_correction_'
        result = []
        for r in rows:
            try:
                data = json.loads(r['value'])
            except (ValueError, TypeError):
                data = {}
            # Sector+layer are in the key name, not in the blob.
            # Key format: feedback_correction_{sector}_{layer}
            # Layer is always the LAST underscore segment.
            key = r['key']
            suffix = key[len(_PREFIX):] if key.startswith(_PREFIX) else key
            parts = suffix.rsplit('_', 1)
            sector_parsed = parts[0] if len(parts) == 2 else suffix
            layer_parsed  = parts[1] if len(parts) == 2 else ''
            result.append({
                'key':        key,
                'sector':     sector_parsed,
                'layer':      layer_parsed,
                'adjustment': data.get('adjustment'),
                'cumulative': data.get('cumulative'),
                'status':     data.get('status', ''),
                'quarter':    data.get('quarter'),
                'applied_at': data.get('applied_at'),
                'updated_at': r['updated_at'],
            })
        return jsonify(result)
    except Exception:
        return jsonify([])
    finally:
        if conn is not None:
            conn.close()


@feedback_bp.route('/api/corrections/reset', methods=['POST'])
def api_corrections_reset():
    try:
        data = flask_request.get_json()
        sector = data.get('sector', '')
        layer = data.get('layer', 'health')
        from feedback.correction_engine import reset_correction
        success = reset_correction(sector, layer)
        return jsonify({'ok': success})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
