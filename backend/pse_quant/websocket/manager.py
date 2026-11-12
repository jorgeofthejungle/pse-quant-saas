"""
pse_quant/websocket/manager.py — High-Throughput WebSocket Swarm Connection Manager
PSE Quant SaaS — Lab 17: Bi-Directional WebSocket Market Data Streaming Swarm

Features:
  - Multiplexed channel & ticker-level subscription routing.
  - Drop-oldest backpressure protection preventing memory bloat on slow clients.
  - Max connection limits with graceful rejection (RFC 6455 status 1008/1013).
  - Background async sender worker tasks for non-blocking broadcasts.
  - Thread-safe operational telemetry.
"""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from typing import Optional, Any
from starlette.websockets import WebSocket, WebSocketDisconnect

from pse_quant.websocket.models import MarketTick, SwarmTelemetry, ServerMessageType

logger = logging.getLogger("pse_quant.websocket")


class WebSocketClientConnection:
    """Represents an active bi-directional WebSocket client session."""

    def __init__(self, connection_id: str, websocket: WebSocket, max_queue_size: int = 100) -> None:
        self.connection_id = connection_id
        self.websocket = websocket
        self.subscribed_tickers: set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.sender_task: Optional[asyncio.Task] = None
        self.messages_sent = 0
        self.messages_dropped = 0


