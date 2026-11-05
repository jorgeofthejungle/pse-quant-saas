"""
pse_quant/api/routes/watchlist.py — Authenticated Member Watchlist Management
Enables logged-in members to retrieve, add, update, and remove watchlisted stocks
with target Margin of Safety (MoS) alert thresholds.
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_db_session
from pse_quant.db.models import User
from pse_quant.services.customer_service import CustomerService
from pse_quant.api.auth import get_current_user
from pse_quant.api.schemas import WatchlistAddRequest, WatchlistItemResponse

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def get_db():
    with get_db_session() as session:
        yield session


@router.get("", response_model=list[WatchlistItemResponse], summary="Get current member watchlist")
def get_member_watchlist(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the authenticated member's personal watchlist items enriched with
    current prices, intrinsic valuations, Margin of Safety (MoS) percentages,
    and alert trigger status.
    """
    return CustomerService.get_customer_watchlist(session=db, user_id=current_user.id)


@router.post("", summary="Add or update a stock in member watchlist")
def add_to_member_watchlist(
    req: WatchlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Adds or updates a stock in the authenticated member's personal watchlist,
    assigning a custom Margin of Safety target cushion and optional notes.
    """
    try:
        item = CustomerService.add_to_watchlist(
            session=db,
            user_id=current_user.id,
            ticker=req.ticker,
            target_mos_pct=req.target_mos_pct,
            notes=req.notes,
        )
        return {
            "status": "success",
            "ticker": item.ticker,
            "target_mos_pct": item.target_mos_pct,
            "notes": item.notes,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{ticker}", summary="Remove a stock from member watchlist")
def remove_from_member_watchlist(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Removes a stock from the authenticated member's personal watchlist.
    """
    clean_ticker = ticker.upper().strip()
    removed = CustomerService.remove_from_watchlist(session=db, user_id=current_user.id, ticker=clean_ticker)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock '{clean_ticker}' was not found in your watchlist.",
        )
    return {"status": "success", "removed": clean_ticker}
