# ============================================================
# routes_settings.py — Settings & Config Display
# PSE Quant SaaS — Dashboard
# ============================================================

import sys
import os
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

import database as db
from db.db_settings import get_setting, set_setting
from config import (DAILY_ALERT_HOUR, DAILY_ALERT_MINUTE,
                    PSE_EDGE_BASE_URL, SCRAPE_DELAY_SECS)

settings_bp = Blueprint('settings', __name__)

_WEBHOOK_KEYS = {
    'rankings':       'DISCORD_WEBHOOK_RANKINGS',
    'alerts':         'DISCORD_WEBHOOK_ALERTS',
    'deep_analysis':  'DISCORD_WEBHOOK_DEEP_ANALYSIS',
    'daily_briefing': 'DISCORD_WEBHOOK_DAILY_BRIEFING',
}


def _mask(url: str) -> str:
    """Masks all but the last 6 chars of a webhook URL."""
    if not url:
        return '(not set)'
    if len(url) <= 6:
        return '***'
    return '***' + url[-6:]


@settings_bp.route('/')
def index():
    # Webhook status
    webhooks = {
        name: {
            'env_key': key,
            'url':     os.getenv(key, ''),
            'masked':  _mask(os.getenv(key, '')),
            'set':     bool(os.getenv(key, '')),
        }
        for name, key in _WEBHOOK_KEYS.items()
    }

    # PayMongo — read from DB first, fallback to .env
    pm_key = os.getenv('PAYMONGO_SECRET_KEY', '')
    pm_monthly = int(get_setting('monthly_price_centavos',
                                  os.getenv('MONTHLY_PRICE_CENTAVOS', 29900))) / 100
    pm_annual  = int(get_setting('annual_price_centavos',
                                  os.getenv('ANNUAL_PRICE_CENTAVOS', 299900))) / 100

    # Scheduler times — read from DB first, fallback to config
    alert_h = int(get_setting('alert_hour',   DAILY_ALERT_HOUR))
    alert_m = int(get_setting('alert_minute', DAILY_ALERT_MINUTE))
    score_h = int(get_setting('score_hour',   16))
    score_m = int(get_setting('score_minute', 0))

    # DB stats
    db_path = db.DB_PATH
    try:
        db_size_kb = round(os.path.getsize(db_path) / 1024, 1)
    except Exception:
        db_size_kb = 0

    try:
        conn   = db.get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_counts = {}
        for t in tables:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM {t['name']}"
            ).fetchone()
            table_counts[t['name']] = row['c'] if row else 0
        conn.close()
    except Exception:
        table_counts = {}

    return render_template(
        'settings.html',
        webhooks       = webhooks,
        pm_key_set     = bool(pm_key),
        pm_monthly     = pm_monthly,
        pm_annual      = pm_annual,
        alert_hour     = alert_h,
        alert_minute   = alert_m,
        score_hour     = score_h,
        score_minute   = score_m,
        pse_base_url   = PSE_EDGE_BASE_URL,
        scrape_delay   = SCRAPE_DELAY_SECS,
        db_path        = str(db_path),
        db_size_kb     = db_size_kb,
        table_counts   = table_counts,
    )


@settings_bp.route('/save-pricing', methods=['POST'])
def save_pricing():
    """Saves monthly and annual prices to DB settings."""
    try:
        monthly_php = float(request.json.get('monthly_php', 0))
        annual_php  = float(request.json.get('annual_php',  0))
        if monthly_php <= 0 or annual_php <= 0:
            return jsonify({'ok': False, 'message': 'Prices must be greater than zero.'})
        set_setting('monthly_price_centavos', int(monthly_php * 100))
        set_setting('annual_price_centavos',  int(annual_php  * 100))
        return jsonify({'ok': True,
                        'message': f'Prices saved: Monthly PHP {monthly_php:.2f} / Annual PHP {annual_php:.2f}'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})


@settings_bp.route('/save-schedule', methods=['POST'])
def save_schedule():
    """Saves scheduler run times to DB. Restart scheduler to apply."""
    try:
        data    = request.json or {}
        alert_h = int(data.get('alert_hour',   6))
        alert_m = int(data.get('alert_minute', 30))
        score_h = int(data.get('score_hour',  16))
        score_m = int(data.get('score_minute', 0))
        if not (0 <= alert_h <= 23 and 0 <= alert_m <= 59):
            return jsonify({'ok': False, 'message': 'Invalid alert time.'})
        if not (0 <= score_h <= 23 and 0 <= score_m <= 59):
            return jsonify({'ok': False, 'message': 'Invalid score time.'})
        set_setting('alert_hour',   alert_h)
        set_setting('alert_minute', alert_m)
        set_setting('score_hour',   score_h)
        set_setting('score_minute', score_m)
        return jsonify({'ok': True,
                        'message': (f'Schedule saved — Alert: {alert_h:02d}:{alert_m:02d} PHT, '
                                    f'Score: {score_h:02d}:{score_m:02d} PHT. '
                                    f'Restart scheduler to apply.')})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})


@settings_bp.route('/test-webhook', methods=['POST'])
def test_webhook():
    """Tests a webhook URL by sending a test message."""
    channel = request.json.get('channel', '')
    env_key = _WEBHOOK_KEYS.get(channel)
    if not env_key:
        return jsonify({'ok': False, 'message': 'Unknown channel.'})

    url = os.getenv(env_key, '')
    if not url:
        return jsonify({'ok': False, 'message': f'{env_key} not set in .env'})

    try:
        from publisher import test_webhook as _test
        ok = _test(url, f'#{channel}')
        return jsonify({'ok': ok,
                        'message': 'Test message sent.' if ok else 'Webhook failed.'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})
