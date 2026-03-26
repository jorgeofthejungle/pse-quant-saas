# ============================================================
# feedback/correction_engine.py — Correction Lifecycle Manager
# PSE Quant SaaS — manages apply/decay/expire/reset for weight corrections
# stored in settings as feedback_correction_{sector}_{layer}
# ============================================================

import json
import logging
from datetime import datetime, timezone

from db.db_connection import get_connection
from config import SCORER_WEIGHTS

log = logging.getLogger(__name__)

_CUMULATIVE_CAP = 0.08
_MIN_LAYER_WEIGHT = 0.10
_DECAY_FACTOR = 0.75
_DECAY_EXPIRY_THRESHOLD = 0.005
_DECAY_QUARTERS = 4  # quarters without reconfirmation before decay kicks in


def _key(sector: str, layer: str) -> str:
    return f"feedback_correction_{sector}_{layer}"


def _read_blob(sector: str, layer: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (_key(sector, layer),)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None


def _write_blob(sector: str, layer: str, blob: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value, updated_at = excluded.updated_at""",
            (_key(sector, layer), json.dumps(blob), datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def _would_violate_min_weight(layer: str, cumulative_after: float) -> bool:
    for weights in SCORER_WEIGHTS.values():
        if layer in weights and weights[layer] + cumulative_after < _MIN_LAYER_WEIGHT:
            return True
    return False


def apply_correction(sector: str, layer: str, adjustment: float, quarter: str) -> bool:
    """Write or update correction. Returns True on success, False on constraint violation."""
    existing = _read_blob(sector, layer)
    prev_cumulative = existing["cumulative"] if existing else 0.0
    prev_version = existing["version"] if existing else 0
    new_cumulative = prev_cumulative + adjustment

    if abs(new_cumulative) > _CUMULATIVE_CAP:
        log.warning(
            "apply_correction: rejected — cumulative %.4f would exceed cap %.2f "
            "(sector=%s layer=%s)", new_cumulative, _CUMULATIVE_CAP, sector, layer
        )
        return False

    if _would_violate_min_weight(layer, new_cumulative):
        log.warning(
            "apply_correction: rejected — layer %s below min weight (sector=%s cumulative=%.4f)",
            layer, sector, new_cumulative
        )
        return False

    # Transition any prior active correction for a different quarter to cooling_down
    if existing and existing.get("status") == "active" and existing.get("quarter") != quarter:
        cooling = {**existing, "status": "cooling_down"}
        _write_blob(sector, layer, cooling)
        log.info(
            "apply_correction: prior correction sector=%s layer=%s q=%s -> cooling_down",
            sector, layer, existing.get("quarter"),
        )

    blob = {
        "adjustment": adjustment,
        "quarter": quarter,
        "cumulative": new_cumulative,
        "version": prev_version + 1,
        "previous_value": prev_cumulative,
        "status": "active",
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_blob(sector, layer, blob)
    log.info(
        "apply_correction: sector=%s layer=%s adj=%.4f cumulative=%.4f v%d",
        sector, layer, adjustment, new_cumulative, blob["version"]
    )
    return True


def decay_corrections() -> int:
    """Apply quarterly decay to all active/decaying corrections. Returns count processed."""
    now = datetime.now(timezone.utc)
    processed = 0

    for c in get_all_corrections():
        if c["status"] not in ("active", "cooling_down", "decaying"):
            continue
        try:
            applied_at = datetime.fromisoformat(c["applied_at"])
            if applied_at.tzinfo is None:
                applied_at = applied_at.replace(tzinfo=timezone.utc)
            quarters_elapsed = (now - applied_at).days / 91
        except (ValueError, TypeError):
            quarters_elapsed = 0

        if quarters_elapsed < _DECAY_QUARTERS:
            continue

        sector, layer = c["sector"], c["layer"]
        old_cum = c["cumulative"]
        new_cum = old_cum * _DECAY_FACTOR

        blob = {k: v for k, v in c.items() if k not in ("sector", "layer")}
        if abs(new_cum) < _DECAY_EXPIRY_THRESHOLD:
            blob.update({"cumulative": 0.0, "adjustment": 0.0, "status": "expired"})
            log.info("decay_corrections: expired sector=%s layer=%s", sector, layer)
        else:
            blob.update({"cumulative": new_cum, "adjustment": new_cum - old_cum, "status": "decaying"})
            log.info("decay_corrections: decayed %s/%s %.4f->%.4f", sector, layer, old_cum, new_cum)

        _write_blob(sector, layer, blob)
        processed += 1

    return processed


def expire_correction(sector: str, layer: str) -> bool:
    """Set status='expired' and zero correction. Returns False if not found."""
    existing = _read_blob(sector, layer)
    if existing is None:
        return False
    _write_blob(sector, layer, {**existing, "status": "expired", "cumulative": 0.0, "adjustment": 0.0})
    log.info("expire_correction: sector=%s layer=%s", sector, layer)
    return True


def reset_correction(sector: str, layer: str) -> bool:
    """Set status='admin_reset' and zero correction. Returns False if not found."""
    existing = _read_blob(sector, layer)
    if existing is None:
        return False
    _write_blob(sector, layer, {**existing, "status": "admin_reset", "cumulative": 0.0, "adjustment": 0.0})
    log.info("reset_correction: sector=%s layer=%s", sector, layer)
    return True


def get_all_corrections() -> list[dict]:
    """Returns all active/cooling_down/decaying corrections from settings table."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'feedback_correction_%'"
        ).fetchall()
    finally:
        conn.close()

    results = []
    prefix = "feedback_correction_"
    for row in rows:
        key, raw = row[0], row[1]
        try:
            blob = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not key.startswith(prefix):
            continue
        # Layer is last token; sector is everything before it
        parts = key[len(prefix):].rsplit("_", 1)
        if len(parts) < 2:
            continue
        sector_part, layer_part = parts
        results.append({
            "sector": sector_part,
            "layer": layer_part,
            "adjustment": blob.get("adjustment", 0.0),
            "cumulative": blob.get("cumulative", 0.0),
            "status": blob.get("status", "unknown"),
            "quarter": blob.get("quarter", ""),
            "applied_at": blob.get("applied_at", ""),
            "version": blob.get("version", 1),
        })

    return results
