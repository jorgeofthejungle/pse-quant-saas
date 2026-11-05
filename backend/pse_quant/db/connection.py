"""
pse_quant/db/connection.py — Database Engine & Session Factory
Provides SQLAlchemy connection pooling for PostgreSQL (and fallback SQLite for local testing).
"""

from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from pse_quant.config import DATABASE_URL
from pse_quant.db.models import Base

# Fallback to local SQLite if DATABASE_URL is not provided (for local unit testing)
_DB_URL = DATABASE_URL
if not _DB_URL:
    _LOCAL_SQLITE = os.path.join(os.path.dirname(__file__), "pse_local.db")
    _DB_URL = f"sqlite:///{_LOCAL_SQLITE}"
elif _DB_URL.startswith("postgres://"):
    # Fix legacy Railway PostgreSQL URLs
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)

# Configure engine with pooling
_IS_SQLITE = _DB_URL.startswith("sqlite")
engine_kwargs = {}
if not _IS_SQLITE:
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    })

engine = create_engine(_DB_URL, **engine_kwargs)

if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Creates all tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


get_session = get_db_session
