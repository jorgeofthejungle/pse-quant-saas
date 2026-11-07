"""
backend/pse_quant/api/limiter.py — Inbound HTTP Rate Limiting & Abuse Prevention
=============================================================================
Enforces tiered rate limits to prevent brute-force authentication attacks,
DoS on calculation endpoints, and unauthorized burst traffic.
"""

from __future__ import annotations
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


def get_real_client_ip(request: Request) -> str:
    """
    Extracts the real client IP, inspecting X-Forwarded-For when behind a proxy/CDN.
    Falls back to direct connection socket host.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first untrusted proxy client IP
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Central SlowAPI Limiter instance
limiter = Limiter(
    key_func=get_real_client_ip,
    default_limits=["120/minute"],
    headers_enabled=False,
    storage_uri="memory://",
)


def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Returns structured 429 Too Many Requests response with Retry-After header."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "TooManyRequests",
            "message": f"Rate limit exceeded: {exc.detail}. Please slow down your requests.",
            "path": request.url.path,
        },
        headers={"Retry-After": "60"},
    )
