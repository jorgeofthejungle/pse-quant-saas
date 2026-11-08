"""
backend/tests/test_db_replicas_and_pool.py — Lab 8: DB Read Replicas & Connection Pool Tests
============================================================================================
Verifies:
  1. DatabasePoolManager initialization, parameter tuning, and dual-engine creation.
  2. Query routing counters (read vs write isolation).
  3. Write session transactional commit and rollback behaviors.
  4. Read session query execution and read-only isolation.
  5. High-concurrency stress test across 25 concurrent threads without pool exhaustion or starvation.
  6. Admin pool metrics and reset endpoints (/api/v1/admin/db/pool-metrics).
  7. Public API endpoints (/api/v1/stocks) routing through reader pool.
"""

from __future__ import annotations
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import text, select
from fastapi.testclient import TestClient

from pse_quant.db.pool import DatabasePoolManager, pool_manager
from pse_quant.db.connection import get_read_session, get_write_session, get_db_session
from pse_quant.db.models import Stock
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


@pytest.fixture
def public_client():
    return TestClient(app)


# ── 1. DatabasePoolManager Engine & Tuning Specs ────────────────

def test_pool_manager_configuration():
    """Verifies default pool size, overflow, timeout, and recycle parameters."""
    pm = DatabasePoolManager()
    assert pm.writer_pool_size >= 10
    assert pm.reader_pool_size >= 15
    assert pm.pool_timeout == 10.0
    assert pm.pool_recycle == 1800

    metrics = pm.get_pool_metrics()
    assert metrics["status"] == "healthy"
    assert "writer_pool" in metrics
    assert "reader_pool" in metrics
    assert "routing" in metrics
    assert "tuning" in metrics
    assert metrics["tuning"]["pool_pre_ping"] is True
    pm.dispose()


def test_pool_manager_replica_detection():
    """Verifies that providing an explicit replica URL marks is_replica_configured=True."""
    pm_no_replica = DatabasePoolManager(writer_url="sqlite:///:memory:", reader_url=None)
    assert pm_no_replica.is_replica_configured is False
    pm_no_replica.dispose()

    pm_replica = DatabasePoolManager(
        writer_url="sqlite:///:memory:",
        reader_url="sqlite:///:memory:"
    )
    assert pm_replica.is_replica_configured is True
    pm_replica.dispose()


# ── 2. Read vs Write Session Routing & Counter Isolation ────────

def test_session_routing_counters():
    """Verifies read and write query routing counters increment atomically."""
    pool_manager.reset_metrics()
    initial = pool_manager.get_pool_metrics()["routing"]
    assert initial["read_queries_routed"] == 0
    assert initial["write_queries_routed"] == 0

    # Execute read session
    with get_read_session() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1

    r_metrics = pool_manager.get_pool_metrics()["routing"]
    assert r_metrics["read_queries_routed"] == 1
    assert r_metrics["write_queries_routed"] == 0

    # Execute write session
    with get_write_session() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1

    rw_metrics = pool_manager.get_pool_metrics()["routing"]
    assert rw_metrics["read_queries_routed"] == 1
    assert rw_metrics["write_queries_routed"] == 1

    # Execute legacy get_db_session (should route to write)
    with get_db_session() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1

    leg_metrics = pool_manager.get_pool_metrics()["routing"]
    assert leg_metrics["read_queries_routed"] == 1
    assert leg_metrics["write_queries_routed"] == 2

    # Reset metrics
    pool_manager.reset_metrics()
    assert pool_manager.get_pool_metrics()["routing"]["total_queries_routed"] == 0


# ── 3. Write Session Commit and Rollback Guarantees ─────────────

