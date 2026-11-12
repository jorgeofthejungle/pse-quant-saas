"""
backend/tests/test_websocket_swarm.py — Test Suite for Bi-Directional WebSocket Swarm
PSE Quant SaaS — Lab 17
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pse_quant.api.main import app
from pse_quant.websocket.manager import websocket_swarm_manager
from pse_quant.websocket.models import MarketTick


@pytest.fixture(autouse=True)
def clean_swarm():
    """Resets WebSocket swarm state before and after each test."""
    asyncio.run(websocket_swarm_manager.reset())
    yield
    asyncio.run(websocket_swarm_manager.reset())


def test_websocket_connection_handshake():
    """Client connecting to /ws/market-data receives immediate connected welcome frame."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/market-data") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        assert "connection_id" in msg
        assert msg["connection_id"].startswith("ws_client_")


def test_websocket_ping_pong_heartbeat():
    """Validates low-overhead ping/pong heartbeat synchronization."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/market-data") as ws:
        # Handshake
        ws.receive_json()

        # Send Ping
        ws.send_json({"action": "ping", "client_time": 1731411234.5})
        response = ws.receive_json()

        assert response["type"] == "pong"
        assert response["client_time"] == 1731411234.5
        assert "server_time" in response


def test_websocket_subscription_and_query():
    """Client can subscribe to tickers and query active subscriptions."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/market-data") as ws:
        ws.receive_json()  # Handshake

        # Subscribe to DMC and AREIT
        ws.send_json({"action": "subscribe", "tickers": ["dmc", "areit"]})
        ack = ws.receive_json()
        assert ack["type"] == "ack"
        assert ack["action"] == "subscribe"
        assert set(ack["added"]) == {"DMC", "AREIT"}
        assert set(ack["subscriptions"]) == {"AREIT", "DMC"}

        # Query subscriptions
        ws.send_json({"action": "get_subscriptions"})
        subs_resp = ws.receive_json()
        assert subs_resp["type"] == "subscriptions"
        assert set(subs_resp["subscriptions"]) == {"AREIT", "DMC"}


def test_selective_market_tick_delivery():
    """
    Subscribers only receive ticks for stocks they explicitly follow.
    Client A (DMC) gets DMC tick.
    Client B (ALI) gets ALI tick and is isolated from DMC ticks.
    """
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/market-data") as ws_a, \
         client.websocket_connect("/api/v1/ws/market-data") as ws_b:
        ws_a.receive_json()
        ws_b.receive_json()

        # Client A subscribes to DMC
        ws_a.send_json({"action": "subscribe", "tickers": ["DMC"]})
        ws_a.receive_json()

        # Client B subscribes to ALI
        ws_b.send_json({"action": "subscribe", "tickers": ["ALI"]})
        ws_b.receive_json()

        # Broadcast DMC tick via Admin API
        res_dmc = client.post("/api/v1/admin/ws/broadcast-tick", json={
            "ticker": "DMC",
            "price": 13.50,
            "change": 0.25,
            "change_pct": 1.88,
            "volume": 250000,
        })
        assert res_dmc.status_code == 200
        assert res_dmc.json()["subscribers_delivered"] == 1

        # Client A must receive DMC tick
        tick_a = ws_a.receive_json()
        assert tick_a["type"] == "tick"
        assert tick_a["data"]["ticker"] == "DMC"
        assert tick_a["data"]["price"] == 13.50

        # Broadcast ALI tick
        res_ali = client.post("/api/v1/admin/ws/broadcast-tick", json={
            "ticker": "ALI",
            "price": 32.20,
            "change": -0.40,
            "change_pct": -1.22,
            "volume": 890000,
        })
        assert res_ali.status_code == 200
        assert res_ali.json()["subscribers_delivered"] == 1

        # Client B must receive ALI tick
        tick_b = ws_b.receive_json()
        assert tick_b["type"] == "tick"
        assert tick_b["data"]["ticker"] == "ALI"
        assert tick_b["data"]["price"] == 32.20


