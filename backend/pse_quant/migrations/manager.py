"""
pse_quant/migrations/manager.py — Zero-Downtime Migration Manager & Orchestrator
PSE Quant SaaS (v2 Rebuild) — Lab 12

Governs the 5-phase Expand-Contract schema lifecycle, enforces mathematical parity gates,
and maintains audit trails in the schema_migrations_ledger table.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from pse_quant.migrations.base import BaseMigration, MigrationPhase
from pse_quant.migrations.m001_payment_centavos import PaymentCentavosMigration
from pse_quant.db.models import SchemaMigrationLedger
from pse_quant.db.connection import get_write_session, get_read_session

logger = logging.getLogger("pse_quant.migrations.manager")


class MigrationManager:
    """Central orchestrator for zero-downtime phased database migrations."""

    def __init__(self):
        self._migrations: Dict[str, BaseMigration] = {}
        # Register default migrations
        self.register(PaymentCentavosMigration())

    def register(self, migration: BaseMigration) -> None:
        """Registers an executable migration instance."""
        self._migrations[migration.name] = migration

    def get_migration(self, name: str) -> Optional[BaseMigration]:
        return self._migrations.get(name)

    def list_migrations(self) -> List[Dict[str, Any]]:
        """Lists all registered migrations with their live ledger state."""
        with get_read_session() as session:
            ledgers = {
                l.migration_name: l
                for l in session.scalars(select(SchemaMigrationLedger)).all()
            }

        result = []
        for name, m in sorted(self._migrations.items()):
            ledger = ledgers.get(name)
            result.append({
                "name": m.name,
                "description": m.description,
                "phase": ledger.phase if ledger else "NOT_STARTED",
                "rows_backfilled": ledger.rows_backfilled if ledger else 0,
                "total_rows": ledger.total_rows if ledger else 0,
                "verified_parity": ledger.verified_parity if ledger else False,
                "started_at": ledger.started_at.isoformat() if ledger and ledger.started_at else None,
                "completed_at": ledger.completed_at.isoformat() if ledger and ledger.completed_at else None,
            })
        return result

    def get_status(self, name: str) -> Dict[str, Any]:
        """Retrieves live phase, pending backfill counts, and verification status for a migration."""
        migration = self.get_migration(name)
        if not migration:
            raise ValueError(f"Migration '{name}' not found.")

        with get_read_session() as session:
            ledger = session.scalar(
                select(SchemaMigrationLedger).where(SchemaMigrationLedger.migration_name == name)
            )
            pending_backfill = migration.count_pending_backfill(session)

        return {
            "name": migration.name,
            "description": migration.description,
            "phase": ledger.phase if ledger else "NOT_STARTED",
            "rows_backfilled": ledger.rows_backfilled if ledger else 0,
            "pending_backfill_rows": pending_backfill,
            "verified_parity": ledger.verified_parity if ledger else False,
            "started_at": ledger.started_at.isoformat() if ledger and ledger.started_at else None,
            "completed_at": ledger.completed_at.isoformat() if ledger and ledger.completed_at else None,
        }

    def advance_phase(
        self,
        name: str,
        target_phase: Optional[MigrationPhase] = None,
    ) -> Dict[str, Any]:
        """
        Advances a migration into its next phase, executing the required DDL,
        parity checks, or contraction steps.
        """
        migration = self.get_migration(name)
        if not migration:
            raise ValueError(f"Migration '{name}' not found.")

        now = datetime.now(timezone.utc)
        phase_order = [
            MigrationPhase.EXPAND,
            MigrationPhase.DUAL_WRITE,
            MigrationPhase.BACKFILL,
            MigrationPhase.READ_NEW,
            MigrationPhase.CONTRACT,
            MigrationPhase.COMPLETED,
        ]

        with get_write_session() as session:
            ledger = session.scalar(
                select(SchemaMigrationLedger).where(SchemaMigrationLedger.migration_name == name)
            )
            current_phase = MigrationPhase(ledger.phase) if ledger else None

            # Determine next phase
            if target_phase:
                next_phase = target_phase
            elif current_phase is None:
                next_phase = MigrationPhase.EXPAND
            else:
                idx = phase_order.index(current_phase)
                if idx >= len(phase_order) - 1:
                    return self.get_status(name)
                next_phase = phase_order[idx + 1]

            # Ensure ledger exists
            if not ledger:
                ledger = SchemaMigrationLedger(
                    migration_name=name,
                    phase=next_phase.value,
                    started_at=now,
                )
                session.add(ledger)
            else:
                ledger.phase = next_phase.value

            # Phase Execution Logic
            if next_phase == MigrationPhase.EXPAND:
                migration.expand(session)

            elif next_phase == MigrationPhase.DUAL_WRITE:
                pass

            elif next_phase == MigrationPhase.BACKFILL:
                pass

            elif next_phase == MigrationPhase.READ_NEW:
                # GATE: Must verify parity before allowing reads to switch
                parity = migration.verify_parity(session)
                if not parity["is_parity_clean"]:
                    raise RuntimeError(
                        f"Cannot advance to READ_NEW: Parity audit failed with {parity['discrepancies_count']} mismatches."
                    )
                ledger.verified_parity = True

            elif next_phase in (MigrationPhase.CONTRACT, MigrationPhase.COMPLETED):
                # Verify again before physical contraction
                parity = migration.verify_parity(session)
                if not parity["is_parity_clean"]:
                    raise RuntimeError(
                        f"Cannot CONTRACT: Parity audit failed with {parity['discrepancies_count']} mismatches."
                    )
                migration.contract(session)
                ledger.phase = MigrationPhase.COMPLETED.value
                ledger.completed_at = now

        return self.get_status(name)

    def run_backfill(
        self,
        name: str,
        batch_size: int = 100,
        max_batches: int = 50,
    ) -> Dict[str, Any]:
        """Executes throttled batch backfills until complete or max_batches is reached."""
        migration = self.get_migration(name)
        if not migration:
            raise ValueError(f"Migration '{name}' not found.")

        batches_processed = 0
        total_backfilled = 0

        while batches_processed < max_batches:
            with get_write_session() as session:
                count = migration.backfill_batch(session, batch_size=batch_size)
                if count == 0:
                    break
                total_backfilled += count
                batches_processed += 1

                # Update ledger counter
                ledger = session.scalar(
                    select(SchemaMigrationLedger).where(SchemaMigrationLedger.migration_name == name)
                )
                if ledger:
                    ledger.rows_backfilled += count

        with get_read_session() as session:
            remaining = migration.count_pending_backfill(session)

        return {
            "migration_name": name,
            "batches_executed": batches_processed,
            "rows_backfilled_in_run": total_backfilled,
            "remaining_unbackfilled_rows": remaining,
            "is_backfill_complete": remaining == 0,
        }

    def verify_parity(self, name: str) -> Dict[str, Any]:
        """Audits mathematical parity across 100% of rows."""
        migration = self.get_migration(name)
        if not migration:
            raise ValueError(f"Migration '{name}' not found.")

        with get_write_session() as session:
            parity = migration.verify_parity(session)
            ledger = session.scalar(
                select(SchemaMigrationLedger).where(SchemaMigrationLedger.migration_name == name)
            )
            if ledger:
                ledger.verified_parity = parity["is_parity_clean"]

        return parity


# Global singleton instance
migration_manager = MigrationManager()
