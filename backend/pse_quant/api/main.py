"""
pse_quant/api/main.py — FastAPI Central Server Application
Authoritative backend decision engine for StockPilot PH.
Serves:
  - Customer Facing Dashboard (/api/v1/stocks, /api/v1/customers)
  - Admin Facing Dashboard (/api/v1/admin)
"""

from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pse_quant.db.connection import init_db
from pse_quant.api.routes import stocks, customers, admin

logger = logging.getLogger("pse_quant.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database schema and warm resources on startup."""
    logger.info("Initializing database schema...")
    init_db()
    logger.info("StockPilot PH Backend API ready.")
    yield


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

# Enable CORS for decoupled frontends (Customer dashboard & Admin dashboard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "*",  # Permissive in development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(stocks.router, prefix="/api/v1")
app.include_router(customers.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health", tags=["system"])
@app.get("/api/v1/health", tags=["system"])
def health_check():
    """Server heartbeat and status check."""
    return {
        "status": "healthy",
        "service": "StockPilot PH Quant Decision Server",
        "version": "2.0.0",
    }
