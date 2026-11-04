"""
backend/tests/test_scraper.py — Unit Tests for PSE Edge Scraper and ETL Pipeline
"""

from __future__ import annotations
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pse_quant.db.models import Base, Stock, Financial, Price, Score, PipelineRun
from pse_quant.scraper.client import PseEdgeClient
from pse_quant.scraper.financials import detect_financial_unit, parse_cell_number, parse_financial_html
from pse_quant.scraper.directory import lookup_company, fetch_directory_by_sector
from pse_quant.scraper.stock_data import fetch_stock_quote, fetch_dividend_history
from pse_quant.scraper.etl import (
    sync_directory,
    sync_stock_quotes,
    sync_financials,
    build_stock_quant_dict,
    compute_scores_and_rankings,
    run_pipeline,
)


# ── Unit Detection Tests ──────────────────────────────────────

def test_detect_financial_unit_billions():
    soup = BeautifulSoup("<div>Amounts in billions of Philippine Pesos</div>", "lxml")
    mult, label = detect_financial_unit(soup)
    assert mult == 1_000_000_000
    assert label == "billions"


def test_detect_financial_unit_millions():
    soup = BeautifulSoup("<div>All figures in millions (PHP)</div>", "lxml")
    mult, label = detect_financial_unit(soup)
    assert mult == 1_000_000
    assert label == "millions"


def test_detect_financial_unit_thousands():
    soup = BeautifulSoup("<div>Table stated in thousands</div>", "lxml")
    mult, label = detect_financial_unit(soup)
    assert mult == 1_000
    assert label == "thousands"


def test_detect_financial_unit_peso():
    soup = BeautifulSoup("<div>Expressed in Philippine Peso</div>", "lxml")
    mult, label = detect_financial_unit(soup)
    assert mult == 1
    assert label == "peso"


def test_detect_financial_unit_currency_header():
    soup = BeautifulSoup("<div>Currency: Philippine Peso in Millions</div>", "lxml")
    mult, label = detect_financial_unit(soup)
    assert mult == 1_000_000
    assert label == "millions"


def test_detect_financial_unit_default():
    soup = BeautifulSoup("<div>No clear indication</div>", "lxml")
    mult, label = detect_financial_unit(soup)
    assert mult == 1_000_000
    assert label == "millions_assumed"


# ── Number Parsing Tests ──────────────────────────────────────

def test_parse_cell_number():
    assert parse_cell_number("1,234.56") == 1234.56
    assert parse_cell_number("(500.25)") == -500.25
    assert parse_cell_number("-") is None
    assert parse_cell_number("—") is None
    assert parse_cell_number("N/A") is None
    assert parse_cell_number("") is None
    assert parse_cell_number(None) is None


# ── HTML Financial Statement Parsing Tests ────────────────────

SAMPLE_FIN_HTML = """
<html>
<body>
    <div>For the fiscal year ended : December 31, 2024</div>
    <div>Currency : In Thousands</div>
    <table>
        <tr>
            <th>Financial Item</th>
            <th>Current Year (2024)</th>
            <th>Previous Year (2023)</th>
        </tr>
        <tr>
            <td>Gross Revenue</td>
            <td>100,000,000</td>
            <td>90,000,000</td>
        </tr>
        <tr>
            <td>Net Income Attributable to Parent</td>
            <td>25,000,000</td>
            <td>20,000,000</td>
        </tr>
        <tr>
            <td>Stockholders' Equity - Parent</td>
            <td>80,000,000</td>
            <td>70,000,000</td>
        </tr>
        <tr>
            <td>Total Liabilities</td>
            <td>40,000,000</td>
            <td>35,000,000</td>
        </tr>
        <tr>
            <td>Earnings Per Share (Basic)</td>
            <td>5.50</td>
            <td>4.80</td>
        </tr>
        <tr>
            <td>Depreciation and Amortization</td>
            <td>5,000,000</td>
            <td>4,500,000</td>
        </tr>
    </table>
</body>
</html>
"""

