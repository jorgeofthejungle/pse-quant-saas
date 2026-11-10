"""
pse_quant/api/routes/snapshots.py — Admin Disaster Recovery & Database Snapshot API
PSE Quant SaaS (v2 Rebuild) — Lab 14

Provides hot non-blocking database backups, cryptographic SHA-256 verification,
retention pruning, and atomic point-in-time restores.
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path

from pse_quant.backup.snapshot_engine import snapshot_engine
from pse_quant.api.routes.admin import require_admin

router = APIRouter(prefix="/admin/snapshots", tags=["admin-snapshots"], dependencies=[Depends(require_admin)])


@router.post("/create", summary="Trigger hot point-in-time database snapshot")
def create_snapshot(
    compress: Optional[bool] = Query(True, description="Enable streaming gzip compression"),
    max_retained: Optional[int] = Query(10, ge=1, le=100, description="Max snapshots to retain"),
):
    """
    Executes a hot online SQLite backup via the SQLite Online Backup API.
    - Zero downtime; holds shared page locks cooperatively.
    - Audits PRAGMA integrity_check before serialization.
    - Compresses with gzip and records SHA-256 in manifest ledger.
    """
    try:
        return snapshot_engine.create_snapshot(compress=compress if compress is not None else True, max_retained=max_retained or 10)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Snapshot generation failed: {exc}")


@router.get("", summary="List all database snapshots")
def list_snapshots():
    """Returns all recorded database snapshots with sizes, compression ratios, and integrity status."""
    return {"snapshots": snapshot_engine.list_snapshots()}


@router.get("/{snapshot_id}", summary="Inspect a specific database snapshot")
def get_snapshot(snapshot_id: str = Path(..., min_length=4, max_length=128)):
    """Retrieves metadata and verification details for a single snapshot."""
    snapshots = snapshot_engine.list_snapshots()
    match = next((s for s in snapshots if s["snapshot_id"] == snapshot_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found.")
    return match


@router.post("/{snapshot_id}/verify", summary="Run cryptographic SHA-256 and integrity audit")
def verify_snapshot(snapshot_id: str = Path(..., min_length=4, max_length=128)):
    """
    Audits snapshot file:
    1. Re-computes SHA-256 to detect bit-rot or file tampering.
    2. Decompresses in sandbox and executes PRAGMA integrity_check.
    """
    try:
        res = snapshot_engine.verify_snapshot(snapshot_id)
        if not res["is_valid"]:
            raise HTTPException(status_code=400, detail=res.get("error", "Integrity audit failed"))
        return res
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{snapshot_id}/restore", summary="Restore database from snapshot")
def restore_snapshot(
    snapshot_id: str = Path(..., min_length=4, max_length=128),
    dry_run: Optional[bool] = Query(False, description="Test decompression & verification without modifying target DB"),
    confirm: Optional[bool] = Query(False, description="Must be true to execute live replacement"),
):
    """
    Restores the database to this verified point-in-time snapshot.
    - Requires confirm=true for live replacement.
    - Automatically creates a pre-restore safety backup (.pre_restore.bak) before replacing live DB.
    """
    if not dry_run and not confirm:
        raise HTTPException(
            status_code=400,
            detail="Restoring the live database requires 'confirm=true'. Pass 'dry_run=true' to test without modifying.",
        )

    try:
        return snapshot_engine.restore_snapshot(snapshot_id=snapshot_id, dry_run=bool(dry_run))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/prune", summary="Prune aged snapshots according to retention policy")
def prune_snapshots(
    max_retained: int = Query(10, ge=1, le=100, description="Maximum number of newest snapshots to keep"),
    max_age_days: Optional[int] = Query(None, ge=1, le=365, description="Prune snapshots older than N days"),
):
    """Deletes aged snapshot files from disk and marks ledger records as 'pruned'."""
    return snapshot_engine.prune_snapshots(max_retained=max_retained, max_age_days=max_age_days)
