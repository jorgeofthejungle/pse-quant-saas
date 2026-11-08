"""
pse_quant/events — Event-Driven Architecture & Alert Fanout Subsystem
====================================================================
Components:
  1. EventBus & global_event_bus: Thread-safe in-memory pub-sub broker.
  2. DomainEvent, MarketTickEvent, QuantValuationEvent, RegimeShiftEvent.
  3. AlertFanoutService: Watchlist matching, MoS filtering, and cooldown deduplication.
"""

from pse_quant.events.bus import (
    EventBus,
    global_event_bus,
    DomainEvent,
    MarketTickEvent,
    QuantValuationEvent,
    RegimeShiftEvent,
)
from pse_quant.events.fanout import AlertFanoutService

# Register AlertFanoutService with the global event bus
global_event_bus.subscribe(
    "quant.valuation.*",
    lambda evt: AlertFanoutService.handle_quant_valuation(evt) if isinstance(evt, QuantValuationEvent) else None,
)

__all__ = [
    "EventBus",
    "global_event_bus",
    "DomainEvent",
    "MarketTickEvent",
    "QuantValuationEvent",
    "RegimeShiftEvent",
    "AlertFanoutService",
]
