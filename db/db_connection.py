# ============================================================
# db_connection.py — PostgreSQL Connection Factory
# PSE Quant SaaS
# ============================================================
# Single source of DB connection. Imported by every db_* module.
# Exposes a sqlite3-compatible API via _PGConn so call sites
# need no changes beyond ? -> %s placeholder substitution.
# ============================================================

import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get('DATABASE_URL')
DB_PATH = None  # PostgreSQL — no local file path


class _PGConn:
    """Thin wrapper that exposes a sqlite3-compatible connection API over psycopg2."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, seq):
        cur = self._conn.cursor()
        cur.executemany(sql, seq)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._conn.close()


def get_connection() -> _PGConn:
    """Returns a PostgreSQL connection wrapped in a sqlite3-compatible interface."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it to your PostgreSQL connection string."
        )
    pg_conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    return _PGConn(pg_conn)
