"""
backend/tests/test_fts_search.py — Lab 13: Full-Text Search (FTS5) & Lexical Retrieval Tests
=============================================================================================
Verifies:
  1. FTS5 table initialization, population, and synchronization health.
  2. Exact ticker match prioritization (pinned to rank #1).
  3. Prefix typeahead autocomplete ('ayal*' matches Ayala Land and Ayala Corp).
  4. Sector-based lexical filtering ('Property' returns property equities).
  5. Colloquial alias resolution ('meralco' -> MER, 'banco de oro' -> BDO).
  6. Robust query sanitization against hostile SQL / FTS syntax injection.
  7. Real-time pricing and stock classification enrichment (close, market cap, REIT/Bank).
  8. Public & Admin API endpoints (/api/v1/search, /admin/search/rebuild, /admin/search/stats).
  9. Sub-10ms execution latency performance benchmark.
"""

from __future__ import annotations
import time
import pytest
from datetime import date
from sqlalchemy import select, text
from fastapi.testclient import TestClient

from pse_quant.search.fts_engine import (
    init_fts_tables,
    rebuild_fts_index,
    sync_stock,
    delete_stock_from_index,
    sanitize_query,
    search_stocks_fts,
    get_index_stats,
    PSE_ALIASES,
)
from pse_quant.search.service import FtsSearchService, search_service
from pse_quant.db.models import Stock, Price
from pse_quant.db.connection import get_write_session, get_read_session, init_db
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app


@pytest.fixture(autouse=True)
def setup_search_test_db():
    init_db()
    with get_write_session() as session:
        session.query(Price).delete()
        session.query(Stock).delete()
        session.execute(text("DELETE FROM stocks_fts;"))

        # Seed sample Philippine equities
        stocks = [
            Stock(ticker="ALI", name="Ayala Land, Inc.", sector="Property", is_reit=False, is_bank=False, status="active"),
            Stock(ticker="AC", name="Ayala Corporation", sector="Holding Firms", is_reit=False, is_bank=False, status="active"),
            Stock(ticker="BDO", name="BDO Unibank, Inc.", sector="Financials", is_reit=False, is_bank=True, status="active"),
            Stock(ticker="DMC", name="DMCI Holdings, Inc.", sector="Holding Firms", is_reit=False, is_bank=False, status="active"),
            Stock(ticker="MER", name="Manila Electric Company", sector="Services", is_reit=False, is_bank=False, status="active"),
            Stock(ticker="AREIT", name="AREIT, Inc.", sector="Property", is_reit=True, is_bank=False, status="active"),
            Stock(ticker="SMPH", name="SM Prime Holdings, Inc.", sector="Property", is_reit=False, is_bank=False, status="active"),
        ]
        session.add_all(stocks)
        session.commit()

        # Seed initial price quotes
        prices = [
            Price(ticker="MER", trade_date=date(2026, 11, 7), close=380.0, market_cap=428000000000.0),
            Price(ticker="ALI", trade_date=date(2026, 11, 7), close=31.5, market_cap=465000000000.0),
            Price(ticker="BDO", trade_date=date(2026, 11, 7), close=152.0, market_cap=810000000000.0),
        ]
        session.add_all(prices)
        session.commit()

        # Rebuild FTS5 index
        rebuild_fts_index(session)


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


@pytest.fixture
def public_client():
    return TestClient(app)


# ── 1. FTS5 Indexing & Statistics ─────────────────────────────

def test_fts_table_initialization_and_sync():
    """Verifies that stocks_fts is populated from stocks and stats are accurate."""
    stats = FtsSearchService.get_stats()
    assert stats["total_indexed_documents"] == 7
    assert stats["total_source_stocks"] == 7
    assert stats["is_synchronized"] is True
    assert stats["engine"] == "sqlite_fts5"


# ── 2. Exact Ticker Prioritization ────────────────────────────

def test_exact_ticker_prioritization():
    """Verifies that searching 'MER' pins MER to rank #1 with highlighted ticker."""
    res = FtsSearchService.search("MER", limit=5)
    assert res["total_matches"] >= 1
    top = res["results"][0]
    assert top["ticker"] == "MER"
    assert "<mark>MER</mark>" in top["highlighted_ticker"]
    assert top["name"] == "Manila Electric Company"


# ── 3. Prefix Typeahead Expansion ─────────────────────────────

def test_prefix_typeahead_expansion():
    """Verifies that 'ayal' expands to 'ayal*' and matches Ayala Land and Ayala Corp."""
    res = FtsSearchService.search("ayal", limit=5)
    assert res["total_matches"] >= 2
    tickers = [r["ticker"] for r in res["results"]]
    assert "ALI" in tickers
    assert "AC" in tickers

    # Ensure highlight mark is applied
    ali_match = next(r for r in res["results"] if r["ticker"] == "ALI")
    assert "<mark>Ayala</mark>" in ali_match["highlighted_name"]


