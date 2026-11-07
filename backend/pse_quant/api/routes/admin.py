"""
pse_quant/api/routes/admin.py — Direct Server Controls for Admin Dashboard
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Path
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from pse_quant.db.connection import get_db_session
from pse_quant.services.stock_service import StockService
from pse_quant.services.customer_service import CustomerService
from pse_quant.db.models import PipelineRun
from pse_quant.api.auth import require_admin
from pse_quant.api.schemas import (
    FinancialOverrideRequest,
    AdminMetricsResponse,
    PipelineTriggerResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


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
    clean_tickers = [t.strip().upper() for t in tickers] if tickers else None
    try:
        run_log = StockService.collect_and_sync_all(session=db, tickers=clean_tickers)
        return {
            "status": run_log.status,
            "run_id": run_log.id,
            "message": "Full ETL pipeline executed successfully.",
            "summary": run_log.summary_json,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {e}")


@router.post("/pipeline/sync-directory", summary="Scrape and synchronize complete PSE ticker directory")
def trigger_sync_directory(db: Session = Depends(get_db)):
    """Fetches the complete active listed company directory from PSE Edge and upserts Stock records."""
    from pse_quant.scraper.client import PseEdgeClient
    from pse_quant.scraper.etl import sync_directory
    client = PseEdgeClient()
    count = sync_directory(client, db)
    return {"status": "completed", "stocks_synced": count}


@router.post("/pipeline/scrape-quotes", summary="Trigger daily quote refresh")
def trigger_scrape_quotes(
    tickers: Optional[list[str]] = Query(None),
    db: Session = Depends(get_db),
):
    """Refreshes current trading prices, market caps, and cash dividends from PSE Edge."""
    clean_tickers = [t.strip().upper() for t in tickers] if tickers else None
    count = StockService.collect_quotes_only(session=db, tickers=clean_tickers)
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
def get_pipeline_runs(limit: int = Query(15, ge=1, le=200), db: Session = Depends(get_db)):
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
def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Returns customer list with subscription status and watchlist counts."""
    return CustomerService.list_customers_admin(session=db, skip=skip, limit=limit)


# ── Stock Data Manual Corrections ─────────────────────────────

@router.post("/stocks/{ticker}/financials/{year}", summary="Manual financial statement correction")
def override_stock_financials(
    ticker: str,
    year: int = Path(..., ge=1990, le=2100),
    req: FinancialOverrideRequest = ...,
    db: Session = Depends(get_db),
):
    """Admin override: Manually update or correct annual financial statement data."""
    clean_ticker = ticker.strip().upper()
    try:
        fin = StockService.override_financial_data(
            session=db,
            ticker=clean_ticker,
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


# ── Scraper Resilience & Circuit Breaker Telemetry ────────────

@router.get("/circuit-breaker/status", summary="Inspect PSE Edge Scraper Circuit Breaker telemetry")
def get_circuit_breaker_status():
    """Returns the live state machine status (CLOSED, OPEN, HALF_OPEN) of the PSE Edge scraper."""
    from pse_quant.scraper.resilience import global_pse_edge_circuit
    return global_pse_edge_circuit.get_state()


@router.post("/circuit-breaker/reset", summary="Manually reset PSE Edge Scraper Circuit Breaker")
def reset_circuit_breaker():
    """Manually resets the circuit breaker back to CLOSED state."""
    from pse_quant.scraper.resilience import global_pse_edge_circuit
    global_pse_edge_circuit.reset()
    return {"status": "success", "message": "Circuit breaker reset to CLOSED", "circuit": global_pse_edge_circuit.get_state()}


@router.get("/dead-letters", summary="List scraper dead-letter poison pills for triage")
def list_scraper_dead_letters(
    status: str = Query("pending", pattern="^(pending|reprocessed|ignored)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Returns recent dead-letter records quarantined during ETL processing."""
    from pse_quant.scraper.resilience import DeadLetterService
    letters = DeadLetterService.list_dead_letters(session=db, status=status, limit=limit)
    return [
        {
            "id": dl.id,
            "ticker": dl.ticker,
            "stage": dl.stage,
            "source_url": dl.source_url,
            "error_reason": dl.error_reason,
            "payload_preview": dl.payload_preview,
            "attempts": dl.attempts,
            "status": dl.status,
            "created_at": dl.created_at.isoformat() if dl.created_at else None,
            "resolved_at": dl.resolved_at.isoformat() if dl.resolved_at else None,
        }
        for dl in letters
    ]


@router.post("/dead-letters/{letter_id}/resolve", summary="Resolve or discard a scraper dead-letter item")
def resolve_scraper_dead_letter(
    letter_id: int = Path(..., ge=1),
    resolution: str = Query("reprocessed", pattern="^(reprocessed|ignored)$"),
    db: Session = Depends(get_db),
):
    """Marks a dead letter as resolved or discarded."""
    from pse_quant.scraper.resilience import DeadLetterService
    resolved = DeadLetterService.resolve_dead_letter(session=db, dead_letter_id=letter_id, resolution=resolution)
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Dead-letter record ID {letter_id} not found.")
    return {"status": "success", "id": resolved.id, "resolution": resolved.status}