def test_parse_financial_html():
    results = parse_financial_html(SAMPLE_FIN_HTML, cmpy_id="188")
    assert len(results) == 2

    # Check 2024: 100,000,000 thousands = 100,000 millions
    r2024 = next(r for r in results if r["year"] == 2024)
    assert r2024["revenue"] == 100000.0
    assert r2024["net_income"] == 25000.0
    assert r2024["equity"] == 80000.0
    assert r2024["total_debt"] == 40000.0
    assert r2024["eps"] == 5.50  # per share is NOT divided by 1000
    assert r2024["depreciation"] == 5000.0
    assert r2024["unit_label"] == "thousands"

    # Check 2023: 90,000,000 thousands = 90,000 millions
    r2023 = next(r for r in results if r["year"] == 2023)
    assert r2023["revenue"] == 90000.0
    assert r2023["net_income"] == 20000.0
    assert r2023["eps"] == 4.80


# ── Directory and Stock Data Scraper Tests ─────────────────────

def test_lookup_company_mock():
    mock_client = MagicMock(spec=PseEdgeClient)
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"symbol": "DMC", "cmpyNm": "DMCI Holdings, Inc.", "cmpyId": "188"},
        {"symbol": "SMPH", "cmpyNm": "SM Prime Holdings, Inc.", "cmpyId": "234"},
    ]
    mock_client.get.return_value = mock_resp

    res = lookup_company(mock_client, "DMC")
    assert res is not None
    assert res["ticker"] == "DMC"
    assert res["cmpy_id"] == "188"
    assert "DMCI" in res["name"]


def test_fetch_stock_quote_mock():
    mock_client = MagicMock(spec=PseEdgeClient)
    quote_html = """
    <table>
        <tr><th>Last Traded Price</th><td>12.50</td></tr>
        <tr><th>Market Capitalization</th><td>165,950,000,000</td></tr>
        <tr><th>P/E Ratio</th><td>6.25</td></tr>
        <tr><th>Outstanding Shares</th><td>13,276,000,000</td></tr>
    </table>
    """
    mock_resp = MagicMock()
    mock_resp.text = quote_html
    mock_client.get.return_value = mock_resp

    quote = fetch_stock_quote(mock_client, "188")
    assert quote is not None
    assert quote["close"] == 12.50
    assert quote["market_cap"] == 165950000000.0
    assert quote["pe"] == 6.25


def test_fetch_dividend_history_mock():
    mock_client = MagicMock(spec=PseEdgeClient)
    div_html = """
    <table>
        <tr>
            <td>1</td>
            <td>Cash</td>
            <td>0.72</td>
            <td>PHP</td>
            <td>03-15-2024</td>
            <td>04-02-2024</td>
        </tr>
        <tr>
            <td>2</td>
            <td>Cash</td>
            <td>0.68</td>
            <td>PHP</td>
            <td>03-14-2023</td>
            <td>04-01-2023</td>
        </tr>
    </table>
    """
    mock_resp = MagicMock()
    mock_resp.text = div_html
    mock_client.get.return_value = mock_resp

    divs = fetch_dividend_history(mock_client, "188")
    assert len(divs) >= 2
    assert divs[0]["year"] == 2024
    assert divs[0]["dps"] == 0.72


# ── Database & ETL Integration Tests ──────────────────────────

@pytest.fixture
def in_memory_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_build_stock_quant_dict(in_memory_session: Session):
    stock = Stock(
        ticker="DMC",
        name="DMCI Holdings, Inc.",
        sector="Holding Firms",
        is_reit=False,
        is_bank=False,
    )
    in_memory_session.add(stock)

    price = Price(
        ticker="DMC",
        trade_date=date(2024, 12, 31),
        close=12.0,
        market_cap=150_000_000_000.0,
    )
    in_memory_session.add(price)

    # 3 years of financials
    f24 = Financial(
        ticker="DMC", year=2024, revenue=120_000.0, net_income=24_000.0,
        equity=80_000.0, total_debt=30_000.0, eps=1.80, dps=1.44,
        operating_cf=30_000.0, capex=10_000.0,
    )
    f23 = Financial(
        ticker="DMC", year=2023, revenue=110_000.0, net_income=22_000.0,
        equity=75_000.0, total_debt=28_000.0, eps=1.65, dps=1.30,
        operating_cf=28_000.0, capex=9_000.0,
    )
    f22 = Financial(
        ticker="DMC", year=2022, revenue=100_000.0, net_income=20_000.0,
        equity=70_000.0, total_debt=25_000.0, eps=1.50, dps=1.20,
        operating_cf=25_000.0, capex=8_000.0,
    )
    in_memory_session.add_all([f24, f23, f22])
    in_memory_session.commit()

    q_dict = build_stock_quant_dict(stock, price, [f24, f23, f22])

    assert q_dict["ticker"] == "DMC"
    assert q_dict["current_price"] == 12.0
    assert q_dict["roe"] == 30.0  # 24k / 80k * 100
    assert q_dict["pe"] == 6.67  # 12.0 / 1.80
    assert q_dict["dividend_yield"] == 12.0  # 1.44 / 12.0 * 100
    assert len(q_dict["revenue_5y"]) == 3
    assert q_dict["revenue_cagr"] is not None


