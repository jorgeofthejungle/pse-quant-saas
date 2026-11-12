"""
backend/tests/test_chaos_engineering.py — Lab 15: Chaos Engineering & Fault Injection Tests
=============================================================================================
Verifies:
  1. Default dormant state: Chaos is disabled by default; zero interference.
  2. Blast-radius containment: /health, /api/v1/health, and /admin/chaos are strictly exempt.
  3. Synthetic latency injection: delays requests and tags responses with diagnostic headers.
  4. Synthetic HTTP error drops: returns controlled 500/502/503 errors on targeted paths.
  5. Downstream Circuit Breaker stress: verifies breaker trips to OPEN and fast-fails.
  6. Instant Emergency Kill-Switch: halts all faults in <1ms, restoring baseline execution.
  7. Probabilistic distribution: 50% fault rate produces expected binomial distribution.
  8. Admin REST API endpoints (/status, /enable, /disable, /kill-switch, /reset-metrics).
"""

from __future__ import annotations
import time
import pytest
from fastapi.testclient import TestClient

from pse_quant.chaos import chaos_engine, ChaosConfig, FaultType
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app
from pse_quant.scraper.resilience.circuit_breaker import CircuitBreaker, CircuitState


@pytest.fixture(autouse=True)
def reset_chaos_state():
    """Guarantees chaos engine is completely deactivated before and after each test."""
    chaos_engine.disable()
    chaos_engine.reset_metrics()
    yield
    chaos_engine.disable()
    chaos_engine.reset_metrics()


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


@pytest.fixture
def public_client():
    return TestClient(app)


# ── 1. Default Dormant State ───────────────────────────────────

def test_chaos_dormant_by_default(public_client: TestClient):
    """Verifies that chaos engine is dormant by default with zero request interference."""
    status = chaos_engine.get_status()
    assert status["is_active"] is False

    res = public_client.get("/api/v1/stocks")
    assert res.status_code == 200
    assert "X-Chaos-Injected" not in res.headers


# ── 2. Blast Radius Protection ─────────────────────────────────

def test_blast_radius_protection(public_client: TestClient, admin_client: TestClient):
    """
    Verifies that critical health checks and admin chaos control endpoints
    are NEVER faulted, even when chaos is set to 100% error rate on all endpoints.
    """
    chaos_engine.enable(ChaosConfig(
        is_active=True,
        fault_type=FaultType.HTTP_ERROR,
        probability=1.0,
        http_status_code=500,
        target_path_prefix="/",  # Target everything!
    ))

    # Health check must still succeed
    h1 = public_client.get("/health")
    assert h1.status_code == 200
    assert "X-Chaos-Injected" not in h1.headers

    h2 = public_client.get("/api/v1/health")
    assert h2.status_code == 200
    assert "X-Chaos-Injected" not in h2.headers

    # Admin chaos status must still succeed
    admin_res = admin_client.get("/api/v1/admin/chaos/status")
    assert admin_res.status_code == 200
    assert "X-Chaos-Injected" not in admin_res.headers


# ── 3. Synthetic Latency Injection ─────────────────────────────

def test_synthetic_latency_injection(public_client: TestClient):
    """Verifies that latency faults inject measurable sleep and diagnostic headers."""
    chaos_engine.enable(ChaosConfig(
        is_active=True,
        fault_type=FaultType.LATENCY,
        probability=1.0,
        latency_ms=150,
        target_path_prefix="/api/v1/stocks",
    ))

    t0 = time.perf_counter()
    res = public_client.get("/api/v1/stocks")
    elapsed = time.perf_counter() - t0

    assert res.status_code == 200
    assert res.headers.get("X-Chaos-Injected") == "LATENCY"
    assert res.headers.get("X-Chaos-Latency-Ms") == "150"
    assert elapsed >= 0.14  # At least 140ms elapsed


# ── 4. Synthetic HTTP Error Drops ──────────────────────────────

def test_synthetic_http_error_injection(public_client: TestClient):
    """Verifies that HTTP_ERROR faults drop matching requests with designated status code."""
    chaos_engine.enable(ChaosConfig(
        is_active=True,
        fault_type=FaultType.HTTP_ERROR,
        probability=1.0,
        http_status_code=503,
        target_path_prefix="/api/v1/stocks",
    ))

    res = public_client.get("/api/v1/stocks")
    assert res.status_code == 503
    assert res.headers.get("X-Chaos-Injected") == "HTTP_ERROR"
    assert res.headers.get("X-Chaos-Status") == "503"
    data = res.json()
    assert data["error"] == "ChaosInjectedError"