class WebSocketSwarmManager:
    """
    Central connection orchestrator managing WebSocket client lifecycles,
    ticker multiplexing, and backpressure-resilient broadcasts.
    """

    def __init__(self, max_connections: int = 1000, max_queue_size: int = 100) -> None:
        self.max_connections = max_connections
        self.max_queue_size = max_queue_size
        self._connections: dict[str, WebSocketClientConnection] = {}
        self._ticker_subscribers: dict[str, set[str]] = {}  # ticker -> set(connection_ids)
        self._lock = asyncio.Lock()

        # Telemetry counters
        self._total_connected = 0
        self._total_messages_sent = 0
        self._total_ticks_broadcast = 0
        self._total_dropped_backpressure = 0

    async def register(self, websocket: WebSocket) -> WebSocketClientConnection:
        """
        Accepts and registers a new WebSocket client if within capacity.
        Raises RuntimeError if maximum connection limits are breached.
        """
        async with self._lock:
            if len(self._connections) >= self.max_connections:
                raise RuntimeError(f"Connection limit reached ({self.max_connections})")

            connection_id = f"ws_client_{uuid.uuid4().hex[:10]}"
            client = WebSocketClientConnection(
                connection_id=connection_id,
                websocket=websocket,
                max_queue_size=self.max_queue_size,
            )
            self._connections[connection_id] = client
            self._total_connected += 1

            # Launch client's isolated asynchronous sender worker
            client.sender_task = asyncio.create_task(self._client_sender_loop(client))

        logger.info(f"WebSocket client connected: {connection_id} (active: {len(self._connections)})")

        # Send welcome handshake
        await self.send_direct(client, {
            "type": ServerMessageType.CONNECTED.value,
            "connection_id": connection_id,
            "message": "Connected to StockPilot PH WebSocket Market Data Swarm",
            "server_time": asyncio.get_event_loop().time(),
        })

        return client

    async def unregister(self, connection_id: str) -> None:
        """Gracefully disconnects a client, cancelling sender loop and scrubbing subscriptions."""
        async with self._lock:
            client = self._connections.pop(connection_id, None)
            if not client:
                return

            # Cancel sender task
            if client.sender_task and not client.sender_task.done():
                client.sender_task.cancel()

            # Clean up all ticker subscription mappings
            for ticker in client.subscribed_tickers:
                if ticker in self._ticker_subscribers:
                    self._ticker_subscribers[ticker].discard(connection_id)
                    if not self._ticker_subscribers[ticker]:
                        del self._ticker_subscribers[ticker]

        logger.info(f"WebSocket client disconnected: {connection_id} (remaining: {len(self._connections)})")

    async def subscribe(self, connection_id: str, tickers: list[str]) -> list[str]:
        """Subscribes a client to a list of equity tickers."""
        normalized = [t.upper().strip() for t in tickers if t.strip()]
        async with self._lock:
            client = self._connections.get(connection_id)
            if not client:
                return []

            for ticker in normalized:
                client.subscribed_tickers.add(ticker)
                if ticker not in self._ticker_subscribers:
                    self._ticker_subscribers[ticker] = set()
                self._ticker_subscribers[ticker].add(connection_id)

            active_subs = sorted(list(client.subscribed_tickers))

        await self.send_direct(client, {
            "type": ServerMessageType.ACK.value,
            "action": "subscribe",
            "added": normalized,
            "subscriptions": active_subs,
        })
        return active_subs

    async def unsubscribe(self, connection_id: str, tickers: list[str]) -> list[str]:
        """Unsubscribes a client from a list of equity tickers."""
        normalized = [t.upper().strip() for t in tickers if t.strip()]
        async with self._lock:
            client = self._connections.get(connection_id)
            if not client:
                return []

            for ticker in normalized:
                client.subscribed_tickers.discard(ticker)
                if ticker in self._ticker_subscribers:
                    self._ticker_subscribers[ticker].discard(connection_id)
                    if not self._ticker_subscribers[ticker]:
                        del self._ticker_subscribers[ticker]

            active_subs = sorted(list(client.subscribed_tickers))

        await self.send_direct(client, {
            "type": ServerMessageType.ACK.value,
            "action": "unsubscribe",
            "removed": normalized,
            "subscriptions": active_subs,
        })
        return active_subs

    async def broadcast_tick(self, tick: MarketTick) -> int:
        """
        Broadcasts a market tick exclusively to clients subscribed to the tick's symbol.
        Applies drop-oldest backpressure if a slow consumer's buffer is saturated.
        """
        symbol = tick.ticker.upper().strip()
        message = {
            "type": ServerMessageType.TICK.value,
            "data": tick.model_dump(mode="json"),
        }

        recipients: list[WebSocketClientConnection] = []
        async with self._lock:
            self._total_ticks_broadcast += 1
            subscriber_ids = self._ticker_subscribers.get(symbol, set())
            for cid in subscriber_ids:
                client = self._connections.get(cid)
                if client:
                    recipients.append(client)

        delivered = 0
        for client in recipients:
            try:
                client.queue.put_nowait(message)
                delivered += 1
            except asyncio.QueueFull:
                # Backpressure protection: Drop the oldest message to keep client in sync with latest price
                try:
                    client.queue.get_nowait()
                    client.queue.put_nowait(message)
                    client.messages_dropped += 1
                    self._total_dropped_backpressure += 1
                    delivered += 1
                except Exception:
                    pass

        return delivered

    async def send_direct(self, client: WebSocketClientConnection, message: dict[str, Any]) -> bool:
        """Enqueues a message directly to a single client's outbound queue."""
        try:
            client.queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            try:
                client.queue.get_nowait()
                client.queue.put_nowait(message)
                self._total_dropped_backpressure += 1
                return True
            except Exception:
                return False

    async def _client_sender_loop(self, client: WebSocketClientConnection) -> None:
        """Dedicated background task draining the client's outbound queue to the WebSocket."""
        try:
            while True:
                msg = await client.queue.get()
                payload = json.dumps(msg)
                await client.websocket.send_text(payload)
                client.messages_sent += 1
                self._total_messages_sent += 1
                client.queue.task_done()
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.debug(f"Sender loop closed for {client.connection_id}: {exc}")

    def get_telemetry(self) -> SwarmTelemetry:
        """Retrieves real-time operational telemetry for the WebSocket swarm."""
        subs_summary: dict[str, int] = {}
        for ticker, clients in self._ticker_subscribers.items():
            subs_summary[ticker] = len(clients)

        return SwarmTelemetry(
            active_connections=len(self._connections),
            max_connections=self.max_connections,
            total_connected=self._total_connected,
            total_messages_sent=self._total_messages_sent,
            total_ticks_broadcast=self._total_ticks_broadcast,
            total_dropped_backpressure=self._total_dropped_backpressure,
            subscriptions_by_ticker=subs_summary,
        )

    async def reset(self) -> None:
        """Shuts down all active connections and resets telemetry counters (used for test teardown)."""
        async with self._lock:
            for client in list(self._connections.values()):
                if client.sender_task and not client.sender_task.done():
                    client.sender_task.cancel()
            self._connections.clear()
            self._ticker_subscribers.clear()
            self._total_connected = 0
            self._total_messages_sent = 0
            self._total_ticks_broadcast = 0
            self._total_dropped_backpressure = 0


# Global Singleton WebSocket Swarm Manager
websocket_swarm_manager = WebSocketSwarmManager()
