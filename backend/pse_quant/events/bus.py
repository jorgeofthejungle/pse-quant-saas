"""
pse_quant/events/bus.py — In-Memory Pub-Sub Event Bus
=====================================================
Thread-safe publish-subscribe message broker decoupling quantitative calculation
and market ingestion events from downstream alert fanout and notification channels.
"""

from __future__ import annotations
import fnmatch
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("pse_quant.events")


@dataclass
class DomainEvent:
    """Base class for all domain events in the system."""
    topic: str = ""
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)


@dataclass
class MarketTickEvent(DomainEvent):
    """Fired when a new quote or price trade arrives."""
    ticker: str = ""
    price: float = 0.0
    volume: Optional[int] = None
    change_pct: Optional[float] = None

    def __post_init__(self):
        if not self.topic:
            self.topic = f"market.tick.{self.ticker.upper()}"


@dataclass
class QuantValuationEvent(DomainEvent):
    """Fired when 3-layer scoring and Margin of Safety valuation is computed."""
    ticker: str = ""
    price: float = 0.0
    intrinsic_value: float = 0.0
    mos_pct: float = 0.0
    score: float = 0.0
    category: str = "Watchlist"

    def __post_init__(self):
        if not self.topic:
            self.topic = f"quant.valuation.{self.ticker.upper()}"


@dataclass
class RegimeShiftEvent(DomainEvent):
    """Fired when macro market conditions shift (e.g. Rate Hike, Foreign Inflow)."""
    regime_title: str = ""
    php_10y_bval: float = 0.0
    z_msci_flow: float = 0.0

    def __post_init__(self):
        if not self.topic:
            self.topic = "macro.regime.shift"


class EventBus:
    """
    Thread-safe publish-subscribe broker with topic pattern matching.
    Supports wildcards like 'quant.valuation.*' and 'market.*'.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, topic_pattern: str, handler: Callable[[Any], None]) -> None:
        """Registers a handler callback for a topic pattern."""
        with self._lock:
            if topic_pattern not in self._subscribers:
                self._subscribers[topic_pattern] = []
            self._subscribers[topic_pattern].append(handler)
            logger.debug(f"Subscribed handler {handler.__name__ if hasattr(handler, '__name__') else handler} to '{topic_pattern}'")

    def unsubscribe(self, topic_pattern: str, handler: Callable[[Any], None]) -> bool:
        """Removes a handler callback."""
        with self._lock:
            if topic_pattern in self._subscribers and handler in self._subscribers[topic_pattern]:
                self._subscribers[topic_pattern].remove(handler)
                return True
            return False

    def publish(self, event: DomainEvent) -> int:
        """
        Dispatches an event to all matching subscribers.
        Returns the number of handlers invoked.
        """
        with self._lock:
            matching_handlers: List[Callable[[Any], None]] = []
            for pattern, handlers in self._subscribers.items():
                if fnmatch.fnmatch(event.topic, pattern):
                    matching_handlers.extend(handlers)

        invoked_count = 0
        for handler in matching_handlers:
            try:
                handler(event)
                invoked_count += 1
            except Exception as exc:
                logger.exception(f"Error executing event handler {handler} on topic '{event.topic}': {exc}")

        logger.debug(f"Published event '{event.topic}' ({event.event_id}) to {invoked_count} handlers")
        return invoked_count

    def clear(self) -> None:
        """Removes all registered subscribers."""
        with self._lock:
            self._subscribers.clear()


# Global singleton event bus
global_event_bus = EventBus()
