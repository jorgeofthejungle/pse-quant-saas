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
                    PSE_EDGE_BASE_URL, SCRAPE_DELAY_SECS,
                    PH_RISK_FREE_RATE, EQUITY_RISK_PREMIUM)

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

    # Financial model rates — read from DB first, fallback to config
    rfr = float(get_setting('ph_risk_free_rate',  PH_RISK_FREE_RATE))
    erp = float(get_setting('equity_risk_premium', EQUITY_RISK_PREMIUM))

    # Scheduler times — read from DB first, fallback to config
    alert_h = int(get_setting('alert_hour',   DAILY_ALERT_HOUR))
    alert_m = int(get_setting('alert_minute', DAILY_ALERT_MINUTE))
    score_h = int(get_setting('score_hour',   16))
    score_m = int(get_setting('score_minute', 0))

    # DB stats (PostgreSQL — no local file size)
    db_path    = 'PostgreSQL'
    db_size_kb = 0

    try:
        conn   = db.get_connection()
        tables = conn.execute(
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
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
        webhooks           = webhooks,
        pm_key_set         = bool(pm_key),
        pm_monthly         = pm_monthly,
        pm_annual          = pm_annual,
        alert_hour         = alert_h,
        alert_minute       = alert_m,
        score_hour         = score_h,
        score_minute       = score_m,
        pse_base_url       = PSE_EDGE_BASE_URL,
        scrape_delay       = SCRAPE_DELAY_SECS,
        db_path            = str(db_path),
        db_size_kb         = db_size_kb,
        table_counts       = table_counts,
        risk_free_rate_pct = round(rfr * 100, 2),
        equity_risk_pct    = round(erp * 100, 2),
        required_return_pct= round((rfr + erp) * 100, 2),
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


@settings_bp.route('/save-model', methods=['POST'])
def save_model():
    """Saves risk-free rate and equity risk premium to DB."""
    try:
        data = request.json or {}
        rfr_pct = float(data.get('risk_free_rate_pct', 0))
        erp_pct = float(data.get('equity_risk_pct', 0))
        if not (0 < rfr_pct < 30):
            return jsonify({'ok': False, 'message': 'Risk-free rate must be between 0% and 30%.'})
        if not (0 < erp_pct < 30):
            return jsonify({'ok': False, 'message': 'Equity risk premium must be between 0% and 30%.'})
        set_setting('ph_risk_free_rate',  rfr_pct / 100)
        set_setting('equity_risk_premium', erp_pct / 100)
        total = round(rfr_pct + erp_pct, 2)
        return jsonify({'ok': True,
                        'message': f'Saved — Risk-free: {rfr_pct:.2f}%, ERP: {erp_pct:.2f}%, Required return: {total:.2f}%',
                        'required_return_pct': total})
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
