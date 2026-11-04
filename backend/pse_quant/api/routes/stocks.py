"""
pse_quant/api/routes/stocks.py — Public & Customer Endpoints for Philippine Equities
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_db_session
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


def get_db():
    with get_db_session() as session:
        yield session


@router.get("", summary="List ranked stocks across portfolios")
def list_stocks(
    portfolio: str = Query("unified", description="Portfolio type: unified, dividend, or value"),
    sector: Optional[str] = Query(None, description="Filter by sector name"),
    min_score: Optional[float] = Query(None, description="Minimum quantitative score"),
    min_mos: Optional[float] = Query(None, description="Minimum Margin of Safety percentage"),
    limit: Optional[int] = Query(50, description="Max records to return"),
    db: Session = Depends(get_db),
):
    """Returns top ranked equities filtered and sorted by deterministic score."""
    rankings = StockService.get_rankings(
        session=db,
        portfolio_type=portfolio,
        sector=sector,
        min_score=min_score,
        min_mos=min_mos,
        limit=limit,
    )
    return {"portfolio": portfolio, "count": len(rankings), "data": rankings}


@router.get("/bargains", summary="High Margin of Safety opportunities")
def get_bargain_stocks(
    min_mos: float = Query(0.0, description="Minimum positive Margin of Safety percentage"),
    db: Session = Depends(get_db),
):
    """Returns equities currently trading below mathematical Intrinsic Value."""
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
def get_stock_profile(ticker: str, db: Session = Depends(get_db)):
    """Retrieves full equity profile, 3-layer factors, valuation models, and 10Y financials."""
    profile = StockService.get_stock_profile(session=db, ticker=ticker)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Stock {ticker.upper()} not found.")
    return profile
