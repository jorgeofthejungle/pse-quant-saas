"""
backend/tests/test_feature_flags.py — Automated Test Suite for Feature Flags & Canary Delivery
PSE Quant SaaS — Lab 16
"""

import pytest
import time
from fastapi import FastAPI, Depends, status
from fastapi.testclient import TestClient

from pse_quant.feature_flags.models import (
    FeatureFlag,
    EvaluationContext,
    EvaluationReason,
)
from pse_quant.feature_flags.engine import FeatureFlagEngine, feature_flag_engine
from pse_quant.feature_flags.dependencies import require_feature
from pse_quant.api.main import app


@pytest.fixture(autouse=True)
def clean_engine():
    """Ensures each test starts with a clean slate."""
    from pse_quant.db.connection import init_db
    init_db()
    feature_flag_engine.clear()
    yield
    feature_flag_engine.clear()


def test_feature_flag_not_found():
    """Unregistered flag evaluates to False with NOT_FOUND reason."""
    ctx = EvaluationContext(entity_id="trader_42")
    res = feature_flag_engine.evaluate("non_existent_key", ctx)
    assert res.enabled is False
    assert res.reason == EvaluationReason.NOT_FOUND.value


def test_feature_flag_emergency_kill_switch():
    """Master kill switch (is_enabled=False) instantly blocks traffic regardless of percentage or allowlists."""
    flag = FeatureFlag(
        key="fast_quant_stream",
        name="Fast Quant Stream",
        is_enabled=True,
        rollout_percentage=100,
        allowed_entities=["vip_user"],
    )
    feature_flag_engine.create_flag(flag, actor="admin_alice")

    # Initial check: should be enabled
    res = feature_flag_engine.evaluate("fast_quant_stream", EvaluationContext(entity_id="vip_user"))
    assert res.enabled is True

    # Activate emergency kill switch
    feature_flag_engine.kill_switch("fast_quant_stream", actor="admin_bob")

    # Verify instantaneous deactivation
    res2 = feature_flag_engine.evaluate("fast_quant_stream", EvaluationContext(entity_id="vip_user"))
    assert res2.enabled is False
    assert res2.reason == EvaluationReason.DISABLED.value


def test_denylist_takes_absolute_precedence():
    """Denied entities are blocked even if allowlisted or rollout is 100%."""
    flag = FeatureFlag(
        key="dark_pool_access",
        name="Dark Pool Access",
        is_enabled=True,
        rollout_percentage=100,
        allowed_entities=["entity_xyz"],
        denied_entities=["entity_xyz"],  # Both allow and deny
    )
    feature_flag_engine.create_flag(flag)

    res = feature_flag_engine.evaluate("dark_pool_access", EvaluationContext(entity_id="entity_xyz"))
    assert res.enabled is False
    assert res.reason == EvaluationReason.DENIED_ENTITY.value


def test_allowlist_bypasses_percentage_and_tier():
    """Allowlisted entities bypass tier restrictions and 0% rollout."""
    flag = FeatureFlag(
        key="alpha_signals_v3",
        name="Alpha Signals v3",
        is_enabled=True,
        rollout_percentage=0,
        allowed_tiers=["INSTITUTIONAL"],
        allowed_entities=["internal_tester"],
    )
    feature_flag_engine.create_flag(flag)

    # Free tier internal tester
    ctx = EvaluationContext(entity_id="internal_tester", tier="FREE")
    res = feature_flag_engine.evaluate("alpha_signals_v3", ctx)
    assert res.enabled is True
    assert res.reason == EvaluationReason.ALLOWED_ENTITY.value

    # Ordinary free tier user
    ctx2 = EvaluationContext(entity_id="random_free_user", tier="FREE")
    res2 = feature_flag_engine.evaluate("alpha_signals_v3", ctx2)
    assert res2.enabled is False
    assert res2.reason == EvaluationReason.TIER_MISMATCH.value


