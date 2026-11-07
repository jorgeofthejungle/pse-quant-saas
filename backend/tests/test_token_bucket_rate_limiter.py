"""
backend/tests/test_token_bucket_rate_limiter.py — Multi-Tier Token Bucket Test Suite
==================================================================================
Verifies:
  1. Token Bucket mathematical correctness (burst consumption, continuous refill, cap limits).
  2. Multi-tier quota governance (Anonymous, Free, Paid, Admin).
  3. Thread safety under concurrent token depletion.
  4. Client fingerprinting (X-Admin-Key, JWT Bearer, Client IP).
  5. FastAPI middleware behavior (X-RateLimit headers, HTTP 429 throttling, Retry-After).
  6. Rate limiting diagnostics endpoint (/api/v1/rate-limit/status).
"""

from __future__ import annotations
import math
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from pse_quant.api.rate_limiting.token_bucket import (
    TokenBucket,
    TokenBucketStore,
    ClientTier,
    TIER_QUOTAS,
)
from pse_quant.api.rate_limiting.fingerprint import resolve_client_fingerprint
from pse_quant.api.rate_limiting.middleware import TokenBucketMiddleware
from pse_quant.services.auth_service import create_access_token, ADMIN_MASTER_KEY
from pse_quant.api.main import app


@pytest.fixture
def test_client():
    return TestClient(app)


# ── 1. Pure Algorithm & Math Tests ──────────────────────────────

def test_token_bucket_burst_and_depletion():
    """Verifies that a bucket permits bursts up to capacity and blocks once depleted."""
    bucket = TokenBucket(capacity=5.0, refill_rate_per_sec=1.0)
    t0 = 1000.0

    # First 5 tokens consumed immediately
    for i in range(5):
        allowed, remaining, retry_after, reset_sec = bucket.consume(cost=1.0, now=t0)
        assert allowed is True
        assert round(remaining) == 4 - i
        assert retry_after == 0.0

    # 6th token must be rejected
    allowed, remaining, retry_after, reset_sec = bucket.consume(cost=1.0, now=t0)
    assert allowed is False
    assert remaining == 0.0
    assert retry_after > 0.0


def test_token_bucket_continuous_refill():
    """Verifies that tokens replenish linearly with elapsed time."""
    bucket = TokenBucket(capacity=10.0, refill_rate_per_sec=2.0)
    t0 = 1000.0

    # Drain bucket completely
    for _ in range(10):
        bucket.consume(cost=1.0, now=t0)

    # 2.5 seconds later -> 2.5 * 2.0 = 5 tokens refilled
    t1 = t0 + 2.5
    allowed, remaining, retry_after, _ = bucket.consume(cost=4.0, now=t1)
    assert allowed is True
    assert round(remaining, 1) == 1.0  # 5 refilled - 4 consumed = 1 remaining


def test_token_bucket_capacity_cap():
    """Verifies that bucket never holds more than its maximum capacity."""
    bucket = TokenBucket(capacity=10.0, refill_rate_per_sec=2.0)
    t0 = 1000.0
    t_distant_future = t0 + 10000.0

    # Even after a long time, remaining tokens cannot exceed capacity
    allowed, remaining, retry_after, reset_sec = bucket.consume(cost=1.0, now=t_distant_future)
    assert allowed is True
    assert remaining <= 9.0


# ── 2. Multi-Tier Quota Presets ─────────────────────────────────

def test_tier_quota_proportions():
    """Asserts institutional quota hierarchy: Admin > Paid > Free > Anonymous."""
    anon_q = TIER_QUOTAS[ClientTier.ANONYMOUS]
    free_q = TIER_QUOTAS[ClientTier.FREE]
    paid_q = TIER_QUOTAS[ClientTier.PAID]
    admin_q = TIER_QUOTAS[ClientTier.ADMIN]

    assert anon_q.capacity < free_q.capacity < paid_q.capacity < admin_q.capacity
    assert anon_q.refill_rate_per_sec < free_q.refill_rate_per_sec < paid_q.refill_rate_per_sec < admin_q.refill_rate_per_sec


# ── 3. Thread Safety Under Concurrent Load ───────────────────────

