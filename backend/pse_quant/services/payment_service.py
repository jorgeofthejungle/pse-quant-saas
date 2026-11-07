"""
pse_quant/services/payment_service.py — Asynchronous Payment & Idempotency Service
Handles HMAC SHA-256 signature verification, idempotent event recording,
and background fulfillment for payment webhooks (PayMongo, Maya, Stripe).
"""

from __future__ import annotations
import hmac
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_db_session
from pse_quant.db.models import PaymentEvent, User, Subscription
from pse_quant.services.customer_service import CustomerService

logger = logging.getLogger("pse_quant.services.payment")

DEFAULT_TEST_SECRET = "whsec_test_secret_key_12345"


class PaymentService:
    """Institutional-grade Payment Webhook Verification & Idempotent Fulfillment Engine."""

    # ── 1. Cryptographic HMAC Signature Verification ─────────

    @staticmethod
    def verify_webhook_signature(
        raw_body: bytes,
        signature_header: str | None,
        secret_key: str | None = None,
    ) -> bool:
        """
        Validates HMAC SHA-256 webhook signatures using constant-time comparison
        to eliminate timing side-channel attacks.

        Supports:
          1. PayMongo format: "t=1620000000,te=<test_sig>,li=<live_sig>"
          2. Standard digest format: "sha256=<hex_digest>" or raw "<hex_digest>"
        """
        if not signature_header:
            logger.warning("Payment webhook missing signature header.")
            return False

        secret = secret_key or os.getenv("PAYMONGO_WEBHOOK_SECRET") or os.getenv("PAYMENT_WEBHOOK_SECRET") or DEFAULT_TEST_SECRET
        secret_bytes = secret.encode("utf-8")

        # PayMongo signature header scheme
        if "t=" in signature_header:
            parts = dict(
                item.split("=", 1) for item in signature_header.split(",") if "=" in item
            )
            timestamp = parts.get("t")
            test_sig = parts.get("te")
            live_sig = parts.get("li")

            if not timestamp or (not test_sig and not live_sig):
                logger.warning(f"Malformed PayMongo signature header: {signature_header}")
                return False

            # PayMongo signature payload: f"{timestamp}.{raw_body.decode('utf-8')}"
            signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
            computed_digest = hmac.new(secret_bytes, signed_payload, hashlib.sha256).hexdigest()

            # Constant-time comparison against test or live signature
            valid = False
            if test_sig and hmac.compare_digest(computed_digest, test_sig):
                valid = True
            elif live_sig and hmac.compare_digest(computed_digest, live_sig):
                valid = True

            if not valid:
                logger.warning("PayMongo signature mismatch.")
            return valid

        # Standard HMAC SHA-256 header (e.g. "sha256=<hex>" or plain hex)
        expected_sig = signature_header.replace("sha256=", "").strip()
        computed_digest = hmac.new(secret_bytes, raw_body, hashlib.sha256).hexdigest()

        is_valid = hmac.compare_digest(computed_digest, expected_sig)
        if not is_valid:
            logger.warning("Webhook HMAC SHA-256 digest mismatch.")
        return is_valid

    # ── 2. Payload Normalization ──────────────────────────────

    @staticmethod
    def parse_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """
        Normalizes polymorphic gateway payloads (PayMongo, Maya, generic)
        into a consistent event dictionary.
        """
        # PayMongo structure: { "data": { "id": "evt_...", "type": "event", "attributes": { "type": "payment.paid", ... } } }
        if "data" in payload and isinstance(payload["data"], dict):
            d = payload["data"]
            event_id = d.get("id", f"evt_{hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]}")
            attrs = d.get("attributes", {})
            event_type = attrs.get("type", "payment.paid")
            event_data = attrs.get("data", {})
            data_attrs = event_data.get("attributes", {}) if isinstance(event_data, dict) else {}

            amount_centavos = data_attrs.get("amount", 0)
            amount_php = float(amount_centavos) / 100.0 if amount_centavos else 0.0

            billing = data_attrs.get("billing", {}) or {}
            customer_email = billing.get("email") or data_attrs.get("customer_email")
            idempotency_key = data_attrs.get("idempotency_key") or event_id

            return {
                "event_id": str(event_id),
                "event_type": str(event_type),
                "amount_php": amount_php,
                "customer_email": customer_email.lower().strip() if customer_email else None,
                "idempotency_key": str(idempotency_key),
                "raw_attributes": attrs,
            }

        # Flat / Generic structure
        event_id = str(payload.get("event_id") or payload.get("id") or f"evt_{hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]}")
        event_type = str(payload.get("event_type") or payload.get("type") or "payment.paid")
        amount_php = float(payload.get("amount_php") or payload.get("amount") or 0.0)
        customer_email = payload.get("customer_email") or payload.get("email")
        idempotency_key = str(payload.get("idempotency_key") or event_id)

        return {
            "event_id": event_id,
            "event_type": event_type,
            "amount_php": amount_php,
            "customer_email": customer_email.lower().strip() if customer_email else None,
            "idempotency_key": idempotency_key,
            "raw_attributes": payload,
        }

    # ── 3. Idempotent Event Recording ─────────────────────────

    @staticmethod
    def record_and_claim_event(
        session: Session,
        provider: str,
        event_id: str,
        event_type: str,
        amount_php: float,
        customer_email: str | None,
        payload_json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[PaymentEvent, bool]:
        """
        Atomically records an inbound payment event.
        Guarantees that duplicate deliveries of the same event return (event, False),
        preventing duplicate fulfillment execution.

        Returns:
            tuple[PaymentEvent, bool]: (event_record, is_newly_claimed)
        """
        # Check by provider + event_id
        existing = session.scalar(
            select(PaymentEvent).where(
                PaymentEvent.provider == provider,
                PaymentEvent.event_id == event_id,
            )
        )

        if existing:
            logger.info(
                f"Idempotent duplicate detected for {provider} event '{event_id}' "
                f"(current status: {existing.status}). Skipping fulfillment."
            )
            return existing, False

        # Check by idempotency_key if provided
        if idempotency_key:
            existing_key = session.scalar(
                select(PaymentEvent).where(
                    PaymentEvent.provider == provider,
                    PaymentEvent.idempotency_key == idempotency_key,
                )
            )
            if existing_key:
                logger.info(
                    f"Idempotent duplicate detected for {provider} key '{idempotency_key}' "
                    f"(event '{existing_key.event_id}'). Skipping fulfillment."
                )
                return existing_key, False

        # Create new pending event
        new_event = PaymentEvent(
            provider=provider,
            event_id=event_id,
            event_type=event_type,
            status="pending",
            amount_php=amount_php,
            customer_email=customer_email,
            idempotency_key=idempotency_key,
            payload_json=payload_json,
        )
        session.add(new_event)
        session.commit()
        session.refresh(new_event)

        logger.info(f"Recorded and claimed new payment event: {provider}::{event_id} (₱{amount_php:,.2f})")
        return new_event, True

    # ── 4. Asynchronous Background Fulfillment Worker ─────────

    @classmethod
    def process_payment_fulfillment(cls, provider: str, event_id: str) -> bool:
        """
        Background task worker that executes order fulfillment:
          1. Provisions user paid status & creates active subscription.
          2. Generates & dispatches the done-for-you PDF research report.
          3. Transitions event status to 'processed' with timestamp.
        """
        with get_db_session() as session:
            event = session.scalar(
                select(PaymentEvent).where(
                    PaymentEvent.provider == provider,
                    PaymentEvent.event_id == event_id,
                )
            )

            if not event:
                logger.error(f"Fulfillment failed: PaymentEvent {provider}::{event_id} not found.")
                return False

            if event.status == "processed":
                logger.info(f"PaymentEvent {provider}::{event_id} already processed. No-op.")
                return True

            try:
                # Only fulfill positive payment events
                if event.event_type in ("payment.paid", "payment_intent.succeeded", "charge.success"):
                    if event.customer_email:
                        # 1. Provision user tier
                        user, _ = CustomerService.register_or_get_customer(
                            session=session,
                            email=event.customer_email,
                            tier="paid",
                        )

                        # 2. Update subscription record
                        CustomerService.update_subscription(
                            session=session,
                            user_id=user.id,
                            plan="on_demand",
                            status="active",
                            amount_php=event.amount_php,
                        )

                        # 3. Dispatch PDF report email asynchronously
                        try:
                            CustomerService.dispatch_weekly_digest(
                                session=session,
                                target_emails=[event.customer_email],
                            )
                        except Exception as email_err:
                            logger.warning(
                                f"Fulfillment email dispatch warning for {event.customer_email}: {email_err}"
                            )

                    event.status = "processed"
                    event.processed_at = datetime.now(timezone.utc)
                    session.commit()
                    logger.info(f"Successfully fulfilled payment {provider}::{event_id} for {event.customer_email}")
                    return True
                else:
                    # Non-paid event (e.g. payment.failed)
                    event.status = "failed"
                    event.error_message = f"Unhandled event type: {event.event_type}"
                    event.processed_at = datetime.now(timezone.utc)
                    session.commit()
                    return False

            except Exception as exc:
                session.rollback()
                logger.exception(f"Exception during fulfillment of {provider}::{event_id}: {exc}")
                event.status = "failed"
                event.error_message = str(exc)
                event.processed_at = datetime.now(timezone.utc)
                session.commit()
                return False
