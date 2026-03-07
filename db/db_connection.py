# ============================================================
# db_connection.py — SQLite Connection & Path Config
# PSE Quant SaaS
# ============================================================
# Single source of the DB path and connection factory.
# Imported by every other db_* module.
# ============================================================

import sqlite3
import os
from pathlib import Path

# DB path: AppData\Local\pse_quant\ (never synced by OneDrive).
# Override with PSE_DB_PATH environment variable or .env entry if needed.
_default_db = Path(os.environ.get('LOCALAPPDATA',
                   Path.home() / 'AppData' / 'Local')) / 'pse_quant' / 'pse_quant.db'
DB_PATH = Path(os.environ.get('PSE_DB_PATH', _default_db))


def get_connection() -> sqlite3.Connection:
    """
    Returns a SQLite connection to pse_quant.db.
    Row factory is set so rows can be accessed by column name.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn
