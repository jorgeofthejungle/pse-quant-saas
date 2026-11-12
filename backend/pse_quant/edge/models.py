"""
pse_quant/edge/models.py — Edge Caching Policies & Telemetry Contracts
PSE Quant SaaS — Lab 18: Multi-Region Ingress & Dynamic Edge Caching Headers
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class CachePolicy(str, Enum):
    """Preset RFC 7234 / RFC 9111 HTTP Cache-Control header directives."""
    PUBLIC_SEMI_STATIC = "public, max-age=60, s-maxage=300, stale-while-revalidate=60"
    PUBLIC_DYNAMIC_TICK = "public, max-age=5, s-maxage=15, stale-while-revalidate=10"
    PRIVATE_USER = "private, no-cache, no-store, must-revalidate"
    NO_STORE = "no-store, no-cache, must-revalidate"


class PurgeRequest(BaseModel):
    """Payload to purge edge cache tags or surrogate keys."""
    tags: list[str] = Field(..., description="List of cache tags to invalidate (e.g. ['stock-DMC', 'pse-market'])")
    actor: str = Field(default="admin", description="Originator of purge event")


class EdgeTelemetry(BaseModel):
    """Operational telemetry tracking edge cache efficiency and POP ingress routing."""
    total_requests_evaluated: int
    not_modified_304_served: int
    cache_miss_200_served: int
    etags_generated: int
    purged_tags_count: int
    last_purged_tag: Optional[str]
    active_pops: dict[str, int]
