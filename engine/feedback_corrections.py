# ============================================================
# engine/feedback_corrections.py — Runtime Weight Override Integration
# PSE Quant SaaS
# ============================================================
# Called by the scorer at runtime to apply feedback weight overrides.
# Always fail-safe: any error returns base weights unchanged.
# ============================================================

import json
import logging
from datetime import datetime, timezone

from db.db_connection import get_connection
from config import SCORER_WEIGHTS

log = logging.getLogger(__name__)

_CUMULATIVE_CAP = 0.08
_MIN_LAYER_WEIGHT = 0.10

_INACTIVE_STATUSES = {"expired", "admin_reset"}


def get_layer_weight_override(sector_group: str, layer: str) -> float:
    """
    Reads feedback_correction_{sector_group}_{layer} from settings.
    Returns cumulative weight adjustment as float, or 0.0 if none/invalid.
    """
    key = f"feedback_correction_{sector_group}_{layer}"
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            log.debug("No correction for %s/%s", sector_group, layer)
            return 0.0

        try:
            blob = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            log.warning("get_layer_weight_override: corrupt JSON for key %s — returning 0.0", key)
            return 0.0

        status = blob.get("status", "")
        if status in _INACTIVE_STATUSES:
            log.debug("Correction %s has status=%s — returning 0.0", key, status)
            return 0.0

        cumulative = float(blob.get("cumulative", 0.0))

        if abs(cumulative) > _CUMULATIVE_CAP:
            log.warning(
                "Correction %s exceeds cumulative cap — returning 0.0 (cumulative=%.4f)",
                key, cumulative
            )
            return 0.0

        # Check no portfolio layer would drop below minimum
        for portfolio_type, weights in SCORER_WEIGHTS.items():
            if layer in weights:
                if weights[layer] + cumulative < _MIN_LAYER_WEIGHT:
                    log.warning(
                        "Correction %s would bring %s layer below min weight in portfolio %s "
                        "— returning 0.0", key, layer, portfolio_type
                    )
                    return 0.0

        return cumulative

    except Exception as exc:
        log.warning(
            "get_layer_weight_override: unexpected error for %s/%s: %s — returning 0.0",
            sector_group, layer, exc
        )
        return 0.0


def get_effective_weights(sector_group: str, portfolio_type: str) -> dict:
    """
    Returns {layer_name: effective_weight} for a given sector_group + portfolio_type.
    Applies proportional redistribution when a correction adjusts one layer.
    Always returns valid weights that sum to ~1.0.
    """
    try:
        base_weights = dict(SCORER_WEIGHTS.get(portfolio_type, {}))
        if not base_weights:
            log.warning(
                "get_effective_weights: unknown portfolio_type=%s, returning empty dict",
                portfolio_type
            )
            return {}

        effective = dict(base_weights)

        for layer in list(base_weights.keys()):
            adjustment = get_layer_weight_override(sector_group, layer)
            if adjustment == 0.0:
                continue

            target_weight = effective[layer] + adjustment

            # Clamp so target layer doesn't go below minimum
            if target_weight < _MIN_LAYER_WEIGHT:
                target_weight = _MIN_LAYER_WEIGHT
                adjustment = target_weight - effective[layer]

            effective[layer] = target_weight

            # Redistribute the inverse of adjustment proportionally to other layers
            other_layers = {k: v for k, v in effective.items() if k != layer}
            total_other = sum(other_layers.values())

            if total_other <= 0:
                continue

            redistribution = -adjustment
            for other_layer, other_weight in other_layers.items():
                share = other_weight / total_other
                new_weight = other_weight + redistribution * share
                # Clamp to minimum
                effective[other_layer] = max(_MIN_LAYER_WEIGHT, new_weight)

            # Renormalize to ensure weights always sum to exactly 1.0
            # (floor clamping can push the total above 1.0)
            total_eff = sum(effective.values())
            if total_eff > 0 and abs(total_eff - 1.0) > 1e-9:
                effective = {k: v / total_eff for k, v in effective.items()}

        return effective

    except Exception as exc:
        log.warning(
            "get_effective_weights: error for sector=%s portfolio=%s: %s — returning base weights",
            sector_group, portfolio_type, exc
        )
        return dict(SCORER_WEIGHTS.get(portfolio_type, {}))


def log_scoring_run_weights(ticker: str, sector_group: str, portfolio_type: str) -> None:
    """
    Logs effective weights to activity_log for audit trail.
    Called once per scoring run / sector batch. Silent on any error.
    """
    try:
        base_weights = dict(SCORER_WEIGHTS.get(portfolio_type, {}))
        overrides = {
            layer: get_layer_weight_override(sector_group, layer)
            for layer in base_weights
        }
        effective_weights = get_effective_weights(sector_group, portfolio_type)

        detail = json.dumps({
            "ticker_sample": ticker,
            "sector_group": sector_group,
            "portfolio_type": portfolio_type,
            "base_weights": base_weights,
            "overrides": overrides,
            "effective_weights": effective_weights,
        })

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO activity_log (timestamp, category, action, detail, status)
                   VALUES (?, 'scoring_weights', 'weight_log', ?, 'ok')""",
                (now, detail)
            )
            conn.commit()
        finally:
            conn.close()

    except Exception as exc:
        log.warning("log_scoring_run_weights: failed silently: %s", exc)
