"""
pse_quant/api/routes/notifications.py — In-App Notifications & Alert Ledger Endpoints
====================================================================================
Exposes personal in-app alerts, unread counts, and read state management for members.
"""

from __future__ import annotations
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, update, func, desc

from pse_quant.db.connection import get_db_session
from pse_quant.db.models import User, UserNotification
from pse_quant.api.auth import get_current_user
from pse_quant.events.bus import global_event_bus, QuantValuationEvent

logger = logging.getLogger("pse_quant.api.notifications")

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_db():
    with get_db_session() as session:
        yield session


class SimulateValuationEventRequest(BaseModel):
    ticker: str = Field(..., json_schema_extra={"example": "AREIT"})
    price: float = Field(..., json_schema_extra={"example": 32.50})
    intrinsic_value: float = Field(..., json_schema_extra={"example": 46.84})
    mos_pct: float = Field(..., json_schema_extra={"example": 30.6})
    score: float = Field(default=82.0, json_schema_extra={"example": 82.0})
    category: str = Field(default="Passive Income Champion", json_schema_extra={"example": "Passive Income Champion"})


@router.get("", summary="List current member notifications & unread count")
def list_notifications(
    unread_only: bool = Query(False, description="Filter for unread notifications only"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves authenticated member's alerts and badge unread count."""
    stmt = (
        select(UserNotification)
        .where(UserNotification.user_id == current_user.id)
        .order_by(desc(UserNotification.created_at))
    )
    if unread_only:
        stmt = stmt.where(UserNotification.is_read.is_(False))

    items = db.scalars(stmt.limit(limit)).all()

    unread_count = db.scalar(
        select(func.count(UserNotification.id)).where(
            UserNotification.user_id == current_user.id,
            UserNotification.is_read.is_(False),
        )
    ) or 0

    return {
        "notifications": [
            {
                "id": n.id,
                "ticker": n.ticker,
                "alert_type": n.alert_type,
                "severity": n.severity,
                "title": n.title,
                "message": n.message,
                "metadata": n.metadata_json,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in items
        ],
        "unread_count": unread_count,
        "total": len(items),
    }


@router.patch("/{notification_id}/read", summary="Mark a single notification as read")
def mark_notification_read(
    notification_id: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marks an alert notification as read."""
    notification = db.scalar(
        select(UserNotification).where(
            UserNotification.id == notification_id,
            UserNotification.user_id == current_user.id,
        )
    )
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification ID {notification_id} not found.",
        )

    notification.is_read = True
    db.commit()
    return {"status": "success", "id": notification.id, "is_read": True}


@router.post("/mark-all-read", summary="Mark all member notifications as read")
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marks all pending unread notifications as read for the current user."""
    result = db.execute(
        update(UserNotification)
        .where(
            UserNotification.user_id == current_user.id,
            UserNotification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    db.commit()
    return {"status": "success", "marked_read_count": result.rowcount}


@router.post("/simulate-event", summary="Simulate domain event to test pub-sub fanout")
def simulate_domain_event(
    req: SimulateValuationEventRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Simulation utility for workbench testing.
    Publishes a QuantValuationEvent to the global event bus.
    """
    event = QuantValuationEvent(
        ticker=req.ticker.upper().strip(),
        price=req.price,
        intrinsic_value=req.intrinsic_value,
        mos_pct=req.mos_pct,
        score=req.score,
        category=req.category,
    )
    invoked = global_event_bus.publish(event)
    return {
        "status": "published",
        "event_id": event.event_id,
        "topic": event.topic,
        "handlers_invoked": invoked,
    }
