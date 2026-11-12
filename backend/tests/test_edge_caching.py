"""
backend/tests/test_edge_caching.py — Test Suite for Dynamic Edge Caching & Ingress Headers
PSE Quant SaaS — Lab 18
"""

import pytest
from fastapi.testclient import TestClient
from pse_quant.api.main import app
from pse_quant.edge.manager import edge_cache_manager


@pytest.fixture(autouse=True)
def clean_edge():
    """Resets edge cache telemetry counters before and after each test."""
    edge_cache_manager.reset()
    yield
    edge_cache_manager.reset()


def test_public_stock_cache_control_headers():
    """Public stock endpoints emit RFC 7234 public cache-control directives and ETags."""
    client = TestClient(app)
    res = client.get("/api/v1/stocks")
    assert res.status_code == 200

    # Cache-Control directives
    cc = res.headers.get("Cache-Control", "")
    assert "public" in cc
    assert "s-maxage=" in cc
    assert "stale-while-revalidate=" in cc

    # Cryptographic ETag
    etag = res.headers.get("ETag")
    assert etag is not None
    assert etag.startswith('"') and etag.endswith('"')

    # Edge surrogate tags & POP telemetry
    assert "stocks" in res.headers.get("Surrogate-Key", "")
    assert res.headers.get("X-Cache-Status") == "MISS"
    assert res.headers.get("X-Edge-Origin-POP") == "MNL"


def test_conditional_get_returns_304_not_modified():
    """Client sending matching If-None-Match receives 304 Not Modified with zero body payload."""
    client = TestClient(app)
    # 1. First fetch
    res1 = client.get("/api/v1/stocks")
    assert res1.status_code == 200
    etag = res1.headers.get("ETag")
    assert etag is not None

    # 2. Conditional fetch with ETag
    res2 = client.get("/api/v1/stocks", headers={"If-None-Match": etag})
    assert res2.status_code == 304
    assert res2.text == ""  # Empty body
    assert res2.headers.get("ETag") == etag
    assert res2.headers.get("X-Cache-Status") == "REVALIDATED"


def test_conditional_get_mismatched_etag_returns_200():
    """Mismatched If-None-Match triggers full 200 OK with fresh response payload."""
    client = TestClient(app)
    res = client.get("/api/v1/stocks", headers={"If-None-Match": '"outdated_hash_123"'})
    assert res.status_code == 200
    assert len(res.text) > 0
    assert res.headers.get("X-Cache-Status") == "MISS"


def test_ticker_surrogate_key_tagging():
    """Single-stock endpoint injects stock-specific surrogate keys for targeted CDN invalidation."""
    client = TestClient(app)
    res = client.get("/api/v1/stocks/DMC")
    assert res.status_code == 200

    surrogate_key = res.headers.get("Surrogate-Key", "")
    assert "stock-DMC" in surrogate_key
    assert "stocks" in surrogate_key


def test_private_endpoint_cache_control():
    """Admin and private endpoints strictly inject no-store / private directives."""
    client = TestClient(app)
    res = client.get("/api/v1/admin/cache/telemetry")
    assert res.status_code == 200

    cc = res.headers.get("Cache-Control", "")
    assert "private" in cc
    assert "no-store" in cc or "no-cache" in cc


def test_multi_region_pop_detection():
    """Extracts Cloudflare CF-Ray or edge region headers into X-Edge-Origin-POP."""
    client = TestClient(app)

    # Cloudflare Singapore POP
    res_sin = client.get("/api/v1/stocks", headers={"CF-Ray": "893bc1a2-SIN"})
    assert res_sin.headers.get("X-Edge-Origin-POP") == "SIN"

    # Hong Kong POP via edge region header
    res_hkg = client.get("/api/v1/stocks", headers={"X-Edge-Region": "HKG"})
    assert res_hkg.headers.get("X-Edge-Origin-POP") == "HKG"


def test_admin_cache_purge_and_telemetry():
    """Admin purge endpoint records invalidation events and increments telemetry."""
    client = TestClient(app)

    # Make 1 miss and 1 revalidation
    res1 = client.get("/api/v1/stocks")
    etag = res1.headers.get("ETag")
    client.get("/api/v1/stocks", headers={"If-None-Match": etag})

    # Purge tags
    res_purge = client.post("/api/v1/admin/cache/purge", json={
        "tags": ["stock-DMC", "pse-market"],
        "actor": "sre_admin",
    })
    assert res_purge.status_code == 200
    assert res_purge.json()["count"] == 2
    assert "stock-DMC" in res_purge.json()["tags_purged"]

    # Verify telemetry
    res_telemetry = client.get("/api/v1/admin/cache/telemetry")
    assert res_telemetry.status_code == 200
    telemetry = res_telemetry.json()
    assert telemetry["total_requests_evaluated"] >= 2
    assert telemetry["not_modified_304_served"] >= 1
    assert telemetry["cache_miss_200_served"] >= 1
    assert telemetry["purged_tags_count"] == 2
    assert telemetry["last_purged_tag"] == "pse-market"
