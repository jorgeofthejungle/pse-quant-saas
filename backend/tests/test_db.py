"""
Tests for pse_quant.db
"""

from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pse_quant.db.models import Base, Stock, Financial, Price, Score, User


def test_database_models_in_memory():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    with TestingSession() as session:
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
