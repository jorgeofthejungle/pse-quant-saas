"""
backend/tests/test_services.py — Unit Tests for Stock & Customer Services
"""

from __future__ import annotations
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pse_quant.db.models import Base, Stock, Financial, Price, Score, User, Subscription, Watchlist
from pse_quant.services.stock_service import StockService
from pse_quant.services.customer_service import CustomerService


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        # Seed sample stock and score
        stock = Stock(ticker="AREIT", name="AREIT, Inc.", sector="Property", is_reit=True, is_bank=False, status="active")
        s.add(stock)
        price = Price(ticker="AREIT", trade_date=date.today(), close=36.50, market_cap=64_300_000_000.0)
        s.add(price)
        s.add_all([
            Financial(ticker="AREIT", year=2024, revenue=8100.0, net_income=5300.0, equity=43200.0, total_debt=15400.0, eps=2.92, dps=2.58, depreciation=850.0),
            Financial(ticker="AREIT", year=2023, revenue=7100.0, net_income=4600.0, equity=38900.0, total_debt=13800.0, eps=2.54, dps=2.24, depreciation=740.0),
        ])
        score_data = {
            "ticker": "AREIT", "name": "AREIT, Inc.", "sector": "Property",
            "score": 73.0, "rank": 1, "category": "Strong Growth", "confidence": 0.8,
            "current_price": 36.50, "intrinsic_value": 46.84, "mos_pct": 22.1,
            "dividend_yield": 7.07, "pe": 12.5, "pb": 1.49, "roe": 12.27, "de_ratio": 0.36,
        }
        score = Score(
            ticker="AREIT",
            run_date=date.today(),
            portfolio_type="unified",
            score=73.0,
            rank=1,
            confidence=0.8,
            category="Strong Growth",
            breakdown_json=score_data,
        )
        s.add(score)
        s.commit()
        yield s


# ── StockService Tests ────────────────────────────────────────

def test_stock_service_get_rankings(session: Session):
    rankings = StockService.get_rankings(session, portfolio_type="unified")
    assert len(rankings) == 1
    assert rankings[0]["ticker"] == "AREIT"
    assert rankings[0]["score"] == 73.0


def test_stock_service_get_profile(session: Session):
    profile = StockService.get_stock_profile(session, "AREIT")
    assert profile is not None
    assert profile["ticker"] == "AREIT"
    assert profile["current_price"] == 36.50
    assert len(profile["historical_financials"]) == 2
    assert profile["intrinsic_value"] is not None


def test_stock_service_get_bargains(session: Session):
    bargains = StockService.get_bargain_stocks(session, min_mos=10.0)
    assert len(bargains) == 1
    assert bargains[0]["ticker"] == "AREIT"

    # Strict MoS filter
    no_bargains = StockService.get_bargain_stocks(session, min_mos=50.0)
    assert len(no_bargains) == 0


def test_stock_service_override_financial_data(session: Session):
    fin = StockService.override_financial_data(
        session,
        ticker="AREIT",
        year=2024,
        data={"revenue": 8500.0, "net_income": 5500.0},
    )
    assert fin.revenue == 8500.0
    assert fin.net_income == 5500.0


# ── CustomerService Tests ─────────────────────────────────────

def test_customer_registration_and_idempotency(session: Session):
    user, created = CustomerService.register_or_get_customer(session, email="investor@example.com", name="Juan Dela Cruz")
    assert created is True
    assert user.email == "investor@example.com"
    assert user.tier == "free"

    # Re-registration returns existing customer
    user2, created2 = CustomerService.register_or_get_customer(session, email="investor@example.com")
    assert created2 is False
    assert user2.id == user.id


def test_customer_subscription_upgrade(session: Session):
    user, _ = CustomerService.register_or_get_customer(session, email="paid@example.com")
    sub = CustomerService.update_subscription(session, user_id=user.id, plan="monthly", amount_php=499.0)

    assert sub.plan == "monthly"
    assert sub.status == "active"
    assert user.tier == "paid"


def test_customer_watchlist_lifecycle(session: Session):
    user, _ = CustomerService.register_or_get_customer(session, email="trader@example.com")

    # Add AREIT with target MoS of 20%
    item = CustomerService.add_to_watchlist(session, user_id=user.id, ticker="AREIT", target_mos_pct=20.0, notes="Strong dividend play")
    assert item.ticker == "AREIT"
    assert item.target_mos_pct == 20.0

    # View watchlist (AREIT current MoS is 22.1% -> is_triggered must be True)
    watchlist = CustomerService.get_customer_watchlist(session, user_id=user.id)
    assert len(watchlist) == 1
    assert watchlist[0]["ticker"] == "AREIT"
    assert watchlist[0]["current_mos_pct"] == 22.1
    assert watchlist[0]["is_triggered"] is True

    # Remove from watchlist
    removed = CustomerService.remove_from_watchlist(session, user_id=user.id, ticker="AREIT")
    assert removed is True
    assert len(CustomerService.get_customer_watchlist(session, user_id=user.id)) == 0


def test_customer_admin_metrics(session: Session):
    user1, _ = CustomerService.register_or_get_customer(session, email="free@example.com")
    user2, _ = CustomerService.register_or_get_customer(session, email="pro@example.com")
    CustomerService.update_subscription(session, user_id=user2.id, plan="monthly", amount_php=499.0)

    metrics = CustomerService.get_admin_metrics(session)
    assert metrics["total_customers"] == 2
    assert metrics["paid_subscribers"] == 1
    assert metrics["free_members"] == 1
    assert metrics["mrr_php"] == 499.0


def test_customer_watchlist_alerts(session: Session):
    user, _ = CustomerService.register_or_get_customer(session, email="alert@example.com")
    CustomerService.add_to_watchlist(session, user_id=user.id, ticker="AREIT", target_mos_pct=15.0)

    alerts = CustomerService.evaluate_and_dispatch_alerts(session)
    assert len(alerts) == 1
    assert alerts[0]["ticker"] == "AREIT"
    assert alerts[0]["user_email"] == "alert@example.com"


def test_customer_dispatch_weekly_digest(session: Session, tmp_path, monkeypatch):
    user, _ = CustomerService.register_or_get_customer(session, email="weekly@example.com", name="Maria Santos")
    res = CustomerService.dispatch_weekly_digest(session, target_emails=["weekly@example.com"])
    assert res["status"] == "completed"
    assert res["recipients_count"] == 1
    assert res["results"][0]["email"] == "weekly@example.com"
    assert res["results"][0]["status"] == "mock_sent"
