"""
backend/tests/test_event_fanout.py — Event-Driven Architecture & Alert Fanout Test Suite
======================================================================================
Verifies:
  1. Thread-safe EventBus publish/subscribe broker with topic wildcards.
  2. AlertFanoutService predicate filtering (ticker matching, target MoS hurdles, user notification prefs).
  3. Anti-fatigue deduplication cooldowns preventing alert spam on fluctuating prices.
  4. In-App Notification persistence (UserNotification) with badge unread counts.
  5. Notification API endpoints (/notifications, /{id}/read, /mark-all-read, /simulate-event).
"""

from __future__ import annotations
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, and_

from pse_quant.api.main import app
from pse_quant.db.connection import get_db_session
from pse_quant.db.models import User, Watchlist, UserNotification, Stock
from pse_quant.events.bus import EventBus, DomainEvent, QuantValuationEvent, global_event_bus
from pse_quant.events.fanout import AlertFanoutService
from pse_quant.services.auth_service import create_access_token


@pytest.fixture
def test_client():
    return TestClient(app)


# ── 1. EventBus Core Mechanics Unit Tests ────────────────────────

def test_event_bus_subscribe_and_publish():
    """Verifies that events are delivered to exact and wildcard subscribers."""
    bus = EventBus()
    received_events = []

    def handle_exact(evt):
        received_events.append(("exact", evt))

    def handle_wildcard(evt):
        received_events.append(("wildcard", evt))

    bus.subscribe("quant.valuation.ALI", handle_exact)
    bus.subscribe("quant.valuation.*", handle_wildcard)

    event = QuantValuationEvent(
        ticker="ALI",
        price=31.0,
        intrinsic_value=40.0,
        mos_pct=22.5,
    )

    invoked = bus.publish(event)
    assert invoked == 2
    assert len(received_events) == 2
    assert received_events[0][0] == "exact"
    assert received_events[1][0] == "wildcard"


def test_event_bus_handler_isolation():
    """Verifies that an error in one handler does not halt subsequent subscribers."""
    bus = EventBus()
    successful = []

    def faulty_handler(evt):
        raise RuntimeError("Handler exploded!")

    def healthy_handler(evt):
        successful.append(evt.event_id)

    bus.subscribe("test.*", faulty_handler)
    bus.subscribe("test.*", healthy_handler)

    test_evt = DomainEvent(topic="test.topic")
    invoked = bus.publish(test_evt)

    assert invoked == 1  # Only the healthy handler succeeded
    assert len(successful) == 1


# ── 2. Fanout Matching & Predicate Filtering ────────────────────

def test_alert_fanout_predicate_filtering():
    """
    Verifies institutional fanout rules:
      - Investor A (Target MoS 20%): TRIGGERED (30% >= 20%)
      - Investor B (Target MoS 35%): NOT TRIGGERED (30% < 35%)
      - Investor C (Watching different ticker): NOT TRIGGERED
      - Investor D (price_alerts=False): NOT TRIGGERED
    """
    ts = int(time.time() * 1000)
    ticker = f"TEST_{ts}"

    with get_db_session() as session:
        # Seed test stocks for foreign key constraints if not present
        if not session.get(Stock, ticker):
            session.add(Stock(ticker=ticker, name=f"Test {ticker}", sector="Property", status="active"))
        if not session.get(Stock, "OTHER_TICKER"):
            session.add(Stock(ticker="OTHER_TICKER", name="Other Stock", sector="Financials", status="active"))
        session.flush()

        # User 1: Qualified (target 20%, alerts enabled)
        u1 = User(email=f"u1_{ts}@test.ph", tier="free", notification_prefs={"price_alerts": True})
        session.add(u1)
        session.flush()
        w1 = Watchlist(user_id=u1.id, ticker=ticker, target_mos_pct=20.0)
        session.add(w1)

        # User 2: Target too high (target 35%)
        u2 = User(email=f"u2_{ts}@test.ph", tier="free", notification_prefs={"price_alerts": True})
        session.add(u2)
        session.flush()
        w2 = Watchlist(user_id=u2.id, ticker=ticker, target_mos_pct=35.0)
        session.add(w2)

        # User 3: Different ticker
        u3 = User(email=f"u3_{ts}@test.ph", tier="free", notification_prefs={"price_alerts": True})
        session.add(u3)
        session.flush()
        w3 = Watchlist(user_id=u3.id, ticker="OTHER_TICKER", target_mos_pct=20.0)
        session.add(w3)

        # User 4: Alerts disabled
        u4 = User(email=f"u4_{ts}@test.ph", tier="free", notification_prefs={"price_alerts": False})
        session.add(u4)
        session.flush()
        w4 = Watchlist(user_id=u4.id, ticker=ticker, target_mos_pct=20.0)
        session.add(w4)

        session.commit()

        # Fire Quant Valuation Event: MoS = 30.0%
        event = QuantValuationEvent(
            ticker=ticker,
            price=30.0,
            intrinsic_value=42.85,
            mos_pct=30.0,
            score=85.0,
            category="Steady Compounder",
        )

        notifications = AlertFanoutService.handle_quant_valuation(event, session=session)

        # Assert only User 1 received the notification
        assert len(notifications) == 1
        n = notifications[0]
        assert n.user_id == u1.id
        assert n.ticker == ticker
        assert n.alert_type == "MOS_BREACH"
        assert n.is_read is False
        assert "30.0%" in n.title


