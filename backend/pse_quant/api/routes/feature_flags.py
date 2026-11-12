"""
pse_quant/api/routes/feature_flags.py — Admin REST API for Feature Flags & Canaries
PSE Quant SaaS — Lab 16
"""

from __future__ import annotations
from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from pse_quant.feature_flags.models import (
    FeatureFlag,
    EvaluationContext,
    EvaluationResult,
    FeatureFlagCreateRequest,
    FeatureFlagUpdateRequest,
)
from pse_quant.feature_flags.engine import feature_flag_engine

router = APIRouter(prefix="/admin/feature-flags", tags=["admin-feature-flags"])


@router.get("", response_model=list[FeatureFlag])
def list_feature_flags():
    """Lists all registered dynamic feature flags."""
    return feature_flag_engine.list_flags()


@router.post("", response_model=FeatureFlag, status_code=status.HTTP_201_CREATED)
def create_feature_flag(payload: FeatureFlagCreateRequest, actor: str = Query(default="admin")):
    """Registers a new feature flag with initial rollout percentage and targeting rules."""
    existing = feature_flag_engine.get_flag(payload.key)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Feature flag with key '{payload.key}' already exists.",
        )
    flag = FeatureFlag(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        is_enabled=payload.is_enabled,
        rollout_percentage=payload.rollout_percentage,
        allowed_tiers=payload.allowed_tiers,
        allowed_entities=payload.allowed_entities,
        denied_entities=payload.denied_entities,
        variants=payload.variants,
    )
    return feature_flag_engine.create_flag(flag, actor=actor)


@router.get("/{flag_key}", response_model=FeatureFlag)
def get_feature_flag(flag_key: str):
    """Retrieves full configuration details for a specific feature flag."""
    flag = feature_flag_engine.get_flag(flag_key)
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{flag_key}' not found.",
        )
    return flag


@router.put("/{flag_key}", response_model=FeatureFlag)
def update_feature_flag(flag_key: str, payload: FeatureFlagUpdateRequest, actor: str = Query(default="admin")):
    """Updates an existing feature flag configuration and records an audit log entry."""
    updates = payload.model_dump(exclude_unset=True)
    try:
        return feature_flag_engine.update_flag(flag_key, updates, actor=actor)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{flag_key}' not found.",
        )


@router.post("/{flag_key}/kill-switch", response_model=FeatureFlag)
def trigger_kill_switch(flag_key: str, actor: str = Query(default="admin_emergency")):
    """
    Sub-millisecond emergency kill switch.
    Immediately sets is_enabled to False across all worker threads.
    """
    try:
        return feature_flag_engine.kill_switch(flag_key, actor=actor)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{flag_key}' not found.",
        )


@router.post("/{flag_key}/evaluate", response_model=EvaluationResult)
def dry_run_evaluate(flag_key: str, context: EvaluationContext):
    """Dry-run evaluates a feature flag against a simulated client context."""
    return feature_flag_engine.evaluate(flag_key, context)


@router.get("/{flag_key}/audit-trail", response_model=list[dict[str, Any]])
def get_flag_audit_trail(flag_key: str, limit: int = Query(default=20, ge=1, le=100)):
    """Retrieves the immutable audit trail for a feature flag."""
    flag = feature_flag_engine.get_flag(flag_key)
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{flag_key}' not found.",
        )
    return feature_flag_engine.get_audit_trail(flag_key, limit=limit)


@router.delete("/{flag_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feature_flag(flag_key: str, actor: str = Query(default="admin")):
    """Deletes a feature flag from in-memory cache and persistent database."""
    deleted = feature_flag_engine.delete_flag(flag_key, actor=actor)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{flag_key}' not found.",
        )
    return None
