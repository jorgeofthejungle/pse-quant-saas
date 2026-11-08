"""
pse_quant/telemetry/middleware.py — Distributed Tracing & Correlation ID Middleware
PSE Quant SaaS (v2 Rebuild) — Lab 10

Extracts or generates X-Correlation-ID, propagates trace context into ContextVar,
calculates high-precision request duration, injects tracing headers, and records
latency histograms.
"""

from __future__ import annotations
import time
import logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pse_quant.telemetry.context import (
    set_correlation_id,
    reset_correlation_id,
    generate_correlation_id,
    set_trace_metadata,
    reset_trace_metadata,
)
from pse_quant.telemetry.tracker import global_latency_tracker

logger = logging.getLogger("pse_quant.telemetry.middleware")


class TracingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware enforcing end-to-end distributed tracing across all HTTP endpoints:
      1. Adopts upstream X-Correlation-ID / X-Request-ID / traceparent or generates a new one.
      2. Binds correlation_id to ambient ContextVar for seamless structured logging.
      3. Measures request latency with time.perf_counter().
      4. Injects X-Correlation-ID and X-Response-Time-Ms headers on every HTTP response.
      5. Records duration in global_latency_tracker for p50/p95/p99 quantile analysis.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Extract or generate Correlation ID
        incoming_corr = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
        )

        # Support W3C traceparent (format: 00-<32char-trace-id>-<16char-span-id>-<flags>)
        if not incoming_corr and "traceparent" in request.headers:
            parts = request.headers["traceparent"].split("-")
            if len(parts) >= 2:
                incoming_corr = f"corr_{parts[1][:16]}"

        correlation_id = incoming_corr if incoming_corr else generate_correlation_id()

        # 2. Bind context
        token_corr = set_correlation_id(correlation_id)
        token_meta = set_trace_metadata({
            "path": request.url.path,
            "method": request.method,
            "client_ip": request.client.host if request.client else "unknown",
        })

        # 3. High-resolution timer
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            global_latency_tracker.record_request(
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                status_code=500,
                correlation_id=correlation_id,
            )
            logger.error(
                "Unhandled error during request %s %s (correlation_id=%s): %s",
                request.method,
                request.url.path,
                correlation_id,
                exc,
                exc_info=True,
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000.0

        # 4. Record latency and trace sample
        global_latency_tracker.record_request(
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
            status_code=status_code,
            correlation_id=correlation_id,
        )

        # 5. Inject response headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}ms"

        # 6. Clean up context tokens
        reset_trace_metadata(token_meta)
        reset_correlation_id(token_corr)

        return response