def test_token_bucket_thread_safety():
    """Verifies that concurrent threads consuming from a bucket do not produce race conditions."""
    capacity = 100.0
    bucket = TokenBucket(capacity=capacity, refill_rate_per_sec=0.0)  # No refill during test
    now = time.time()

    success_count = 0
    fail_count = 0

    def attempt_consume():
        nonlocal success_count, fail_count
        allowed, _, _, _ = bucket.consume(cost=1.0, now=now)
        if allowed:
            success_count += 1
        else:
            fail_count += 1

    # Launch 150 threads simultaneously targeting a 100-token bucket
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(attempt_consume) for _ in range(150)]
        for f in futures:
            f.result()

    assert success_count == 100
    assert fail_count == 50
    assert bucket.tokens == 0.0


# ── 4. Fingerprint & Tier Resolution Tests ───────────────────────

def test_resolve_client_fingerprint_admin_key():
    from unittest.mock import Mock
    req = Mock()
    req.headers = {"X-Admin-Key": ADMIN_MASTER_KEY}
    client_key, tier = resolve_client_fingerprint(req)
    assert tier == ClientTier.ADMIN
    assert client_key == "admin:master"


def test_resolve_client_fingerprint_jwt_paid_tier():
    from unittest.mock import Mock
    token = create_access_token({"sub": "42", "role": "member", "tier": "paid"})
    req = Mock()
    req.headers = {"Authorization": f"Bearer {token}"}
    client_key, tier = resolve_client_fingerprint(req)
    assert tier == ClientTier.PAID
    assert "user:paid:42" in client_key


def test_resolve_client_fingerprint_jwt_free_tier():
    from unittest.mock import Mock
    token = create_access_token({"sub": "99", "role": "member", "tier": "free"})
    req = Mock()
    req.headers = {"Authorization": f"Bearer {token}"}
    client_key, tier = resolve_client_fingerprint(req)
    assert tier == ClientTier.FREE
    assert "user:free:99" in client_key


def test_resolve_client_fingerprint_anonymous_ip():
    from unittest.mock import Mock
    req = Mock()
    req.headers = {"X-Forwarded-For": "112.198.10.5, 10.0.0.1"}
    req.client = None
    client_key, tier = resolve_client_fingerprint(req)
    assert tier == ClientTier.ANONYMOUS
    assert client_key == "ip:112.198.10.5"


# ── 5. End-to-End Middleware & Throttling (HTTP 429) ─────────────

def test_middleware_injects_x_ratelimit_headers(test_client):
    """Verifies that normal requests receive standard X-RateLimit headers."""
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200

    # Non-exempt endpoint
    response = test_client.get("/api/v1/rate-limit/status")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Tier" in response.headers


def test_middleware_throttles_exhausted_bucket():
    """
    Creates an isolated test application with a tiny 3-token bucket
    and verifies that the 4th request receives HTTP 429 with Retry-After.
    """
    isolated_app = FastAPI()
    isolated_store = TokenBucketStore()

    # Pre-seed a tight bucket for test IP
    tight_bucket = TokenBucket(capacity=3.0, refill_rate_per_sec=0.1)
    isolated_store._buckets["ip:192.0.2.1"] = tight_bucket
    isolated_store._tier_map["ip:192.0.2.1"] = ClientTier.ANONYMOUS

    isolated_app.add_middleware(TokenBucketMiddleware, store=isolated_store)

    @isolated_app.get("/test-endpoint")
    def test_endpoint():
        return {"ok": True}

    client = TestClient(isolated_app)
    headers = {"X-Forwarded-For": "192.0.2.1"}

    # 3 requests allowed
    for _ in range(3):
        res = client.get("/test-endpoint", headers=headers)
        assert res.status_code == 200

    # 4th request must be rejected with HTTP 429
    res4 = client.get("/test-endpoint", headers=headers)
    assert res4.status_code == 429
    data = res4.json()
    assert data["error"] == "TooManyRequests"
    assert "Retry-After" in res4.headers
    assert int(res4.headers["Retry-After"]) >= 1
    assert res4.headers["X-RateLimit-Remaining"] == "0"


# ── 6. Diagnostics Route Inspection ─────────────────────────────

def test_rate_limit_diagnostics_endpoint(test_client):
    """Verifies that the /api/v1/rate-limit/status route returns the client tier matrix."""
    response = test_client.get("/api/v1/rate-limit/status")
    assert response.status_code == 200
    data = response.json()
    assert "client_key" in data
    assert "tier" in data
    assert "burst_capacity" in data
    assert "refill_rate_per_sec" in data
    assert "tier_matrix" in data
    assert "anonymous" in data["tier_matrix"]
    assert "paid" in data["tier_matrix"]
    assert "admin" in data["tier_matrix"]
