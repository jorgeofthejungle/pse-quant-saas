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
from config import (DAILY_ALERT_HOUR, DAILY_ALERT_MINUTE,
                    PSE_EDGE_BASE_URL, SCRAPE_DELAY_SECS)

settings_bp = Blueprint('settings', __name__)

_WEBHOOK_KEYS = {
    'pure_dividend':   'DISCORD_WEBHOOK_DIVIDEND',
    'dividend_growth': 'DISCORD_WEBHOOK_HYBRID',
    'value':           'DISCORD_WEBHOOK_VALUE',
    'alerts':          'DISCORD_WEBHOOK_ALERTS',
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

    # PayMongo
    pm_key = os.getenv('PAYMONGO_SECRET_KEY', '')
    pm_monthly  = int(os.getenv('MONTHLY_PRICE_CENTAVOS', 29900))
    pm_annual   = int(os.getenv('ANNUAL_PRICE_CENTAVOS', 299900))

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
        pm_monthly     = pm_monthly / 100,
        pm_annual      = pm_annual  / 100,
        alert_time     = f"{DAILY_ALERT_HOUR:02d}:{DAILY_ALERT_MINUTE:02d}",
        score_time     = "16:00",
        pse_base_url   = PSE_EDGE_BASE_URL,
        scrape_delay   = SCRAPE_DELAY_SECS,
        db_path        = str(db_path),
        db_size_kb     = db_size_kb,
        table_counts   = table_counts,
    )


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
