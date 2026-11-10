"""
backend/tests/test_disaster_recovery_snapshots.py — Lab 14: Disaster Recovery & Snapshots Tests
=================================================================================================
Verifies:
  1. Hot online snapshot generation via SQLite Online Backup API without downtime.
  2. Streaming gzip compression ratio and space savings.
  3. Cryptographic SHA-256 verification and bit-rot / tamper detection.
  4. PRAGMA integrity_check validation on snapshot artifacts.
  5. Dry-run restoration audit (validates restorable state without touching live DB).
  6. Atomic live database restore and recovery after catastrophic data loss.
  7. Automated retention policy pruning (bounded snapshot count on disk).
  8. Admin REST API endpoints (/admin/snapshots/create, list, verify, restore, prune).
"""

from __future__ import annotations
import os
import shutil
import sqlite3
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from pse_quant.backup.snapshot_engine import SnapshotEngine, snapshot_engine
from pse_quant.db.models import DatabaseSnapshotManifest
from pse_quant.db.connection import get_write_session, init_db
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app

TEST_BACKUP_DIR = "test_backups"
TEST_ORIGIN_DB = os.path.abspath(os.path.join(TEST_BACKUP_DIR, "isolated_origin.db"))


@pytest.fixture(autouse=True)
def setup_snapshot_test_env():
    init_db()
    os.makedirs(TEST_BACKUP_DIR, exist_ok=True)
    with get_write_session() as session:
        session.query(DatabaseSnapshotManifest).delete()

    # Create an isolated SQLite database for backup and restore testing
    conn = sqlite3.connect(TEST_ORIGIN_DB)
    conn.execute("CREATE TABLE stocks (ticker TEXT PRIMARY KEY, name TEXT, sector TEXT);")
    conn.execute("CREATE TABLE prices (id INTEGER PRIMARY KEY, ticker TEXT, close REAL);")
    conn.execute("""
        INSERT INTO stocks VALUES 
            ('ALI', 'Ayala Land, Inc.', 'Property'),
            ('BDO', 'BDO Unibank, Inc.', 'Financials'),
            ('MER', 'Manila Electric Company', 'Services'),
            ('DMC', 'DMCI Holdings, Inc.', 'Holding Firms'),
            ('AC', 'Ayala Corporation', 'Holding Firms');
    """)
    conn.execute("""
        INSERT INTO prices VALUES 
            (1, 'ALI', 31.5),
            (2, 'BDO', 152.0),
            (3, 'MER', 380.0);
    """)
    conn.commit()
    conn.close()

    yield

    # Teardown test backup directory
    if os.path.exists(TEST_BACKUP_DIR):
        shutil.rmtree(TEST_BACKUP_DIR, ignore_errors=True)


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


@pytest.fixture
def public_client():
    return TestClient(app)


# ── 1. Hot Online Snapshot & Compression ───────────────────────

def test_hot_online_snapshot_creation():
    """Verifies non-blocking hot snapshot creation, gzip compression, and manifest logging."""
    snap = SnapshotEngine.create_snapshot(source_db_path=TEST_ORIGIN_DB, backup_dir=TEST_BACKUP_DIR, compress=True)

    assert snap["snapshot_id"].startswith("snap_")
    assert snap["filename"].endswith(".db.gz")
    assert os.path.exists(snap["filepath"])
    assert snap["raw_bytes"] > 0
    assert snap["compressed_bytes"] > 0
    # Compressed bytes should be smaller than raw SQLite DB bytes
    assert snap["compressed_bytes"] < snap["raw_bytes"]
    assert snap["compression_ratio"] < 1.0
    assert len(snap["sha256_checksum"]) == 64
    assert snap["is_verified"] is True
    assert snap["tables_count"] == 2
    assert snap["total_rows"] == 8  # 5 stocks + 3 prices


# ── 2. SHA-256 Verification & Tamper Detection ─────────────────

def test_sha256_verification_and_tamper_detection():
    """Verifies SHA-256 checksum audit passes on clean file and catches bit-rot / tampering."""
    snap = SnapshotEngine.create_snapshot(source_db_path=TEST_ORIGIN_DB, backup_dir=TEST_BACKUP_DIR, compress=True)
    snap_id = snap["snapshot_id"]

    # 1. Clean verification
    audit = SnapshotEngine.verify_snapshot(snap_id, backup_dir=TEST_BACKUP_DIR)
    assert audit["is_valid"] is True
    assert audit["sha256_match"] is True
    assert audit["integrity_status"] == "ok"

    # 2. Tamper file: flip bytes in the compressed archive
    with open(snap["filepath"], "r+b") as f:
        f.seek(50)
        original_byte = f.read(1)
        f.seek(50)
        # Invert the byte
        f.write(bytes([original_byte[0] ^ 0xFF]))

    # 3. Audit tampered file -> must fail!
    tampered_audit = SnapshotEngine.verify_snapshot(snap_id, backup_dir=TEST_BACKUP_DIR)
    assert tampered_audit["is_valid"] is False
    assert tampered_audit["sha256_match"] is False
    assert "Cryptographic SHA-256 mismatch" in tampered_audit["error"]


# ── 3. Dry-Run Restore Audit ───────────────────────────────────

