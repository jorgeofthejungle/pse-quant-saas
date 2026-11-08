"""
backend/tests/test_distributed_tracing.py — Lab 10: Distributed Tracing & Observability Tests
=============================================================================================
Verifies:
  1. ContextVar correlation ID and trace metadata ambient propagation.
  2. Structured JSON log formatting with active correlation ID and exception serialization.
  3. LatencyTracker percentile math (p50, p95, p99) and bounded circular trace buffer.
  4. TracingMiddleware header propagation (X-Correlation-ID, X-Response-Time-Ms, traceparent).
  5. Background task worker trace context inheritance (HTTP request -> TaskRecord -> Worker thread).
  6. Admin telemetry endpoints (/api/v1/admin/telemetry/latency, /traces, /live, /reset).
"""

from __future__ import annotations
import json
import logging
import io
import pytest
from fastapi.testclient import TestClient

from pse_quant.telemetry.context import (
    get_correlation_id,
    set_correlation_id,
    reset_correlation_id,
    generate_correlation_id,
    get_trace_metadata,
    set_trace_metadata,
    reset_trace_metadata,
)
from pse_quant.telemetry.logging import StructuredJsonFormatter, CorrelationIdFilter
from pse_quant.telemetry.tracker import LatencyTracker, global_latency_tracker
from pse_quant.tasks.engine import task_queue, TaskWorker, task, TaskStatus
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


@pytest.fixture
def public_client():
    return TestClient(app)


# ── 1. ContextVar Ambient Propagation ──────────────────────────

def test_context_var_correlation_id_lifecycle():
    """Tests setting, retrieving, and resetting correlation ID in ambient execution context."""
    assert get_correlation_id() == ""

    test_corr = generate_correlation_id()
    assert test_corr.startswith("corr_")

    token = set_correlation_id(test_corr)
    assert get_correlation_id() == test_corr

    reset_correlation_id(token)
    assert get_correlation_id() == ""


def test_context_var_trace_metadata_lifecycle():
    """Tests ambient trace metadata dictionary binding."""
    meta = {"path": "/api/v1/stocks", "method": "GET", "user_id": 42}
    token = set_trace_metadata(meta)
    assert get_trace_metadata() == meta

    reset_trace_metadata(token)
    assert get_trace_metadata() == {}


# ── 2. Structured JSON Logging ─────────────────────────────────

def test_structured_json_log_formatter():
    """Verifies logger outputs RFC-compliant JSON with active correlation ID."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredJsonFormatter())
    handler.addFilter(CorrelationIdFilter())

    test_logger = logging.getLogger("pse_quant.test.tracing")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(handler)

    token = set_correlation_id("corr_log_test_abc123")
    try:
        test_logger.info("Executed market screening rule", extra={"path": "/stocks", "status_code": 200})
    finally:
        reset_correlation_id(token)

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "pse_quant.test.tracing"
    assert data["message"] == "Executed market screening rule"
    assert data["correlation_id"] == "corr_log_test_abc123"
    assert data["path"] == "/stocks"
    assert data["status_code"] == 200
    assert "timestamp" in data


def test_structured_json_log_exception_trace():
    """Verifies exceptions are serialized into structured JSON with stack traces."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredJsonFormatter())

    test_logger = logging.getLogger("pse_quant.test.exceptions")
    test_logger.addHandler(handler)

    try:
        raise ValueError("Invalid stock ticker format")
    except ValueError:
        test_logger.error("Valuation failed", exc_info=True)

    data = json.loads(stream.getvalue().strip())
    assert "exception" in data
    assert data["exception"]["type"] == "ValueError"
    assert "Invalid stock ticker format" in data["exception"]["message"]
    assert len(data["exception"]["stack"]) > 0


# ── 3. LatencyTracker Reservoir & Quantile Math ─────────────────

def test_latency_tracker_percentiles():
    """Tests quantile computation (p50, p95, p99) against controlled samples."""
    tracker = LatencyTracker(max_traces=50)

    # Seed 100 samples from 1.0ms to 100.0ms
    for i in range(1, 101):
        tracker.record_request(
            method="GET",
            path="/api/v1/stocks",
            duration_ms=float(i),
            status_code=200,
            correlation_id=f"corr_{i}",
        )

    summary = tracker.get_summary()
    route_stats = summary["routes"]["GET /api/v1/stocks"]

    assert route_stats["count"] == 100
    assert route_stats["min_ms"] == 1.0
    assert route_stats["max_ms"] == 100.0
    assert 49.0 <= route_stats["p50_ms"] <= 52.0
    assert 94.0 <= route_stats["p95_ms"] <= 96.0
    assert 98.0 <= route_stats["p99_ms"] <= 100.0
    assert route_stats["avg_ms"] == 50.5

    # Check recent trace buffer
    traces = tracker.get_recent_traces(limit=10)
    assert len(traces) == 10
    assert traces[0]["correlation_id"] == "corr_100"


# ── 4. TracingMiddleware & Header Propagation ──────────────────

