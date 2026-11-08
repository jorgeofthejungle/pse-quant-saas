"""
pse_quant/db/pool.py — High-Performance Connection Pool & Read Replica Router
PSE Quant SaaS (v2 Rebuild) — Lab 8

Decouples heavy background write operations (ETL scraping, payment fulfillment, alerts)
from fast, concurrent read traffic (screeners, stock fact cards, ranking lookups).
Provides connection pool telemetry and graceful local SQLite fallback.
"""

from __future__ import annotations
import os
import threading
from typing import Any, Dict
from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from pse_quant.config import (
    DATABASE_URL,
    DATABASE_REPLICA_URL,
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW,
    DB_POOL_TIMEOUT,
    DB_POOL_RECYCLE,
    DB_REPLICA_POOL_SIZE,
    DB_REPLICA_MAX_OVERFLOW,
)


def _normalize_db_url(url: str | None) -> str:
    """Normalizes database connection string with local SQLite fallback."""
    if not url:
        local_sqlite = os.path.join(os.path.dirname(__file__), "pse_local.db")
        return f"sqlite:///{local_sqlite}"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class DatabasePoolManager:
    """
    Manages dual-engine database connections (Writer and Reader Replica)
    with tuned pooling parameters and query routing observability.
    """

    def __init__(
        self,
        writer_url: str | None = None,
        reader_url: str | None = None,
        writer_pool_size: int = DB_POOL_SIZE,
        writer_max_overflow: int = DB_MAX_OVERFLOW,
        reader_pool_size: int = DB_REPLICA_POOL_SIZE,
        reader_max_overflow: int = DB_REPLICA_MAX_OVERFLOW,
        pool_timeout: float = DB_POOL_TIMEOUT,
        pool_recycle: int = DB_POOL_RECYCLE,
    ):
        self.writer_url = _normalize_db_url(writer_url or DATABASE_URL)
        self.is_replica_configured = bool(reader_url or DATABASE_REPLICA_URL)
        self.reader_url = _normalize_db_url(reader_url or DATABASE_REPLICA_URL or self.writer_url)

        self.writer_pool_size = writer_pool_size
        self.writer_max_overflow = writer_max_overflow
        self.reader_pool_size = reader_pool_size
        self.reader_max_overflow = reader_max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle

        # Routing counters & thread lock
        self._read_queries_routed = 0
        self._write_queries_routed = 0
        self._lock = threading.Lock()

        # Initialize engines
        self.writer_engine = self._create_engine_instance(
            url=self.writer_url,
            pool_size=self.writer_pool_size,
            max_overflow=self.writer_max_overflow,
            name="writer",
        )
        self.reader_engine = self._create_engine_instance(
            url=self.reader_url,
            pool_size=self.reader_pool_size,
            max_overflow=self.reader_max_overflow,
            name="reader",
        )

        # Session factories
        self.WriterSession = sessionmaker(
            autocommit=False, autoflush=False, bind=self.writer_engine
        )
        self.ReaderSession = sessionmaker(
            autocommit=False, autoflush=False, bind=self.reader_engine
        )

    def _create_engine_instance(
        self, url: str, pool_size: int, max_overflow: int, name: str
    ) -> Engine:
        """Configures a tuned SQLAlchemy engine with QueuePool telemetry."""
        is_sqlite = url.startswith("sqlite")
        kwargs: dict[str, Any] = {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "pool_pre_ping": True,
        }

        if is_sqlite:
            # File-based SQLite supports QueuePool for concurrent multi-threaded access
            kwargs["poolclass"] = QueuePool
            kwargs["connect_args"] = {"timeout": 30, "check_same_thread": False}

        engine = create_engine(url, **kwargs)

        if is_sqlite:
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        return engine

    def record_read(self) -> None:
        """Atomically increments read query routing counter."""
        with self._lock:
            self._read_queries_routed += 1

    def record_write(self) -> None:
        """Atomically increments write query routing counter."""
        with self._lock:
            self._write_queries_routed += 1

    def reset_metrics(self) -> None:
        """Resets telemetry counters for testing and monitoring windows."""
        with self._lock:
            self._read_queries_routed = 0
            self._write_queries_routed = 0

    @staticmethod
    def _extract_pool_stats(engine: Engine) -> Dict[str, Any]:
        """Extracts runtime checked-in, checked-out, and overflow stats from an engine pool."""
        pool = engine.pool
        size = pool.size() if hasattr(pool, "size") else 0
        checked_in = pool.checkedin() if hasattr(pool, "checkedin") else 0
        checked_out = pool.checkedout() if hasattr(pool, "checkedout") else 0
        overflow = pool.overflow() if hasattr(pool, "overflow") else 0
        # In QueuePool, negative overflow means free capacity remaining under pool_size
        active_connections = checked_out + max(0, overflow)

        return {
            "pool_size": size,
            "checked_in": checked_in,
            "checked_out": checked_out,
            "overflow": overflow,
            "active_connections": active_connections,
        }

    def get_pool_metrics(self) -> Dict[str, Any]:
        """Returns deep telemetry for both connection pools and query routing distribution."""
        with self._lock:
            reads = self._read_queries_routed
            writes = self._write_queries_routed

        total = reads + writes
        read_ratio = round((reads / total) * 100.0, 2) if total > 0 else 0.0

        return {
            "status": "healthy",
            "routing": {
                "read_queries_routed": reads,
                "write_queries_routed": writes,
                "total_queries_routed": total,
                "read_percentage": read_ratio,
                "read_replica_configured": self.is_replica_configured,
            },
            "writer_pool": self._extract_pool_stats(self.writer_engine),
            "reader_pool": self._extract_pool_stats(self.reader_engine),
            "tuning": {
                "writer_pool_size": self.writer_pool_size,
                "writer_max_overflow": self.writer_max_overflow,
                "reader_pool_size": self.reader_pool_size,
                "reader_max_overflow": self.reader_max_overflow,
                "pool_timeout_seconds": self.pool_timeout,
                "pool_recycle_seconds": self.pool_recycle,
                "pool_pre_ping": True,
            },
        }

    def dispose(self) -> None:
        """Gracefully closes all connections across both writer and reader pools."""
        self.writer_engine.dispose()
        self.reader_engine.dispose()


# Global singleton instance
pool_manager = DatabasePoolManager()