def test_scoring_and_etl_pipeline(in_memory_session: Session):
    # Setup test stock
    stock = Stock(
        ticker="AREIT",
        name="AREIT, Inc.",
        sector="Property",
        is_reit=True,
        is_bank=False,
        cmpy_id="679",
        status="active",
    )
    in_memory_session.add(stock)

    price = Price(
        ticker="AREIT",
        trade_date=date.today(),
        close=35.0,
        market_cap=60_000_000_000.0,
    )
    in_memory_session.add(price)

    # 3 years of financial records
    in_memory_session.add_all([
        Financial(ticker="AREIT", year=2024, revenue=7500.0, net_income=5000.0, equity=40000.0, total_debt=15000.0, eps=2.80, dps=2.50, operating_cf=5200.0, capex=500.0, depreciation=800.0),
        Financial(ticker="AREIT", year=2023, revenue=6500.0, net_income=4200.0, equity=36000.0, total_debt=12000.0, eps=2.40, dps=2.15, operating_cf=4400.0, capex=400.0, depreciation=700.0),
        Financial(ticker="AREIT", year=2022, revenue=5500.0, net_income=3500.0, equity=32000.0, total_debt=10000.0, eps=2.00, dps=1.80, operating_cf=3600.0, capex=300.0, depreciation=600.0),
    ])
    in_memory_session.commit()

    # Compute scores and rankings
    results = compute_scores_and_rankings(in_memory_session, portfolio_types=["unified", "dividend"])

    assert "unified" in results
    assert "dividend" in results
    assert len(results["unified"]) == 1

    areit_result = results["unified"][0]
    assert areit_result["ticker"] == "AREIT"
    assert areit_result["score"] > 50.0
    assert areit_result["rank"] == 1
    assert "intrinsic_value" in areit_result
    assert "mos_pct" in areit_result

    # Verify score row written in DB
    score_in_db = in_memory_session.scalar(
        select(Score).where(Score.ticker == "AREIT", Score.portfolio_type == "unified")
    )
    assert score_in_db is not None
    assert score_in_db.score == areit_result["score"]
    assert score_in_db.rank == 1


def test_run_pipeline_orchestration(in_memory_session: Session):
    # Test running pipeline with mock client and already populated stocks
    stock = Stock(ticker="SMPH", name="SM Prime Holdings", sector="Property", cmpy_id="234", status="active")
    in_memory_session.add(stock)
    in_memory_session.add(Price(ticker="SMPH", trade_date=date.today(), close=28.0, market_cap=800_000_000_000.0))
    in_memory_session.add_all([
        Financial(ticker="SMPH", year=2024, revenue=130000.0, net_income=40000.0, equity=350000.0, total_debt=200000.0, eps=1.40, dps=0.45, operating_cf=45000.0, capex=30000.0),
        Financial(ticker="SMPH", year=2023, revenue=115000.0, net_income=35000.0, equity=320000.0, total_debt=180000.0, eps=1.22, dps=0.40, operating_cf=40000.0, capex=25000.0),
    ])
    in_memory_session.commit()

    # Run pipeline without live network scraping (sync_dir=False, sync_quotes=False, sync_fins=False)
    pipeline_run = run_pipeline(
        session=in_memory_session,
        sync_dir=False,
        sync_quotes=False,
        sync_fins=False,
        portfolio_types=["unified"],
    )

    assert pipeline_run.status == "completed"
    assert pipeline_run.summary_json is not None
    assert pipeline_run.summary_json["ranked_counts"]["unified"] == 1
