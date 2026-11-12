"""
pse_quant/api/routes/chaos.py — Admin Chaos Engineering Control API
PSE Quant SaaS (v2 Rebuild) — Lab 15

Exposes REST controls to activate controlled fault experiments (latency, errors, circuit breaker stress),
monitor telemetry, and trigger an immediate emergency kill-switch.
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query, Body

from pse_quant.chaos import chaos_engine, ChaosConfig, FaultType
from pse_quant.api.routes.admin import require_admin

router = APIRouter(prefix="/admin/chaos", tags=["admin-chaos"], dependencies=[Depends(require_admin)])


@router.get("/status", summary="Inspect live chaos experiment configuration & telemetry")
def get_chaos_status():
    """Returns the current state, active fault type, hit probability, and injection telemetry."""
    return chaos_engine.get_status()


@router.post("/enable", summary="Activate controlled chaos fault injection")
def enable_chaos(
    fault_type: Optional[str] = Query("latency", pattern="^(latency|http_error|circuit_breaker_stress|db_starvation)$"),
    probability: Optional[float] = Query(0.5, ge=0.0, le=1.0, description="Fault probability [0.0 - 1.0]"),
    latency_ms: Optional[int] = Query(300, ge=10, le=10000, description="Latency delay in ms (for latency fault)"),
    status_code: Optional[int] = Query(503, ge=400, le=599, description="HTTP status code (for http_error fault)"),
    target_path: Optional[str] = Query("/api/v1/stocks", description="Target path prefix for fault injection"),
):
    """
    Activates controlled synthetic faults.
    Blast radius is permanently bounded: /health, /api/v1/health, and /api/v1/admin/chaos are strictly exempt.
    """
    config = ChaosConfig(
        is_active=True,
        fault_type=FaultType(fault_type or "latency"),
        probability=probability if probability is not None else 0.5,
        latency_ms=latency_ms or 300,
        http_status_code=status_code or 503,
        target_path_prefix=target_path or "/api/v1/stocks",
    )
    return chaos_engine.enable(config)


@router.post("/disable", summary="Deactivate active chaos experiments")
def disable_chaos():
    """Stops all chaos injections, returning system to normal baseline execution."""
    return chaos_engine.disable()


@router.post("/kill-switch", summary="Emergency abort: immediately halt all chaos faults in <1ms")
def emergency_kill_switch():
    """Instant emergency abort: terminates all active faults across all threads and workers."""
    return chaos_engine.emergency_kill_switch()


@router.post("/reset-metrics", summary="Reset chaos telemetry counters")
def reset_chaos_metrics():
    """Resets injected and bypassed request counters to zero."""
    return chaos_engine.reset_metrics()
