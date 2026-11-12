"""
pse_quant/api/main.py — FastAPI Central Server Application
Authoritative backend decision engine for StockPilot PH.
Serves:
  - Customer Facing Dashboard (/api/v1/stocks, /api/v1/customers)
  - Admin Facing Dashboard (/api/v1/admin)
  - Payment Webhook Ingestion (/api/v1/payments)
  - Rate Limiting Diagnostics (/api/v1/rate-limit)
  - Distributed Task Queue (/api/v1/tasks)
"""

from __future__ import annotations
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from pse_quant.db.connection import init_db
from pse_quant.api.limiter import limiter, custom_rate_limit_handler
from pse_quant.api.rate_limiting import TokenBucketMiddleware
from pse_quant.telemetry import TracingMiddleware
from pse_quant.chaos import ChaosMiddleware
from pse_quant.api.routes import (
    stocks,
    customers,
    admin,
    auth,
    watchlist,
    reports,
    oaas,
    payments,
    rate_limit,
    notifications,
    tasks,
    stream,
    search,
    snapshots,
    chaos,
)

logger = logging.getLogger("pse_quant.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database schema, background worker swarm, and warm resources on startup."""
    logger.info("Initializing database schema...")
    init_db()

    enable_workers = os.getenv("ENABLE_TASK_WORKERS", "false").lower() in ("true", "1", "yes")
    if enable_workers:
        logger.info("Starting background task worker swarm...")
        from pse_quant.tasks import global_worker_swarm
        global_worker_swarm.start_all()

    logger.info("StockPilot PH Backend API ready.")
    yield

    if enable_workers:
        logger.info("Shutting down background task worker swarm...")
        from pse_quant.tasks import global_worker_swarm
        global_worker_swarm.stop_all()


app = FastAPI(
    title="StockPilot PH — Quant Decision Server",
    description=(
        "Authoritative backend service for Philippine equity quantitative screening, "
        "deterministic 3-layer scoring, risk-adjusted Margin of Safety valuations, "
        "customer lifecycle management, and email digest distribution."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ── Rate Limiting Layers ──────────────────────────────────────
# Layer 1: SlowAPI (Per-route burst protection)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

# Layer 2: Institutional Token Bucket Middleware (Multi-tier quota & RFC headers)
_token_bucket_enabled = os.getenv("ENABLE_TOKEN_BUCKET_RATE_LIMIT", "true").lower() in ("true", "1", "yes")
app.add_middleware(TokenBucketMiddleware, enabled=_token_bucket_enabled)

# Layer 3: Distributed Tracing & Correlation ID Context Propagation
app.add_middleware(TracingMiddleware)

# Layer 4: Controlled Chaos Engineering & Fault Injection Middleware
app.add_middleware(ChaosMiddleware)


# ── Dynamic CORS Configuration ────────────────────────────────
_raw_cors = os.getenv("CORS_ORIGINS", "")
_allowed_origins = [
    origin.strip() for origin in _raw_cors.split(",") if origin.strip()
] if _raw_cors else [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# ── Security Headers Middleware ───────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Injects defensive HTTP security headers into every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ── Global Exception Handler ──────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Prevents stack traces and sensitive server internals from leaking to clients."""
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "A server error occurred while processing the request.",
            "path": request.url.path,
        },
    )


# Mount API Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(watchlist.router, prefix="/api/v1")
app.include_router(stocks.router, prefix="/api/v1")
app.include_router(customers.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(oaas.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(rate_limit.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(stream.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(snapshots.router, prefix="/api/v1")
app.include_router(chaos.router, prefix="/api/v1")


@app.get("/health", tags=["system"])
@app.get("/api/v1/health", tags=["system"])
def health_check():
    """Server heartbeat and status check."""
    return {
        "status": "healthy",
        "service": "StockPilot PH Quant Decision Server",
        "version": "2.0.0",
    }
