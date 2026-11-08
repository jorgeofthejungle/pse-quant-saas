"""
backend/tests/test_cache_aside.py — Multi-Tier Cache-Aside & Stampede Protection Tests
=====================================================================================
Verifies:
  1. CacheEngine L1 in-memory get, set, TTL expiry, and hit/miss telemetry.
  2. Bounded capacity with Least-Recently-Used (LRU) eviction.
  3. Single-Flight Mutex Locking preventing Cache Stampedes (Dog-Piling) across 30 concurrent threads.
  4. Pattern and tag-based automated cache invalidation.
  5. StockService integration (first call miss -> second call hit).
  6. Admin observability (/admin/cache/metrics) and flush endpoints (/admin/cache/flush).
"""

from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient

from pse_quant.cache.engine import CacheEngine
from pse_quant.cache import global_cache
from pse_quant.services.stock_service import StockService
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.db.connection import get_db_session
from pse_quant.api.main import app


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


# ── 1. CacheEngine Core Math & Behavior Tests ───────────────────

def test_cache_get_set_and_metrics():
    """Tests basic get, set, hit, miss, and hit ratio computation."""
    cache = CacheEngine(max_entries=100, default_ttl_seconds=60.0)

    # Initial miss
    assert cache.get("missing_key") is None
    m = cache.get_metrics()
    assert m["hits"] == 0
    assert m["misses"] == 1
    assert m["hit_ratio"] == 0.0

    # Set and hit
    cache.set("user:123", {"name": "Juan"}, ttl_seconds=60.0)
    val = cache.get("user:123")
    assert val == {"name": "Juan"}

    m = cache.get_metrics()
    assert m["hits"] == 1
    assert m["misses"] == 1
    assert m["hit_ratio"] == 0.5


def test_cache_ttl_expiration():
    """Verifies that expired items are evicted and return None."""
    cache = CacheEngine(max_entries=100, default_ttl_seconds=10.0)
    t0 = 1000.0

    cache.set("temp_key", "temporary_value", ttl_seconds=5.0, jitter_pct=0.0, now=t0)

    # Valid before expiration
    assert cache.get("temp_key", now=t0 + 4.0) == "temporary_value"

    # Expired after 5 seconds
    assert cache.get("temp_key", now=t0 + 6.0) is None
    assert cache.get_metrics()["evictions"] == 1


def test_cache_lru_bounded_eviction():
    """Verifies that least recently used items are evicted when capacity is reached."""
    cache = CacheEngine(max_entries=3)
    t0 = 1000.0

    cache.set("k1", "v1", now=t0)
    cache.set("k2", "v2", now=t0 + 1.0)
    cache.set("k3", "v3", now=t0 + 2.0)

    # Access k1 and k2 to make k3 the least recently accessed
    cache.get("k1", now=t0 + 3.0)
    cache.get("k2", now=t0 + 4.0)

    # Add 4th item (exceeds max_entries=3)
    cache.set("k4", "v4", now=t0 + 5.0)

    # k3 must have been evicted as LRU
    assert cache.get("k3", now=t0 + 6.0) is None
    assert cache.get("k1", now=t0 + 6.0) == "v1"
    assert cache.get("k2", now=t0 + 6.0) == "v2"
    assert cache.get("k4", now=t0 + 6.0) == "v4"


def test_pattern_and_tag_invalidation():
    """Verifies glob pattern and tag-based invalidation."""
    cache = CacheEngine(max_entries=100)

    cache.set("stock:profile:AREIT", {"ticker": "AREIT"}, tags=["stock", "profile"])
    cache.set("stock:profile:BDO", {"ticker": "BDO"}, tags=["stock", "profile"])
    cache.set("stock:rankings:unified", [{"rank": 1}], tags=["stock", "rankings"])
    cache.set("user:session:99", {"user_id": 99}, tags=["auth"])

    # Pattern invalidation: stock:profile:*
    cleared = cache.invalidate_pattern("stock:profile:*")
    assert cleared == 2
    assert cache.get("stock:profile:AREIT") is None
    assert cache.get("stock:profile:BDO") is None
    assert cache.get("stock:rankings:unified") is not None

    # Tag invalidation: auth
    tag_cleared = cache.invalidate_tag("auth")
    assert tag_cleared == 1
    assert cache.get("user:session:99") is None


