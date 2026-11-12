"""
pse_quant/api/routes/websocket.py — Bi-Directional WebSocket Market Data Streaming Endpoints
PSE Quant SaaS — Lab 17
"""

from __future__ import annotations
import json
import time
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status

from pse_quant.websocket.models import (
    ClientAction,
    ServerMessageType,
    MarketTick,
    SwarmTelemetry,
)
from pse_quant.websocket.manager import websocket_swarm_manager

logger = logging.getLogger("pse_quant.websocket.route")

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/market-data")
async def websocket_market_data_endpoint(websocket: WebSocket):
    """
    Bi-directional market data streaming endpoint.
    Clients dynamically subscribe to equity tickers, exchange ping/pong heartbeats,
    and receive real-time tick execution updates with drop-oldest backpressure protection.
    """
    await websocket.accept()
    try:
        client = await websocket_swarm_manager.register(websocket)
    except RuntimeError as exc:
        logger.warning(f"Rejecting WebSocket client: {exc}")
        await websocket.close(code=1008, reason="Max connection capacity reached")
        return

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                payload = json.loads(raw_text)
            except Exception:
                await websocket_swarm_manager.send_direct(client, {
                    "type": ServerMessageType.ERROR.value,
                    "message": "Malformed JSON payload",
                })
                continue

            action = payload.get("action")
            if action == ClientAction.PING.value:
                await websocket_swarm_manager.send_direct(client, {
                    "type": ServerMessageType.PONG.value,
                    "client_time": payload.get("client_time"),
                    "server_time": time.time(),
                })
            elif action == ClientAction.SUBSCRIBE.value:
                tickers = payload.get("tickers", [])
                await websocket_swarm_manager.subscribe(client.connection_id, tickers)
            elif action == ClientAction.UNSUBSCRIBE.value:
                tickers = payload.get("tickers", [])
                await websocket_swarm_manager.unsubscribe(client.connection_id, tickers)
            elif action == ClientAction.GET_SUBSCRIPTIONS.value:
                await websocket_swarm_manager.send_direct(client, {
                    "type": ServerMessageType.SUBSCRIPTIONS.value,
                    "subscriptions": sorted(list(client.subscribed_tickers)),
                })
            else:
                await websocket_swarm_manager.send_direct(client, {
                    "type": ServerMessageType.ERROR.value,
                    "message": f"Unsupported action: '{action}'",
                })

    except WebSocketDisconnect:
        logger.debug(f"Client disconnected: {client.connection_id}")
    except Exception as exc:
        logger.warning(f"Unexpected WebSocket error for {client.connection_id}: {exc}")
    finally:
        await websocket_swarm_manager.unregister(client.connection_id)


@router.get("/admin/ws/status", response_model=SwarmTelemetry)
def get_websocket_swarm_status():
    """Retrieves live operational metrics and subscriber distributions for the WebSocket swarm."""
    return websocket_swarm_manager.get_telemetry()


@router.post("/admin/ws/broadcast-tick")
async def broadcast_market_tick(tick: MarketTick):
    """Admin/ETL endpoint to inject or broadcast a market tick to all subscribed clients."""
    recipients = await websocket_swarm_manager.broadcast_tick(tick)
    return {
        "status": "broadcasted",
        "ticker": tick.ticker,
        "price": tick.price,
        "subscribers_delivered": recipients,
    }