def test_dry_run_restore_validation():
    """Verifies that dry-run restore tests decompression without modifying target database."""
    snap = SnapshotEngine.create_snapshot(source_db_path=TEST_ORIGIN_DB, backup_dir=TEST_BACKUP_DIR, compress=True)
    snap_id = snap["snapshot_id"]

    res = SnapshotEngine.restore_snapshot(snap_id, target_db_path=TEST_ORIGIN_DB, dry_run=True, backup_dir=TEST_BACKUP_DIR)
    assert res["status"] == "dry_run_success"
    assert "Snapshot verified clean" in res["message"]

    # Verify origin database remains intact
    conn = sqlite3.connect(TEST_ORIGIN_DB)
    stocks_count = conn.execute("SELECT count(*) FROM stocks;").fetchone()[0]
    conn.close()
    assert stocks_count == 5


# ── 4. Atomic Live Database Restoration ────────────────────────

def test_atomic_live_restore_recovers_data():
    """
    Simulates catastrophic data loss (truncating stocks table) and recovers
    all data via atomic snapshot restoration.
    """
    # 1. Take initial clean snapshot
    snap = SnapshotEngine.create_snapshot(source_db_path=TEST_ORIGIN_DB, backup_dir=TEST_BACKUP_DIR, compress=True)
    snap_id = snap["snapshot_id"]

    # 2. Simulate catastrophic failure: delete 4 stocks from isolated DB
    conn = sqlite3.connect(TEST_ORIGIN_DB)
    conn.execute("DELETE FROM stocks WHERE ticker != 'ALI';")
    conn.commit()
    count_corrupted = conn.execute("SELECT count(*) FROM stocks;").fetchone()[0]
    conn.close()
    assert count_corrupted == 1

    # 3. Restore from snapshot into isolated DB
    restore_res = SnapshotEngine.restore_snapshot(snap_id, target_db_path=TEST_ORIGIN_DB, dry_run=False, backup_dir=TEST_BACKUP_DIR)
    assert restore_res["status"] == "restored"
    assert restore_res["safety_backup_path"] is not None
    assert os.path.exists(restore_res["safety_backup_path"])

    # 4. Verify all 5 stocks are fully recovered!
    conn = sqlite3.connect(TEST_ORIGIN_DB)
    recovered_count = conn.execute("SELECT count(*) FROM stocks;").fetchone()[0]
    tickers = {r[0] for r in conn.execute("SELECT ticker FROM stocks;").fetchall()}
    conn.close()

    assert recovered_count == 5
    assert tickers == {"ALI", "BDO", "MER", "DMC", "AC"}

    # Cleanup safety backup
    if os.path.exists(restore_res["safety_backup_path"]):
        os.remove(restore_res["safety_backup_path"])


# ── 5. Retention Pruning Policy ────────────────────────────────

def test_retention_pruning_policy():
    """Verifies that creating snapshots beyond max_retained automatically prunes older files."""
    # Create 5 snapshots with max_retained=3
    created_ids = []
    for _ in range(5):
        s = SnapshotEngine.create_snapshot(source_db_path=TEST_ORIGIN_DB, backup_dir=TEST_BACKUP_DIR, compress=True, max_retained=3)
        created_ids.append(s["snapshot_id"])

    # List all manifests
    all_snaps = SnapshotEngine.list_snapshots()
    completed = [s for s in all_snaps if s["status"] == "completed"]
    pruned = [s for s in all_snaps if s["status"] == "pruned"]

    # Only 3 newest should be completed and exist on disk
    assert len(completed) == 3
    assert len(pruned) >= 2

    # Verify physical file deletion for pruned snapshots
    for p in pruned:
        assert not os.path.exists(p["filepath"])


# ── 6. Admin API Endpoints ─────────────────────────────────────

def test_admin_snapshot_endpoints(admin_client: TestClient, public_client: TestClient):
    """Verifies security and REST workflow on /api/v1/admin/snapshots."""
    # 1. Unauthorized
    unauth = public_client.get("/api/v1/admin/snapshots")
    assert unauth.status_code == 401

    # 2. Create snapshot via API
    create_res = admin_client.post("/api/v1/admin/snapshots/create?compress=true&max_retained=5")
    assert create_res.status_code == 200
    data = create_res.json()
    assert "snapshot_id" in data
    snap_id = data["snapshot_id"]

    # 3. List snapshots
    list_res = admin_client.get("/api/v1/admin/snapshots")
    assert list_res.status_code == 200
    assert len(list_res.json()["snapshots"]) >= 1

    # 4. Get specific snapshot
    get_res = admin_client.get(f"/api/v1/admin/snapshots/{snap_id}")
    assert get_res.status_code == 200
    assert get_res.json()["snapshot_id"] == snap_id

    # 5. Verify integrity via API
    ver_res = admin_client.post(f"/api/v1/admin/snapshots/{snap_id}/verify")
    assert ver_res.status_code == 200
    assert ver_res.json()["is_valid"] is True

    # 6. Restore guard: missing confirm=true
    rest_guard = admin_client.post(f"/api/v1/admin/snapshots/{snap_id}/restore")
    assert rest_guard.status_code == 400
    assert "confirm=true" in rest_guard.json()["detail"]

    # 7. Dry run restore via API
    dry_res = admin_client.post(f"/api/v1/admin/snapshots/{snap_id}/restore?dry_run=true")
    assert dry_res.status_code == 200
    assert dry_res.json()["status"] == "dry_run_success"

    # 8. Prune endpoint via API
    prune_res = admin_client.post("/api/v1/admin/snapshots/prune?max_retained=2")
    assert prune_res.status_code == 200
    assert "pruned_count" in prune_res.json()
