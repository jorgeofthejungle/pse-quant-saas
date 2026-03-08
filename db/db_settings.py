# ============================================================
# db_settings.py — Runtime Settings (key-value store)
# PSE Quant SaaS
# ============================================================
# Stores admin-editable settings (pricing, schedule times) in
# the `settings` DB table. Survives dashboard restarts without
# requiring .env or config.py edits.
# ============================================================

from datetime import datetime
from db.db_connection import get_connection


def get_setting(key: str, default=None):
    """Returns the stored value for key, or default if not set."""
    try:
        conn  = get_connection()
        row   = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row['value'] if row else default
    except Exception:
        return default


def set_setting(key: str, value: str):
    """Upserts a key-value setting."""
    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_connection()
    conn.execute("""
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    """, (key, str(value), now))
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    """Returns all settings as a {key: value} dict."""
    try:
        conn = get_connection()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        return {r['key']: r['value'] for r in rows}
    except Exception:
        return {}
