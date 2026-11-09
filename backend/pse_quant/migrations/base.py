"""
pse_quant/migrations/base.py — Abstract Base Class for Zero-Downtime Migrations
PSE Quant SaaS (v2 Rebuild) — Lab 12

Defines the 5-phase Expand-Contract / Parallel-Run lifecycle contract.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict
from sqlalchemy.orm import Session


class MigrationPhase(str, Enum):
    EXPAND = "EXPAND"
    DUAL_WRITE = "DUAL_WRITE"
    BACKFILL = "BACKFILL"
    READ_NEW = "READ_NEW"
    CONTRACT = "CONTRACT"
    COMPLETED = "COMPLETED"


class BaseMigration(ABC):
    """Abstract contract enforcing phased, non-destructive schema evolution."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def expand(self, session: Session) -> None:
        """Phase 1: Adds new column(s) or table(s) non-destructively without locks."""
        pass

    @abstractmethod
    def backfill_batch(self, session: Session, batch_size: int = 100) -> int:
        """
        Phase 3: Backfills historical rows in throttled chunks.
        Returns the number of rows backfilled in this batch.
        """
        pass

    @abstractmethod
    def count_pending_backfill(self, session: Session) -> int:
        """Returns total historical rows remaining to be backfilled."""
        pass

    @abstractmethod
    def verify_parity(self, session: Session) -> Dict[str, Any]:
        """
        Phase 4: Performs 100% mathematical and data parity verification
        between old and new fields before contracting.
        """
        pass

    @abstractmethod
    def contract(self, session: Session) -> None:
        """Phase 5: Drops or decommissions old legacy column(s)."""
        pass