def test_websocket_unsubscribe_lifecycle():
    """Unsubscribing halts subsequent tick delivery for that symbol."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/market-data") as ws:
        ws.receive_json()

        # Subscribe to DMC and SMPH
        ws.send_json({"action": "subscribe", "tickers": ["DMC", "SMPH"]})
        ws.receive_json()

        # Unsubscribe from DMC
        ws.send_json({"action": "unsubscribe", "tickers": ["DMC"]})
        ack_unsub = ws.receive_json()
        assert ack_unsub["type"] == "ack"
        assert ack_unsub["action"] == "unsubscribe"
        assert "DMC" in ack_unsub["removed"]
        assert ack_unsub["subscriptions"] == ["SMPH"]

        # Broadcast DMC: Delivered count should be 0
        res_dmc = client.post("/api/v1/admin/ws/broadcast-tick", json={
            "ticker": "DMC",
            "price": 13.80,
            "change": 0.30,
            "change_pct": 2.22,
            "volume": 120000,
        })
        assert res_dmc.json()["subscribers_delivered"] == 0

        # Broadcast SMPH: Delivered count should be 1
        res_smph = client.post("/api/v1/admin/ws/broadcast-tick", json={
            "ticker": "SMPH",
            "price": 28.50,
            "change": 0.10,
            "change_pct": 0.35,
            "volume": 450000,
        })
        assert res_smph.json()["subscribers_delivered"] == 1

        tick = ws.receive_json()
        assert tick["data"]["ticker"] == "SMPH"
        assert tick["data"]["price"] == 28.50


def test_concurrent_multi_client_fanout():
    """Multiple clients listening to the same stock all receive identical ticks."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/market-data") as ws1, \
         client.websocket_connect("/api/v1/ws/market-data") as ws2:
        ws1.receive_json()
        ws2.receive_json()

        # Both subscribe to BDO
        ws1.send_json({"action": "subscribe", "tickers": ["BDO"]})
        ws2.send_json({"action": "subscribe", "tickers": ["BDO"]})
        ws1.receive_json()
        ws2.receive_json()

        # Broadcast tick
        client.post("/api/v1/admin/ws/broadcast-tick", json={
            "ticker": "BDO",
            "price": 158.00,
            "change": 1.50,
            "change_pct": 0.96,
            "volume": 600000,
        })

        t1 = ws1.receive_json()
        t2 = ws2.receive_json()

        assert t1["data"]["ticker"] == "BDO"
        assert t2["data"]["ticker"] == "BDO"
        assert t1["data"]["price"] == 158.00
        assert t2["data"]["price"] == 158.00


def test_backpressure_drop_oldest_mechanism():
    """
    When client buffer is saturated, oldest messages are dropped to keep
    low latency and prevent out-of-memory crashes.
    """
    client = TestClient(app)
    # Temporarily set max_queue_size to 3
    orig_queue_size = websocket_swarm_manager.max_queue_size
    websocket_swarm_manager.max_queue_size = 3
    try:
        with client.websocket_connect("/api/v1/ws/market-data") as ws:
            ws.receive_json()  # Handshake
            ws.send_json({"action": "subscribe", "tickers": ["TEST_TICKER"]})
            ws.receive_json()  # Ack

            # Broadcast 10 ticks rapidly
            for i in range(10):
                client.post("/api/v1/admin/ws/broadcast-tick", json={
                    "ticker": "TEST_TICKER",
                    "price": float(100 + i),
                    "change": 1.0,
                    "change_pct": 1.0,
                    "volume": 1000,
                })

            telemetry = client.get("/api/v1/admin/ws/status").json()
            assert telemetry["total_ticks_broadcast"] == 10
            # Some messages dropped due to buffer size 3
            assert telemetry["total_dropped_backpressure"] > 0
    finally:
        websocket_swarm_manager.max_queue_size = orig_queue_size


def test_admin_telemetry_status():
    """Admin telemetry returns active connections, tickers, and counters."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/market-data") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "tickers": ["MER", "ICT"]})
        ws.receive_json()

        res = client.get("/api/v1/admin/ws/status")
        assert res.status_code == 200
        data = res.json()
        assert data["active_connections"] == 1
        assert "MER" in data["subscriptions_by_ticker"]
        assert "ICT" in data["subscriptions_by_ticker"]
        assert data["subscriptions_by_ticker"]["MER"] == 1