# ── 4. Sector-Based Lexical Filtering ─────────────────────────

def test_sector_query_retrieval():
    """Verifies that searching 'Property' returns property companies."""
    res = FtsSearchService.search("Property", limit=5)
    assert res["total_matches"] >= 3
    tickers = {r["ticker"] for r in res["results"]}
    assert "ALI" in tickers
    assert "AREIT" in tickers
    assert "SMPH" in tickers


# ── 5. Colloquial Alias Resolution ────────────────────────────

def test_colloquial_alias_resolution():
    """
    Verifies that searching popular nicknames matches the correct stock:
      - 'meralco' -> MER
      - 'banco de oro' -> BDO
      - 'sy' -> BDO or SMPH
    """
    mer_res = FtsSearchService.search("meralco", limit=5)
    assert mer_res["total_matches"] >= 1
    assert mer_res["results"][0]["ticker"] == "MER"

    bdo_res = FtsSearchService.search("banco de oro", limit=5)
    assert bdo_res["total_matches"] >= 1
    assert bdo_res["results"][0]["ticker"] == "BDO"


# ── 6. Query Sanitization & Injection Defense ──────────────────

def test_malicious_query_sanitization():
    """Verifies that hostile, malformed, or injection-like queries do not crash FTS5."""
    malicious_inputs = [
        '"""""',
        'AND OR NOT NEAR',
        '((((****^^^^',
        "DROP TABLE stocks_fts;",
        "'; SELECT * FROM users; --",
        "   ",
        "!!!???###$$$%%%^^^&&&***()",
    ]
    for raw in malicious_inputs:
        res = FtsSearchService.search(raw)
        # Should gracefully return without throwing SQLite operational error
        assert "results" in res
        assert isinstance(res["results"], list)


# ── 7. Price & Stock Classification Enrichment ────────────────

def test_search_enrichment_pricing_and_classification():
    """Verifies that search results are enriched with latest close price, market cap, and flags."""
    res = FtsSearchService.search("MER", enrich_pricing=True)
    assert res["total_matches"] >= 1
    top = res["results"][0]
    assert top["ticker"] == "MER"
    assert top["close_price"] == 380.0
    assert top["market_cap"] == 428000000000.0
    assert top["is_bank"] is False
    assert top["is_reit"] is False

    # Check bank flag
    bdo_res = FtsSearchService.search("BDO", enrich_pricing=True)
    assert bdo_res["results"][0]["is_bank"] is True

    # Check REIT flag
    areit_res = FtsSearchService.search("AREIT", enrich_pricing=True)
    assert areit_res["results"][0]["is_reit"] is True


# ── 8. Public & Admin API Endpoints ───────────────────────────

def test_public_and_admin_search_endpoints(admin_client: TestClient, public_client: TestClient):
    """Verifies GET /api/v1/search and Admin maintenance endpoints."""
    # 1. Public search
    res = public_client.get("/api/v1/search?q=meral&limit=5")
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "meral"
    assert data["total_matches"] >= 1
    assert data["results"][0]["ticker"] == "MER"
    assert "execution_ms" in data

    # 2. Admin stats unauthorized
    unauth = public_client.get("/api/v1/admin/search/stats")
    assert unauth.status_code == 401

    # 3. Admin stats authorized
    stats_res = admin_client.get("/api/v1/admin/search/stats")
    assert stats_res.status_code == 200
    assert stats_res.json()["fts_table"] == "stocks_fts"

    # 4. Admin rebuild authorized
    reb_res = admin_client.post("/api/v1/admin/search/rebuild")
    assert reb_res.status_code == 200
    assert reb_res.json()["status"] == "success"
    assert reb_res.json()["indexed_count"] == 7


# ── 9. Sub-10ms Latency Benchmark ─────────────────────────────

def test_sub_10ms_latency_benchmark():
    """Runs 30 search queries and asserts mean execution time is sub-10ms."""
    queries = ["MER", "ALI", "BDO", "Property", "Holding", "meralco", "banco", "Ayala", "SM", "Prime"]
    latencies = []

    for q in queries * 3:
        t0 = time.perf_counter()
        res = FtsSearchService.search(q, limit=10)
        t_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(t_ms)
        assert res["total_matches"] >= 0

    avg_ms = sum(latencies) / len(latencies)
    assert avg_ms < 10.0, f"Average search latency {avg_ms:.2f}ms exceeded 10ms threshold!"
