"""
pse_quant/chaos/models.py — Chaos Engineering & Fault Injection Models
PSE Quant SaaS (v2 Rebuild) — Lab 15
"""

from __future__ import annotations
from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class FaultType(str, Enum):
    LATENCY = "latency"
    HTTP_ERROR = "http_error"
    CIRCUIT_BREAKER_STRESS = "circuit_breaker_stress"
    DB_STARVATION = "db_starvation"


class ChaosConfig(BaseModel):
    """Configuration for controlled runtime chaos fault injection."""
    is_active: bool = False
    fault_type: FaultType = FaultType.LATENCY
    probability: float = Field(default=0.5, ge=0.0, le=1.0, description="Fault injection probability [0.0, 1.0]")
    latency_ms: int = Field(default=300, ge=10, le=10000, description="Synthetic latency in milliseconds")
    http_status_code: int = Field(default=503, ge=400, le=599, description="Synthetic HTTP status code for HTTP_ERROR")
    target_path_prefix: str = Field(default="/api/v1/stocks", description="Target URL path prefix for fault injection")
    exempt_path_prefixes: List[str] = Field(
        default_factory=lambda: [
            "/health",
            "/api/v1/health",
            "/api/v1/admin/chaos",
            "/docs",
            "/openapi.json",
        ],
        description="Protected paths exempt from fault injection (blast-radius lock)",
    )


class ChaosTelemetry(BaseModel):
    """Runtime observability telemetry tracking chaos injections and bypasses."""
    injected_requests_count: int = 0
    bypassed_requests_count: int = 0
    faults_by_type: Dict[str, int] = Field(default_factory=dict)
    last_injected_at: Optional[datetime] = None
