"""
backend/tests/test_sse_streaming.py — Lab 11: Real-Time Server-Sent Events (SSE) Streaming Tests
================================================================================================
Verifies:
  1. W3C EventSource protocol message formatting (id, event, retry, data).
  2. StreamHub channel subscription, broadcast delivery, and unsubscription cleanup.
  3. Cross-thread broadcast from background worker threads into async queues.
  4. Slow consumer backpressure handling (dropping oldest on queue full).
  5. TaskWorker progress broadcasting hook integration.
  6. AlertFanoutService real-time SSE notification broadcast.
  7. FastAPI streaming endpoints (/stream/tasks/{id}, /stream/market, /stream/hub/metrics).
"""

from __future__ import annotations
import json
import asyncio
import threading
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pse_quant.streaming.hub import StreamHub, format_sse_event, stream_hub
from pse_quant.tasks.engine import task_queue, TaskWorker, task, broadcast_task_progress, TaskStatus
from pse_quant.events.fanout import AlertFanoutService
from pse_quant.events.bus import QuantValuationEvent
from pse_quant.db.models import User, Watchlist, Stock, Price, Score, UserNotification, TaskRecord
from pse_quant.db.connection import get_write_session, get_read_session, init_db
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_write_session() as session:
        session.query(TaskRecord).delete()


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


@pytest.fixture
def public_client():
    return TestClient(app)


# ── 1. W3C SSE Event Formatting ────────────────────────────────

def test_format_sse_event_structure():
    """Verifies that format_sse_event produces valid W3C EventSource blocks."""
    event_str = format_sse_event(
        event_type="market_tick",
        data={"ticker": "ALI", "price": 34.50},
        event_id="evt_101",
        retry_ms=5000,
    )

    lines = event_str.strip().split("\n")
    assert "id: evt_101" in lines
    assert "event: market_tick" in lines
    assert "retry: 5000" in lines
    assert 'data: {"ticker": "ALI", "price": 34.5}' in lines
    assert event_str.endswith("\n\n")


# ── 2. StreamHub Subscription & Broadcast ──────────────────────

def test_stream_hub_subscription_and_delivery():
    """Tests subscribing a queue, broadcasting to channel, and reading formatted event."""
    hub = StreamHub()
    channel = "test:feed_alpha"

    # Subscribe
    q = hub.subscribe(channel)
    metrics = hub.get_metrics()
    assert metrics["active_channels"] == 1
    assert metrics["total_active_subscribers"] == 1
    assert metrics["channels"][channel] == 1

    # Broadcast event
    delivered = hub.broadcast(channel, "price_update", {"ticker": "BDO", "price": 158.0})
    assert delivered == 1

    # Read from queue
    msg = q.get_nowait()
    assert "event: price_update" in msg
    assert '"ticker": "BDO"' in msg

    # Unsubscribe
    hub.unsubscribe(channel, q)
    assert hub.get_metrics()["active_channels"] == 0
    assert hub.get_metrics()["total_active_subscribers"] == 0


# ── 3. Cross-Thread Background Worker Broadcast ────────────────

def test_stream_hub_cross_thread_broadcasting():
    """Verifies that background threads can broadcast events to async subscribers safely."""
    hub = StreamHub()
    channel = "tasks:job_99"
    q = hub.subscribe(channel)

    def _worker():
        for i in range(5):
            hub.broadcast(channel, "step_progress", {"step": i + 1, "pct": (i + 1) * 20})
            time.sleep(0.02)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()

    # Verify all 5 events delivered
    received = []
    while not q.empty():
        received.append(q.get_nowait())

    assert len(received) == 5
    assert "step_progress" in received[0]
    assert '"pct": 100' in received[-1]
    hub.unsubscribe(channel, q)


# ── 4. Slow Consumer Backpressure (Queue Drop Oldest) ──────────

def test_stream_hub_slow_consumer_backpressure():
    """Verifies that bounded subscriber queues drop the oldest event when full without deadlocking."""
    hub = StreamHub()
    channel = "overflow:test"
    # Small queue size of 2
    q = hub.subscribe(channel, max_queue_size=2)

    # Broadcast 4 items
    for i in range(4):
        hub.broadcast(channel, "tick", {"seq": i})

    assert q.qsize() == 2
    first_msg = q.get_nowait()
    second_msg = q.get_nowait()

    # The oldest seq 0 and 1 were dropped; seq 2 and 3 remain
    assert '"seq": 2' in first_msg
    assert '"seq": 3' in second_msg
    hub.unsubscribe(channel, q)


# ── 5. Task Progress Broadcasting Hook ─────────────────────────

