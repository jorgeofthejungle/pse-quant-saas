"""
backend/tests/test_watchlist.py — Unit Tests for Authenticated Watchlist API
"""

from __future__ import annotations
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from pse_quant.db.models import Base, Stock, Price, Score, User
from pse_quant.services.auth_service import AuthService
from pse_quant.api.main import app
from pse_quant.api.routes.watchlist import get_db as get_db_watchlist
from pse_quant.api.routes.auth import get_db as get_db_auth
from pse_quant.api.auth import get_db as get_db_security


@pytest.fixture
def auth_client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)

    # Seed stock and score
    stock = Stock(ticker="AREIT", name="AREIT, Inc.", sector="Property", is_reit=True, status="active")
    session.add(stock)
    price = Price(ticker="AREIT", trade_date=date.today(), close=36.50, market_cap=64_300_000_000.0)
    session.add(price)
    score_data = {
        "ticker": "AREIT",
        "name": "AREIT, Inc.",
        "sector": "Property",
        "score": 73.0,
        "rank": 1,
        "category": "Strong Growth",
        "current_price": 36.50,
        "intrinsic_value": 46.84,
        "mos_pct": 22.1,
    }
    score = Score(
        ticker="AREIT",
        run_date=date.today(),
        portfolio_type="unified",
        score=73.0,
        rank=1,
        category="Strong Growth",
        breakdown_json=score_data,
    )
    session.add(score)

    stock2 = Stock(ticker="DMC", name="DMCI Holdings, Inc.", sector="Holding Firms", status="active")
    session.add(stock2)
    price2 = Price(ticker="DMC", trade_date=date.today(), close=12.40, market_cap=164_670_000_000.0)
    session.add(price2)
    score_data2 = {
        "ticker": "DMC",
        "name": "DMCI Holdings, Inc.",
        "sector": "Holding Firms",
        "score": 68.5,
        "rank": 2,
        "category": "Quality",
        "current_price": 12.40,
        "intrinsic_value": 15.20,
        "mos_pct": 18.4,
    }
    score2 = Score(
        ticker="DMC",
        run_date=date.today(),
        portfolio_type="unified",
        score=68.5,
        rank=2,
        category="Quality",
        breakdown_json=score_data2,
    )
    session.add(score2)
    session.commit()

    # Create member user
    user, token = AuthService.register_member(
        session,
        email="trader@investor.ph",
        password="Password123!",
        name="Juan Trader",
    )

    def override_get_db():
        yield session

    app.dependency_overrides[get_db_watchlist] = override_get_db
    app.dependency_overrides[get_db_auth] = override_get_db
    app.dependency_overrides[get_db_security] = override_get_db

    client = TestClient(app)
    yield client, token, session

    app.dependency_overrides.clear()
    session.close()


def test_watchlist_unauthorized(auth_client):
    client, _, _ = auth_client
    # Unauthenticated GET should return 401
    res = client.get("/api/v1/watchlist")
    assert res.status_code == 401


def test_watchlist_crud_flow(auth_client):
    client, token, _ = auth_client
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Initial watchlist is empty
    res = client.get("/api/v1/watchlist", headers=headers)
    assert res.status_code == 200
    assert res.json() == []

    # 2. Add AREIT with target MoS 20.0%
    payload = {"ticker": "AREIT", "target_mos_pct": 20.0, "notes": "Dividend compounder"}
    res = client.post("/api/v1/watchlist", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["ticker"] == "AREIT"
    assert data["target_mos_pct"] == 20.0

    # 3. Retrieve watchlist: AREIT should be present with enriched calculation
    res = client.get("/api/v1/watchlist", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    areit = items[0]
    assert areit["ticker"] == "AREIT"
    assert areit["current_price"] == 36.50
    assert areit["current_mos_pct"] == 22.1
    assert areit["target_mos_pct"] == 20.0
    assert areit["is_triggered"] is True  # 22.1 >= 20.0

    # 4. Add DMC with target MoS 25.0%
    client.post("/api/v1/watchlist", json={"ticker": "DMC", "target_mos_pct": 25.0}, headers=headers)
    res = client.get("/api/v1/watchlist", headers=headers)
    assert len(res.json()) == 2
    dmc = next(i for i in res.json() if i["ticker"] == "DMC")
    assert dmc["current_mos_pct"] == 18.4
    assert dmc["target_mos_pct"] == 25.0
    assert dmc["is_triggered"] is False  # 18.4 < 25.0

    # 5. Remove AREIT
    del_res = client.delete("/api/v1/watchlist/AREIT", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["removed"] == "AREIT"

    # Verify only DMC remains
    res = client.get("/api/v1/watchlist", headers=headers)
    assert len(res.json()) == 1
    assert res.json()[0]["ticker"] == "DMC"

    # 6. Removing non-existent stock returns 404
    del_404 = client.delete("/api/v1/watchlist/UNKNOWN", headers=headers)
    assert del_404.status_code == 404