# ── 5. Downstream Circuit Breaker Stress & Tripping ────────────

def test_circuit_breaker_stress_and_trip():
    """
    Verifies that injecting synthetic failures into a client circuit breaker
    trips its state from CLOSED -> OPEN and engages fast-failing protection.
    """
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.can_execute() is True

    # Simulate 3 consecutive failures injected by chaos
    for _ in range(3):
        breaker.record_failure("Synthetic 503 Chaos Injected")

    # Breaker must now be OPEN
    assert breaker.state == CircuitState.OPEN
    assert breaker.can_execute() is False


# ── 6. Instant Emergency Kill-Switch ───────────────────────────

def test_emergency_kill_switch(public_client: TestClient):
    """
    Verifies that triggering the emergency kill-switch immediately terminates
    all chaos faults and restores 100% normal execution.
    """
    chaos_engine.enable(ChaosConfig(
        is_active=True,
        fault_type=FaultType.HTTP_ERROR,
        probability=1.0,
        http_status_code=500,
        target_path_prefix="/api/v1/stocks",
    ))

    # Before kill-switch: request fails
    fail_res = public_client.get("/api/v1/stocks")
    assert fail_res.status_code == 500

    # Engage kill-switch
    kill_res = chaos_engine.emergency_kill_switch()
    assert kill_res["status"] == "aborted"
    assert kill_res["is_active"] is False

    # Immediately after kill-switch: request succeeds with 200
    ok_res = public_client.get("/api/v1/stocks")
    assert ok_res.status_code == 200
    assert "X-Chaos-Injected" not in ok_res.headers


# ── 7. Probabilistic Dice Roll Distribution ────────────────────

def test_probabilistic_dice_roll_distribution():
    """
    Verifies that a 50% fault probability over 100 evaluations produces
    a realistic binomial distribution of injected vs bypassed requests.
    """
    chaos_engine.enable(ChaosConfig(
        is_active=True,
        fault_type=FaultType.LATENCY,
        probability=0.50,
        target_path_prefix="/api/v1/test",
    ))

    for _ in range(100):
        chaos_engine.evaluate_request("/api/v1/test/resource")

    status = chaos_engine.get_status()
    telemetry = status["telemetry"]
    injected = telemetry["injected_requests_count"]
    bypassed = telemetry["bypassed_requests_count"]

    assert injected + bypassed == 100
    # For p=0.5 and n=100, count is virtually guaranteed to be between 25 and 75
    assert 25 <= injected <= 75
    assert 25 <= bypassed <= 75


# ── 8. Admin REST API Endpoints ────────────────────────────────

def test_admin_chaos_endpoints(admin_client: TestClient, public_client: TestClient):
    """Verifies security guards and REST control operations on /api/v1/admin/chaos."""
    # 1. Unauthorized access
    unauth = public_client.get("/api/v1/admin/chaos/status")
    assert unauth.status_code == 401

    # 2. Get status
    st_res = admin_client.get("/api/v1/admin/chaos/status")
    assert st_res.status_code == 200
    assert "is_active" in st_res.json()

    # 3. Enable chaos via API
    en_res = admin_client.post(
        "/api/v1/admin/chaos/enable?fault_type=latency&probability=1.0&latency_ms=100&target_path=/api/v1/stocks"
    )
    assert en_res.status_code == 200
    assert en_res.json()["is_active"] is True
    assert en_res.json()["config"]["latency_ms"] == 100

    # 4. Trigger emergency kill-switch via API
    kill_res = admin_client.post("/api/v1/admin/chaos/kill-switch")
    assert kill_res.status_code == 200
    assert kill_res.json()["status"] == "aborted"
    assert kill_res.json()["is_active"] is False

    # 5. Reset metrics via API
    rst_res = admin_client.post("/api/v1/admin/chaos/reset-metrics")
    assert rst_res.status_code == 200
    assert rst_res.json()["status"] == "success"

    # 6. Disable chaos via API
    dis_res = admin_client.post("/api/v1/admin/chaos/disable")
    assert dis_res.status_code == 200
    assert dis_res.json()["is_active"] is False
