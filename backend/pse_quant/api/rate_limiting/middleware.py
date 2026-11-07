"""
pse_quant/api/rate_limiting/middleware.py — Token Bucket Rate Limiting Middleware
================================================================================
FastAPI middleware implementing the multi-tier Token Bucket algorithm with standard
IETF rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After).
"""

from __future__ import annotations
import math
import logging
from typing import Callable, Set
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from pse_quant.api.rate_limiting.token_bucket import TokenBucketStore, ClientTier
from pse_quant.api.rate_limiting.fingerprint import resolve_client_fingerprint

logger = logging.getLogger("pse_quant.rate_limit")

# Global in-memory bucket store
global_token_store = TokenBucketStore()

# Endpoints exempt from token bucket throttling
EXEMPT_PATHS: Set[str] = {
    "/health",
    "/api/v1/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class TokenBucketMiddleware(BaseHTTPMiddleware):
    """
    Middleware that intercepts incoming requests, resolves client tier,
    consumes tokens from the client's TokenBucket, and decorates responses
    with standard X-RateLimit headers.
    """

    def __init__(self, app, store: TokenBucketStore | None = None, enabled: bool = True):
        super().__init__(app)
        self.store = store or global_token_store
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # 1. Resolve Identity and Tier
        client_key, tier = resolve_client_fingerprint(request)

        # 2. Evaluate Token Consumption
        result = self.store.evaluate(client_key=client_key, tier=tier, cost=1.0)

        # 3. Handle Throttling (HTTP 429)
        if not result.allowed:
            logger.warning(
                f"Rate limit exceeded: {client_key} ({tier.value}) on {request.method} {request.url.path}. "
                f"Retry-After: {result.retry_after_seconds}s"
            )
            retry_after_int = max(1, math.ceil(result.retry_after_seconds))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "TooManyRequests",
                    "message": f"Rate limit exceeded for tier '{tier.value}'. Bucket capacity depleted.",
                    "tier": tier.value,
                    "burst_capacity": result.burst_capacity,
                    "retry_after_seconds": result.retry_after_seconds,
                    "path": request.url.path,
                },
                headers={
                    "Retry-After": str(retry_after_int),
                    "X-RateLimit-Limit": str(result.burst_capacity),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_seconds),
                    "X-RateLimit-Tier": tier.value,
                },
            )

        # 4. Proceed & Inject Rate Limit Headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.burst_capacity)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining_tokens)
        response.headers["X-RateLimit-Reset"] = str(result.reset_seconds)
        response.headers["X-RateLimit-Tier"] = tier.value
        return response
