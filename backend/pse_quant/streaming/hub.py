"""
pse_quant/streaming/hub.py — Real-Time Server-Sent Events (SSE) Stream Hub
PSE Quant SaaS (v2 Rebuild) — Lab 11

Provides high-throughput, channel-based pub-sub streaming compliant with the
W3C EventSource specification. Enables real-time reactive updates for:
  - Background task execution progress (ETL, PDF compilation, valuation runs).
  - In-app Margin of Safety portfolio alerts.
  - Real-time market ticks and price shifts.
  - Live admin performance telemetry.
"""

from __future__ import annotations
import json
import uuid
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, AsyncGenerator
from starlette.requests import Request

logger = logging.getLogger("pse_quant.streaming")


def format_sse_event(
    event_type: str,
    data: Any,
    event_id: Optional[str] = None,
    retry_ms: Optional[int] = 3000,
) -> str:
    """
    Serializes a message into a W3C-compliant Server-Sent Event block:
      id: <event_id>\n
      event: <event_type>\n
      retry: <retry_ms>\n
      data: <json_string>\n\n
    """
    eid = event_id or f"evt_{uuid.uuid4().hex[:12]}"
    json_data = json.dumps(data, default=str)

    lines = [f"id: {eid}"]
    if event_type:
        lines.append(f"event: {event_type}")
    if retry_ms is not None:
        lines.append(f"retry: {retry_ms}")
    lines.append(f"data: {json_data}")

    return "\n".join(lines) + "\n\n"


class StreamHub:
    """
    Central channel-based streaming hub managing client queues, thread-safe
    event dispatching, periodic keep-alive pings, and disconnect cleanups.
    """

    def __init__(self):
        self._channels: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = threading.Lock()
        self._total_events_dispatched = 0

    def subscribe(self, channel: str, max_queue_size: int = 100) -> asyncio.Queue:
        """Registers a new client queue to receive events for a channel."""
        q: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        with self._lock:
            if channel not in self._channels:
                self._channels[channel] = set()
            self._channels[channel].add(q)
            logger.debug("Client subscribed to channel '%s' (active: %d)", channel, len(self._channels[channel]))
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        """Unregisters a client queue and purges empty channel buckets."""
        with self._lock:
            if channel in self._channels:
                self._channels[channel].discard(q)
                if not self._channels[channel]:
                    del self._channels[channel]
            logger.debug("Client unsubscribed from channel '%s'", channel)

    def broadcast(
        self,
        channel: str,
        event_type: str,
        data: Any,
        event_id: Optional[str] = None,
        retry_ms: Optional[int] = 3000,
    ) -> int:
        """
        Thread-safe dispatch: formats and delivers an SSE message to all subscribers of a channel.
        Can be invoked from synchronous code, background worker threads, or async coroutines.
        """
        formatted = format_sse_event(
            event_type=event_type,
            data=data,
            event_id=event_id,
            retry_ms=retry_ms,
        )

        with self._lock:
            queues = list(self._channels.get(channel, set()))
            self._total_events_dispatched += 1

        delivered = 0
        for q in queues:
            try:
                # put_nowait works safely across threads for asyncio.Queue if queue is not full
                if q.full():
                    try:
                        q.get_nowait()  # Drop oldest event on slow consumer backpressure
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(formatted)
                delivered += 1
            except Exception as exc:
                logger.warning("Failed to deliver SSE event to queue in channel '%s': %s", channel, exc)

        return delivered

    async def event_generator(
        self,
        channel: str,
        request: Optional[Request] = None,
        ping_interval: float = 5.0,
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronous generator yielding SSE chunks for a FastAPI StreamingResponse.
        Features automatic keep-alive comment pings and disconnect detection.
        """
        q = self.subscribe(channel)
        try:
            # Send initial connection acknowledgment
            yield format_sse_event(
                event_type="connected",
                data={
                    "channel": channel,
                    "connected_at": datetime.now(timezone.utc).isoformat(),
                    "status": "active",
                },
            )

            while True:
                # Check for client disconnect
                if request and await request.is_disconnected():
                    logger.debug("Detected client disconnect on channel '%s'", channel)
                    break

                try:
                    # Wait for next event or heartbeat timeout
                    message = await asyncio.wait_for(q.get(), timeout=ping_interval)
                    yield message
                except asyncio.TimeoutError:
                    # Yield W3C comment keep-alive ping to prevent proxy drops
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            logger.debug("SSE stream cancelled for channel '%s'", channel)
        finally:
            self.unsubscribe(channel, q)

    def get_metrics(self) -> Dict[str, Any]:
        """Returns live channel subscriptions and event dispatch telemetry."""
        with self._lock:
            channel_counts = {k: len(v) for k, v in self._channels.items()}
            total_active_subscribers = sum(channel_counts.values())
            total_events = self._total_events_dispatched

        return {
            "status": "healthy",
            "active_channels": len(channel_counts),
            "total_active_subscribers": total_active_subscribers,
            "total_events_dispatched": total_events,
            "channels": channel_counts,
        }

    def reset(self) -> None:
        """Clears all channels for test tear-down."""
        with self._lock:
            self._channels.clear()
            self._total_events_dispatched = 0


# Global singleton streaming hub
stream_hub = StreamHub()
