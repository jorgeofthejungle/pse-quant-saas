"""
pse_quant/events/fanout.py — Event-Driven Alert Fanout & Cooldown Engine
========================================================================
Fans out domain events (QuantValuationEvent, MarketTickEvent) to interested
customer watchlists with intelligent deduplication cooldowns and in-app persistence.
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_db_session
from pse_quant.db.models import User, Watchlist, UserNotification, EmailLog
from pse_quant.events.bus import QuantValuationEvent

logger = logging.getLogger("pse_quant.events.fanout")

DEFAULT_COOLDOWN_HOURS = 4.0


class AlertFanoutService:
    """Evaluates domain events against registered watchlists with deduplication."""

    @classmethod
    def handle_quant_valuation(
        cls,
        event: QuantValuationEvent,
        session: Optional[Session] = None,
        cooldown_hours: float = DEFAULT_COOLDOWN_HOURS,
    ) -> List[UserNotification]:
        """
        Receives a QuantValuationEvent, finds interested investors,
        applies threshold filtering & cooldown checks, and creates notifications.
        """
        if session is not None:
            return cls._process_fanout(event, session, cooldown_hours)

        with get_db_session() as new_session:
            return cls._process_fanout(event, new_session, cooldown_hours)

    @classmethod
    def _process_fanout(
        cls,
        event: QuantValuationEvent,
        session: Session,
        cooldown_hours: float,
    ) -> List[UserNotification]:
        ticker = event.ticker.upper().strip()
        now = datetime.now(timezone.utc)
        cooldown_cutoff = now - timedelta(hours=cooldown_hours)

        # 1. Query all users watching this specific ticker
        watchlist_items = session.scalars(
            select(Watchlist).where(Watchlist.ticker == ticker)
        ).all()

        if not watchlist_items:
            logger.debug(f"Fan-out skipped: Zero investors watching ticker '{ticker}'")
            return []

        generated_notifications: List[UserNotification] = []

        for item in watchlist_items:
            user = session.get(User, item.user_id)
            if not user or user.status != "active":
                continue

            # 2. Check notification preferences
            prefs = user.notification_prefs or {}
            if not prefs.get("price_alerts", True):
                continue

            # 3. Check Target Margin of Safety threshold
            target_mos = float(item.target_mos_pct if item.target_mos_pct is not None else 20.0)
            if event.mos_pct < target_mos:
                continue

            # 4. Anti-Fatigue Deduplication Cooldown Check
            # Prevent spamming the investor if price oscillates around threshold
            existing_recent = session.scalar(
                select(UserNotification).where(
                    and_(
                        UserNotification.user_id == user.id,
                        UserNotification.ticker == ticker,
                        UserNotification.alert_type == "MOS_BREACH",
                        UserNotification.created_at >= cooldown_cutoff,
                    )
                )
            )

            if existing_recent is not None:
                logger.info(
                    f"Alert suppressed by cooldown ({cooldown_hours}h) for user {user.id} on ticker {ticker}. "
                    f"Last alert created at {existing_recent.created_at}."
                )
                continue

            # 5. Build and Persist In-App Notification
            title = f"Margin of Safety Alert: {ticker} reached {event.mos_pct:.1f}% MoS"
            message = (
                f"{ticker} is currently trading at ₱{event.price:.2f} vs. Intrinsic Value ₱{event.intrinsic_value:.2f}, "
                f"exceeding your target Margin of Safety of {target_mos:.0f}%."
            )
            meta = {
                "ticker": ticker,
                "current_price": event.price,
                "intrinsic_value": event.intrinsic_value,
                "mos_pct": event.mos_pct,
                "target_mos_pct": target_mos,
                "score": event.score,
                "category": event.category,
            }

            notification = UserNotification(
                user_id=user.id,
                ticker=ticker,
                alert_type="MOS_BREACH",
                severity="opportunity",
                title=title,
                message=message,
                metadata_json=meta,
                is_read=False,
            )
            session.add(notification)

            # Optional: Mirror to EmailLog for email digest delivery
            if prefs.get("email_alerts", False):
                email_log = EmailLog(
                    recipient_email=user.email,
                    subject=f"[StockPilot Alert] {title}",
                    email_type="mos_alert",
                    status="queued",
                )
                session.add(email_log)

            generated_notifications.append(notification)
            logger.info(f"Generated MoS alert notification for user {user.email} on {ticker} (MoS: {event.mos_pct:.1f}%)")

        if generated_notifications:
            session.commit()
            for n in generated_notifications:
                session.refresh(n)
                # Broadcast real-time SSE notification
                try:
                    from pse_quant.streaming.hub import stream_hub
                    stream_hub.broadcast(
                        channel=f"alerts:user:{n.user_id}",
                        event_type="alert_notification",
                        data={
                            "id": n.id,
                            "ticker": n.ticker,
                            "title": n.title,
                            "message": n.message,
                            "severity": n.severity,
                            "metadata": n.metadata_json,
                            "created_at": n.created_at.isoformat() if n.created_at else None,
                        },
                    )
                except Exception as e:
                    logger.warning("Failed to broadcast SSE alert for user %d: %s", n.user_id, e)

        return generated_notifications
