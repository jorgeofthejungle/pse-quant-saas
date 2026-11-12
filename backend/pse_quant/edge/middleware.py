"""
pse_quant/edge/middleware.py — Dynamic Edge Caching & POP Ingress Middleware
PSE Quant SaaS — Lab 18: Multi-Region Ingress & Dynamic Edge Caching Headers

Features:
  - Multi-region POP ingress detection (CF-Ray, X-Edge-Region, default Manila MNL).
  - Dynamic RFC 7234 Cache-Control policy enforcement.
  - Deterministic SHA-256 ETag generation.
  - Sub-millisecond RFC 7232 HTTP 304 Not Modified short-circuiting.
  - Surrogate-Key & Cache-Tag header propagation for selective edge invalidation.
"""

from __future__ import annotations
import logging
from typing import Callable, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pse_quant.edge.models import CachePolicy
from pse_quant.edge.etag import compute_etag, is_etag_match
from pse_quant.edge.manager import edge_cache_manager

logger = logging.getLogger("pse_quant.edge.middleware")


class DynamicEdgeCacheMiddleware(BaseHTTPMiddleware):
    """
    Edge-aware ingress middleware generating conditional caching directives,
    ETag validators, and multi-region routing telemetry.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Multi-Region POP Ingress Telemetry Extraction
        pop = self._extract_edge_pop(request)

        # 2. Skip non-cacheable streaming or websocket upgrades
        if request.scope.get("type") == "websocket" or request.url.path.startswith("/api/v1/stream"):
            response = await call_next(request)
            response.headers["X-Edge-Origin-POP"] = pop
            return response

        # 3. Call downstream route handler
        response = await call_next(request)

        # Skip SSE streams or non-GET/HEAD methods
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            response.headers["X-Edge-Origin-POP"] = pop
            return response

        if request.method not in ("GET", "HEAD"):
            response.headers["X-Edge-Origin-POP"] = pop
            return response

        # 4. Determine Cache Policy and Surrogate Tags
        policy, tags = self._resolve_cache_policy_and_tags(request.url.path, request.headers)

        # 5. Handle ETag & 304 Conditional Responses for 200 OK payloads
        if response.status_code == 200:
            # Consume body chunks safely
            response_body = [chunk async for chunk in response.body_iterator]
            body_bytes = b"".join(response_body)

            etag = compute_etag(body_bytes)
            edge_cache_manager.record_etag()

            if_none_match = request.headers.get("if-none-match")
            if is_etag_match(if_none_match, etag):
                edge_cache_manager.record_304(pop)
                not_modified_resp = Response(
                    status_code=304,
                    headers={
                        "ETag": etag,
                        "Cache-Control": policy,
                        "X-Cache-Status": "REVALIDATED",
                        "X-Edge-Origin-POP": pop,
                    },
                )
                # Copy correlation / tracing headers
                for header_key in ("X-Correlation-ID", "X-Response-Time-Ms"):
                    if header_key in response.headers:
                        not_modified_resp.headers[header_key] = response.headers[header_key]
                return not_modified_resp

            # Cache Miss (Fresh 200 Body with ETag)
            edge_cache_manager.record_200(pop)
            headers = dict(response.headers)
            headers["ETag"] = etag
            headers["Cache-Control"] = policy
            headers["X-Cache-Status"] = "MISS"
            headers["X-Edge-Origin-POP"] = pop
            if tags:
                tag_str = " ".join(tags)
                headers["Surrogate-Key"] = tag_str
                headers["Cache-Tag"] = tag_str

            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        # Non-200 responses
        response.headers["X-Edge-Origin-POP"] = pop
        response.headers["Cache-Control"] = policy
        return response

    @staticmethod
    def _extract_edge_pop(request: Request) -> str:
        """Extracts Cloudflare / Vercel Edge POP or defaults to Manila primary."""
        cf_ray = request.headers.get("cf-ray")
        if cf_ray and "-" in cf_ray:
            return cf_ray.split("-")[-1].upper()

        edge_region = request.headers.get("x-edge-region") or request.headers.get("cf-ipcountry")
        if edge_region:
            return edge_region.upper()

        return "MNL"

    @staticmethod
    def _resolve_cache_policy_and_tags(path: str, headers: dict) -> tuple[str, list[str]]:
        """Resolves Cache-Control directives and surrogate invalidation tags based on path semantics."""
        # Authenticated or user-private resources
        if (
            path.startswith("/api/v1/admin")
            or path.startswith("/api/v1/customers/me")
            or path.startswith("/api/v1/watchlist")
            or "authorization" in headers
        ):
            return CachePolicy.PRIVATE_USER.value, []

        # System health liveness
        if path in ("/health", "/api/v1/health"):
            return CachePolicy.NO_STORE.value, []

        # Stocks public quant data
        if path.startswith("/api/v1/stocks"):
            parts = path.strip("/").split("/")
            tags = ["stocks", "pse-market"]
            if len(parts) >= 4 and parts[3]:  # /api/v1/stocks/{ticker}
                ticker = parts[3].upper()
                tags.insert(0, f"stock-{ticker}")
            return CachePolicy.PUBLIC_SEMI_STATIC.value, tags

        return CachePolicy.PUBLIC_DYNAMIC_TICK.value, ["general"]