def test_tracing_middleware_generates_correlation_id(public_client: TestClient):
    """Verifies that an incoming request without correlation header receives an auto-generated one."""
    res = public_client.get("/api/v1/health")
    assert res.status_code == 200

    corr_id = res.headers.get("X-Correlation-ID")
    assert corr_id is not None
    assert corr_id.startswith("corr_")

    resp_time = res.headers.get("X-Response-Time-Ms")
    assert resp_time is not None
    assert resp_time.endswith("ms")


def test_tracing_middleware_preserves_custom_correlation_id(public_client: TestClient):
    """Verifies that an incoming X-Correlation-ID header is propagated into the response."""
    custom_id = "corr_custom_client_98765"
    res = public_client.get("/api/v1/health", headers={"X-Correlation-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Correlation-ID") == custom_id


def test_tracing_middleware_adopts_traceparent(public_client: TestClient):
    """Verifies W3C traceparent header extraction."""
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    res = public_client.get("/api/v1/health", headers={"traceparent": traceparent})
    assert res.status_code == 200

    corr_id = res.headers.get("X-Correlation-ID")
    assert corr_id is not None
    assert "4bf92f3577b34da6" in corr_id


# ── 5. Background Worker Trace Context Inheritance ─────────────

def test_task_worker_inherits_correlation_id():
    """
    Verifies that enqueuing a background task within an HTTP context
    inherits the ambient correlation ID, and the worker restores it upon execution.
    """
    observed_corr: list[str] = []

    @task("test.trace_inspector")
    def inspect_trace(payload: dict) -> dict:
        current_corr = get_correlation_id()
        observed_corr.append(current_corr)
        return {"observed_corr": current_corr}

    # Simulate active HTTP request correlation
    parent_corr = "corr_http_req_root_555"
    token = set_correlation_id(parent_corr)
    try:
        task_info = task_queue.enqueue("test.trace_inspector", payload={"foo": "bar"})
    finally:
        reset_correlation_id(token)

    task_id = task_info["task_id"]

    # Execute with worker in separate context
    worker = TaskWorker(worker_id="trace_test_worker")
    processed = worker.run_once()
    assert processed is True

    # Assert worker restored exact parent correlation ID
    assert len(observed_corr) == 1
    assert observed_corr[0] == parent_corr

    status = task_queue.get_task_status(task_id)
    assert status["status"] == TaskStatus.COMPLETED
    assert status["result"]["observed_corr"] == parent_corr


# ── 6. Admin Observability Endpoints ───────────────────────────

def test_admin_telemetry_latency_endpoint(admin_client: TestClient, public_client: TestClient):
    """Verifies GET /api/v1/admin/telemetry/latency returns route histograms."""
    # Generate some traffic
    public_client.get("/api/v1/health")
    public_client.get("/api/v1/stocks?limit=2")

    res = admin_client.get("/api/v1/admin/telemetry/latency")
    assert res.status_code == 200
    data = res.json()

    assert "overall" in data
    assert "routes" in data
    assert data["overall"]["total_requests"] >= 2
    assert "p50_ms" in data["overall"]
    assert "p95_ms" in data["overall"]


def test_admin_telemetry_traces_endpoint(admin_client: TestClient, public_client: TestClient):
    """Verifies GET /api/v1/admin/telemetry/traces returns recent sampled requests."""
    corr_header = "corr_unique_trace_999"
    public_client.get("/api/v1/health", headers={"X-Correlation-ID": corr_header})

    res = admin_client.get("/api/v1/admin/telemetry/traces?limit=10")
    assert res.status_code == 200
    data = res.json()

    assert "traces" in data
    corrs = [t["correlation_id"] for t in data["traces"]]
    assert corr_header in corrs


def test_admin_telemetry_live_pulse(admin_client: TestClient):
    """Verifies GET /api/v1/admin/telemetry/live unified system pulse."""
    res = admin_client.get("/api/v1/admin/telemetry/live")
    assert res.status_code == 200
    pulse = res.json()

    assert pulse["status"] == "healthy"
    assert "latency" in pulse
    assert "database_pools" in pulse
    assert "cache" in pulse
    assert "task_queue" in pulse


def test_admin_telemetry_reset(admin_client: TestClient, public_client: TestClient):
    """Verifies POST /api/v1/admin/telemetry/reset flushes reservoirs."""
    public_client.get("/api/v1/health")
    public_client.get("/api/v1/stocks?limit=1")

    reset_res = admin_client.post("/api/v1/admin/telemetry/reset")
    assert reset_res.status_code == 200

    check_res = admin_client.get("/api/v1/admin/telemetry/latency")
    data = check_res.json()
    # Pre-reset routes were completely flushed
    assert "GET /api/v1/health" not in data["routes"]
    assert "GET /api/v1/stocks" not in data["routes"]
    # Only the reset request itself recorded upon completion
    assert "POST /api/v1/admin/telemetry/reset" in data["routes"]
