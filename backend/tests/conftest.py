"""
backend/tests/conftest.py — Global Test Configuration & DB Invariant Fixtures
Ensures deterministic database initialization and baseline equities (DMC, AREIT)
exist across all test runners, regardless of test execution order on Linux or Windows.
"""

from datetime import date
import pytest
from pse_quant.db.connection import init_db, get_write_session
from pse_quant.db.models import Stock, Financial, Price, Score
from pse_quant.cache import global_cache


@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    """Initializes the database schema and seeds sample equities once per test session."""
    init_db()

    with get_write_session() as session:
        # 1. Seed DMC
        dmc = session.get(Stock, "DMC")
        if not dmc:
            dmc = Stock(
                ticker="DMC",
                name="DMCI Holdings",
                sector="Holding Firms",
                is_bank=False,
                is_reit=False,
            )
            session.add(dmc)

        # 2. Seed AREIT
        areit = session.get(Stock, "AREIT")
        if not areit:
            areit = Stock(
                ticker="AREIT",
                name="AREIT Inc",
                sector="Property",
                is_bank=False,
                is_reit=True,
                status="active",
            )
            session.add(areit)

        # 3. Seed DITO (Speculative / Hype-Check Anchor)
        dito = session.get(Stock, "DITO")
        if not dito:
            dito = Stock(
                ticker="DITO",
                name="DITO CME Holdings Corp.",
                sector="Services",
                is_bank=False,
                is_reit=False,
                status="active",
            )
            session.add(dito)

        # 4. Seed ALI (Property Blue Chip)
        ali = session.get(Stock, "ALI")
        if not ali:
            ali = Stock(
                ticker="ALI",
                name="Ayala Land Inc",
                sector="Property",
                is_bank=False,
                is_reit=False,
                status="active",
            )
            session.add(ali)

        # 4. Seed prices
        dmc_price = session.query(Price).filter_by(ticker="DMC").first()
        if not dmc_price:
            session.add(Price(ticker="DMC", trade_date=date(2026, 11, 4), close=11.50, market_cap=305000.0))

        areit_price = session.query(Price).filter_by(ticker="AREIT").first()
        if not areit_price:
            session.add(Price(ticker="AREIT", trade_date=date(2026, 11, 4), close=34.00, market_cap=65000.0))

        dito_price = session.query(Price).filter_by(ticker="DITO").first()
        if not dito_price:
            session.add(Price(ticker="DITO", trade_date=date(2026, 11, 4), close=1.65, market_cap=25000.0))

        ali_price = session.query(Price).filter_by(ticker="ALI").first()
        if not ali_price:
            session.add(Price(ticker="ALI", trade_date=date(2026, 11, 4), close=28.00, market_cap=400000.0))

        # 5. Seed financials for DITO (negative earnings -> triggers hype trap)
        dito_fin = session.query(Financial).filter_by(ticker="DITO").first()
        if not dito_fin:
            session.add(Financial(
                ticker="DITO",
                year=2025,
                revenue=5000.0,
                net_income=-15000.0,
                equity=-20000.0,
                eps=-1.20,
                dps=0.0,
            ))

        # 4. Seed scores
        dmc_score = session.query(Score).filter_by(ticker="DMC", portfolio_type="unified").first()
        if not dmc_score:
            session.add(Score(
                ticker="DMC",
                run_date=date(2026, 11, 4),
                portfolio_type="unified",
                score=78.5,
                rank=1,
                category="Highest Quality",
                breakdown_json={
                    "ticker": "DMC",
                    "name": "DMCI Holdings",
                    "score": 78.5,
                    "health_score": 80.0,
                    "improvement_score": 75.0,
                    "persistence_score": 82.0,
                    "sector": "Holding Firms",
                    "mos_pct": 22.3,
                    "margin_of_safety_pct": 22.3,
                    "roe_pct": 15.0,
                    "debt_to_equity": 0.5,
                    "current_price": 11.50,
                    "intrinsic_value": 14.80,
                },
            ))

        areit_score = session.query(Score).filter_by(ticker="AREIT", portfolio_type="unified").first()
        if not areit_score:
            session.add(Score(
                ticker="AREIT",
                run_date=date(2026, 11, 4),
                portfolio_type="unified",
                score=82.0,
                rank=2,
                category="Highest Quality",
                breakdown_json={
                    "ticker": "AREIT",
                    "name": "AREIT Inc",
                    "score": 82.0,
                    "health_score": 85.0,
                    "improvement_score": 78.0,
                    "persistence_score": 84.0,
                    "sector": "Property",
                    "mos_pct": 18.1,
                    "margin_of_safety_pct": 18.1,
                    "roe_pct": 12.0,
                    "debt_to_equity": 0.6,
                    "current_price": 34.00,
                    "intrinsic_value": 41.50,
                },
            ))

        dito_score = session.query(Score).filter_by(ticker="DITO", portfolio_type="unified").first()
        if not dito_score:
            session.add(Score(
                ticker="DITO",
                run_date=date(2026, 11, 4),
                portfolio_type="unified",
                score=28.5,
                rank=99,
                category="Hype Trap",
                breakdown_json={
                    "ticker": "DITO",
                    "name": "DITO CME Holdings Corp.",
                    "score": 28.5,
                    "health_score": 30.0,
                    "improvement_score": 25.0,
                    "persistence_score": 30.0,
                    "sector": "Services",
                    "mos_pct": -120.0,
                    "dividend_yield": 0.0,
                    "roe": -18.5,
                    "debt_to_equity": 4.20,
                    "current_price": 1.65,
                    "intrinsic_value": 0.75,
                },
            ))

        ali_score = session.query(Score).filter_by(ticker="ALI", portfolio_type="unified").first()
        if not ali_score:
            session.add(Score(
                ticker="ALI",
                run_date=date(2026, 11, 4),
                portfolio_type="unified",
                score=75.0,
                rank=3,
                category="Highest Quality",
                breakdown_json={
                    "ticker": "ALI",
                    "name": "Ayala Land Inc",
                    "score": 75.0,
                    "health_score": 78.0,
                    "improvement_score": 72.0,
                    "persistence_score": 75.0,
                    "sector": "Property",
                    "mos_pct": 15.0,
                    "margin_of_safety_pct": 15.0,
                    "roe_pct": 11.5,
                    "debt_to_equity": 0.8,
                    "current_price": 28.00,
                    "intrinsic_value": 33.00,
                },
            ))

        session.commit()

    global_cache.flush_all()
    yield
