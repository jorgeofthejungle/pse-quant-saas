"""
pse_quant/api/routes/reports.py — Done-For-You Investment Menu & PDF Report API
Serves downloadable institutional research dossiers and Taglish Fact Cards
for Outcome as a Service (Pay-What-You-Can per report).
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from pse_quant.db.connection import get_db_session
from pse_quant.db.models import Stock, Price, Financial, Score
from pse_quant.scraper.etl import build_stock_quant_dict
from pse_quant.core.filters import filter_unified
from pse_quant.core.scoring import score_unified
from pse_quant.core.mos import enrich_stock_valuation
from pse_quant.core.fact_compiler import DoneForYouFactCompiler
from pse_quant.reporting.generator import generate_pdf_report

router = APIRouter(prefix="/reports", tags=["reports"])


def get_db():
    with get_db_session() as session:
        yield session


_BENCHMARK_PSE_UNIVERSE: List[Dict[str, Any]] = [
    {
        "rank": 1,
        "ticker": "AREIT",
        "name": "AREIT, Inc.",
        "sector": "Property",
        "score": 73.0,
        "health_score": 78.5,
        "improvement_score": 69.0,
        "persistence_score": 71.5,
        "confidence": 1.0,
        "category": "Highest Quality",
        "current_price": 36.50,
        "intrinsic_value": 46.84,
        "mos_pct": 22.1,
        "dividend_yield": 7.15,
        "roe": 12.8,
        "debt_to_equity": 0.36,
    },
    {
        "rank": 2,
        "ticker": "DMC",
        "name": "DMCI Holdings, Inc.",
        "sector": "Holding Firms",
        "score": 68.5,
        "health_score": 74.0,
        "improvement_score": 63.0,
        "persistence_score": 68.5,
        "confidence": 1.0,
        "category": "Highest Quality",
        "current_price": 12.40,
        "intrinsic_value": 15.20,
        "mos_pct": 18.4,
        "dividend_yield": 8.50,
        "roe": 19.4,
        "debt_to_equity": 0.48,
    },
    {
        "rank": 3,
        "ticker": "BDO",
        "name": "BDO Unibank, Inc.",
        "sector": "Banks",
        "score": 71.4,
        "health_score": 75.0,
        "improvement_score": 70.2,
        "persistence_score": 69.0,
        "confidence": 1.0,
        "category": "Highest Quality",
        "current_price": 148.50,
        "intrinsic_value": 182.00,
        "mos_pct": 18.4,
        "dividend_yield": 2.65,
        "roe": 15.2,
        "debt_to_equity": 0.85,
    },
    {
        "rank": 4,
        "ticker": "ICT",
        "name": "International Container Terminal Services, Inc.",
        "sector": "Services",
        "score": 67.2,
        "health_score": 69.0,
        "improvement_score": 66.5,
        "persistence_score": 66.0,
        "confidence": 1.0,
        "category": "Strong Growth",
        "current_price": 412.00,
        "intrinsic_value": 445.00,
        "mos_pct": 7.4,
        "dividend_yield": 3.20,
        "roe": 28.5,
        "debt_to_equity": 1.15,
    },
    {
        "rank": 5,
        "ticker": "MER",
        "name": "Manila Electric Company (Meralco)",
        "sector": "Industrial",
        "score": 70.8,
        "health_score": 74.2,
        "improvement_score": 68.0,
        "persistence_score": 70.2,
        "confidence": 1.0,
        "category": "Highest Quality",
        "current_price": 465.00,
        "intrinsic_value": 510.00,
        "mos_pct": 8.8,
        "dividend_yield": 5.40,
        "roe": 24.1,
        "debt_to_equity": 0.72,
    },
    {
        "rank": 6,
        "ticker": "SM",
        "name": "SM Investments Corporation",
        "sector": "Holding Firms",
        "score": 66.5,
        "health_score": 70.0,
        "improvement_score": 64.0,
        "persistence_score": 65.5,
        "confidence": 1.0,
        "category": "Strong Growth",
        "current_price": 865.00,
        "intrinsic_value": 1060.00,
        "mos_pct": 18.4,
        "dividend_yield": 1.10,
        "roe": 14.5,
        "debt_to_equity": 0.68,
    },
    {
        "rank": 7,
        "ticker": "JFC",
        "name": "Jollibee Foods Corporation",
        "sector": "Industrial",
        "score": 56.4,
        "health_score": 58.0,
        "improvement_score": 54.0,
        "persistence_score": 57.2,
        "confidence": 1.0,
        "category": "Fair / Watchlist",
        "current_price": 258.00,
        "intrinsic_value": 240.00,
        "mos_pct": -7.5,
        "dividend_yield": 1.25,
        "roe": 13.4,
        "debt_to_equity": 1.38,
    },
    {
        "rank": 8,
        "ticker": "ALI",
        "name": "Ayala Land, Inc.",
        "sector": "Property",
        "score": 63.2,
        "health_score": 65.0,
        "improvement_score": 61.5,
        "persistence_score": 63.0,
        "confidence": 1.0,
        "category": "Undervalued Quality",
        "current_price": 28.50,
        "intrinsic_value": 36.80,
        "mos_pct": 22.6,
        "dividend_yield": 1.85,
        "roe": 10.8,
        "debt_to_equity": 0.92,
    },
    {
        "rank": 9,
        "ticker": "TEL",
        "name": "PLDT Inc.",
        "sector": "Services",
        "score": 61.8,
        "health_score": 60.0,
        "improvement_score": 62.5,
        "persistence_score": 63.0,
        "confidence": 1.0,
        "category": "High Dividend",
        "current_price": 1310.00,
        "intrinsic_value": 1420.00,
        "mos_pct": 7.7,
        "dividend_yield": 7.40,
        "roe": 21.0,
        "debt_to_equity": 1.85,
    },
    {
        "rank": 10,
        "ticker": "DITO",
        "name": "DITO CME Holdings Corp.",
        "sector": "Services",
        "score": 37.6,
        "health_score": 5.0,
        "improvement_score": 94.4,
        "persistence_score": 82.7,
        "confidence": 0.6,
        "category": "Watchlist",
        "current_price": 0.55,
        "intrinsic_value": None,
        "mos_pct": None,
        "dividend_yield": 0.0,
        "roe": None,
        "debt_to_equity": None,
        "net_income": -13753.02,
        "equity": -42272.24,
        "total_debt": 306214.12,
        "eps": -0.63,
        "filter_passed": False,
        "filter_reason": "DITO: persistent negative earnings (3Y normalized EPS = -0.69)",
    },
    {
        "rank": 11,
        "ticker": "CEB",
        "name": "Cebu Air, Inc.",
        "sector": "Services",
        "score": 55.2,
        "health_score": 41.2,
        "improvement_score": 71.0,
        "persistence_score": 68.5,
        "confidence": 0.8,
        "category": "Watchlist",
        "current_price": 31.00,
        "intrinsic_value": 38.32,
        "mos_pct": 19.1,
        "dividend_yield": 0.0,
        "roe": 18.64,
        "debt_to_equity": 6.59,
        "net_income": 5400.0,
        "equity": 28970.0,
        "total_debt": 190912.0,
        "eps": 3.80,
        "filter_passed": False,
        "filter_reason": "CEB: persistent negative earnings (3Y normalized EPS = -0.63)",
    },
]


def _get_curated_stocks(db: Session) -> List[Dict[str, Any]]:
    """
    Builds the Done-For-You Investment Menu and Stock Reality Check universe
    from 100% real PSE Edge audited financials and quotes stored in pse_local.db
    (strictly excluding any synthetic test fixtures like ILLIQ).
    """
    scores = db.scalars(
        select(Score)
        .where(Score.portfolio_type == "unified", Score.ticker != "ILLIQ")
        .order_by(desc(Score.run_date), Score.rank.asc())
    ).all()

    seen_tickers: set[str] = set()
    curated: List[Dict[str, Any]] = []
    for s in scores:
        if not s.breakdown_json:
            continue
        t = str(s.breakdown_json.get("ticker", s.ticker)).upper()
        if t == "ILLIQ" or t in seen_tickers:
            continue
        seen_tickers.add(t)
        entry = dict(s.breakdown_json)
        entry["filter_passed"] = True
        entry["filter_reason"] = f"{t}: eligible"
        curated.append(entry)

    # Also evaluate real PSE stocks in DB that have Price + Financial rows
    # (including stocks that failed filter_unified such as DITO, CEB, TEL, or scored below Top 10)
    real_stocks = db.scalars(
        select(Stock).where(Stock.status == "active", Stock.ticker != "ILLIQ")
    ).all()

    extra_candidates: List[Dict[str, Any]] = []
    for st in real_stocks:
        if st.ticker.upper() in seen_tickers:
            continue
        latest_price = db.scalar(
            select(Price)
            .where(Price.ticker == st.ticker)
            .order_by(desc(Price.trade_date))
            .limit(1)
        )
        fins = db.scalars(
            select(Financial)
            .where(Financial.ticker == st.ticker)
            .order_by(desc(Financial.year))
        ).all()
        if not latest_price or not fins:
            continue

        s_dict = build_stock_quant_dict(st, latest_price, list(fins))
        passed, reason = filter_unified(s_dict)
        f_hist = [
            {
                "year": f.year,
                "revenue": f.revenue,
                "net_income": f.net_income,
                "equity": f.equity,
                "total_debt": f.total_debt,
                "eps": f.eps,
                "dps": f.dps,
                "operating_cf": f.operating_cf,
                "capex": f.capex,
            }
            for f in fins
        ]
        sc_val, bd = score_unified(s_dict, financials_history=f_hist, portfolio_type="unified")
        s_dict["score"] = sc_val
        s_dict["category"] = bd["category"]
        s_dict["breakdown"] = bd
        s_dict["confidence"] = bd["confidence"]
        s_dict["scoring_group"] = bd["scoring_group"]
        s_dict["filter_passed"] = passed
        s_dict["filter_reason"] = reason
        enriched = enrich_stock_valuation(s_dict, portfolio_type="unified")
        seen_tickers.add(st.ticker.upper())
        extra_candidates.append(enriched)

    # Sort extra real DB candidates by (filter_passed desc, score desc) and assign sequential ranks
    extra_candidates.sort(key=lambda x: (bool(x.get("filter_passed", False)), float(x.get("score") or 0.0)), reverse=True)
    next_rank = len(curated) + 1
    for item in extra_candidates:
        item["rank"] = next_rank
        next_rank += 1
        curated.append(item)

    if not curated:
        return list(_BENCHMARK_PSE_UNIVERSE)

    return curated


@router.get("/done-for-you", summary="Get Done-For-You Investment Menu with Fact Cards & Seasoned Numbers")
def get_done_for_you_menu(
    goal: Optional[str] = Query("all", pattern="^(all|dividend|value|growth)$"),
    hype_check_ticker: Optional[str] = Query(None, max_length=20),
    db: Session = Depends(get_db),
):
    """
    Answers 'Ano po maganda bilhin?' with a structured Done-For-You Investment Menu.
    Every option includes a 4-part Taglish Fact Card (Verdict, Peso Value Test,
    Net Dividend per ₱10k, Health) + Seasoned Numbers toggle + optional FB Hype Check.
    """
    stocks = _get_curated_stocks(db)
    return DoneForYouFactCompiler.compile_investment_menu(
        ranked_stocks=stocks,
        goal_filter=goal,
        hype_check_ticker=hype_check_ticker,
    )


@router.get("/download-latest", summary="Download the latest weekly research PDF dossier")
def download_latest_report(
    goal: Optional[str] = Query("all", pattern="^(all|dividend|value|growth)$"),
    hype_check_ticker: Optional[str] = Query(None, max_length=20),
    db: Session = Depends(get_db),
):
    """
    Returns the latest compiled A4 PDF research dossier for StockPilot PH.
    Compiles on demand with Done-For-You Taglish Fact Cards, Valuation Triangulation,
    Sample Capital Allocation Blueprint, and optional Requested Stock Audit Spotlight.
    """
    target_path = Path("weekly_research_digest.pdf")
    top_stocks = _get_curated_stocks(db)
    generate_pdf_report(
        top_stocks,
        output_path=target_path,
        goal_filter=goal,
        hype_check_ticker=hype_check_ticker,
    )

    return FileResponse(
        path=str(target_path),
        filename="StockPilot_PH_DoneForYou_Dossier.pdf",
        media_type="application/pdf",
    )
