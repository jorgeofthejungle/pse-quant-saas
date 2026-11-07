"""
pse_quant/scraper/resilience — Resilient Ingestion Subsystem
============================================================
Components:
  1. CircuitBreaker: Fast-fail protection during upstream PSE Edge outages.
  2. calculate_jittered_backoff: Exponential backoff with Full Jitter.
  3. DeadLetterService: Quarantine and triage of malformed filings.
"""

from pse_quant.scraper.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenException,
)
from pse_quant.scraper.resilience.backoff import calculate_jittered_backoff
from pse_quant.scraper.resilience.dead_letter import DeadLetterService

# Shared global circuit breaker for PSE Edge
global_pse_edge_circuit = CircuitBreaker(
    name="pse_edge",
    failure_threshold=5,
    cooldown_seconds=30.0,
)

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerOpenException",
    "calculate_jittered_backoff",
    "DeadLetterService",
    "global_pse_edge_circuit",
]
