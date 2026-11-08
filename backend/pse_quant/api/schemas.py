"""
pse_quant/api/schemas.py — Pydantic Schemas for Customer & Stock Data API
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ── Customer Schemas ──────────────────────────────────────────

class CustomerSignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="Customer email address")
    name: Optional[str] = Field(None, max_length=150, description="Customer full name")
    tier: str = Field("free", description="Subscription tier: free or paid")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean:
            raise ValueError("Invalid email format.")
        return clean

    @field_validator("tier")
    @classmethod
    def clean_tier(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in ("free", "paid"):
            raise ValueError("Tier must be 'free' or 'paid'.")
        return val


class CustomerResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    tier: str
    status: str
    notification_prefs: Optional[dict[str, Any]] = None
    created_at: str


class SubscriptionUpdateRequest(BaseModel):
    plan: str = Field(..., description="monthly, annual, lifetime, on_demand, or free")
    status: str = Field("active", description="active, cancelled, or suspended")
    amount_php: Optional[float] = Field(None, ge=0.0)

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in ("free", "monthly", "annual", "lifetime", "on_demand"):
            raise ValueError("Plan must be 'free', 'monthly', 'annual', 'lifetime', or 'on_demand'.")
        return val

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in ("active", "cancelled", "suspended"):
            raise ValueError("Status must be 'active', 'cancelled', or 'suspended'.")
        return val


class WatchlistAddRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=15, description="PSE Ticker Symbol, e.g. AREIT")
    target_mos_pct: float = Field(20.0, ge=-100.0, le=200.0, description="Target Margin of Safety threshold percentage")
    notes: Optional[str] = Field(None, max_length=500, description="Personal investment rationale or notes")

    @field_validator("ticker")
    @classmethod
    def clean_ticker(cls, v: str) -> str:
        clean = v.strip().upper()
        if not clean:
            raise ValueError("Ticker symbol cannot be empty.")
        return clean


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


# ── Outcome-as-a-Service (On-Demand PWYC) Schemas ─────────────

class OnDemandCheckoutRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="Customer email address")
    name: Optional[str] = Field(None, max_length=150, description="Customer name")
    amount_php: float = Field(
        249.0,
        ge=49.0,
        le=100_000.0,
        description="Pay-What-You-Can (PWYC) contribution in PHP (minimum ₱49 floor to cover data/server costs)",
    )
    payment_method: str = Field("gcash", description="Payment method: gcash, maya, card")
    investor_goal: Optional[str] = Field(
        "all",
        pattern="^(all|dividend|value|growth)$",
        description="Investor goal preference: all, dividend, value, or growth",
    )
    hype_check_ticker: Optional[str] = Field(
        None,
        max_length=20,
        description="Optional stock ticker seen in Facebook groups/forums for instant Hype Check",
    )
    starting_capital_php: Optional[float] = Field(
        10_000.0,
        ge=1_000.0,
        le=100_000_000.0,
        description="Optional reference capital in PHP",
    )

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean:
            raise ValueError("Invalid email format.")
        return clean


class OnDemandCheckoutResponse(BaseModel):
    status: str
    email: str
    tier: str
    plan: str
    unlocked: bool
    amount_paid_php: Optional[float] = None
    pwyc_impact_note: Optional[str] = None
    download_url: str
    message: str


class VerifyAccessRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="Customer email address to verify")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean:
            raise ValueError("Invalid email format.")
        return clean


class VerifyAccessResponse(BaseModel):
    has_access: bool
    email: str
    tier: Optional[str] = None
    name: Optional[str] = None
    message: str


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



# ── Background Task Schemas ───────────────────────────────────

class TaskEnqueueRequest(BaseModel):
    task_name: str = Field(..., min_length=2, max_length=128, description="Registered task name e.g. 'etl.sync_all'")
    payload: Optional[dict[str, Any]] = Field(default_factory=dict, description="Task execution arguments")
    priority: Optional[int] = Field(5, ge=1, le=10, description="Task priority (1-10, higher processed first)")
    max_retries: Optional[int] = Field(3, ge=0, le=10, description="Maximum retry attempts on failure")


class TaskEnqueueResponse(BaseModel):
    task_id: str
    task_name: str
    status: str
    priority: int
    max_retries: int
    created_at: str
