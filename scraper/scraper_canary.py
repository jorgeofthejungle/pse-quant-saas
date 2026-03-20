# ============================================================
# scraper_canary.py — Scraper Change Detection Utilities
# PSE Quant SaaS — scraper sub-module
# ============================================================
# Canary checks detect when PSE Edge changes HTML structure.
# On failure: logs to settings DB and sends admin DM (once/day).
# Non-fatal — callers continue running after a canary failure.
# ============================================================

import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _get_setting(key: str) -> str | None:
    """Read a value from the settings table. Returns None if not found."""
    try:
        from db.db_connection import get_connection
        conn = get_connection()
        row = conn.execute(
            'SELECT value FROM settings WHERE key = ?', (key,)
        ).fetchone()
        conn.close()
        return row['value'] if row else None
    except Exception:
        return None


def _save_setting(key: str, value: str) -> None:
    """Upsert a value into the settings table."""
    try:
        from db.db_connection import get_connection
        now = datetime.now().isoformat()
        conn = get_connection()
        conn.execute(
            'INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
            (key, value, now),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _already_alerted_today(scraper_name: str, canary_name: str) -> bool:
    """Returns True if an alert was already sent for this canary today."""
    key = f'scraper_alert_{scraper_name}_{canary_name}'
    last_alert = _get_setting(key)
    if not last_alert:
        return False
    try:
        last_dt = datetime.fromisoformat(last_alert)
        return (datetime.now() - last_dt) < timedelta(hours=24)
    except (ValueError, TypeError):
        return False


def _mark_alerted(scraper_name: str, canary_name: str) -> None:
    """Record that an alert was sent now (for dedup)."""
    key = f'scraper_alert_{scraper_name}_{canary_name}'
    _save_setting(key, datetime.now().isoformat())


def fire_canary(scraper_name: str, canary_name: str, detail: str) -> None:
    """
    Called when a canary check fails.

    1. Logs the failure to settings table under 'scraper_health_{scraper_name}'.
    2. Sends admin DM via discord_dm.send_dm_text (once per canary per day).
    3. Always logs to console.

    Non-fatal: callers should handle this and continue execution.
    """
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_value = f'FAIL: {canary_name} | {detail} | {now_str}'

    # Always log to settings table
    _save_setting(f'scraper_health_{scraper_name}', log_value)

    # Console log (ASCII-safe for Windows cp1252 console)
    print(f'[CANARY FAIL] {scraper_name}.{canary_name}: {detail}')

    # Anti-spam: only DM once per canary per day
    if _already_alerted_today(scraper_name, canary_name):
        return

    admin_id = os.getenv('ADMIN_DISCORD_ID', '')
    if not admin_id:
        return

    message = (
        f'WARNING SCRAPER ALERT: PSE Edge structure may have changed\n\n'
        f'Scraper: {scraper_name}\n'
        f'Canary: {canary_name}\n'
        f'Detail: {detail}\n'
        f'Time: {now_str}\n\n'
        f'Check PSE Edge manually and update the scraper if needed.'
    )

    try:
        from discord.discord_dm import send_dm_text
        ok, err = send_dm_text(admin_id, message)
        if ok:
            _mark_alerted(scraper_name, canary_name)
        else:
            print(f'[CANARY] DM send failed: {err}')
    except Exception as exc:
        print(f'[CANARY] DM error: {exc}')