def test_task_progress_broadcast_hook():
    """Tests broadcast_task_progress publishing milestone events to tasks:{task_id} channel."""
    task_id = "task_test_sse_123"
    channel = f"tasks:{task_id}"
    q = stream_hub.subscribe(channel)

    try:
        broadcast_task_progress(task_id=task_id, progress_pct=45, message="Scraping financial statements")
        assert not q.empty()
        msg = q.get_nowait()
        assert "event: task_progress" in msg
        assert '"progress_pct": 45' in msg
        assert "Scraping financial statements" in msg
    finally:
        stream_hub.unsubscribe(channel, q)


# ── 6. AlertFanoutService Real-Time SSE Broadcast ──────────────

def test_alert_fanout_broadcasts_to_user_sse_channel():
    """
    Verifies that when AlertFanoutService generates an in-app notification,
    it automatically broadcasts to the user's personal SSE channel (alerts:user:{user_id}).
    """
    test_email = "sse_fanout_trader@quant.ph"
    with get_write_session() as session:
        # Create user
        user = session.scalar(select(User).where(User.email == test_email))
        if not user:
            user = User(email=test_email, name="SSE Trader", tier="paid", status="active", role="member")
            user.notification_prefs = {"price_alerts": True, "email_alerts": False}
            session.add(user)
            session.flush()

        user_id = user.id

        # Seed stock & watchlist
        if not session.get(Stock, "AREIT"):
            session.add(Stock(ticker="AREIT", name="AREIT, Inc.", sector="Property", status="active"))
            session.flush()

        wl = session.scalar(Watchlist.__table__.select().where(Watchlist.user_id == user_id, Watchlist.ticker == "AREIT"))
        if not wl:
            session.add(Watchlist(user_id=user_id, ticker="AREIT", target_mos_pct=15.0))

        # Clear previous notifications
        session.query(UserNotification).filter(UserNotification.user_id == user_id).delete()

    # Subscribe to user's SSE channel
    channel = f"alerts:user:{user_id}"
    q = stream_hub.subscribe(channel)

    try:
        event = QuantValuationEvent(
            ticker="AREIT",
            price=32.0,
            intrinsic_value=45.0,
            mos_pct=28.9,  # >= 15.0 target
            score=75.0,
            category="Strong Growth",
        )

        with get_write_session() as session:
            AlertFanoutService.handle_quant_valuation(event, session=session)

        # Assert notification was broadcast to SSE channel
        assert not q.empty(), "Expected SSE notification on user channel"
        sse_chunk = q.get_nowait()
        assert "event: alert_notification" in sse_chunk
        assert "AREIT" in sse_chunk
        assert "28.9%" in sse_chunk
    finally:
        stream_hub.unsubscribe(channel, q)


# ── 7. FastAPI SSE Endpoints ───────────────────────────────────

def test_api_task_stream_completed_task(public_client: TestClient):
    """Verifies GET /api/v1/stream/tasks/{id} sends initial & terminal metadata when task is completed."""
    t_info = task_queue.enqueue("test.echo", payload={"val": 42}, priority=10)
    task_id = t_info["task_id"]
    worker = TaskWorker(worker_id="test_worker_stream")
    while task_queue.get_task_status(task_id)["status"] == "pending":
        worker.run_once()

    with public_client.stream("GET", f"/api/v1/stream/tasks/{task_id}") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        lines = list(response.iter_lines())
        text = "\n".join(lines)
        assert "task_initial" in text or "task_terminal" in text
        assert '"status": "completed"' in text


def test_api_task_stream_live_events(public_client: TestClient):
    """Verifies live event streaming and clean exit on terminal event."""
    t_info = task_queue.enqueue("test.echo", payload={"val": 99}, priority=5)
    task_id = t_info["task_id"]

    def _publish_later():
        time.sleep(0.05)
        stream_hub.broadcast(
            channel=f"tasks:{task_id}",
            event_type="task_progress",
            data={"status": "completed", "result": {"echo": 99}},
        )

    t = threading.Thread(target=_publish_later)
    t.start()

    with public_client.stream("GET", f"/api/v1/stream/tasks/{task_id}") as response:
        assert response.status_code == 200
        lines = list(response.iter_lines())
        text = "\n".join(lines)
        assert "task_progress" in text or "task_initial" in text
        assert '"status": "completed"' in text

    t.join()


def test_api_stream_hub_metrics(admin_client: TestClient, public_client: TestClient):
    """Verifies GET /api/v1/stream/hub/metrics and POST /api/v1/stream/publish."""
    # 1. Unauthorized
    unauth = public_client.get("/api/v1/stream/hub/metrics")
    assert unauth.status_code == 401

    # 2. Authorized metrics
    res = admin_client.get("/api/v1/stream/hub/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "active_channels" in data
    assert "total_events_dispatched" in data

    # 3. Publish endpoint
    pub_res = admin_client.post(
        "/api/v1/stream/publish?channel=market:ticks&event_type=tick",
        json={"ticker": "TEL", "price": 1250.0},
    )
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "success"
