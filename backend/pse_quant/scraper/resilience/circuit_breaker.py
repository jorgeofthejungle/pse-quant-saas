"""
pse_quant/scraper/resilience/circuit_breaker.py — Circuit Breaker Pattern
========================================================================
Prevents cascading failures and resource exhaustion during upstream outages
(PSE Edge 502/503/504 errors). Implements the classic 3-state machine:
  CLOSED -> OPEN -> HALF-OPEN -> CLOSED
"""

from __future__ import annotations
import time
import threading
import logging
from enum import Enum
from typing import Optional, Callable, Any

logger = logging.getLogger("pse_quant.scraper.resilience")


class CircuitState(str, Enum):
    """States of the Circuit Breaker."""
    CLOSED = "CLOSED"       # Normal operation; calls proceed through
    OPEN = "OPEN"           # Upstream failing; fast-fail immediately without network call
    HALF_OPEN = "HALF_OPEN" # Cooldown expired; testing upstream with canary request


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""

    def __init__(self, message: str, cooldown_remaining_sec: float):
        super().__init__(message)
        self.cooldown_remaining_sec = round(cooldown_remaining_sec, 2)


class CircuitBreaker:
    """
    Thread-safe implementation of the Circuit Breaker pattern.
    Protects downstream workers from stalling on a down upstream service.
    """

    def __init__(
        self,
        name: str = "pse_edge",
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        recovery_time: Optional[float] = None,
        half_open_successes: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = recovery_time if recovery_time is not None else cooldown_seconds
        self.half_open_successes = half_open_successes

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._half_open_success_count = 0
        self._last_state_change = time.time()
        self._last_failure_reason: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_cooldown_transition()
            return self._state

    def can_execute(self, now: Optional[float] = None) -> bool:
        """Determines whether a call is allowed to proceed."""
        current_time = now if now is not None else time.time()
        with self._lock:
            self._check_cooldown_transition(current_time)
            return self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Executes a callable under circuit breaker protection, fast-failing if OPEN."""
        if not self.can_execute():
            raise RuntimeError(f"Circuit breaker is OPEN (name={self.name})")
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as exc:
            self.record_failure(reason=str(exc))
            raise

    def _check_cooldown_transition(self, current_time: Optional[float] = None) -> None:
        """Transitions from OPEN to HALF_OPEN if the cooldown period has elapsed."""
        now = current_time if current_time is not None else time.time()
        if self._state == CircuitState.OPEN:
            elapsed = now - self._last_state_change
            if elapsed >= self.cooldown_seconds:
                logger.info(
                    f"CircuitBreaker [{self.name}] cooldown expired ({elapsed:.1f}s >= {self.cooldown_seconds}s). "
                    f"Transitioning OPEN -> HALF_OPEN."
                )
                self._state = CircuitState.HALF_OPEN
                self._half_open_success_count = 0
                self._last_state_change = now

    def record_success(self) -> None:
        """Records a successful operation."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_success_count += 1
                if self._half_open_success_count >= self.half_open_successes:
                    logger.info(
                        f"CircuitBreaker [{self.name}] canary probe succeeded. "
                        f"Transitioning HALF_OPEN -> CLOSED (healthy)."
                    )
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._last_state_change = time.time()
                    self._last_failure_reason = None
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0
                self._last_failure_reason = None

    def record_failure(self, reason: Optional[str] = None) -> None:
        """Records an operation failure."""
        now = time.time()
        with self._lock:
            self._last_failure_reason = reason or "Unknown failure"
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"CircuitBreaker [{self.name}] canary probe failed ({self._last_failure_reason}). "
                    f"Re-tripping HALF_OPEN -> OPEN."
                )
                self._state = CircuitState.OPEN
                self._last_state_change = now
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures += 1
                logger.warning(
                    f"CircuitBreaker [{self.name}] failure recorded: "
                    f"{self._consecutive_failures}/{self.failure_threshold} ({self._last_failure_reason})"
                )
                if self._consecutive_failures >= self.failure_threshold:
                    logger.error(
                        f"CircuitBreaker [{self.name}] failure threshold reached ({self._consecutive_failures}). "
                        f"Tripping circuit CLOSED -> OPEN."
                    )
                    self._state = CircuitState.OPEN
                    self._last_state_change = now

    def reset(self) -> None:
        """Manually forces the circuit breaker back to CLOSED state."""
        with self._lock:
            logger.info(f"CircuitBreaker [{self.name}] manually reset to CLOSED.")
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._half_open_success_count = 0
            self._last_state_change = time.time()
            self._last_failure_reason = None

    def get_state(self) -> dict[str, Any]:
        """Returns observable telemetry dictionary."""
        with self._lock:
            self._check_cooldown_transition()
            now = time.time()
            cooldown_remaining = max(0.0, self.cooldown_seconds - (now - self._last_state_change)) if self._state == CircuitState.OPEN else 0.0

            return {
                "name": self.name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self.failure_threshold,
                "cooldown_seconds": self.cooldown_seconds,
                "cooldown_remaining_sec": round(cooldown_remaining, 2),
                "last_failure_reason": self._last_failure_reason,
                "last_state_change": self._last_state_change,
            }
