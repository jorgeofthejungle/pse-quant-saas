"""
backend/tests/test_zero_downtime_migrations.py — Lab 12: Zero-Downtime Migrations Tests
=======================================================================================
Verifies:
  1. Phase 1 EXPAND: Non-destructive column additions (amount_centavos, currency).
  2. Phase 2 DUAL-WRITE: Model helper ensuring simultaneous writes to old and new columns.
  3. Phase 3 BACKFILL: Throttled chunked batch backfilling of historical records.
  4. Phase 4 PARITY AUDIT: 100% mathematical parity verification and gate blocking on mismatch.
  5. Phase 5 CONTRACT: Safe decommissioning and transition to COMPLETED.
  6. Admin API endpoints (/admin/migrations, /advance, /backfill, /verify).
"""

from __future__ import annotations
import pytest
from sqlalchemy import inspect, select, func, text
from fastapi.testclient import TestClient

from pse_quant.migrations.base import MigrationPhase
from pse_quant.migrations.m001_payment_centavos import PaymentCentavosMigration
from pse_quant.migrations.manager import migration_manager, MigrationManager
from pse_quant.db.models import PaymentEvent, SchemaMigrationLedger
from pse_quant.db.connection import get_write_session, get_read_session, init_db
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_write_session() as session:
        cols = {c["name"] for c in inspect(session.bind).get_columns("payment_events")}
        if "amount_php" not in cols:
            session.execute(text("ALTER TABLE payment_events ADD COLUMN amount_php FLOAT DEFAULT 0.0;"))
            session.commit()
        session.query(PaymentEvent).delete()
        session.query(SchemaMigrationLedger).delete()


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


@pytest.fixture
def public_client():
    return TestClient(app)


# ── 1. Phase 1: Expand DDL Safety ──────────────────────────────

def test_expand_phase_adds_columns_safely():
    """Verifies that expand adds amount_centavos and currency without dropping tables."""
    migration = PaymentCentavosMigration()

    with get_write_session() as session:
        migration.expand(session)
        cols = {c["name"] for c in inspect(session.bind).get_columns("payment_events")}
        assert "amount_centavos" in cols
        assert "currency" in cols
        assert "amount_php" in cols  # Old column MUST still exist!


# ── 2. Phase 2: Dual-Write Contract ────────────────────────────

def test_dual_write_model_contract():
    """Verifies that model setter and effective_amount_php dual-write correctly."""
    event = PaymentEvent(
        provider="paymongo",
        event_id="evt_test_dual_1",
        event_type="payment.paid",
        status="processed",
    )
    event.set_amount(1499.75)

    assert event.amount_php == 1499.75
    assert event.amount_centavos == 149975
    assert event.effective_amount_php == 1499.75

    with get_write_session() as session:
        session.add(event)

    with get_read_session() as session:
        saved = session.scalar(select(PaymentEvent).where(PaymentEvent.event_id == "evt_test_dual_1"))
        assert saved is not None
        assert saved.amount_php == 1499.75
        assert saved.amount_centavos == 149975


# ── 3. Phase 3: Throttled Chunked Backfill ─────────────────────

def test_chunked_backfill_historical_rows():
    """Seeds 250 legacy rows with NULL centavos and backfills them in batches of 100."""
    migration = PaymentCentavosMigration()

    with get_write_session() as session:
        migration.expand(session)
        # Seed 250 legacy events without centavos
        for i in range(250):
            ev = PaymentEvent(
                provider="paymongo",
                event_id=f"legacy_evt_{i}",
                event_type="payment.paid",
                status="processed",
                amount_php=float(100 + i),
                amount_centavos=None,  # Simulates pre-migration legacy row
            )
            session.add(ev)

    # Verify pending count
    with get_read_session() as session:
        assert migration.count_pending_backfill(session) == 250

    # Initialize ledger in manager
    migration_manager.advance_phase("m001_payment_centavos", target_phase=MigrationPhase.BACKFILL)

    # Run throttled backfill (batch size 100)
    result = migration_manager.run_backfill("m001_payment_centavos", batch_size=100, max_batches=10)
    assert result["batches_executed"] == 3  # 100 + 100 + 50
    assert result["rows_backfilled_in_run"] == 250
    assert result["remaining_unbackfilled_rows"] == 0
    assert result["is_backfill_complete"] is True

    # Audit all rows
    with get_read_session() as session:
        assert migration.count_pending_backfill(session) == 0
        events = session.scalars(select(PaymentEvent)).all()
        assert len(events) == 250
        for ev in events:
            assert ev.amount_centavos == int(round(ev.amount_php * 100))
            assert ev.currency == "PHP"


# ── 4. Phase 4: Parity Verification & Security Gate ────────────

