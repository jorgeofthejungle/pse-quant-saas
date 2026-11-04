"""
pse_quant/api/routes/customers.py — Customer Management & Personalized Watchlists API
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from pse_quant.db.connection import get_db_session
from pse_quant.services.customer_service import CustomerService
from pse_quant.db.models import User
from pse_quant.api.schemas import (
    CustomerSignupRequest,
    CustomerResponse,
    SubscriptionUpdateRequest,
    WatchlistAddRequest,
    WatchlistItemResponse,
)

router = APIRouter(prefix="/customers", tags=["customers"])


def get_db():
    with get_db_session() as session:
        yield session


@router.post("/signup", response_model=CustomerResponse, summary="Register new customer or email lead")
def signup(req: CustomerSignupRequest, db: Session = Depends(get_db)):
    """Registers customer email, provisions free subscription, and creates profile."""
    user, _created = CustomerService.register_or_get_customer(
        session=db,
        email=req.email,
        name=req.name,
        tier=req.tier,
    )
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "tier": user.tier,
        "status": user.status,
        "notification_prefs": user.notification_prefs,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/{identifier}", response_model=CustomerResponse, summary="Get customer profile by ID or email")
def get_customer(identifier: str, db: Session = Depends(get_db)):
    """Retrieves customer record by email address or numeric ID."""
    if identifier.isdigit():
        user = db.get(User, int(identifier))
    else:
        user = db.scalar(select(User).where(User.email == identifier.lower().strip()))

    if not user:
        raise HTTPException(status_code=404, detail="Customer not found.")

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "tier": user.tier,
        "status": user.status,
        "notification_prefs": user.notification_prefs,
        "created_at": user.created_at.isoformat(),
    }


@router.post("/{user_id}/subscription", summary="Update customer subscription plan")
def update_subscription(user_id: int, req: SubscriptionUpdateRequest, db: Session = Depends(get_db)):
    """Modifies customer subscription (free, monthly, annual, lifetime)."""
    try:
        sub = CustomerService.update_subscription(
            session=db,
            user_id=user_id,
            plan=req.plan,
            status=req.status,
            amount_php=req.amount_php,
        )
        return {
            "status": "success",
            "user_id": user_id,
            "plan": sub.plan,
            "sub_status": sub.status,
            "amount_php": sub.amount_php,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{user_id}/watchlist", response_model=list[WatchlistItemResponse], summary="Get customer watchlist")
def get_watchlist(user_id: int, db: Session = Depends(get_db)):
    """Returns customer watchlist items with live prices and Margin of Safety target alerts."""
    return CustomerService.get_customer_watchlist(session=db, user_id=user_id)


@router.post("/{user_id}/watchlist", summary="Add stock to customer watchlist")
def add_to_watchlist(user_id: int, req: WatchlistAddRequest, db: Session = Depends(get_db)):
    """Adds or updates a stock in the customer's watchlist with a target Margin of Safety."""
    try:
        item = CustomerService.add_to_watchlist(
            session=db,
            user_id=user_id,
            ticker=req.ticker,
            target_mos_pct=req.target_mos_pct,
            notes=req.notes,
        )
        return {"status": "success", "ticker": item.ticker, "target_mos_pct": item.target_mos_pct}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_id}/watchlist/{ticker}", summary="Remove stock from customer watchlist")
def remove_from_watchlist(user_id: int, ticker: str, db: Session = Depends(get_db)):
    """Removes a stock from customer's watchlist."""
    removed = CustomerService.remove_from_watchlist(session=db, user_id=user_id, ticker=ticker)
    if not removed:
        raise HTTPException(status_code=404, detail="Stock not present in watchlist.")
    return {"status": "success", "removed": ticker.upper()}
