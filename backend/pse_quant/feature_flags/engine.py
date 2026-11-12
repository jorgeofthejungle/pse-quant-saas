"""
pse_quant/feature_flags/engine.py — Core Feature Flag & Canary Evaluation Engine
PSE Quant SaaS — Lab 16: Dynamic Feature Flags & Progressive Canary Delivery Engine

Provides:
  - Sub-microsecond deterministic sticky hashing for canary rollouts.
  - Multi-tier targeting, entity allowlists, and denylists.
  - Sub-millisecond emergency kill-switch.
  - In-memory thread-safe cache with write-through relational persistence & audit ledger.
"""

from __future__ import annotations
import hashlib
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Any

from pse_quant.feature_flags.models import (
    FeatureFlag,
    EvaluationContext,
    EvaluationResult,
    EvaluationReason,
    AuditAction,
)
from pse_quant.db.connection import get_write_session, get_read_session
from pse_quant.db.models import FeatureFlagRecord, FeatureFlagAuditRecord

logger = logging.getLogger("pse_quant.feature_flags")


class FeatureFlagEngine:
    """
    Enterprise-grade, thread-safe Feature Flag & Canary Rollout Engine.
    Evaluates flags in sub-millisecond in-memory cache with relational DB backup.
    """

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlag] = {}
        self._in_memory_audits: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self._is_initialized = False

    def initialize(self) -> None:
        """Loads all flags from persistent storage into the fast in-memory cache."""
        with self._lock:
            try:
                from pse_quant.db.connection import init_db
                init_db()
            except Exception as exc:
                logger.warning(f"Failed to run init_db in feature flag engine: {exc}")

            try:
                with get_read_session() as session:
                    records = session.query(FeatureFlagRecord).all()
                    for rec in records:
                        flag = FeatureFlag(
                            key=rec.key,
                            name=rec.name,
                            description=rec.description or "",
                            is_enabled=rec.is_enabled,
                            rollout_percentage=rec.rollout_percentage,
                            allowed_tiers=rec.allowed_tiers_json or [],
                            allowed_entities=rec.allowed_entities_json or [],
                            denied_entities=rec.denied_entities_json or [],
                            variants=rec.variants_json or {},
                            created_at=rec.created_at,
                            updated_at=rec.updated_at,
                        )
                        self._flags[flag.key] = flag
                logger.info(f"Loaded {len(self._flags)} feature flags into in-memory cache.")
            except Exception as exc:
                logger.warning(f"Could not load feature flags from DB (running in-memory only): {exc}")
            finally:
                self._is_initialized = True

    @staticmethod
    def compute_bucket(flag_key: str, entity_id: str) -> int:
        """
        Computes a deterministic hash bucket [0, 99] for sticky canary rollouts.
        Guarantees monotonicity: as rollout_percentage expands from N to M (M > N),
        all entities previously enabled remain enabled.
        """
        token = f"{flag_key}:{entity_id}".encode("utf-8")
        # 32-bit integer modulo 100
        digest = hashlib.sha256(token).hexdigest()
        return int(digest[:8], 16) % 100

    @staticmethod
    def _select_variant(variants: dict[str, int], flag_key: str, entity_id: str) -> Optional[str]:
        """Deterministically assigns an A/B variant if variants are configured."""
        if not variants:
            return None
        total_weight = sum(variants.values())
        if total_weight <= 0:
            return None
        token = f"{flag_key}:variant:{entity_id}".encode("utf-8")
        digest = hashlib.sha256(token).hexdigest()
        roll = int(digest[:8], 16) % total_weight
        cumulative = 0
        for variant_name, weight in variants.items():
            cumulative += weight
            if roll < cumulative:
                return variant_name
        return list(variants.keys())[0]

    def evaluate(self, flag_key: str, context: Optional[EvaluationContext] = None) -> EvaluationResult:
        """
        High-throughput, sub-microsecond feature flag evaluation pipeline.
        
        Evaluation Precedence:
          1. Flag Existence -> if not found -> NOT_FOUND, False
          2. Master Switch (is_enabled) -> if False -> DISABLED, False (Emergency Kill-Switch)
          3. Denied Entities -> if matched -> DENIED_ENTITY, False
          4. Allowed Entities -> if matched -> ALLOWED_ENTITY, True (Bypasses percentage)
          5. Allowed Tiers -> if specified and tier not matched -> TIER_MISMATCH, False
          6. Canary Percentage ->
             - 100% -> PERCENTAGE_CANARY_MATCH, True
             - 0%   -> PERCENTAGE_CANARY_MISS, False
             - Hash bucket < rollout_percentage -> True else False
        """
        start_ns = time.perf_counter_ns()
        if context is None:
            context = EvaluationContext()

        with self._lock:
            flag = self._flags.get(flag_key)

        if flag is None:
            latency_us = (time.perf_counter_ns() - start_ns) / 1000.0
            return EvaluationResult(
                flag_key=flag_key,
                enabled=False,
                reason=EvaluationReason.NOT_FOUND.value,
                evaluation_latency_us=latency_us,
            )

        # 1. Master Kill-Switch
        if not flag.is_enabled:
            latency_us = (time.perf_counter_ns() - start_ns) / 1000.0
            return EvaluationResult(
                flag_key=flag_key,
                enabled=False,
                reason=EvaluationReason.DISABLED.value,
                evaluation_latency_us=latency_us,
            )

        # 2. Denied Entities (Highest targeting priority)
        if context.entity_id in flag.denied_entities:
            latency_us = (time.perf_counter_ns() - start_ns) / 1000.0
            return EvaluationResult(
                flag_key=flag_key,
                enabled=False,
                reason=EvaluationReason.DENIED_ENTITY.value,
                evaluation_latency_us=latency_us,
            )

        # 3. Allowed Entities (Allowlist bypasses percentage and tier restrictions)
        if context.entity_id in flag.allowed_entities:
            variant = self._select_variant(flag.variants, flag_key, context.entity_id)
            latency_us = (time.perf_counter_ns() - start_ns) / 1000.0
            return EvaluationResult(
                flag_key=flag_key,
                enabled=True,
                reason=EvaluationReason.ALLOWED_ENTITY.value,
                variant=variant,
                evaluation_latency_us=latency_us,
            )

        # 4. Multi-Tier Targeting Gate
        if flag.allowed_tiers:
            client_tier = (context.tier or "FREE").upper()
            normalized_allowed = [t.upper() for t in flag.allowed_tiers]
            if client_tier not in normalized_allowed:
                latency_us = (time.perf_counter_ns() - start_ns) / 1000.0
                return EvaluationResult(
                    flag_key=flag_key,
                    enabled=False,
                    reason=EvaluationReason.TIER_MISMATCH.value,
                    evaluation_latency_us=latency_us,
                )

        # 5. Deterministic Sticky Canary Rollout
        if flag.rollout_percentage >= 100:
            variant = self._select_variant(flag.variants, flag_key, context.entity_id)
            latency_us = (time.perf_counter_ns() - start_ns) / 1000.0
            return EvaluationResult(
                flag_key=flag_key,
                enabled=True,
                reason=EvaluationReason.PERCENTAGE_CANARY_MATCH.value,
                bucket=0,
                variant=variant,
                evaluation_latency_us=latency_us,
            )

        if flag.rollout_percentage <= 0:
            latency_us = (time.perf_counter_ns() - start_ns) / 1000.0
            return EvaluationResult(
                flag_key=flag_key,
                enabled=False,
                reason=EvaluationReason.PERCENTAGE_CANARY_MISS.value,
                bucket=0,
                evaluation_latency_us=latency_us,
            )

        bucket = self.compute_bucket(flag_key, context.entity_id)
        is_in_bucket = bucket < flag.rollout_percentage
        reason = (
            EvaluationReason.PERCENTAGE_CANARY_MATCH.value
            if is_in_bucket
            else EvaluationReason.PERCENTAGE_CANARY_MISS.value
        )
        variant = self._select_variant(flag.variants, flag_key, context.entity_id) if is_in_bucket else None
        latency_us = (time.perf_counter_ns() - start_ns) / 1000.0

        return EvaluationResult(
            flag_key=flag_key,
            enabled=is_in_bucket,
            reason=reason,
            bucket=bucket,
            variant=variant,
            evaluation_latency_us=latency_us,
        )

    def create_flag(self, flag: FeatureFlag, actor: str = "admin") -> FeatureFlag:
        """Registers a new feature flag, writing to persistent storage and audit ledger."""
        with self._lock:
            flag.updated_at = datetime.now(timezone.utc)
            self._flags[flag.key] = flag

            self._persist_flag(flag)
            self._record_audit(
                flag_key=flag.key,
                actor=actor,
                action=AuditAction.CREATE.value,
                details=flag.model_dump(mode="json"),
            )
            return flag

    def update_flag(self, key: str, updates: dict[str, Any], actor: str = "admin") -> FeatureFlag:
        """Modifies an existing feature flag and logs an immutable audit trail entry."""
        with self._lock:
            flag = self._flags.get(key)
            if flag is None:
                raise KeyError(f"Feature flag '{key}' does not exist.")

            old_state = flag.model_dump(mode="json")
            for field, val in updates.items():
                if val is not None and hasattr(flag, field):
                    setattr(flag, field, val)
            flag.updated_at = datetime.now(timezone.utc)

            self._persist_flag(flag)
            self._record_audit(
                flag_key=key,
                actor=actor,
                action=AuditAction.UPDATE.value,
                details={"old": old_state, "new": flag.model_dump(mode="json")},
            )
            return flag

    def kill_switch(self, key: str, actor: str = "admin") -> FeatureFlag:
        """Sub-millisecond emergency kill-switch instantly deactivates a flag across all threads."""
        with self._lock:
            flag = self._flags.get(key)
            if flag is None:
                raise KeyError(f"Feature flag '{key}' does not exist.")

            flag.is_enabled = False
            flag.updated_at = datetime.now(timezone.utc)

            self._persist_flag(flag)
            self._record_audit(
                flag_key=key,
                actor=actor,
                action=AuditAction.KILL_SWITCH.value,
                details={"is_enabled": False, "triggered_at": datetime.now(timezone.utc).isoformat()},
            )
            logger.warning(f"EMERGENCY KILL-SWITCH triggered for feature flag '{key}' by {actor}!")
            return flag

    def delete_flag(self, key: str, actor: str = "admin") -> bool:
        """Removes a feature flag and records the deletion in the audit trail."""
        with self._lock:
            if key not in self._flags:
                return False
            old_flag = self._flags.pop(key)

            try:
                with get_write_session() as session:
                    rec = session.query(FeatureFlagRecord).filter_by(key=key).first()
                    if rec:
                        session.delete(rec)
            except Exception as exc:
                logger.warning(f"Could not delete flag '{key}' from DB: {exc}")

            self._record_audit(
                flag_key=key,
                actor=actor,
                action=AuditAction.DELETE.value,
                details={"deleted_flag": old_flag.model_dump(mode="json")},
            )
            return True

    def get_flag(self, key: str) -> Optional[FeatureFlag]:
        """Retrieves a feature flag by its key."""
        with self._lock:
            return self._flags.get(key)

    def list_flags(self) -> list[FeatureFlag]:
        """Lists all registered feature flags."""
        with self._lock:
            return list(self._flags.values())

    def clear(self) -> None:
        """Resets in-memory flags (primarily for isolated test fixtures)."""
        with self._lock:
            self._flags.clear()
            self._in_memory_audits.clear()

    def get_audit_trail(self, key: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        """Queries the persistent audit ledger for historical flag mutations with in-memory fallback."""
        try:
            with get_read_session() as session:
                query = session.query(FeatureFlagAuditRecord)
                if key:
                    query = query.filter_by(flag_key=key)
                records = query.order_by(FeatureFlagAuditRecord.created_at.desc()).limit(limit).all()
                if records:
                    return [
                        {
                            "id": r.id,
                            "flag_key": r.flag_key,
                            "actor": r.actor,
                            "action": r.action,
                            "details": r.details_json,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                        }
                        for r in records
                    ]
        except Exception as exc:
            logger.warning(f"Could not query audit trail from DB: {exc}")

        # Fallback to in-memory audit log
        with self._lock:
            filtered = [
                a for a in reversed(self._in_memory_audits)
                if key is None or a["flag_key"] == key
            ]
            return filtered[:limit]

    def _persist_flag(self, flag: FeatureFlag) -> None:
        """Syncs the in-memory flag state into relational storage."""
        try:
            with get_write_session() as session:
                rec = session.query(FeatureFlagRecord).filter_by(key=flag.key).first()
                if not rec:
                    rec = FeatureFlagRecord(
                        key=flag.key,
                        name=flag.name,
                        description=flag.description,
                        is_enabled=flag.is_enabled,
                        rollout_percentage=flag.rollout_percentage,
                        allowed_tiers_json=flag.allowed_tiers,
                        allowed_entities_json=flag.allowed_entities,
                        denied_entities_json=flag.denied_entities,
                        variants_json=flag.variants,
                    )
                    session.add(rec)
                else:
                    rec.name = flag.name
                    rec.description = flag.description
                    rec.is_enabled = flag.is_enabled
                    rec.rollout_percentage = flag.rollout_percentage
                    rec.allowed_tiers_json = flag.allowed_tiers
                    rec.allowed_entities_json = flag.allowed_entities
                    rec.denied_entities_json = flag.denied_entities
                    rec.variants_json = flag.variants
        except Exception as exc:
            logger.warning(f"Could not persist feature flag '{flag.key}' to DB: {exc}")

    def _record_audit(self, flag_key: str, actor: str, action: str, details: dict[str, Any]) -> None:
        """Appends an immutable audit entry to in-memory audit log and relational database."""
        entry = {
            "id": len(self._in_memory_audits) + 1,
            "flag_key": flag_key,
            "actor": actor,
            "action": action,
            "details": details,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._in_memory_audits.append(entry)

        try:
            with get_write_session() as session:
                audit = FeatureFlagAuditRecord(
                    flag_key=flag_key,
                    actor=actor,
                    action=action,
                    details_json=details,
                )
                session.add(audit)
        except Exception as exc:
            logger.warning(f"Could not record audit log for '{flag_key}' to DB: {exc}")


# Global Singleton Instance
feature_flag_engine = FeatureFlagEngine()
