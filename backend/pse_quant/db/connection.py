"""
pse_quant/db/connection.py — Database Engine & Session Factory
PSE Quant SaaS (v2 Rebuild) — Lab 8

Provides SQLAlchemy connection pooling for PostgreSQL (and fallback SQLite for local testing),
dual-engine read replica routing, and transaction management.
"""

from __future__ import annotations
from contextlib import contextmanager
from typing import Generator
from sqlalchemy.orm import Session

from pse_quant.db.models import Base
from pse_quant.db.pool import pool_manager, DatabasePoolManager

# Backward-compatible references
engine = pool_manager.writer_engine
SessionLocal = pool_manager.WriterSession


def init_db() -> None:
    """Creates all tables on the primary writer engine if they do not exist."""
    Base.metadata.create_all(bind=pool_manager.writer_engine)
    try:
        from pse_quant.search.fts_engine import init_fts_tables
        with get_write_session() as session:
            init_fts_tables(session)
    except Exception:
        pass


@contextmanager
def get_write_session() -> Generator[Session, None, None]:
    """
    Context manager for write sessions:
    - Routes to the primary (writer) database pool.
    - Executes within a transaction with automatic commit/rollback.
    - Increments the write query routing counter.
    """
    pool_manager.record_write()
    session = pool_manager.WriterSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_read_session() -> Generator[Session, None, None]:
    """
    Context manager for read sessions:
    - Routes to the read replica pool (or isolated reader pool in SQLite fallback).
    - Read-only execution with zero commit round-trip latency.
    - Increments the read query routing counter.
    """
    pool_manager.record_read()
    session = pool_manager.ReaderSession()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Default session context manager with automatic commit/rollback.
    Maintains 100% backward compatibility for existing callers.
    """
    with get_write_session() as session:
        yield session


get_session = get_db_session


def get_db() -> Generator[Session, None, None]:
    """FastAPI route dependency for transactional write sessions."""
    with get_write_session() as session:
        yield session


def get_read_db() -> Generator[Session, None, None]:
    """FastAPI route dependency for high-throughput read-only sessions."""
    with get_read_session() as session:
        yield session