# ── 2. Single-Flight Cache Stampede (Dog-Pile) Protection ────────

def test_single_flight_stampede_protection():
    """
    Simulates 30 concurrent threads requesting the exact same expired key.
    The single-flight mutex must ensure the expensive origin fetcher runs
    EXACTLY ONCE, preventing origin server collapse.
    """
    cache = CacheEngine(max_entries=100)
    origin_call_count = 0

    def expensive_fetcher():
        nonlocal origin_call_count
        origin_call_count += 1
        time.sleep(0.05)  # Simulate DB query & quant math latency
        return {"data": "expensive_result"}

    def worker_call():
        return cache.get_or_compute(
            key="hot_stock:DMC",
            fetcher_fn=expensive_fetcher,
            ttl_seconds=60.0,
        )

    # Launch 30 threads simultaneously targeting the exact same key
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(worker_call) for _ in range(30)]
        results = [f.result() for f in futures]

    # All 30 callers got the correct result
    for res in results:
        assert res == {"data": "expensive_result"}

    # CRITICAL: Fetcher was executed only ONCE!
    assert origin_call_count == 1


# ── 3. StockService Cache-Aside Integration ──────────────────────

def test_stock_service_profile_caching():
    """Verifies that StockService.get_stock_profile uses cache-aside lazy loading."""
    global_cache.flush_all()
    global_cache.reset_metrics()

    with get_db_session() as session:
        # First call: Cache Miss (Origin DB Read + Quant Math)
        p1 = StockService.get_stock_profile(session, "AREIT")
        assert p1 is not None
        assert p1["ticker"] == "AREIT"

        m1 = global_cache.get_metrics()
        assert m1["hits"] == 0
        assert m1["misses"] >= 1

        # Second call: Cache Hit (Instant <1ms response)
        p2 = StockService.get_stock_profile(session, "AREIT")
        assert p2 == p1

        m2 = global_cache.get_metrics()
        assert m2["hits"] >= 1


def test_stock_service_rankings_caching():
    """Verifies that StockService.get_rankings uses cache-aside lazy loading."""
    global_cache.flush_all()
    global_cache.reset_metrics()

    with get_db_session() as session:
        r1 = StockService.get_rankings(session, portfolio_type="unified")
        assert isinstance(r1, list)

        # Second call hits cache
        r2 = StockService.get_rankings(session, portfolio_type="unified")
        assert r2 == r1
        assert global_cache.get_metrics()["hits"] >= 1


# ── 4. Admin Telemetry & Flush Endpoints ─────────────────────────

def test_admin_cache_metrics_endpoint(admin_client):
    """Verifies GET /admin/cache/metrics."""
    res = admin_client.get("/api/v1/admin/cache/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "active_entries" in data
    assert "hits" in data
    assert "misses" in data
    assert "hit_ratio" in data


def test_admin_cache_flush_endpoint(admin_client):
    """Verifies POST /admin/cache/flush."""
    global_cache.set("test:admin:1", "data")
    global_cache.set("test:admin:2", "data")

    # Flush with pattern
    res = admin_client.post("/api/v1/admin/cache/flush?pattern=test:admin:*")
    assert res.status_code == 200
    assert res.json()["keys_cleared"] == 2

    # Flush all
    global_cache.set("another:key", 123)
    res_all = admin_client.post("/api/v1/admin/cache/flush")
    assert res_all.status_code == 200
    assert res_all.json()["metrics"]["active_entries"] == 0
