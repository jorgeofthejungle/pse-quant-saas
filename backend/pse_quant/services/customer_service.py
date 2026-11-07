"""
pse_quant/services/customer_service.py — Customer Data Service
Handles customer registration, subscriptions, personalized watchlists,
and automated research report / alert email processing.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session

from pse_quant.db.models import User, Subscription, Watchlist, Stock, Price, Score, EmailLog
from pse_quant.reporting.generator import generate_pdf_report
from pse_quant.email.sender import send_weekly_report

logger = logging.getLogger("pse_quant.services.customer")


class CustomerService:
    """Service layer for customer lifecycle, subscriptions, watchlists, and email distribution."""

    # ── Data Collection & Customer Registration ───────────────

    @staticmethod
    def register_or_get_customer(
        session: Session,
        email: str,
        name: str | None = None,
        tier: str = "free",
    ) -> tuple[User, bool]:
        """
        Registers a new customer or retrieves existing customer.
        Returns (user, is_created).
        """
        clean_email = email.lower().strip()
        user = session.scalar(select(User).where(User.email == clean_email))
        created = False

        if not user:
            user = User(
                email=clean_email,
                name=name.strip() if name else None,
                tier=tier,
                status="active",
                notification_prefs={"weekly_report": True, "daily_brief": True, "price_alerts": True},
            )
            session.add(user)
            session.flush()

            # Create default subscription entry
            sub = Subscription(
                user_id=user.id,
                plan="free" if tier == "free" else "monthly",
                status="active",
                amount_php=0.0 if tier == "free" else 499.0,
                current_period_start=datetime.now(timezone.utc),
            )
            session.add(sub)
            session.commit()
            created = True
            logger.info(f"Registered new customer: {clean_email} (tier: {tier})")
        else:
            if name and not user.name:
                user.name = name.strip()
                session.commit()

        return user, created

    @staticmethod
    def update_subscription(
        session: Session,
        user_id: int,
        plan: str,  # free, monthly, annual, lifetime
        status: str = "active",
        amount_php: float | None = None,
    ) -> Subscription:
        """Updates a customer's active subscription tier."""
        user = session.get(User, user_id)
        if not user:
            raise ValueError(f"User ID {user_id} not found.")

        sub = session.scalar(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(desc(Subscription.created_at))
        )

        plan_prices = {
            "free": 0.0,
            "monthly": 499.0,
            "annual": 4990.0,
            "lifetime": 9990.0,
            "on_demand": 499.0,
        }
        price = amount_php if amount_php is not None else plan_prices.get(plan, 499.0)

        if not sub:
            sub = Subscription(
                user_id=user_id,
                plan=plan,
                status=status,
                amount_php=price,
                current_period_start=datetime.now(timezone.utc),
            )
            session.add(sub)
        else:
            sub.plan = plan
            sub.status = status
            sub.amount_php = price
            sub.current_period_start = datetime.now(timezone.utc)

        user.tier = "free" if plan == "free" else "paid"
        session.commit()
        logger.info(f"Updated subscription for user {user_id}: plan={plan}, status={status}")
        return sub

    # ── Watchlist Collection & Processing ─────────────────────

    @staticmethod
    def add_to_watchlist(
        session: Session,
        user_id: int,
        ticker: str,
        target_mos_pct: float = 20.0,
        notes: str | None = None,
    ) -> Watchlist:
        """Adds or updates a stock in the customer's personal watchlist."""
        clean_ticker = ticker.upper().strip()
        stock = session.get(Stock, clean_ticker)
        if not stock:
            raise ValueError(f"Stock {clean_ticker} does not exist.")

        user = session.get(User, user_id)
        if not user:
            raise ValueError(f"User ID {user_id} not found.")

        item = session.scalar(
            select(Watchlist).where(
                Watchlist.user_id == user_id,
                Watchlist.ticker == clean_ticker,
            )
        )
        if not item:
            item = Watchlist(
                user_id=user_id,
                ticker=clean_ticker,
                target_mos_pct=target_mos_pct,
                notes=notes,
            )
            session.add(item)
        else:
            item.target_mos_pct = target_mos_pct
            if notes is not None:
                item.notes = notes

        session.commit()
        logger.info(f"User {user_id} added {clean_ticker} to watchlist (target MoS: {target_mos_pct}%)")
        return item

    @staticmethod
    def remove_from_watchlist(session: Session, user_id: int, ticker: str) -> bool:
        """Removes a stock from customer's personal watchlist."""
        clean_ticker = ticker.upper().strip()
        item = session.scalar(
            select(Watchlist).where(
                Watchlist.user_id == user_id,
                Watchlist.ticker == clean_ticker,
            )
        )
        if item:
            session.delete(item)
            session.commit()
            return True
        return False

    @staticmethod
    def get_customer_watchlist(session: Session, user_id: int) -> list[dict[str, Any]]:
        """
        Retrieves customer's watchlist items with real-time stock valuation and target comparison.
        """
        items = session.scalars(
            select(Watchlist).where(Watchlist.user_id == user_id).order_by(Watchlist.created_at.desc())
        ).all()

        results = []
        for w in items:
            stock = session.get(Stock, w.ticker)
            latest_price = session.scalar(
                select(Price).where(Price.ticker == w.ticker).order_by(desc(Price.trade_date)).limit(1)
            )
            score_row = session.scalar(
                select(Score).where(Score.ticker == w.ticker, Score.portfolio_type == "unified").limit(1)
            )

            current_mos = None
            intrinsic_val = None
            if score_row and score_row.breakdown_json:
                current_mos = score_row.breakdown_json.get("mos_pct")
                intrinsic_val = score_row.breakdown_json.get("intrinsic_value")

            target = w.target_mos_pct or 20.0
            is_triggered = current_mos is not None and current_mos >= target

            results.append({
                "ticker": w.ticker,
                "name": stock.name if stock else w.ticker,
                "sector": stock.sector if stock else "General",
                "current_price": latest_price.close if latest_price else None,
                "intrinsic_value": intrinsic_val,
                "current_mos_pct": current_mos,
                "target_mos_pct": target,
                "is_triggered": is_triggered,
                "notes": w.notes,
                "added_at": w.created_at.isoformat(),
            })

        return results

    # ── Customer Data Processing: Alerts & Email Distribution ──

    @staticmethod
    def evaluate_and_dispatch_alerts(session: Session) -> list[dict[str, Any]]:
        """
        Evaluates active customer watchlists and identifies opportunities where
        current Margin of Safety meets or exceeds customer target.
        Logs to EmailLog.
        """
        all_watchlists = session.scalars(select(Watchlist)).all()
        dispatched_alerts = []

        for item in all_watchlists:
            user = session.get(User, item.user_id)
            if not user or user.status != "active":
                continue

            prefs = user.notification_prefs or {}
            if not prefs.get("price_alerts", True):
                continue

            score_row = session.scalar(
                select(Score).where(Score.ticker == item.ticker, Score.portfolio_type == "unified").limit(1)
            )
            if not score_row or not score_row.breakdown_json:
                continue

            current_mos = score_row.breakdown_json.get("mos_pct")
            target_mos = item.target_mos_pct or 20.0

            if current_mos is not None and current_mos >= target_mos:
                subj = f"[StockPilot Alert] {item.ticker} reached your target MoS of {target_mos:.0f}% (Current: {current_mos:.1f}%)"
                log = EmailLog(
                    recipient_email=user.email,
                    subject=subj,
                    email_type="mos_alert",
                    status="sent",
                    sent_at=datetime.now(timezone.utc),
                )
                session.add(log)
                dispatched_alerts.append({
                    "user_email": user.email,
                    "ticker": item.ticker,
                    "current_mos": current_mos,
                    "target_mos": target_mos,
                })

        session.commit()
        return dispatched_alerts

    @staticmethod
    def dispatch_weekly_digest(
        session: Session,
        target_emails: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Generates executive A4 PDF research report and emails it to all subscribed customers.
        """
        scores = session.scalars(
            select(Score).where(Score.portfolio_type == "unified").order_by(Score.rank.asc())
        ).all()
        top_stocks = [s.breakdown_json for s in scores if s.breakdown_json]

        if not top_stocks:
            return {"status": "skipped", "reason": "No scored stocks available"}

        # Generate report to temp file
        pdf_path = "weekly_research_digest.pdf"
        generate_pdf_report(top_stocks, output_path=pdf_path)

        # Determine recipients
        if target_emails:
            recipients = target_emails
        else:
            active_users = session.scalars(
                select(User).where(User.status == "active")
            ).all()
            recipients = [
                u.email for u in active_users
                if (u.notification_prefs or {}).get("weekly_report", True)
            ]

        results = []
        for email in recipients:
            user_obj = session.scalar(select(User).where(User.email == email))
            name = (user_obj.name if user_obj and user_obj.name else None) or "Investor"
            res = send_weekly_report(
                to=email,
                member_name=name,
                run_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                pdf_path=pdf_path,
                top_stocks=top_stocks,
            )
            log = EmailLog(
                recipient_email=email,
                subject="StockPilot PH Weekly Quantitative Rankings & Valuation Digest",
                email_type="weekly_report",
                status=res.get("status", "sent"),
                resend_id=res.get("id"),
                sent_at=datetime.now(timezone.utc),
            )
            session.add(log)
            results.append({"email": email, "status": res.get("status")})

        session.commit()
        return {
            "status": "completed",
            "recipients_count": len(recipients),
            "results": results,
            "pdf_path": str(pdf_path),
        }

    # ── Admin Intelligence Queries ────────────────────────────

    @staticmethod
    def get_admin_metrics(session: Session) -> dict[str, Any]:
        """Calculates executive SaaS customer metrics for admin dashboard."""
        total_users = session.scalar(select(func.count(User.id))) or 0
        paid_users = session.scalar(select(func.count(User.id)).where(User.tier == "paid")) or 0
        active_watchlists = session.scalar(select(func.count(Watchlist.id))) or 0
        emails_sent = session.scalar(select(func.count(EmailLog.id)).where(EmailLog.status == "sent")) or 0

        # Calculate estimated Monthly Recurring Revenue (MRR) and On-Demand Revenue
        active_subs = session.scalars(
            select(Subscription).where(Subscription.status == "active", Subscription.plan != "free")
        ).all()
        mrr_php = sum(s.amount_php for s in active_subs if s.plan == "monthly")
        mrr_php += sum((s.amount_php / 12.0) for s in active_subs if s.plan == "annual")
        mrr_php += sum((s.amount_php / 24.0) for s in active_subs if s.plan == "lifetime")
        on_demand_revenue_php = sum(s.amount_php for s in active_subs if s.plan == "on_demand")

        return {
            "total_customers": total_users,
            "paid_subscribers": paid_users,
            "free_members": total_users - paid_users,
            "mrr_php": round(mrr_php, 2),
            "on_demand_revenue_php": round(on_demand_revenue_php, 2),
            "active_watchlists": active_watchlists,
            "total_emails_delivered": emails_sent,
        }

    @staticmethod
    def list_customers_admin(
        session: Session,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Lists customers with their active subscriptions and watchlist counts."""
        users = session.scalars(
            select(User).order_by(desc(User.created_at)).offset(skip).limit(limit)
        ).all()

        customer_list = []
        for u in users:
            sub = session.scalar(
                select(Subscription).where(Subscription.user_id == u.id).order_by(desc(Subscription.created_at))
            )
            w_count = session.scalar(
                select(func.count(Watchlist.id)).where(Watchlist.user_id == u.id)
            ) or 0

            customer_list.append({
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "tier": u.tier,
                "status": u.status,
                "plan": sub.plan if sub else "free",
                "sub_status": sub.status if sub else "active",
                "watchlist_count": w_count,
                "created_at": u.created_at.isoformat(),
            })

        return customer_list
