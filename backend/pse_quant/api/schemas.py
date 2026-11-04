"""
pse_quant/api/schemas.py — Pydantic Schemas for Customer & Stock Data API
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Customer Schemas ──────────────────────────────────────────

class CustomerSignupRequest(BaseModel):
    email: str = Field(..., description="Customer email address")
    name: Optional[str] = Field(None, description="Customer full name")
    tier: str = Field("free", description="Subscription tier: free or paid")


class CustomerResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    tier: str
    status: str
    notification_prefs: Optional[dict[str, Any]] = None
    created_at: str


class SubscriptionUpdateRequest(BaseModel):
    plan: str = Field(..., description="monthly, annual, lifetime, or free")
    status: str = Field("active", description="active or cancelled")
    amount_php: Optional[float] = None


class WatchlistAddRequest(BaseModel):
    ticker: str = Field(..., description="PSE Ticker Symbol, e.g. AREIT")
    target_mos_pct: float = Field(20.0, description="Target Margin of Safety threshold percentage")
    notes: Optional[str] = Field(None, description="Personal investment rationale or notes")


class WatchlistItemResponse(BaseModel):
    ticker: str
    name: str
    sector: str
    current_price: Optional[float] = None
    intrinsic_value: Optional[float] = None
    current_mos_pct: Optional[float] = None
    target_mos_pct: float
    is_triggered: bool
    notes: Optional[str] = None
    added_at: str


# ── Stock Data Schemas ────────────────────────────────────────

class StockRankingSchema(BaseModel):
    rank: int
    ticker: str
    name: str
    sector: str
    score: float
    confidence: float
    category: str
    current_price: Optional[float] = None
    intrinsic_value: Optional[float] = None
    mos_pct: Optional[float] = None
    dividend_yield: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    de_ratio: Optional[float] = None


class StockProfileResponse(BaseModel):
    ticker: str
    name: str
    sector: str
    is_bank: bool
    is_reit: bool
    status: str
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    trade_date: Optional[str] = None
    score: Optional[float] = None
    rank: Optional[int] = None
    category: Optional[str] = None
    confidence: Optional[float] = None
    intrinsic_value: Optional[float] = None
    mos_pct: Optional[float] = None
    mos_target_price: Optional[float] = None
    valuation: dict[str, Any]
    layers: dict[str, Any]
    historical_financials: list[dict[str, Any]]


class MacroBenchmarkResponse(BaseModel):
    ph_10y_bond_rate: float
    equity_risk_premium: float
    base_required_return: float
    conglomerate_holding_discount: float
    special_dividend_cap: float


# ── Admin Schemas ─────────────────────────────────────────────

class FinancialOverrideRequest(BaseModel):
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    equity: Optional[float] = None
    total_debt: Optional[float] = None
    eps: Optional[float] = None
    dps: Optional[float] = None
    operating_cf: Optional[float] = None
    capex: Optional[float] = None


class AdminMetricsResponse(BaseModel):
    total_customers: int
    paid_subscribers: int
    free_members: int
    mrr_php: float
    active_watchlists: int
    total_emails_delivered: int


class PipelineTriggerResponse(BaseModel):
    status: str
    run_id: Optional[int] = None
    message: str
    summary: Optional[dict[str, Any]] = None
