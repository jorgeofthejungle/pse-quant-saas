"""
pse_quant/scraper/resilience/dead_letter.py — Dead-Letter Queue (DLQ) Ledger Service
====================================================================================
Isolates corrupt, malformed, or poisoned scraper payloads into a durable database
ledger so the broader batch ETL can continue without crashing.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from pse_quant.db.models import ScraperDeadLetter

logger = logging.getLogger("pse_quant.scraper.dead_letter")


class DeadLetterService:
    """Manages recording, retrieval, and triage of scraper dead-letter records."""

    @staticmethod
    def record_dead_letter(
        session: Session,
        ticker: str,
        stage: str,
        source_url: str,
        error_reason: str,
        payload_preview: Optional[str] = None,
        attempts: int = 1,
    ) -> ScraperDeadLetter:
        """
        Inserts a new poison-pill record into the dead-letter queue.
        Commits immediately to guarantee persistence even if outer pipeline fails.
        """
        clean_ticker = (ticker or "UNKNOWN").upper().strip()
        trimmed_preview = (payload_preview[:2000] if payload_preview else None)

        dead_letter = ScraperDeadLetter(
            ticker=clean_ticker,
            stage=stage,
            source_url=source_url,
            error_reason=error_reason[:1000],
            payload_preview=trimmed_preview,
            attempts=attempts,
            status="pending",
        )
        session.add(dead_letter)
        session.commit()
        session.refresh(dead_letter)

        logger.warning(
            f"Dead-letter recorded for [{clean_ticker}] at stage '{stage}': {error_reason}"
        )
        return dead_letter

    @staticmethod
    def list_dead_letters(
        session: Session,
        status: str = "pending",
        limit: int = 50,
    ) -> List[ScraperDeadLetter]:
        """Queries recent dead letters for administrative review."""
        stmt = (
            select(ScraperDeadLetter)
            .where(ScraperDeadLetter.status == status)
            .order_by(desc(ScraperDeadLetter.created_at))
            .limit(limit)
        )
        return list(session.scalars(stmt).all())

    @staticmethod
    def resolve_dead_letter(
        session: Session,
        dead_letter_id: int,
        resolution: str = "reprocessed",  # reprocessed, ignored
    ) -> Optional[ScraperDeadLetter]:
        """Marks a dead letter as resolved or discarded."""
        dl = session.get(ScraperDeadLetter, dead_letter_id)
        if dl:
            dl.status = resolution
            dl.resolved_at = datetime.now(timezone.utc)
            session.commit()
        return dl
