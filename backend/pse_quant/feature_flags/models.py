"""
pse_quant/feature_flags/models.py — Feature Flag Data Contracts & Types
PSE Quant SaaS — Lab 16: Feature Flags & Progressive Canary Delivery Engine
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class EvaluationReason(str, Enum):
    DISABLED = "DISABLED"
    NOT_FOUND = "NOT_FOUND"
    DENIED_ENTITY = "DENIED_ENTITY"
    ALLOWED_ENTITY = "ALLOWED_ENTITY"
    TIER_MISMATCH = "TIER_MISMATCH"
    PERCENTAGE_CANARY_MATCH = "PERCENTAGE_CANARY_MATCH"
    PERCENTAGE_CANARY_MISS = "PERCENTAGE_CANARY_MISS"
    GLOBAL_KILL_SWITCH = "GLOBAL_KILL_SWITCH"
    DEFAULT_FALLBACK = "DEFAULT_FALLBACK"


class AuditAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    KILL_SWITCH = "KILL_SWITCH"
    ENABLE = "ENABLE"
    DELETE = "DELETE"


class EvaluationContext(BaseModel):
    """Execution context supplied by request headers, auth tokens, or calling services."""
    entity_id: str = Field(default="anonymous", description="Unique entity identifier (user ID, tenant ID, or client IP)")
    tier: Optional[str] = Field(default="FREE", description="Subscription tier (e.g., FREE, PRO, INSTITUTIONAL, ADMIN)")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Arbitrary evaluation attributes")


class FeatureFlag(BaseModel):
    """Full definition of a dynamic feature flag."""
    key: str = Field(..., description="Unique snake_case feature flag key (e.g. 'dark_pool_v2')")
    name: str = Field(..., description="Human-readable feature name")
    description: str = Field(default="", description="Detailed summary of functionality controlled by this flag")
    is_enabled: bool = Field(default=False, description="Master toggle / emergency kill-switch")
    rollout_percentage: int = Field(default=0, ge=0, le=100, description="Percentage of traffic targeted (0 to 100)")
    allowed_tiers: list[str] = Field(default_factory=list, description="Targeted tiers (empty = open to all tiers)")
    allowed_entities: list[str] = Field(default_factory=list, description="Entities guaranteed to have flag ENABLED")
    denied_entities: list[str] = Field(default_factory=list, description="Entities guaranteed to have flag DISABLED")
    variants: dict[str, int] = Field(default_factory=dict, description="A/B test variants and weight distribution")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvaluationResult(BaseModel):
    """Result of evaluating a feature flag against a specific context."""
    flag_key: str
    enabled: bool
    reason: str
    bucket: Optional[int] = None
    variant: Optional[str] = None
    evaluation_latency_us: float = 0.0


class FeatureFlagCreateRequest(BaseModel):
    key: str
    name: str
    description: str = ""
    is_enabled: bool = False
    rollout_percentage: int = Field(default=0, ge=0, le=100)
    allowed_tiers: list[str] = Field(default_factory=list)
    allowed_entities: list[str] = Field(default_factory=list)
    denied_entities: list[str] = Field(default_factory=list)
    variants: dict[str, int] = Field(default_factory=dict)


class FeatureFlagUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    rollout_percentage: Optional[int] = Field(default=None, ge=0, le=100)
    allowed_tiers: Optional[list[str]] = None
    allowed_entities: Optional[list[str]] = None
    denied_entities: Optional[list[str]] = None
    variants: Optional[dict[str, int]] = None