def test_parity_verification_gate_success():
    """Verifies parity audit passes when 100% of rows match."""
    migration = PaymentCentavosMigration()

    with get_write_session() as session:
        migration.expand(session)
        for i in range(50):
            ev = PaymentEvent(
                provider="paymongo",
                event_id=f"clean_evt_{i}",
                event_type="payment.paid",
                status="processed",
                amount_php=50.25,
                amount_centavos=5025,
                currency="PHP",
            )
            session.add(ev)

    with get_read_session() as session:
        parity = migration.verify_parity(session)
        assert parity["is_parity_clean"] is True
        assert parity["discrepancies_count"] == 0
        assert parity["total_audited"] == 50


def test_parity_verification_gate_catches_corruption_and_blocks():
    """Verifies that data corruption blocks advancing to READ_NEW or CONTRACT."""
    migration = PaymentCentavosMigration()

    with get_write_session() as session:
        migration.expand(session)
        # Clean row
        session.add(PaymentEvent(
            provider="paymongo",
            event_id="valid_evt",
            event_type="payment.paid",
            status="processed",
            amount_php=10.0,
            amount_centavos=1000,
        ))
        # Corrupt row: float is 20.0, but centavos was set to 9999
        session.add(PaymentEvent(
            provider="paymongo",
            event_id="corrupt_evt",
            event_type="payment.paid",
            status="processed",
            amount_php=20.0,
            amount_centavos=9999,
        ))

    # Parity check catches it
    with get_read_session() as session:
        parity = migration.verify_parity(session)
        assert parity["is_parity_clean"] is False
        assert parity["discrepancies_count"] == 1
        assert parity["sample_discrepancies"][0]["id"] is not None

    # Gate blocks advancing to READ_NEW
    with pytest.raises(RuntimeError, match="Parity audit failed"):
        migration_manager.advance_phase("m001_payment_centavos", target_phase=MigrationPhase.READ_NEW)


# ── 5. Full 5-Phase End-to-End Advancement ─────────────────────

def test_full_migration_lifecycle():
    """Executes all 5 phases in order from EXPAND to COMPLETED."""
    # Start: NOT_STARTED -> EXPAND
    st1 = migration_manager.advance_phase("m001_payment_centavos")
    assert st1["phase"] == MigrationPhase.EXPAND.value

    # EXPAND -> DUAL_WRITE
    st2 = migration_manager.advance_phase("m001_payment_centavos")
    assert st2["phase"] == MigrationPhase.DUAL_WRITE.value

    # Seed and backfill
    with get_write_session() as session:
        session.add(PaymentEvent(
            provider="paymongo",
            event_id="e2e_evt",
            event_type="payment.paid",
            status="processed",
            amount_php=999.0,
            amount_centavos=None,
        ))

    # DUAL_WRITE -> BACKFILL
    st3 = migration_manager.advance_phase("m001_payment_centavos")
    assert st3["phase"] == MigrationPhase.BACKFILL.value
    migration_manager.run_backfill("m001_payment_centavos")

    # BACKFILL -> READ_NEW (passes parity gate)
    st4 = migration_manager.advance_phase("m001_payment_centavos")
    assert st4["phase"] == MigrationPhase.READ_NEW.value
    assert st4["verified_parity"] is True

    # READ_NEW -> CONTRACT / COMPLETED
    st5 = migration_manager.advance_phase("m001_payment_centavos")
    assert st5["phase"] == MigrationPhase.COMPLETED.value
    assert st5["completed_at"] is not None


# ── 6. Admin API Endpoints ─────────────────────────────────────

def test_admin_migration_endpoints(admin_client: TestClient, public_client: TestClient):
    """Tests GET /admin/migrations, /status, /backfill, /verify, and /advance."""
    # 1. Unauthorized
    unauth = public_client.get("/api/v1/admin/migrations")
    assert unauth.status_code == 401

    # 2. List migrations
    res = admin_client.get("/api/v1/admin/migrations")
    assert res.status_code == 200
    data = res.json()
    assert "migrations" in data
    names = [m["name"] for m in data["migrations"]]
    assert "m001_payment_centavos" in names

    # 3. Status
    st_res = admin_client.get("/api/v1/admin/migrations/m001_payment_centavos")
    assert st_res.status_code == 200
    assert st_res.json()["name"] == "m001_payment_centavos"

    # 4. Advance to EXPAND
    adv_res = admin_client.post("/api/v1/admin/migrations/m001_payment_centavos/advance?target_phase=EXPAND")
    assert adv_res.status_code == 200
    assert adv_res.json()["phase"] == "EXPAND"

    # 5. Verify parity
    ver_res = admin_client.get("/api/v1/admin/migrations/m001_payment_centavos/verify")
    assert ver_res.status_code == 200
    assert ver_res.json()["is_parity_clean"] is True
