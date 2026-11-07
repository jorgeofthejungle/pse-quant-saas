"""
backend/tests/test_api.py — Unit & Integration Tests for FastAPI Endpoints
"""

from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from datetime import date

from pse_quant.db.models import Base, Stock, Price, Financial, Score
from pse_quant.api.main import app
from pse_quant.api.routes.stocks import get_db as get_db_stocks
from pse_quant.api.routes.customers import get_db as get_db_customers
from pse_quant.api.routes.admin import get_db as get_db_admin


from sqlalchemy.pool import StaticPool

@pytest.fixture
def client_with_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    # Seed test stock
    stock = Stock(ticker="AREIT", name="AREIT, Inc.", sector="Property", is_reit=True, is_bank=False, status="active")
    session.add(stock)
    session.add(Price(ticker="AREIT", trade_date=date.today(), close=36.50, market_cap=64_300_000_000.0))
    session.add(Financial(ticker="AREIT", year=2024, revenue=8100.0, net_income=5300.0, equity=43200.0, total_debt=15400.0, eps=2.92, dps=2.58))
    score_data = {
        "ticker": "AREIT", "name": "AREIT, Inc.", "sector": "Property",
        "score": 73.0, "rank": 1, "category": "Strong Growth", "confidence": 0.8,
        "current_price": 36.50, "intrinsic_value": 46.84, "mos_pct": 22.1,
        "dividend_yield": 7.07, "pe": 12.5, "pb": 1.49, "roe": 12.27, "de_ratio": 0.36,
    }
    session.add(Score(
        ticker="AREIT", run_date=date.today(), portfolio_type="unified",
        score=73.0, rank=1, confidence=0.8, category="Strong Growth",
        breakdown_json=score_data
    ))
    session.commit()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db_stocks] = override_get_db
    app.dependency_overrides[get_db_customers] = override_get_db
    app.dependency_overrides[get_db_admin] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    session.close()


def test_health_endpoint(client_with_db: TestClient):
    resp = client_with_db.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_macro_benchmarks_endpoint(client_with_db: TestClient):
    resp = client_with_db.get("/api/v1/stocks/macro")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ph_10y_bond_rate"] == 6.5
    assert data["equity_risk_premium"] == 5.0
    assert data["conglomerate_holding_discount"] == 20.0


def test_list_stocks_endpoint(client_with_db: TestClient):
    resp = client_with_db.get("/api/v1/stocks?portfolio=unified")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["data"][0]["ticker"] == "AREIT"


def test_stock_profile_endpoint(client_with_db: TestClient):
    resp = client_with_db.get("/api/v1/stocks/AREIT")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AREIT"
    assert data["current_price"] == 36.50
    assert data["intrinsic_value"] is not None


def test_customer_lifecycle_api(client_with_db: TestClient):
    # 1. Signup
    signup_resp = client_with_db.post("/api/v1/customers/signup", json={"email": "client@example.com", "name": "Maria Santos"})
    assert signup_resp.status_code == 200
    cust = signup_resp.json()
    user_id = cust["id"]
    assert cust["email"] == "client@example.com"
    assert cust["tier"] == "free"

    # 2. Add to watchlist
    wl_resp = client_with_db.post(f"/api/v1/customers/{user_id}/watchlist", json={"ticker": "AREIT", "target_mos_pct": 20.0})
    assert wl_resp.status_code == 200

    # 3. View watchlist
    get_wl = client_with_db.get(f"/api/v1/customers/{user_id}/watchlist")
    assert get_wl.status_code == 200
    items = get_wl.json()
    assert len(items) == 1
    assert items[0]["ticker"] == "AREIT"
    assert items[0]["is_triggered"] is True

    # 4. Admin metrics (requires admin privileges)
    from pse_quant.services.auth_service import ADMIN_MASTER_KEY
    metrics_resp = client_with_db.get("/api/v1/admin/metrics", headers={"X-Admin-Key": ADMIN_MASTER_KEY})
    assert metrics_resp.status_code == 200
    m = metrics_resp.json()
    assert m["total_customers"] >= 1


def test_api_query_parameter_validation(client_with_db: TestClient):
    # Invalid portfolio type
    resp = client_with_db.get("/api/v1/stocks?portfolio=crypto")
    assert resp.status_code == 422

    # Negative min_score
    resp = client_with_db.get("/api/v1/stocks?min_score=-5.0")
    assert resp.status_code == 422

    # Absurd limit
    resp = client_with_db.get("/api/v1/stocks?limit=1000")
    assert resp.status_code == 422


def test_api_schema_boundary_validation(client_with_db: TestClient):
    # Invalid email signup
    resp = client_with_db.post("/api/v1/customers/signup", json={"email": "not-an-email"})
    assert resp.status_code == 422

    # Valid signup with whitespace email normalization
    resp = client_with_db.post("/api/v1/customers/signup", json={"email": " ValidUser@Example.com "})
    assert resp.status_code == 200
    assert resp.json()["email"] == "validuser@example.com"
    uid = resp.json()["id"]

    # Invalid subscription plan
    resp = client_with_db.post(f"/api/v1/customers/{uid}/subscription", json={"plan": "diamond"})
    assert resp.status_code == 422

    # Watchlist ticker auto-sanitization (whitespace and lower-case)
    resp = client_with_db.post(f"/api/v1/customers/{uid}/watchlist", json={"ticker": "  areit  ", "target_mos_pct": 15.0})
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "AREIT"

    # Out of bounds target_mos_pct
    resp = client_with_db.post(f"/api/v1/customers/{uid}/watchlist", json={"ticker": "AREIT", "target_mos_pct": -500.0})
    assert resp.status_code == 422


def test_on_demand_outcome_checkout_and_verify(client_with_db: TestClient):
    """Test Outcome as a Service (OaaS) on-demand checkout and email verification."""
    # 1. On-Demand Checkout with Email & Fixed Fee
    checkout_payload = {
        "email": "investor.demand@example.com",
        "name": "Maria Santos",
        "amount_php": 499.0,
        "payment_method": "gcash",
    }
    resp = client_with_db.post("/api/v1/customers/on-demand-checkout", json=checkout_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["email"] == "investor.demand@example.com"
    assert data["tier"] == "paid"
    assert data["plan"] == "on_demand"
    assert data["unlocked"] is True
    assert "download_url" in data

    # 2. Verify Access by Email
    verify_resp = client_with_db.post("/api/v1/customers/verify-access", json={"email": "investor.demand@example.com"})
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["has_access"] is True
    assert verify_data["email"] == "investor.demand@example.com"
    assert verify_data["tier"] == "paid"

    # 3. Verify Non-existent Email
    unknown_resp = client_with_db.post("/api/v1/customers/verify-access", json={"email": "nobody@example.com"})
    assert unknown_resp.status_code == 200
    assert unknown_resp.json()["has_access"] is False


def test_reports_download_endpoint(client_with_db: TestClient):
    """Test /api/v1/reports/download-latest generates or serves PDF."""
    resp = client_with_db.get("/api/v1/reports/download-latest")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0