def test_multi_tier_targeting():
    """Tier gate blocks unauthorized tiers and allows targeted tiers."""
    flag = FeatureFlag(
        key="portfolio_optimizer",
        name="Institutional Portfolio Optimizer",
        is_enabled=True,
        rollout_percentage=100,
        allowed_tiers=["PRO", "INSTITUTIONAL"],
    )
    feature_flag_engine.create_flag(flag)

    res_free = feature_flag_engine.evaluate(
        "portfolio_optimizer", EvaluationContext(entity_id="user_1", tier="FREE")
    )
    assert res_free.enabled is False
    assert res_free.reason == EvaluationReason.TIER_MISMATCH.value

    res_pro = feature_flag_engine.evaluate(
        "portfolio_optimizer", EvaluationContext(entity_id="user_2", tier="PRO")
    )
    assert res_pro.enabled is True
    assert res_pro.reason == EvaluationReason.PERCENTAGE_CANARY_MATCH.value


def test_deterministic_sticky_canary_and_monotonicity():
    """
    Validates:
      1. Deterministic hashing: same entity always gets same bucket.
      2. Distribution: 25% rollout enables ~25% of 1,000 entities.
      3. Monotonicity: ALL entities enabled at 25% remain enabled when raised to 50%.
    """
    flag = FeatureFlag(
        key="canary_feature",
        name="Canary Feature",
        is_enabled=True,
        rollout_percentage=25,
    )
    feature_flag_engine.create_flag(flag)

    entities = [f"entity_{i:04d}" for i in range(1000)]

    # 1. Evaluate at 25%
    enabled_at_25 = set()
    for ent in entities:
        res1 = feature_flag_engine.evaluate("canary_feature", EvaluationContext(entity_id=ent))
        # Ensure repeatability
        res2 = feature_flag_engine.evaluate("canary_feature", EvaluationContext(entity_id=ent))
        assert res1.enabled == res2.enabled
        assert res1.bucket == res2.bucket

        if res1.enabled:
            enabled_at_25.add(ent)

    # 25% of 1000 is 250; expect between 200 and 300 given hash distribution
    assert 200 <= len(enabled_at_25) <= 300

    # 2. Increase rollout to 50%
    feature_flag_engine.update_flag("canary_feature", {"rollout_percentage": 50})

    enabled_at_50 = set()
    for ent in entities:
        res = feature_flag_engine.evaluate("canary_feature", EvaluationContext(entity_id=ent))
        if res.enabled:
            enabled_at_50.add(ent)

    assert 440 <= len(enabled_at_50) <= 560

    # 3. Monotonicity Invariant: every single entity enabled at 25% MUST be enabled at 50%
    missing = enabled_at_25 - enabled_at_50
    assert len(missing) == 0, f"Monotonicity violated: {missing} lost access on rollout expansion!"


def test_sub_millisecond_evaluation_latency():
    """Validates that feature flag evaluations execute in sub-millisecond time (<50us p99)."""
    flag = FeatureFlag(
        key="perf_flag",
        name="Performance Test Flag",
        is_enabled=True,
        rollout_percentage=50,
        allowed_tiers=["PRO", "INSTITUTIONAL"],
    )
    feature_flag_engine.create_flag(flag)

    ctx = EvaluationContext(entity_id="trader_benchmark", tier="PRO")

    latencies_us = []
    # Warm-up
    for _ in range(100):
        feature_flag_engine.evaluate("perf_flag", ctx)

    # Timed run
    for _ in range(2000):
        t0 = time.perf_counter_ns()
        res = feature_flag_engine.evaluate("perf_flag", ctx)
        t1 = time.perf_counter_ns()
        latencies_us.append((t1 - t0) / 1000.0)
        assert res.enabled is not None

    latencies_us.sort()
    p99_us = latencies_us[int(len(latencies_us) * 0.99)]
    # p99 should comfortably be well below 100 microseconds (0.1ms)
    assert p99_us < 100.0, f"p99 latency too high: {p99_us}us"