def test_write_session_commit_and_rollback():
    """Verifies automatic transaction commit on success and rollback on exception."""
    test_ticker = "ZZTEST_L8"

    # Clean up if exists
    with get_write_session() as session:
        existing = session.get(Stock, test_ticker)
        if existing:
            session.delete(existing)

    # 1. Automatic commit
    with get_write_session() as session:
        stock = Stock(
            ticker=test_ticker,
            name="Lab 8 Pool Test Stock",
            sector="Holding Firms",
            status="active",
        )
        session.add(stock)

    # Verify committed and readable
    with get_read_session() as session:
        saved = session.get(Stock, test_ticker)
        assert saved is not None
        assert saved.name == "Lab 8 Pool Test Stock"

    # 2. Rollback on exception
    with pytest.raises(RuntimeError):
        with get_write_session() as session:
            stock = session.get(Stock, test_ticker)
            stock.name = "Mutated Name"
            session.add(stock)
            raise RuntimeError("Simulated transaction failure")

    # Verify not mutated
    with get_read_session() as session:
        current = session.get(Stock, test_ticker)
        assert current.name == "Lab 8 Pool Test Stock"

    # Clean up
    with get_write_session() as session:
        stock = session.get(Stock, test_ticker)
        if stock:
            session.delete(stock)


# ── 4. High-Concurrency Stress Test (No Starvation) ─────────────

def test_concurrent_read_sessions_under_load():
    """
    Spawns 25 concurrent threads all querying the reader pool simultaneously.
    Verifies that connections are checked out and returned without pool timeout.
    """
    num_threads = 25
    barrier = threading.Barrier(num_threads)
    results: list[int] = []
    errors: list[Exception] = []

    def _worker(thread_idx: int):
        try:
            # Synchronize start to maximize simultaneous checkout contention
            barrier.wait(timeout=5.0)
            with get_read_session() as session:
                val = session.execute(text("SELECT 1")).scalar()
                results.append(val)
        except Exception as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(_worker, i) for i in range(num_threads)]
        for f in futures:
            f.result()

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    assert len(results) == num_threads
    assert all(r == 1 for r in results)

    # Verify all checked-out connections returned to pool
    metrics = pool_manager.get_pool_metrics()
    assert metrics["reader_pool"]["checked_out"] == 0


# ── 5. Admin Pool Telemetry API Endpoints ───────────────────────

def test_admin_db_pool_metrics_endpoint(admin_client: TestClient):
    """Tests GET /api/v1/admin/db/pool-metrics with authorization and payload validation."""
    # 1. Unauthorized
    unauth = TestClient(app)
    res_unauth = unauth.get("/api/v1/admin/db/pool-metrics")
    assert res_unauth.status_code == 401

    # 2. Authorized
    res = admin_client.get("/api/v1/admin/db/pool-metrics")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "healthy"
    assert "routing" in data
    assert "writer_pool" in data
    assert "reader_pool" in data
    assert "tuning" in data
    assert data["writer_pool"]["pool_size"] == 15
    assert data["reader_pool"]["pool_size"] == 25
    assert data["tuning"]["pool_timeout_seconds"] == 10.0


def test_admin_db_pool_metrics_reset_endpoint(admin_client: TestClient):
    """Tests POST /api/v1/admin/db/pool-metrics/reset endpoint."""
    # Trigger routing counter
    with get_read_session() as session:
        session.execute(text("SELECT 1"))

    pre_res = admin_client.get("/api/v1/admin/db/pool-metrics")
    assert pre_res.json()["routing"]["read_queries_routed"] >= 1

    # Reset
    reset_res = admin_client.post("/api/v1/admin/db/pool-metrics/reset")
    assert reset_res.status_code == 200
    reset_data = reset_res.json()
    assert reset_data["status"] == "success"
    assert reset_data["metrics"]["routing"]["read_queries_routed"] == 0
    assert reset_data["metrics"]["routing"]["write_queries_routed"] == 0


# ── 6. Public API Route Traffic Distribution Integration ────────

def test_public_stocks_api_routes_to_reader(public_client: TestClient):
    """
    Verifies that calling the public stocks API endpoints automatically routes
    traffic to the read replica pool via get_read_db dependency.
    """
    pool_manager.reset_metrics()

    # Public endpoint: GET /api/v1/stocks
    res1 = public_client.get("/api/v1/stocks?limit=5")
    assert res1.status_code == 200

    metrics1 = pool_manager.get_pool_metrics()["routing"]
    assert metrics1["read_queries_routed"] >= 1

    # Public endpoint: GET /api/v1/stocks/ALI
    res2 = public_client.get("/api/v1/stocks/ALI")
    assert res2.status_code == 200

    metrics2 = pool_manager.get_pool_metrics()["routing"]
    assert metrics2["read_queries_routed"] >= 2
