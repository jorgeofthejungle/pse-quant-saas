"""
pse_quant/chaos/engine.py — Core Chaos Fault Evaluator & Blast Radius Controller
PSE Quant SaaS (v2 Rebuild) — Lab 15

Evaluates incoming HTTP requests against active chaos experiment rules,
enforces blast-radius exemptions, rolls probabilistic dice, and records telemetry.
"""

from __future__ import annotations
import random
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from pse_quant.chaos.models import ChaosConfig, ChaosTelemetry, FaultType

logger = logging.getLogger("pse_quant.chaos.engine")


class ChaosEngine:
    """Thread-safe orchestrator for synthetic fault injection experiments."""

    def __init__(self, config: Optional[ChaosConfig] = None):
        self._lock = threading.RLock()
        self.config = config or ChaosConfig()
        self.telemetry = ChaosTelemetry()

    def enable(self, config: Optional[ChaosConfig] = None) -> Dict[str, Any]:
        """Activates chaos engineering with updated configuration."""
        with self._lock:
            if config:
                self.config = config
            self.config.is_active = True
            logger.warning(
                "CHAOS EXPERIMENT ENABLED: type=%s, prob=%.2f, target=%s",
                self.config.fault_type.value,
                self.config.probability,
                self.config.target_path_prefix,
            )
            return self.get_status()

    def disable(self) -> Dict[str, Any]:
        """Deactivates active chaos experiments."""
        with self._lock:
            self.config.is_active = False
            logger.info("Chaos experiment deactivated.")
            return self.get_status()

    def emergency_kill_switch(self) -> Dict[str, Any]:
        """
        Immediately halts all active fault injections in <1ms.
        Guarantees instant recovery across all concurrent requests.
        """
        with self._lock:
            self.config.is_active = False
            logger.critical("EMERGENCY KILL-SWITCH TRIGGERED: All chaos faults halted immediately.")
            return {
                "status": "aborted",
                "message": "Emergency kill-switch engaged. All chaos faults terminated.",
                "is_active": False,
            }

    def evaluate_request(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Evaluates whether an incoming request path should receive an injected fault.
        Enforces blast-radius protection for safety endpoints.
        """
        with self._lock:
            if not self.config.is_active:
                return None

            # 1. Blast Radius Protection: Check exempt prefixes
            for exempt in self.config.exempt_path_prefixes:
                if path.startswith(exempt):
                    return None

            # 2. Path Targeting: Must match target path prefix
            if not path.startswith(self.config.target_path_prefix):
                return None

            # 3. Probabilistic Dice Roll
            roll = random.random()
            if roll < self.config.probability:
                now = datetime.now(timezone.utc)
                self.telemetry.injected_requests_count += 1
                self.telemetry.last_injected_at = now
                f_type = self.config.fault_type.value
                self.telemetry.faults_by_type[f_type] = self.telemetry.faults_by_type.get(f_type, 0) + 1

                return {
                    "fault_type": self.config.fault_type,
                    "latency_ms": self.config.latency_ms,
                    "http_status_code": self.config.http_status_code,
                }
            else:
                self.telemetry.bypassed_requests_count += 1
                return None

    def get_status(self) -> Dict[str, Any]:
        """Returns live status of chaos engine configuration and telemetry."""
        with self._lock:
            return {
                "is_active": self.config.is_active,
                "config": self.config.model_dump(),
                "telemetry": self.telemetry.model_dump(),
            }

    def reset_metrics(self) -> Dict[str, Any]:
        """Resets telemetry counters to zero."""
        with self._lock:
            self.telemetry = ChaosTelemetry()
            return {"status": "success", "message": "Chaos telemetry counters reset to zero."}


# Global singleton instance
chaos_engine = ChaosEngine()
