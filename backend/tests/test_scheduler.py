"""
backend/tests/test_scheduler.py — Unit Tests for Scheduler Engine
"""

from __future__ import annotations
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from pse_quant.db.models import Base, Stock, Price, Score, User, Watchlist
from pse_quant.scheduler import get_current_pht, execute_job, run_scheduler_daemon


@pytest.fixture
def scheduler_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        # Seed test user and stock
        user = User(email="scheduler_test@investor.ph", name="Test Scheduler", status="active")
        s.add(user)
        stock = Stock(ticker="AREIT", name="AREIT, Inc.", sector="Property", is_reit=True, status="active")
        s.add(stock)
        price = Price(ticker="AREIT", trade_date=date.today(), close=36.50, market_cap=64_300_000_000.0)
        s.add(price)
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
        s.add(score)
        s.flush()

        watchlist = Watchlist(user_id=user.id, ticker="AREIT", target_mos_pct=20.0)
        s.add(watchlist)
        s.commit()
        yield s


def test_scheduler_timezone():
    pht = get_current_pht()
    assert pht.tzinfo is not None
    assert pht.tzinfo.tzname(None) == "PHT"


def test_execute_morning_alerts(scheduler_session: Session):
    res = execute_job("morning_alerts", session=scheduler_session)
    assert res["status"] == "completed"
    assert res["job"] == "morning_alerts"
    assert res["summary"]["alerts_dispatched_count"] >= 1


def test_execute_weekly_report(scheduler_session: Session):
    res = execute_job("weekly_report", session=scheduler_session)
    assert res["status"] == "completed"
    assert res["job"] == "weekly_report"
    assert res["summary"]["digest_result"]["status"] == "completed"


def test_execute_invalid_job(scheduler_session: Session):
    res = execute_job("non_existent_task", session=scheduler_session)
    assert res["status"] == "failed"
    assert "error" in res


def test_scheduler_daemon_single_iteration():
    # Verify daemon exits cleanly after max_iterations=1
    run_scheduler_daemon(poll_interval=0, max_iterations=1)


def test_scheduler_tick_idempotency(monkeypatch):
    from datetime import datetime
    from pse_quant.scheduler import run_scheduler_tick, _LAST_EXECUTED, PHT_TZ

    _LAST_EXECUTED.clear()
    # Mock Wednesday at 16:02 PHT (market close window)
    mock_pht_now = datetime(2026, 11, 4, 16, 2, 0, tzinfo=PHT_TZ)
    monkeypatch.setattr("pse_quant.scheduler.get_current_pht", lambda: mock_pht_now)
    monkeypatch.setattr("pse_quant.scheduler.execute_job", lambda job: {"status": "completed", "job": job})

    # First tick -> must execute
    res1 = run_scheduler_tick()
    assert len(res1) == 1
    assert res1[0]["job"] == "quotes_sync"

    # Second tick on same date at 16:03 PHT -> must NOT re-execute
    mock_pht_later = datetime(2026, 11, 4, 16, 3, 0, tzinfo=PHT_TZ)
    monkeypatch.setattr("pse_quant.scheduler.get_current_pht", lambda: mock_pht_later)
    res2 = run_scheduler_tick()
    assert len(res2) == 0
    _LAST_EXECUTED.clear()