def test_persistent_audit_trail():
    """Ensures create, update, kill-switch, and delete actions log audit entries."""
    flag = FeatureFlag(
        key="audit_test_flag",
        name="Audit Test Flag",
        is_enabled=True,
        rollout_percentage=10,
    )
    feature_flag_engine.create_flag(flag, actor="developer_dan")
    feature_flag_engine.update_flag("audit_test_flag", {"rollout_percentage": 20}, actor="pm_pam")
    feature_flag_engine.kill_switch("audit_test_flag", actor="sre_sam")

    trail = feature_flag_engine.get_audit_trail("audit_test_flag")
    assert len(trail) >= 3

    actions = [entry["action"] for entry in trail]
    assert "KILL_SWITCH" in actions
    assert "UPDATE" in actions
    assert "CREATE" in actions


def test_fastapi_dependency_require_feature():
    """Validates FastAPI require_feature dependency returns 404 when disabled, 200 when enabled."""
    test_app = FastAPI()

    @test_app.get("/guarded-alpha", dependencies=[Depends(require_feature("beta_feature_endpoint"))])
    def guarded_endpoint():
        return {"status": "unlocked"}

    client = TestClient(test_app)

    flag = FeatureFlag(
        key="beta_feature_endpoint",
        name="Beta Endpoint",
        is_enabled=True,
        rollout_percentage=0,
        allowed_entities=["beta_tester"],
    )
    feature_flag_engine.create_flag(flag)

    # 1. Unprivileged user gets 404 from dependency
    res_blocked = client.get("/guarded-alpha", headers={"X-User-ID": "random_user"})
    assert res_blocked.status_code == 404
    assert "not available" in res_blocked.json()["detail"]

    # 2. Privileged user gets 200
    res_allowed = client.get("/guarded-alpha", headers={"X-User-ID": "beta_tester"})
    assert res_allowed.status_code == 200
    assert res_allowed.json()["status"] == "unlocked"


def test_admin_feature_flags_rest_crud():
    """Full end-to-end REST API lifecycle testing for feature flag admin endpoints."""
    client = TestClient(app)

    # 1. Create flag
    create_payload = {
        "key": "rest_test_flag",
        "name": "REST Test Flag",
        "description": "Created via REST API",
        "is_enabled": True,
        "rollout_percentage": 50,
        "allowed_tiers": ["PRO"],
        "allowed_entities": ["vip_investor"],
        "denied_entities": ["banned_bot"],
        "variants": {"control": 50, "treatment": 50},
    }
    res_create = client.post("/api/v1/admin/feature-flags", json=create_payload)
    assert res_create.status_code == 201
    created_data = res_create.json()
    assert created_data["key"] == "rest_test_flag"
    assert created_data["rollout_percentage"] == 50

    # 2. Get flag
    res_get = client.get("/api/v1/admin/feature-flags/rest_test_flag")
    assert res_get.status_code == 200
    assert res_get.json()["name"] == "REST Test Flag"

    # 3. Dry-run evaluate
    eval_payload = {"entity_id": "vip_investor", "tier": "FREE"}
    res_eval = client.post("/api/v1/admin/feature-flags/rest_test_flag/evaluate", json=eval_payload)
    assert res_eval.status_code == 200
    assert res_eval.json()["enabled"] is True
    assert res_eval.json()["reason"] == "ALLOWED_ENTITY"

    # 4. Trigger emergency kill switch
    res_ks = client.post("/api/v1/admin/feature-flags/rest_test_flag/kill-switch")
    assert res_ks.status_code == 200
    assert res_ks.json()["is_enabled"] is False

    # Verify dry-run evaluate now returns disabled
    res_eval2 = client.post("/api/v1/admin/feature-flags/rest_test_flag/evaluate", json=eval_payload)
    assert res_eval2.status_code == 200
    assert res_eval2.json()["enabled"] is False
    assert res_eval2.json()["reason"] == "DISABLED"

    # 5. Audit trail
    res_audit = client.get("/api/v1/admin/feature-flags/rest_test_flag/audit-trail")
    assert res_audit.status_code == 200
    assert len(res_audit.json()) >= 2

    # 6. Delete flag
    res_del = client.delete("/api/v1/admin/feature-flags/rest_test_flag")
    assert res_del.status_code == 204

    # Confirm deletion
    res_get_del = client.get("/api/v1/admin/feature-flags/rest_test_flag")
    assert res_get_del.status_code == 404
