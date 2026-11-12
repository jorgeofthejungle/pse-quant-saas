"""
pse_quant/chaos/middleware.py — FastAPI ASGI Chaos Injection Middleware
PSE Quant SaaS (v2 Rebuild) — Lab 15

Intercepts incoming HTTP requests, applies active chaos faults (latency, HTTP errors,
circuit breaker stress, DB starvation), and tags responses with diagnostic headers.
"""

from __future__ import annotations
import asyncio
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pse_quant.chaos.engine import chaos_engine
from pse_quant.chaos.models import FaultType

logger = logging.getLogger("pse_quant.chaos.middleware")


class ChaosMiddleware(BaseHTTPMiddleware):
    """ASGI Middleware evaluating and executing controlled synthetic faults."""

    async def dispatch(self, request: Request, call_next) -> Response:
        fault = chaos_engine.evaluate_request(request.url.path)

        if not fault:
            return await call_next(request)

        fault_type = fault["fault_type"]

        # ── 1. Synthetic Latency Delay ───────────────────────────────
        if fault_type == FaultType.LATENCY:
            latency_ms = fault["latency_ms"]
            logger.warning("CHAOS FAULT: Injecting %dms latency into %s", latency_ms, request.url.path)
            await asyncio.sleep(latency_ms / 1000.0)
            response = await call_next(request)
            response.headers["X-Chaos-Injected"] = "LATENCY"
            response.headers["X-Chaos-Latency-Ms"] = str(latency_ms)
            return response

        # ── 2. Synthetic HTTP Error Drop ─────────────────────────────
        elif fault_type == FaultType.HTTP_ERROR:
            status_code = fault["http_status_code"]
            logger.warning("CHAOS FAULT: Dropping request %s with HTTP %d", request.url.path, status_code)
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": "ChaosInjectedError",
                    "message": f"Synthetic HTTP {status_code} fault injected by ChaosEngine.",
                    "path": request.url.path,
                },
                headers={
                    "X-Chaos-Injected": "HTTP_ERROR",
                    "X-Chaos-Status": str(status_code),
                },
            )

        # ── 3. Downstream Circuit Breaker Stress ─────────────────────
        elif fault_type == FaultType.CIRCUIT_BREAKER_STRESS:
            logger.warning("CHAOS FAULT: Circuit breaker stress injection on %s", request.url.path)
            return JSONResponse(
                status_code=503,
                content={
                    "error": "CircuitBreakerStressFault",
                    "message": "Synthetic downstream failure injected to test circuit breaker trip & half-open recovery.",
                    "path": request.url.path,
                },
                headers={
                    "X-Chaos-Injected": "CIRCUIT_BREAKER_STRESS",
                    "X-Chaos-Status": "503",
                },
            )

        # ── 4. Synthetic Database Starvation Fault ───────────────────
        elif fault_type == FaultType.DB_STARVATION:
            logger.warning("CHAOS FAULT: Database pool starvation injection on %s", request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "DatabasePoolStarvationFault",
                    "message": "Synthetic connection pool timeout injected to test graceful DB degradation.",
                    "path": request.url.path,
                },
                headers={
                    "X-Chaos-Injected": "DB_STARVATION",
                    "X-Chaos-Status": "500",
                },
            )

        # Fallback
        return await call_next(request)
