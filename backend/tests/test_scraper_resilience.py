"""
backend/tests/test_scraper_resilience.py — Scraper Resilience, Circuit Breaker & DLQ Tests
========================================================================================
Verifies:
  1. Circuit Breaker 3-state machine (CLOSED -> OPEN -> HALF-OPEN -> CLOSED).
  2. Full Jitter exponential backoff calculations and upper bounds.
  3. Scraper client fast-fail execution when circuit is OPEN.
  4. Dead-Letter Queue persistence and poison-pill isolation during batch ETL.
  5. Admin telemetry endpoints for circuit breaker and dead-letter review.
"""

from __future__ import annotations
import time
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from pse_quant.api.main import app
from pse_quant.db.connection import get_db_session
from pse_quant.db.models import ScraperDeadLetter, Stock
from pse_quant.scraper.resilience import (
    CircuitBreaker,
    CircuitState,
    calculate_jittered_backoff,
    DeadLetterService,
)
from pse_quant.scraper.client import PseEdgeClient
from pse_quant.scraper.etl import sync_stock_quotes, sync_financials
from pse_quant.services.auth_service import ADMIN_MASTER_KEY


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


# ── 1. Circuit Breaker State Machine Unit Tests ──────────────────

def test_circuit_breaker_transitions():
    """Tests the complete lifecycle: CLOSED -> OPEN -> HALF-OPEN -> CLOSED."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=3, cooldown_seconds=10.0)

    # 1. Starts CLOSED
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 2. Record 2 failures (threshold is 3) -> Still CLOSED
    cb.record_failure("503 Service Unavailable")
    cb.record_failure("504 Gateway Timeout")
    assert cb.state == CircuitState.CLOSED

    # 3. 3rd failure -> Trips OPEN
    cb.record_failure("502 Bad Gateway")
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute(now=time.time()) is False

    # 4. Before cooldown expires -> Remains OPEN
    now = time.time()
    assert cb.can_execute(now=now + 5.0) is False

    # 5. After cooldown expires (t0 + 11s) -> Transitions to HALF-OPEN
    assert cb.can_execute(now=now + 11.0) is True
    assert cb.state == CircuitState.HALF_OPEN

    # 6. Successful canary probe -> Resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


def test_circuit_breaker_half_open_failure_re_trips():
    """In HALF-OPEN state, a single probe failure immediately re-trips back to OPEN."""
    cb = CircuitBreaker(name="test_probe_fail", failure_threshold=2, cooldown_seconds=5.0)
    now = time.time()

    # Trip to OPEN
    cb.record_failure("Timeout 1")
    cb.record_failure("Timeout 2")
    assert cb.state == CircuitState.OPEN

    # Cooldown expires -> HALF-OPEN
    assert cb.can_execute(now=now + 6.0) is True
    assert cb.state == CircuitState.HALF_OPEN

    # Failed probe probe -> Re-trips to OPEN
    cb.record_failure("Probe failed")
    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_manual_reset():
    """Verifies that an administrator can force-reset an OPEN breaker."""
    cb = CircuitBreaker(name="test_reset", failure_threshold=1, cooldown_seconds=60.0)
    cb.record_failure("Fatal outage")
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


# ── 2. Full Jitter Exponential Backoff Tests ────────────────────

def test_calculate_jittered_backoff_bounds():
    """Verifies backoff delays adhere to [0, min(max_delay, base * 2^attempt)]."""
    base = 1.0
    max_d = 16.0

    # With minimum random factor (0.0) -> delay is 0.0
    zero_delay = calculate_jittered_backoff(attempt=3, base_delay=base, max_delay=max_d, rng=lambda: 0.0)
    assert zero_delay == 0.0

    # With maximum random factor (1.0) on attempt 2: base * 2^2 = 4.0
    max_attempt2 = calculate_jittered_backoff(attempt=2, base_delay=base, max_delay=max_d, rng=lambda: 1.0)
    assert max_attempt2 == 4.0

    # Large attempt capped at max_delay
    capped_delay = calculate_jittered_backoff(attempt=10, base_delay=base, max_delay=max_d, rng=lambda: 1.0)
    assert capped_delay == max_d


def test_calculate_jittered_backoff_distribution():
    """Verifies that delays across 50 iterations vary and are not identical."""
    delays = [calculate_jittered_backoff(attempt=2, base_delay=1.0, max_delay=10.0) for _ in range(50)]
    assert len(set(delays)) > 30  # High entropy
    assert all(0.0 <= d <= 4.0 for d in delays)


# ── 3. Resilient Client Fast-Fail Integration ───────────────────

def test_client_fast_fails_when_circuit_open():
    """Verifies that when circuit is OPEN, PseEdgeClient.get() returns None immediately without waiting."""
    cb = CircuitBreaker(name="fast_fail_test", failure_threshold=1, cooldown_seconds=30.0)
    cb.record_failure("Simulated outage")
    assert cb.state == CircuitState.OPEN

    client = PseEdgeClient(delay_secs=0.01, circuit=cb)

    start = time.time()
    resp = client.get("/companyPage/stockData.do")
    elapsed = time.time() - start

    assert resp is None
    assert elapsed < 0.05  # Instant fail-fast (<50ms)


# ── 4. Dead-Letter Queue (DLQ) & Poison-Pill Isolation ───────────

def test_dead_letter_service_record_and_resolve():
    """Verifies DLQ record creation, listing, and resolution."""
    test_ticker = f"BAD_{int(time.time() * 1000)}"

    with get_db_session() as session:
        # 1. Record poison pill
        dl = DeadLetterService.record_dead_letter(
            session=session,
            ticker=test_ticker,
            stage="financials",
            source_url="https://edge.pse.com.ph/financials/bad.do",
            error_reason="KeyError: 'operating_cash_flow' missing from filing",
            payload_preview='{"ticker": "BAD", "year": "N/A"}',
            attempts=3,
        )
        assert dl.id is not None
        assert dl.status == "pending"
        dl_id = dl.id

        # 2. List pending
        pending = DeadLetterService.list_dead_letters(session=session, status="pending")
        matching = [item for item in pending if item.ticker == test_ticker]
        assert len(matching) == 1
        assert matching[0].error_reason.startswith("KeyError")

        # 3. Resolve poison pill
        resolved = DeadLetterService.resolve_dead_letter(session=session, dead_letter_id=dl_id, resolution="reprocessed")
        assert resolved.status == "reprocessed"
        assert resolved.resolved_at is not None


def test_batch_etl_continues_past_poison_pill():
    """
    Simulates a corrupt stock disclosure. Verifies that the scraper catches the error,
    logs it to DeadLetterService, and continues processing the rest of the batch without crashing.
    """
    poison_ticker = "POISON_TEST"

    with get_db_session() as session:
        # Seed test stock
        stock = session.get(Stock, poison_ticker)
        if not stock:
            stock = Stock(ticker=poison_ticker, name="Poison Corp", sector="Industrial", cmpy_id="999999", status="active")
            session.add(stock)
            session.commit()

        # Mock fetch_stock_quote to raise an unhandled exception for this stock
        with patch("pse_quant.scraper.etl.fetch_stock_quote", side_effect=ValueError("Corrupt HTML structure in disclosure")):
            mock_client = PseEdgeClient(delay_secs=0.0)
            synced = sync_stock_quotes(client=mock_client, session=session, tickers=[poison_ticker])
            assert synced == 0

        # Assert poison pill was caught and recorded into DeadLetter table
        letters = DeadLetterService.list_dead_letters(session=session, status="pending")
        found = [l for l in letters if l.ticker == poison_ticker]
        assert len(found) >= 1
        assert "Corrupt HTML" in found[0].error_reason


# ── 5. Admin Telemetry & Control Endpoints ───────────────────────

def test_admin_circuit_breaker_telemetry_and_reset(admin_client):
    """Verifies GET /admin/circuit-breaker/status and POST /admin/circuit-breaker/reset."""
    # 1. Get status
    res = admin_client.get("/api/v1/admin/circuit-breaker/status")
    assert res.status_code == 200
    data = res.json()
    assert "state" in data
    assert "consecutive_failures" in data
    assert "failure_threshold" in data

    # 2. Reset breaker
    reset_res = admin_client.post("/api/v1/admin/circuit-breaker/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["circuit"]["state"] == "CLOSED"


def test_admin_dead_letters_endpoint(admin_client):
    """Verifies GET /admin/dead-letters and POST /admin/dead-letters/{id}/resolve."""
    test_ticker = f"DLQ_{int(time.time() * 1000)}"

    with get_db_session() as session:
        dl = DeadLetterService.record_dead_letter(
            session=session,
            ticker=test_ticker,
            stage="quote",
            source_url="https://edge.pse.com.ph/quote/test.do",
            error_reason="HTTP 500 Internal Error from PSE Edge",
        )
        dl_id = dl.id

    # List dead letters via API
    res = admin_client.get("/api/v1/admin/dead-letters?status=pending")
    assert res.status_code == 200
    items = res.json()
    assert any(item["id"] == dl_id for item in items)

    # Resolve dead letter via API
    resolve_res = admin_client.post(f"/api/v1/admin/dead-letters/{dl_id}/resolve?resolution=ignored")
    assert resolve_res.status_code == 200
    assert resolve_res.json()["resolution"] == "ignored"
