"""
pse_quant/api/routes/stocks.py — Public & Customer Endpoints for Philippine Equities
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_read_session
from pse_quant.services.stock_service import StockService
from pse_quant.config import (
    PH_RISK_FREE_RATE,
    EQUITY_RISK_PREMIUM,
    CONGLOMERATE_DISCOUNT,
)
from pse_quant.core.validator import SPECIAL_DIVIDEND_YIELD_CAP
from pse_quant.api.schemas import (
    StockProfileResponse,
    MacroBenchmarkResponse,
)

router = APIRouter(prefix="/stocks", tags=["stocks"])


def get_read_db():
    """FastAPI dependency: routes to reader replica pool."""
    with get_read_session() as session:
        yield session


# Alias for backward compatibility and test dependency overrides
get_db = get_read_db


@router.get("", summary="List ranked stocks across portfolios")
def list_stocks(
    portfolio: str = Query("unified", pattern="^(unified|dividend|value)$", description="Portfolio type: unified, dividend, or value"),
    sector: Optional[str] = Query(None, max_length=100, description="Filter by sector name"),
    min_score: Optional[float] = Query(None, ge=0.0, le=100.0, description="Minimum quantitative score (0-100)"),
    min_mos: Optional[float] = Query(None, ge=-100.0, le=200.0, description="Minimum Margin of Safety percentage"),
    limit: Optional[int] = Query(50, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_read_db),
):
    """Returns top ranked equities filtered and sorted by deterministic score (routed to read replica)."""
    clean_sector = sector.strip() if sector else None
    rankings = StockService.get_rankings(
        session=db,
        portfolio_type=portfolio,
        sector=clean_sector,
        min_score=min_score,
        min_mos=min_mos,
        limit=limit,
    )
    return {"portfolio": portfolio, "count": len(rankings), "data": rankings}


@router.get("/bargains", summary="High Margin of Safety opportunities")
def get_bargain_stocks(
    min_mos: float = Query(0.0, ge=-100.0, le=200.0, description="Minimum positive Margin of Safety percentage"),
    db: Session = Depends(get_read_db),
):
    """Returns equities currently trading below mathematical Intrinsic Value (routed to read replica)."""
    bargains = StockService.get_bargain_stocks(session=db, min_mos=min_mos)
    return {"count": len(bargains), "data": bargains}


@router.get("/macro", response_model=MacroBenchmarkResponse, summary="Philippine macro hurdle rates")
def get_macro_benchmarks():
    """Returns official hurdle rates: PH 10Y Bond, Damodaran ERP, and Conglomerate discount."""
    return {
        "ph_10y_bond_rate": PH_RISK_FREE_RATE * 100.0,
        "equity_risk_premium": EQUITY_RISK_PREMIUM * 100.0,
        "base_required_return": (PH_RISK_FREE_RATE + EQUITY_RISK_PREMIUM) * 100.0,
        "conglomerate_holding_discount": CONGLOMERATE_DISCOUNT * 100.0,
        "special_dividend_cap": SPECIAL_DIVIDEND_YIELD_CAP,
    }


@router.get("/{ticker}", response_model=StockProfileResponse, summary="Deep-dive equity profile")
def get_stock_profile(ticker: str, db: Session = Depends(get_read_db)):
    """Retrieves full equity profile, 3-layer factors, valuation models, and 10Y financials (routed to read replica)."""
    clean_ticker = ticker.strip().upper()
    profile = StockService.get_stock_profile(session=db, ticker=clean_ticker)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Stock {clean_ticker} not found.")
    return profile
