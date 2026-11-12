"""
pse_quant/websocket/models.py — Market Data WebSocket Contracts & Telemetry
PSE Quant SaaS — Lab 17: Bi-Directional WebSocket Market Data Streaming Swarm
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class ClientAction(str, Enum):
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"
    GET_SUBSCRIPTIONS = "get_subscriptions"


class ServerMessageType(str, Enum):
    CONNECTED = "connected"
    ACK = "ack"
    PONG = "pong"
    TICK = "tick"
    DEPTH = "depth"
    ERROR = "error"
    SUBSCRIPTIONS = "subscriptions"


class ClientFrame(BaseModel):
    """Inbound message from a connected WebSocket client."""
    action: ClientAction = Field(..., description="Action to perform: subscribe, unsubscribe, ping, get_subscriptions")
    tickers: list[str] = Field(default_factory=list, description="List of PSE ticker symbols (e.g. ['DMC', 'AREIT'])")
    client_time: Optional[float] = Field(default=None, description="Epoch timestamp sent during client ping")


class MarketTick(BaseModel):
    """Real-time market price update for an individual equity."""
    ticker: str = Field(..., description="PSE stock ticker symbol")
    price: float = Field(..., description="Current traded execution price in PHP")
    change: float = Field(default=0.0, description="Price change in PHP relative to previous close")
    change_pct: float = Field(default=0.0, description="Percentage price change")
    volume: int = Field(default=0, description="Cumulative traded shares volume")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SwarmTelemetry(BaseModel):
    """Real-time operational metrics for the WebSocket swarm connection manager."""
    active_connections: int
    max_connections: int
    total_connected: int
    total_messages_sent: int
    total_ticks_broadcast: int
    total_dropped_backpressure: int
    subscriptions_by_ticker: dict[str, int]
