"""
pse_quant/feature_flags/dependencies.py — FastAPI Endpoint Ingress Guards
PSE Quant SaaS — Lab 16: Feature Flags & Progressive Canary Delivery Engine
"""

from __future__ import annotations
from typing import Callable
from fastapi import Request, HTTPException, status

from pse_quant.feature_flags.models import EvaluationContext, EvaluationResult
from pse_quant.feature_flags.engine import feature_flag_engine


def require_feature(flag_key: str) -> Callable[[Request], EvaluationResult]:
    """
    FastAPI endpoint dependency guarding routes behind a dynamic feature flag.
    If the flag evaluates to False for the requesting client, an HTTP 404
    is raised to prevent leaking the existence of dark-launched features.
    """
    async def _dependency(request: Request) -> EvaluationResult:
        # Extract entity identification from headers or client IP
        entity_id = (
            request.headers.get("X-User-ID")
            or request.headers.get("X-Client-ID")
            or (request.client.host if request.client else "anonymous")
        )
        tier = request.headers.get("X-Client-Tier", "FREE")

        context = EvaluationContext(
            entity_id=entity_id,
            tier=tier,
            attributes={
                "path": request.url.path,
                "method": request.method,
                "user_agent": request.headers.get("User-Agent", ""),
            },
        )

        result = feature_flag_engine.evaluate(flag_key, context)

        if not result.enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint or feature '{flag_key}' is not available.",
            )

        # Attach evaluation result to request state for downstream handler consumption
        if not hasattr(request.state, "features"):
            request.state.features = {}
        request.state.features[flag_key] = result

        return result

    return _dependency
