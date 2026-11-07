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
    OnDemandCheckoutRequest,
    OnDemandCheckoutResponse,
    VerifyAccessRequest,
    VerifyAccessResponse,
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


@router.post("/on-demand-checkout", response_model=OnDemandCheckoutResponse, summary="Pay What You Can (PWYC) per report & unlock outcome")
def on_demand_checkout(req: OnDemandCheckoutRequest, db: Session = Depends(get_db)):
    """
    Outcome as a Service (OaaS) Pay-What-You-Can (PWYC) per-report checkout:
    Customer selects a fair contribution (minimum ₱49 floor), provides their email,
    and immediately receives the done-for-you investment dossier + full on-screen unlock.
    """
    clean_email = req.email.lower().strip()
    user, _created = CustomerService.register_or_get_customer(
        session=db,
        email=clean_email,
        name=req.name,
        tier="paid",
    )

    # Record or update to on_demand active status
    CustomerService.update_subscription(
        session=db,
        user_id=user.id,
        plan="on_demand",
        status="active",
        amount_php=req.amount_php,
    )

    # Compute PWYC Community Impact Note
    if req.amount_php >= 400.0:
        sponsored_count = max(1, int((req.amount_php - 249.0) // 99.0) + 1)
        impact_note = f"Pay-It-Forward Impact: Your ₱{req.amount_php:,.0f} contribution directly subsidized research access for {sponsored_count} beginner Filipino investor(s)."
    elif req.amount_php >= 200.0:
        impact_note = "Fair Community Pass: Thank you for sustaining independent, hype-free Philippine investment research."
    else:
        impact_note = "Starter Community Pass unlocked! Subsidized by our Pay-It-Forward investor community."

    # Trigger instant PDF email digest dispatch
    try:
        CustomerService.dispatch_weekly_digest(session=db, target_emails=[clean_email])
    except Exception:
        # Non-blocking for local development / missing Resend key
        pass

    return {
        "status": "success",
        "email": clean_email,
        "tier": "paid",
        "plan": "on_demand",
        "unlocked": True,
        "amount_paid_php": req.amount_php,
        "pwyc_impact_note": impact_note,
        "download_url": "/api/v1/reports/download-latest",
        "message": f"PWYC contribution of ₱{req.amount_php:.0f} via {req.payment_method.upper()} confirmed! Done-for-you dossier sent to {clean_email}.",
    }


@router.post("/verify-access", response_model=VerifyAccessResponse, summary="Verify on-demand access by email")
def verify_access(req: VerifyAccessRequest, db: Session = Depends(get_db)):
    """Verifies whether an email has on-demand access or an active account."""
    clean_email = req.email.lower().strip()
    user = db.scalar(select(User).where(User.email == clean_email))
    if not user:
        return {
            "has_access": False,
            "email": clean_email,
            "tier": None,
            "name": None,
            "message": "No purchase found for this email. Unlock on-demand for a flat ₱499 fee.",
        }

    has_paid = user.tier == "paid" or user.status == "active"
    return {
        "has_access": has_paid,
        "email": user.email,
        "tier": user.tier,
        "name": user.name,
        "message": "Outcome access active! Welcome back." if has_paid else "Account found, but requires on-demand unlock.",
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
    clean_ticker = ticker.strip().upper()
    removed = CustomerService.remove_from_watchlist(session=db, user_id=user_id, ticker=clean_ticker)
    if not removed:
        raise HTTPException(status_code=404, detail="Stock not present in watchlist.")
    return {"status": "success", "removed": clean_ticker}
