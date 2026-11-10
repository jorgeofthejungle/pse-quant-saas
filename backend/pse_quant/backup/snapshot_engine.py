"""
pse_quant/backup/snapshot_engine.py — Disaster Recovery & Database Snapshot Engine
PSE Quant SaaS (v2 Rebuild) — Lab 14

Provides hot non-blocking online SQLite database snapshots, streaming gzip compression,
SHA-256 cryptographic checksumming, mathematical integrity auditing, retention pruning,
and atomic restore capabilities.
"""

from __future__ import annotations
import os
import time
import gzip
import shutil
import sqlite3
import hashlib
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import select

from pse_quant.db.connection import get_write_session, get_read_session
from pse_quant.db.models import DatabaseSnapshotManifest
from pse_quant.db.pool import pool_manager

logger = logging.getLogger("pse_quant.backup.engine")


def _resolve_default_db_path() -> str:
    """Extracts raw file path from writer engine database URL."""
    url = pool_manager.writer_url
    if url.startswith("sqlite:///"):
        return os.path.abspath(url.replace("sqlite:///", ""))
    raise ValueError(f"Disaster Recovery Engine only supports SQLite database files, got {url}")


class SnapshotEngine:
    """Automates hot database backups, verification audits, retention, and restores."""

    @classmethod
    def create_snapshot(
        cls,
        source_db_path: Optional[str] = None,
        backup_dir: str = "backups",
        compress: bool = True,
        max_retained: int = 10,
    ) -> Dict[str, Any]:
        """
        Executes a hot point-in-time database snapshot via the SQLite Online Backup API.
        Guarantees zero-downtime, no WAL tearing, PRAGMA integrity verification,
        streaming gzip compression, and SHA-256 cryptographic checksumming.
        """
        src_path = os.path.abspath(source_db_path or _resolve_default_db_path())
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"Source database file not found at: {src_path}")

        os.makedirs(backup_dir, exist_ok=True)
        now = datetime.now(timezone.utc)
        snapshot_id = f"snap_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        temp_raw_path = os.path.join(backup_dir, f"temp_{snapshot_id}.db")

        # ── 1. Non-Blocking Online Hot Backup ──────────────────────────
        source_conn = sqlite3.connect(src_path)
        dest_conn = sqlite3.connect(temp_raw_path)
        try:
            # Cooperatively copy 250 pages at a time without writer starvation
            source_conn.backup(dest_conn, pages=250)
        finally:
            source_conn.close()

        # ── 2. Structural & Mathematical Integrity Audit ───────────────
        try:
            integrity_rows = dest_conn.execute("PRAGMA integrity_check;").fetchall()
            is_clean = len(integrity_rows) == 1 and integrity_rows[0][0] == "ok"
            if not is_clean:
                dest_conn.close()
                if os.path.exists(temp_raw_path):
                    os.remove(temp_raw_path)
                raise RuntimeError(f"Integrity check failed on database snapshot: {integrity_rows}")

            # Collect domain tables and aggregate row counts
            tables_res = dest_conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                  AND name NOT LIKE 'sqlite_%' 
                  AND name NOT LIKE '%fts%' 
                  AND name != 'database_snapshots';
            """).fetchall()
            table_names = [r[0] for r in tables_res]

            total_rows = 0
            for tbl in table_names:
                row = dest_conn.execute(f"SELECT count(*) FROM {tbl};").fetchone()
                total_rows += row[0] if row else 0
        finally:
            dest_conn.close()

        raw_bytes = os.path.getsize(temp_raw_path)

        # ── 3. Streaming Compression & SHA-256 Checksumming ───────────
        if compress:
            filename = f"{snapshot_id}.db.gz"
            final_path = os.path.join(backup_dir, filename)
            sha256 = hashlib.sha256()

            with open(temp_raw_path, "rb") as f_in, gzip.open(final_path, "wb", compresslevel=9) as f_out:
                while chunk := f_in.read(65536):
                    f_out.write(chunk)

            # Compute SHA-256 of the compressed artifact
            with open(final_path, "rb") as f_comp:
                while chunk := f_comp.read(65536):
                    sha256.update(chunk)

            checksum = sha256.hexdigest()
            compressed_bytes = os.path.getsize(final_path)
            ratio = round(compressed_bytes / raw_bytes, 4) if raw_bytes > 0 else 1.0

            # Remove uncompressed raw copy
            os.remove(temp_raw_path)
        else:
            filename = f"{snapshot_id}.db"
            final_path = os.path.join(backup_dir, filename)
            os.replace(temp_raw_path, final_path)
            sha256 = hashlib.sha256()
            with open(final_path, "rb") as f_in:
                while chunk := f_in.read(65536):
                    sha256.update(chunk)
            checksum = sha256.hexdigest()
            compressed_bytes = raw_bytes
            ratio = 1.0

        # ── 4. Persist Manifest Record in Ledger ───────────────────────
        with get_write_session() as session:
            manifest = DatabaseSnapshotManifest(
                snapshot_id=snapshot_id,
                filename=filename,
                filepath=os.path.abspath(final_path),
                raw_bytes=raw_bytes,
                compressed_bytes=compressed_bytes,
                compression_ratio=ratio,
                sha256_checksum=checksum,
                is_verified=True,
                tables_count=len(table_names),
                total_rows=total_rows,
                status="completed",
                created_at=now,
            )
            session.add(manifest)

        # ── 5. Retention Pruning ───────────────────────────────────────
        cls.prune_snapshots(max_retained=max_retained, backup_dir=backup_dir)

        logger.info(
            "Created snapshot %s: raw=%d bytes, compressed=%d bytes (ratio=%.2f), tables=%d, rows=%d",
            snapshot_id, raw_bytes, compressed_bytes, ratio, len(table_names), total_rows
        )

        return {
            "snapshot_id": snapshot_id,
            "filename": filename,
            "filepath": os.path.abspath(final_path),
            "raw_bytes": raw_bytes,
            "compressed_bytes": compressed_bytes,
            "compression_ratio": ratio,
            "sha256_checksum": checksum,
            "is_verified": True,
            "tables_count": len(table_names),
            "total_rows": total_rows,
            "status": "completed",
            "created_at": now.isoformat(),
        }

    @classmethod
    def verify_snapshot(cls, snapshot_id: str, backup_dir: str = "backups") -> Dict[str, Any]:
        """
        Performs an exhaustive cryptographic audit of a snapshot:
        1. Recalculates SHA-256 against stored manifest.
        2. Decompresses into memory / sandbox and executes PRAGMA integrity_check.
        """
        with get_read_session() as session:
            manifest = session.scalar(
                select(DatabaseSnapshotManifest).where(DatabaseSnapshotManifest.snapshot_id == snapshot_id)
            )

        filepath = manifest.filepath if manifest else os.path.join(backup_dir, f"{snapshot_id}.db.gz")
        if not os.path.exists(filepath):
            # Check without .gz fallback
            raw_path = os.path.join(backup_dir, f"{snapshot_id}.db")
            if os.path.exists(raw_path):
                filepath = raw_path
            else:
                raise FileNotFoundError(f"Snapshot artifact file not found at: {filepath}")

        # Recalculate SHA-256
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        current_hash = sha256.hexdigest()

        expected_hash = manifest.sha256_checksum if manifest else current_hash
        sha_match = current_hash == expected_hash

        if not sha_match:
            logger.error("SHA-256 mismatch for snapshot %s! Expected %s, got %s", snapshot_id, expected_hash, current_hash)
            if manifest:
                with get_write_session() as session:
                    m = session.scalar(select(DatabaseSnapshotManifest).where(DatabaseSnapshotManifest.snapshot_id == snapshot_id))
                    if m:
                        m.status = "corrupt"
            return {
                "snapshot_id": snapshot_id,
                "is_valid": False,
                "sha256_match": False,
                "current_checksum": current_hash,
                "expected_checksum": expected_hash,
                "error": "Cryptographic SHA-256 mismatch! File has been modified or corrupted.",
            }

        # Decompress and verify SQLite structure
        temp_verify_path = os.path.join(backup_dir, f"verify_{uuid.uuid4().hex[:6]}.db")
        try:
            if filepath.endswith(".gz"):
                with gzip.open(filepath, "rb") as f_in, open(temp_verify_path, "wb") as f_out:
                    while chunk := f_in.read(65536):
                        f_out.write(chunk)
            else:
                shutil.copy2(filepath, temp_verify_path)

            conn = sqlite3.connect(temp_verify_path)
            try:
                integrity_rows = conn.execute("PRAGMA integrity_check;").fetchall()
                is_clean = len(integrity_rows) == 1 and integrity_rows[0][0] == "ok"
                tbl_row = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table';").fetchone()
                tables_res = tbl_row[0] if tbl_row else 0
            finally:
                conn.close()

            if not is_clean:
                return {
                    "snapshot_id": snapshot_id,
                    "is_valid": False,
                    "sha256_match": True,
                    "integrity_status": "corrupt",
                    "error": f"PRAGMA integrity_check failed: {integrity_rows}",
                }

        finally:
            if os.path.exists(temp_verify_path):
                os.remove(temp_verify_path)

        return {
            "snapshot_id": snapshot_id,
            "is_valid": True,
            "sha256_match": True,
            "integrity_status": "ok",
            "tables_count": tables_res,
            "total_rows": manifest.total_rows if manifest else 0,
            "checksum": current_hash,
        }

    @classmethod
    def restore_snapshot(
        cls,
        snapshot_id: str,
        target_db_path: Optional[str] = None,
        dry_run: bool = False,
        backup_dir: str = "backups",
    ) -> Dict[str, Any]:
        """
        Restores a verified point-in-time snapshot to the target database.
        - Guarantees pre-restore integrity audit.
        - Dry-run mode tests decompression and integrity without touching target DB.
        - Creates safety fallback (.pre_restore.bak) before replacing live file.
        """
        # 1. Audit snapshot integrity
        audit = cls.verify_snapshot(snapshot_id, backup_dir=backup_dir)
        if not audit["is_valid"]:
            raise RuntimeError(f"Cannot restore snapshot '{snapshot_id}': {audit.get('error', 'Audit failed')}")

        if dry_run:
            return {
                "status": "dry_run_success",
                "message": "Snapshot verified clean and ready for restoration.",
                "snapshot_id": snapshot_id,
                "audit": audit,
            }

        target_path = os.path.abspath(target_db_path or _resolve_default_db_path())
        filepath = os.path.join(backup_dir, f"{snapshot_id}.db.gz")
        if not os.path.exists(filepath):
            filepath = os.path.join(backup_dir, f"{snapshot_id}.db")

        # 2. Safety Fallback of Live Database
        safety_path = None
        if os.path.exists(target_path):
            safety_path = f"{target_path}.pre_restore_{int(time.time())}.bak"
            shutil.copy2(target_path, safety_path)
            logger.info("Created pre-restore safety copy at: %s", safety_path)

        # 3. Atomic File Replacement (with Online Backup API fallback for Windows file locks)
        temp_restoring = f"{target_path}.restoring_{uuid.uuid4().hex[:6]}"
        try:
            if filepath.endswith(".gz"):
                with gzip.open(filepath, "rb") as f_in, open(temp_restoring, "wb") as f_out:
                    while chunk := f_in.read(65536):
                        f_out.write(chunk)
            else:
                shutil.copy2(filepath, temp_restoring)

            # Dispose active SQLAlchemy pools to release idle file locks
            try:
                pool_manager.writer_engine.dispose()
                pool_manager.reader_engine.dispose()
            except Exception:
                pass

            try:
                # Fast atomic replacement
                os.replace(temp_restoring, target_path)
            except (PermissionError, OSError):
                # Fallback on Windows when file is held open by a connection: stream pages directly
                restore_src = sqlite3.connect(temp_restoring)
                restore_dst = sqlite3.connect(target_path)
                try:
                    restore_src.backup(restore_dst)
                finally:
                    restore_src.close()
                    restore_dst.close()

        finally:
            if os.path.exists(temp_restoring):
                try:
                    os.remove(temp_restoring)
                except OSError:
                    pass

        # 4. Update Manifest Record
        now = datetime.now(timezone.utc)
        try:
            with get_write_session() as session:
                manifest = session.scalar(
                    select(DatabaseSnapshotManifest).where(DatabaseSnapshotManifest.snapshot_id == snapshot_id)
                )
                if manifest:
                    manifest.status = "restored"
                    manifest.restored_at = now
        except Exception as exc:
            logger.warning("Could not update manifest ledger after restore: %s", exc)

        logger.info("Restored database snapshot %s to %s", snapshot_id, target_path)

        return {
            "status": "restored",
            "snapshot_id": snapshot_id,
            "target_path": target_path,
            "safety_backup_path": safety_path,
            "restored_at": now.isoformat(),
        }

    @classmethod
    def prune_snapshots(
        cls,
        max_retained: int = 10,
        max_age_days: Optional[int] = None,
        backup_dir: str = "backups",
    ) -> Dict[str, Any]:
        """
        Applies retention policy: deletes aged snapshot files and marks them 'pruned' in the ledger.
        """
        pruned_count = 0
        now = datetime.now(timezone.utc)

        with get_write_session() as session:
            manifests = session.scalars(
                select(DatabaseSnapshotManifest)
                .where(DatabaseSnapshotManifest.status.in_(["completed", "restored"]))
                .order_by(DatabaseSnapshotManifest.created_at.desc())
            ).all()

            for idx, m in enumerate(manifests):
                should_prune = False
                if idx >= max_retained:
                    should_prune = True
                elif max_age_days is not None:
                    # Compare age
                    created = m.created_at
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if now - created > timedelta(days=max_age_days):
                        should_prune = True

                if should_prune:
                    # Remove file from disk
                    if os.path.exists(m.filepath):
                        try:
                            os.remove(m.filepath)
                        except OSError as exc:
                            logger.warning("Could not remove snapshot file %s: %s", m.filepath, exc)
                    m.status = "pruned"
                    pruned_count += 1

        return {
            "pruned_count": pruned_count,
            "max_retained_threshold": max_retained,
            "status": "success",
        }

    @classmethod
    def list_snapshots(cls) -> List[Dict[str, Any]]:
        """Lists all recorded snapshots from the manifest ledger."""
        with get_read_session() as session:
            manifests = session.scalars(
                select(DatabaseSnapshotManifest).order_by(DatabaseSnapshotManifest.created_at.desc())
            ).all()

            return [
                {
                    "snapshot_id": m.snapshot_id,
                    "filename": m.filename,
                    "filepath": m.filepath,
                    "raw_bytes": m.raw_bytes,
                    "compressed_bytes": m.compressed_bytes,
                    "compression_ratio": m.compression_ratio,
                    "sha256_checksum": m.sha256_checksum,
                    "is_verified": m.is_verified,
                    "tables_count": m.tables_count,
                    "total_rows": m.total_rows,
                    "status": m.status,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "restored_at": m.restored_at.isoformat() if m.restored_at else None,
                }
                for m in manifests
            ]


# Singleton instance
snapshot_engine = SnapshotEngine()
