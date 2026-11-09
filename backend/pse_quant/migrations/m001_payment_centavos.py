"""
pse_quant/migrations/m001_payment_centavos.py — Migration: Payment Centavos
PSE Quant SaaS (v2 Rebuild) — Lab 12

Migrates PaymentEvent from floating-point amount_php to fixed-precision integer
amount_centavos and currency code (PHP) using the 5-phase Expand-Contract pattern.
"""

from __future__ import annotations
import logging
from typing import Dict, Any
from sqlalchemy import text, inspect, select, func
from sqlalchemy.orm import Session

from pse_quant.migrations.base import BaseMigration
from pse_quant.db.models import PaymentEvent

logger = logging.getLogger("pse_quant.migrations.m001")


class PaymentCentavosMigration(BaseMigration):
    name = "m001_payment_centavos"
    description = "Migrate PaymentEvent amount_php (Float) to amount_centavos (Integer) + currency (PHP)"

    def expand(self, session: Session) -> None:
        """Phase 1: Adds amount_centavos and currency columns if they do not exist."""
        inspector = inspect(session.bind)
        cols = {c["name"] for c in inspector.get_columns("payment_events")}

        if "amount_php" not in cols:
            logger.info("Phase 1 EXPAND: Adding legacy column 'amount_php' to payment_events")
            session.execute(text("ALTER TABLE payment_events ADD COLUMN amount_php FLOAT DEFAULT 0.0;"))

        if "amount_centavos" not in cols:
            logger.info("Phase 1 EXPAND: Adding column 'amount_centavos' to payment_events")
            session.execute(text("ALTER TABLE payment_events ADD COLUMN amount_centavos INTEGER;"))

        if "currency" not in cols:
            logger.info("Phase 1 EXPAND: Adding column 'currency' to payment_events")
            session.execute(text("ALTER TABLE payment_events ADD COLUMN currency VARCHAR(3) DEFAULT 'PHP';"))

        session.commit()

    def backfill_batch(self, session: Session, batch_size: int = 100) -> int:
        """Phase 3: Backfills historical rows where amount_centavos is NULL."""
        events = session.scalars(
            select(PaymentEvent)
            .where(PaymentEvent.amount_centavos.is_(None))
            .limit(batch_size)
        ).all()

        if not events:
            return 0

        for ev in events:
            ev.amount_centavos = int(round((ev.amount_php or 0.0) * 100))
            ev.currency = ev.currency or "PHP"

        session.commit()
        logger.info("Phase 3 BACKFILL: Processed %d records", len(events))
        return len(events)

    def count_pending_backfill(self, session: Session) -> int:
        """Returns total historical rows remaining to be backfilled."""
        return session.scalar(
            select(func.count(PaymentEvent.id))
            .where(PaymentEvent.amount_centavos.is_(None))
        ) or 0

    def verify_parity(self, session: Session) -> Dict[str, Any]:
        """
        Phase 4: Performs 100% mathematical audit comparing floating-point PHP
        against fixed-precision centavos across all records.
        """
        inspector = inspect(session.bind)
        cols = {c["name"] for c in inspector.get_columns("payment_events")}
        if "amount_php" not in cols:
            total = session.scalar(select(func.count(PaymentEvent.id))) or 0
            return {
                "total_audited": total,
                "discrepancies_count": 0,
                "is_parity_clean": True,
                "sample_discrepancies": [],
                "note": "Legacy column amount_php has already been contracted.",
            }

        events = session.scalars(select(PaymentEvent)).all()
        discrepancies = []

        for ev in events:
            if ev.amount_centavos is None:
                discrepancies.append({
                    "id": ev.id,
                    "reason": "amount_centavos is NULL (unbackfilled row)",
                    "amount_php": ev.amount_php,
                })
                continue

            expected_centavos = int(round((ev.amount_php or 0.0) * 100))
            if ev.amount_centavos != expected_centavos:
                discrepancies.append({
                    "id": ev.id,
                    "reason": "Mathematical mismatch",
                    "amount_php": ev.amount_php,
                    "amount_centavos": ev.amount_centavos,
                    "expected_centavos": expected_centavos,
                })

        return {
            "total_audited": len(events),
            "discrepancies_count": len(discrepancies),
            "is_parity_clean": len(discrepancies) == 0,
            "sample_discrepancies": discrepancies[:10],
        }

    def contract(self, session: Session) -> None:
        """Phase 5: Drops legacy amount_php column after 100% verified migration."""
        inspector = inspect(session.bind)
        cols = {c["name"] for c in inspector.get_columns("payment_events")}

        if "amount_php" in cols:
            logger.info("Phase 5 CONTRACT: Dropping legacy column 'amount_php' from payment_events")
            try:
                session.execute(text("ALTER TABLE payment_events DROP COLUMN amount_php;"))
                session.commit()
            except Exception as exc:
                logger.warning("Could not execute DROP COLUMN (database dialect might not support it): %s", exc)
