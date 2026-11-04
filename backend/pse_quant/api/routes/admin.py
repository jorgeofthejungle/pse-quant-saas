"""
pse_quant/api/routes/admin.py — Direct Server Controls for Admin Dashboard
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from pse_quant.db.connection import get_db_session
from pse_quant.services.stock_service import StockService
from pse_quant.services.customer_service import CustomerService
from pse_quant.db.models import PipelineRun
from pse_quant.api.schemas import (
    FinancialOverrideRequest,
    AdminMetricsResponse,
    PipelineTriggerResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def get_db():
    with get_db_session() as session:
        yield session


# ── Pipeline & Scraper Controls ───────────────────────────────

@router.post("/pipeline/sync-all", response_model=PipelineTriggerResponse, summary="Trigger full ETL scrape and scoring")
def trigger_full_pipeline(
    tickers: Optional[list[str]] = Query(None, description="Optional tickers to restrict scrape to"),
    db: Session = Depends(get_db),
):
    """Executes directory sync, quotes, multi-year financial statements, and 3-layer scoring."""
    try:
        run_log = StockService.collect_and_sync_all(session=db, tickers=tickers)
        return {
            "status": run_log.status,
            "run_id": run_log.id,
            "message": "Full ETL pipeline executed successfully.",
            "summary": run_log.summary_json,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {e}")


@router.post("/pipeline/scrape-quotes", summary="Trigger daily quote refresh")
def trigger_scrape_quotes(
    tickers: Optional[list[str]] = Query(None),
    db: Session = Depends(get_db),
):
    """Refreshes current trading prices, market caps, and cash dividends from PSE Edge."""
    count = StockService.collect_quotes_only(session=db, tickers=tickers)
    return {"status": "completed", "quotes_updated": count}


@router.post("/pipeline/score", summary="Recompute quantitative scores")
def trigger_recompute_scores(db: Session = Depends(get_db)):
    """Recomputes deterministic 3-layer scores and MoS intrinsic valuations."""
    ranked = StockService.recompute_scores(session=db)
    counts = {p: len(items) for p, items in ranked.items()}
    return {"status": "completed", "portfolio_counts": counts}


@router.post("/pipeline/email-digest", summary="Trigger weekly research email dispatch")
def trigger_email_digest(
    recipients: Optional[list[str]] = Query(None, description="Target email list or all active subscribers"),
    db: Session = Depends(get_db),
):
    """Generates executive A4 PDF report and sends weekly digest via Resend API."""
    result = CustomerService.dispatch_weekly_digest(session=db, target_emails=recipients)
    return result


@router.post("/pipeline/evaluate-alerts", summary="Check watchlist target MoS alerts")
def trigger_evaluate_alerts(db: Session = Depends(get_db)):
    """Evaluates customer watchlists and identifies opportunities meeting target MoS."""
    dispatched = CustomerService.evaluate_and_dispatch_alerts(session=db)
    return {"status": "completed", "alerts_dispatched": len(dispatched), "details": dispatched}


@router.get("/pipeline/runs", summary="Audit log of previous pipeline runs")
def get_pipeline_runs(limit: int = 15, db: Session = Depends(get_db)):
    """Returns recent pipeline execution history, status, and canary reports."""
    runs = db.scalars(
        select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "run_type": r.run_type,
            "status": r.status,
            "summary": r.summary_json,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


# ── Customer Intelligence & SaaS Metrics ──────────────────────

@router.get("/metrics", response_model=AdminMetricsResponse, summary="Executive SaaS customer metrics")
def get_admin_metrics(db: Session = Depends(get_db)):
    """Returns total customers, paid subscribers, MRR, and email telemetry."""
    return CustomerService.get_admin_metrics(session=db)


@router.get("/customers", summary="List all customers for administration")
def list_customers(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Returns customer list with subscription status and watchlist counts."""
    return CustomerService.list_customers_admin(session=db, skip=skip, limit=limit)


# ── Stock Data Manual Corrections ─────────────────────────────

@router.post("/stocks/{ticker}/financials/{year}", summary="Manual financial statement correction")
def override_stock_financials(
    ticker: str,
    year: int,
    req: FinancialOverrideRequest,
    db: Session = Depends(get_db),
):
    """Admin override: Manually update or correct annual financial statement data."""
    try:
        fin = StockService.override_financial_data(
            session=db,
            ticker=ticker,
            year=year,
            data=req.model_dump(exclude_unset=True),
        )
        return {
            "status": "success",
            "ticker": fin.ticker,
            "year": fin.year,
            "revenue": fin.revenue,
            "net_income": fin.net_income,
            "equity": fin.equity,
            "eps": fin.eps,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
