"""
Tests for pse_quant.db — Schema, Relationships, Constraints & Cascade Integrity
"""

from __future__ import annotations
import pytest
from datetime import date, datetime, timezone
from sqlalchemy import create_engine, select, func, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from pse_quant.db.models import (
    Base,
    Stock,
    Financial,
    Price,
    Score,
    User,
    Subscription,
    Watchlist,
    EmailLog,
    PipelineRun,
)


@pytest.fixture
def db_session():
    test_engine = create_engine("sqlite:///:memory:")

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    with TestingSession() as session:
        yield session


def test_database_models_in_memory(db_session: Session):
    session = db_session
    # Create a stock
    stock = Stock(
        ticker="DMC",
        name="DMCI Holdings",
        sector="Holding Firms",
        is_bank=False,
        is_reit=False,
    )
    session.add(stock)

    # Add financials
    fin = Financial(
        ticker="DMC",
        year=2025,
        revenue=50000.0,
        net_income=18000.0,
        equity=119000.0,
        eps=3.8,
        dps=0.96,
    )
    session.add(fin)

    # Add price
    price = Price(
        ticker="DMC",
        trade_date=date(2026, 11, 4),
        close=11.50,
        market_cap=305000.0,
    )
    session.add(price)

    # Add score
    score = Score(
        ticker="DMC",
        run_date=date(2026, 11, 4),
        portfolio_type="unified",
        score=78.5,
        rank=1,
        category="Highest Quality",
        breakdown_json={"health": 80.0, "improvement": 75.0, "persistence": 82.0},
    )
    session.add(score)

    # Add user
    user = User(
        email="subscriber@example.com",
        name="Josh B",
        tier="paid",
    )
    session.add(user)
    session.commit()

    # Query back
    loaded = session.query(Stock).filter_by(ticker="DMC").first()
    assert loaded is not None
    assert loaded.name == "DMCI Holdings"
    assert len(loaded.financials) == 1
    assert loaded.financials[0].revenue == 50000.0
    assert len(loaded.prices) == 1
    assert loaded.prices[0].close == 11.50
    assert len(loaded.scores) == 1
    assert loaded.scores[0].score == 78.5

    loaded_user = session.query(User).filter_by(email="subscriber@example.com").first()
    assert loaded_user is not None
    assert loaded_user.tier == "paid"


def test_stock_cascade_deletion(db_session: Session):
    session = db_session
    # Setup stock with child rows
    stock = Stock(ticker="AREIT", name="AREIT, Inc.", sector="Property", is_reit=True)
    session.add(stock)
    session.add(Financial(ticker="AREIT", year=2024, revenue=8000.0))
    session.add(Price(ticker="AREIT", trade_date=date(2026, 11, 4), close=36.0))
    session.add(Score(ticker="AREIT", run_date=date(2026, 11, 4), portfolio_type="unified", score=80.0, category="Quality"))

    user = User(email="investor@example.ph", name="Trader")
    session.add(user)
    session.flush()

    session.add(Watchlist(user_id=user.id, ticker="AREIT", target_mos_pct=20.0))
    session.commit()

    # Verify rows exist
    assert session.scalar(select(func.count(Financial.id)).where(Financial.ticker == "AREIT")) == 1
    assert session.scalar(select(func.count(Price.id)).where(Price.ticker == "AREIT")) == 1
    assert session.scalar(select(func.count(Score.id)).where(Score.ticker == "AREIT")) == 1
    assert session.scalar(select(func.count(Watchlist.id)).where(Watchlist.ticker == "AREIT")) == 1

    # Delete parent stock -> all child rows must cascade-delete
    session.delete(stock)
    session.commit()

    assert session.scalar(select(func.count(Financial.id)).where(Financial.ticker == "AREIT")) == 0
    assert session.scalar(select(func.count(Price.id)).where(Price.ticker == "AREIT")) == 0
    assert session.scalar(select(func.count(Score.id)).where(Score.ticker == "AREIT")) == 0
    assert session.scalar(select(func.count(Watchlist.id)).where(Watchlist.ticker == "AREIT")) == 0
    # User remains intact
    assert session.get(User, user.id) is not None


def test_user_cascade_deletion(db_session: Session):
    session = db_session
    user = User(email="retiree@example.ph", name="Juan")
    stock = Stock(ticker="BDO", name="BDO Unibank", sector="Financials", is_bank=True)
    session.add_all([user, stock])
    session.flush()

    session.add(Subscription(user_id=user.id, plan="annual", amount_php=4990.0))
    session.add(Watchlist(user_id=user.id, ticker="BDO", target_mos_pct=15.0))
    session.add(EmailLog(recipient_email=user.email, subject="Welcome", email_type="welcome"))
    session.commit()

    # Verify child rows exist
    assert session.scalar(select(func.count(Subscription.id)).where(Subscription.user_id == user.id)) == 1
    assert session.scalar(select(func.count(Watchlist.id)).where(Watchlist.user_id == user.id)) == 1
    assert session.scalar(select(func.count(EmailLog.id)).where(EmailLog.recipient_email == user.email)) == 1

    # Delete user -> Subscription and Watchlist cascade, EmailLog remains for compliance
    session.delete(user)
    session.commit()

    assert session.scalar(select(func.count(Subscription.id)).where(Subscription.user_id == user.id)) == 0
    assert session.scalar(select(func.count(Watchlist.id)).where(Watchlist.user_id == user.id)) == 0
    # Email audit log is preserved
    assert session.scalar(select(func.count(EmailLog.id)).where(EmailLog.recipient_email == "retiree@example.ph")) == 1


def test_unique_constraints(db_session: Session):
    session = db_session
    stock = Stock(ticker="ICT", name="ICTSI", sector="Services")
    session.add(stock)
    session.add(Financial(ticker="ICT", year=2024, revenue=1000.0))
    session.commit()

    # Duplicate financial ticker + year -> IntegrityError
    session.add(Financial(ticker="ICT", year=2024, revenue=2000.0))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # Duplicate user email -> IntegrityError
    session.add(User(email="unique@example.com"))
    session.commit()
    session.add(User(email="unique@example.com"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_json_column_serialization(db_session: Session):
    session = db_session
    user = User(
        email="prefs@example.com",
        notification_prefs={"daily_brief": False, "weekly_report": True, "custom_alert_level": 3},
    )
    run = PipelineRun(
        run_type="test_run",
        summary_json={"tickers_processed": ["DMC", "AREIT"], "success_rate": 1.0},
    )
    session.add_all([user, run])
    session.commit()

    loaded_user = session.query(User).filter_by(email="prefs@example.com").first()
    assert loaded_user.notification_prefs["daily_brief"] is False
    assert loaded_user.notification_prefs["custom_alert_level"] == 3

    loaded_run = session.get(PipelineRun, run.id)
    assert loaded_run.summary_json["success_rate"] == 1.0
    assert "DMC" in loaded_run.summary_json["tickers_processed"]