# ── 3. Anti-Fatigue Deduplication Cooldown ──────────────────────

def test_alert_deduplication_cooldown():
    """
    Verifies that subsequent events within the cooldown window do NOT
    generate duplicate spam alerts for the investor.
    """
    ts = int(time.time() * 1000)
    ticker = f"COOL_{ts}"

    with get_db_session() as session:
        # Seed test stock for foreign key constraints if not present
        if not session.get(Stock, ticker):
            session.add(Stock(ticker=ticker, name=f"Cool {ticker}", sector="Property", status="active"))
        session.flush()

        user = User(email=f"cooldown_{ts}@test.ph", tier="free", notification_prefs={"price_alerts": True})
        session.add(user)
        session.flush()
        w = Watchlist(user_id=user.id, ticker=ticker, target_mos_pct=20.0)
        session.add(w)
        session.commit()

        event = QuantValuationEvent(
            ticker=ticker,
            price=30.0,
            intrinsic_value=40.0,
            mos_pct=25.0,
        )

        # First Event -> Notification created
        first_alerts = AlertFanoutService.handle_quant_valuation(event, session=session, cooldown_hours=4.0)
        assert len(first_alerts) == 1

        # Second Event 1 minute later -> SUPPRESSED by Cooldown
        second_alerts = AlertFanoutService.handle_quant_valuation(event, session=session, cooldown_hours=4.0)
        assert len(second_alerts) == 0

        # Assert total notifications in DB remains exactly 1
        all_notifs = session.scalars(
            select(UserNotification).where(
                and_(UserNotification.user_id == user.id, UserNotification.ticker == ticker)
            )
        ).all()
        assert len(all_notifs) == 1


# ── 4. Notifications API & Read State Endpoints ─────────────────

def test_notifications_api_lifecycle(test_client):
    """
    Tests the complete in-app notification API:
      - Listing notifications with unread counts
      - Marking single notification as read
      - Marking all notifications as read
    """
    ts = int(time.time() * 1000)

    with get_db_session() as session:
        user = User(email=f"api_notif_{ts}@test.ph", tier="paid")
        session.add(user)
        session.flush()

        n1 = UserNotification(
            user_id=user.id,
            ticker="AREIT",
            alert_type="MOS_BREACH",
            title="AREIT 22% MoS",
            message="AREIT is undervalued",
            is_read=False,
        )
        n2 = UserNotification(
            user_id=user.id,
            ticker="DMC",
            alert_type="MOS_BREACH",
            title="DMC 28% MoS",
            message="DMC is undervalued",
            is_read=False,
        )
        session.add_all([n1, n2])
        session.commit()

        user_id = user.id
        n1_id = n1.id

    token = create_access_token({"sub": str(user_id), "role": "member", "tier": "paid"})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET /api/v1/notifications -> unread_count=2
    res = test_client.get("/api/v1/notifications", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["unread_count"] == 2
    assert len(data["notifications"]) == 2

    # 2. PATCH /api/v1/notifications/{id}/read -> marks n1 read
    patch_res = test_client.patch(f"/api/v1/notifications/{n1_id}/read", headers=headers)
    assert patch_res.status_code == 200
    assert patch_res.json()["is_read"] is True

    # 3. Verify unread count is now 1
    res2 = test_client.get("/api/v1/notifications", headers=headers)
    assert res2.json()["unread_count"] == 1

    # 4. POST /api/v1/notifications/mark-all-read -> marks remaining read
    mark_all_res = test_client.post("/api/v1/notifications/mark-all-read", headers=headers)
    assert mark_all_res.status_code == 200
    assert mark_all_res.json()["marked_read_count"] == 1

    # 5. Verify unread count is now 0
    res3 = test_client.get("/api/v1/notifications", headers=headers)
    assert res3.json()["unread_count"] == 0


def test_simulate_domain_event_endpoint(test_client):
    """Verifies POST /api/v1/notifications/simulate-event workbench tool."""
    ts = int(time.time() * 1000)

    with get_db_session() as session:
        user = User(email=f"sim_{ts}@test.ph", tier="free")
        session.add(user)
        session.commit()
        user_id = user.id

    token = create_access_token({"sub": str(user_id), "role": "member", "tier": "free"})
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "ticker": "AREIT",
        "price": 32.50,
        "intrinsic_value": 46.84,
        "mos_pct": 30.6,
        "score": 82.0,
        "category": "Passive Income Champion",
    }

    res = test_client.post("/api/v1/notifications/simulate-event", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "published"
    assert "AREIT" in data["topic"]
    assert data["handlers_invoked"] >= 1
