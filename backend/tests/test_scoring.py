"""
Tests for pse_quant.core.scoring
"""

from pse_quant.core.scoring import (
    score_health,
    score_improvement,
    score_persistence,
    score_unified,
    rank_stocks,
    calc_data_confidence,
    get_category,
)


def test_get_category():
    assert get_category(85.0)[0] == "Highest Quality"
    assert get_category(60.0)[0] == "Strong Growth"
    assert get_category(40.0)[0] == "Watchlist"
    assert get_category(20.0)[0] == "Weak"


def test_calc_data_confidence():
    assert calc_data_confidence({"eps_5y": [1, 2, 3, 4, 5], "revenue_5y": [1, 2, 3, 4, 5]}) == 1.0
    assert calc_data_confidence({"eps_5y": [1, 2, 3, 4], "revenue_5y": [1, 2, 3, 4]}) == 0.90
    assert calc_data_confidence({"eps_5y": [1, 2, 3], "revenue_5y": [1, 2, 3]}) == 0.80
    assert calc_data_confidence({"eps_5y": [1, 2], "revenue_5y": [1, 2]}) == 0.60
    assert calc_data_confidence({"eps_5y": [1], "revenue_5y": [1]}) == 0.0


def test_score_health():
    strong_stock = {
        "ticker": "DMC",
        "roe": 18.0,
        "net_income_3y": [18000, 16000, 14000],
        "revenue_5y": [50000, 48000, 45000, 42000, 40000],
        "de_ratio": 0.5,
        "eps_5y": [3.8, 3.5, 3.2, 2.9, 2.5],
        "pb": 1.1,
    }
    score, breakdown = score_health(strong_stock, "holding")
    assert score is not None
    assert score > 75.0
    assert "roe" in breakdown["factors"]
    assert "eps_stability" in breakdown["factors"]


def test_score_improvement():
    improving_stock = {
        "ticker": "GROW",
        "revenue_5y": [50000, 45000, 40000, 36000, 32000],  # ~10% YoY growth
        "eps_5y": [5.0, 4.5, 4.0, 3.5, 3.0],
        "roe": 20.0,
    }
    financials_history = [
        {"equity": 10000, "net_income": 2000},
        {"equity": 9000, "net_income": 1600},
        {"equity": 8000, "net_income": 1200},
        {"equity": 7000, "net_income": 700},  # 3y ago ROE = 10%
    ]
    score, breakdown = score_improvement(improving_stock, financials_history, "industrial")
    assert score is not None
    assert score > 75.0
    assert breakdown["factors"]["_momentum_bonus"] is not None


def test_score_persistence():
    steady_stock = {
        "ticker": "STEADY",
        "revenue_5y": [50000, 45000, 40000, 36000, 32000],  # 4 consecutive increases
        "eps_5y": [5.0, 4.5, 4.0, 3.5, 3.0],
    }
    score, breakdown = score_persistence(steady_stock, "services")
    assert score is not None
    assert score >= 80.0


def test_score_unified_deterministic():
    stock = {
        "ticker": "DMC",
        "sector": "Holding Firms",
        "roe": 18.0,
        "net_income_3y": [18000, 16000, 14000],
        "revenue_5y": [50000, 45000, 40000, 35000, 30000],
        "eps_5y": [5.0, 4.5, 4.0, 3.5, 3.0],
        "de_ratio": 0.5,
        "pb": 1.1,
    }
    score1, _ = score_unified(stock)
    score2, _ = score_unified(stock)
    assert score1 == score2
    assert score1 > 70.0


def test_rank_stocks_and_threshold():
    stocks = [
        {
            "ticker": "HIGH",
            "sector": "Industrial",
            "roe": 22.0,
            "net_income_3y": [2000, 1800, 1500],
            "revenue_5y": [10000, 9000, 8000, 7000, 6000],
            "eps_5y": [4.0, 3.5, 3.0, 2.5, 2.0],
            "de_ratio": 0.4,
            "pb": 1.0,
        },
        {
            "ticker": "MED",
            "sector": "Industrial",
            "roe": 10.0,
            "net_income_3y": [800, 800, 800],
            "revenue_5y": [5000, 5000, 5000, 5000, 5000],
            "eps_5y": [1.5, 1.5, 1.5, 1.5, 1.5],
            "de_ratio": 1.0,
            "pb": 1.5,
        },
    ]
    ranked = rank_stocks(stocks)
    assert len(ranked) >= 1
    assert ranked[0]["ticker"] == "HIGH"
    assert ranked[0]["rank"] == 1
