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


# ── Multi-Tier Cache-Aside Management & Observability ─────────

@router.get("/cache/metrics", summary="Inspect Cache-Aside telemetry and hit ratio")
def get_cache_metrics():
    """Returns active cache entries, hits, misses, hit ratio, and eviction metrics."""
    from pse_quant.cache import global_cache
    return global_cache.get_metrics()


@router.post("/cache/flush", summary="Manually flush or pattern-invalidate cache entries")
def flush_cache(pattern: Optional[str] = Query(None, description="Optional glob pattern e.g. 'stock:profile:*'")):
    """Flushes entire cache or clears entries matching the specified glob pattern."""
    from pse_quant.cache import global_cache
    if pattern:
        cleared = global_cache.invalidate_pattern(pattern)
        msg = f"Invalidated {cleared} keys matching '{pattern}'"
    else:
        cleared = global_cache.flush_all()
        msg = f"Flushed all {cleared} cache keys"

    return {
        "status": "success",
        "message": msg,
        "keys_cleared": cleared,
        "metrics": global_cache.get_metrics(),
    }


# ── Database Connection Pool & Replica Telemetry ─────────────

@router.get("/db/pool-metrics", summary="Inspect Database Connection Pool and Read-Replica metrics")
def get_db_pool_metrics():
    """Returns writer & reader connection pool telemetry, active checked-out connections, and routing distribution."""
    from pse_quant.db.pool import pool_manager
    return pool_manager.get_pool_metrics()


@router.post("/db/pool-metrics/reset", summary="Reset Database Query Routing telemetry counters")
def reset_db_pool_metrics():
    """Resets the query routing telemetry counters."""
    from pse_quant.db.pool import pool_manager
    pool_manager.reset_metrics()
    return {
        "status": "success",
        "message": "Query routing counters reset to 0",
        "metrics": pool_manager.get_pool_metrics(),
    }



# ── Distributed Tracing & Latency Telemetry ──────────────────

@router.get("/telemetry/latency", summary="Inspect route latency histograms and quantiles (p50, p95, p99)")
def get_telemetry_latency():
    """Returns rolling latency percentiles (p50, p95, p99, min, max, avg) per endpoint."""
    from pse_quant.telemetry import global_latency_tracker
    return global_latency_tracker.get_summary()


@router.get("/telemetry/traces", summary="List recent sampled request traces with correlation IDs")
def get_telemetry_traces(limit: int = Query(50, ge=1, le=200)):
    """Returns recent request traces with X-Correlation-ID, duration, and HTTP status."""
    from pse_quant.telemetry import global_latency_tracker
    return {"traces": global_latency_tracker.get_recent_traces(limit=limit)}


@router.get("/telemetry/live", summary="Unified system pulse (latency, DB pool, cache, task queue)")
def get_telemetry_live():
    """Returns a single executive health payload aggregating all subsystem metrics."""
    from pse_quant.telemetry import global_latency_tracker
    from pse_quant.db.pool import pool_manager
    from pse_quant.cache import global_cache
    from pse_quant.tasks.engine import task_queue

    return {
        "status": "healthy",
        "latency": global_latency_tracker.get_summary()["overall"],
        "database_pools": pool_manager.get_pool_metrics()["routing"],
        "cache": global_cache.get_metrics(),
        "task_queue": task_queue.get_metrics(),
    }


@router.post("/telemetry/reset", summary="Reset latency reservoirs and trace buffer")
def reset_telemetry():
    """Flushes rolling latency samples and trace buffer."""
    from pse_quant.telemetry import global_latency_tracker
    global_latency_tracker.reset()
    return {"status": "success", "message": "Latency tracker and trace buffer reset to 0."}



# ── Zero-Downtime Database Migration Controls ─────────────────

@router.get("/migrations", summary="List all schema migrations and their current phase")
def list_migrations():
    """Returns all registered Expand-Contract migrations and their execution phases."""
    from pse_quant.migrations import migration_manager
    return {"migrations": migration_manager.list_migrations()}


@router.get("/migrations/{name}", summary="Inspect status of a specific migration")
def get_migration_status(name: str = Path(..., min_length=2, max_length=128)):
    """Returns current phase, pending backfill counts, and verification status."""
    from pse_quant.migrations import migration_manager
    try:
        return migration_manager.get_status(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/migrations/{name}/advance", summary="Advance a migration to the next phase")
def advance_migration(
    name: str = Path(..., min_length=2, max_length=128),
    target_phase: Optional[str] = Query(None, pattern="^(EXPAND|DUAL_WRITE|BACKFILL|READ_NEW|CONTRACT|COMPLETED)$"),
):
    """Advances migration through the 5-phase lifecycle (EXPAND -> DUAL_WRITE -> BACKFILL -> READ_NEW -> CONTRACT)."""
    from pse_quant.migrations import migration_manager, MigrationPhase
    try:
        phase_enum = MigrationPhase(target_phase) if target_phase else None
        return migration_manager.advance_phase(name, target_phase=phase_enum)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/migrations/{name}/backfill", summary="Execute chunked historical backfill")
def backfill_migration(
    name: str = Path(..., min_length=2, max_length=128),
    batch_size: int = Query(100, ge=1, le=1000),
    max_batches: int = Query(50, ge=1, le=500),
):
    """Executes throttled batch updates for historical records without locking tables."""
    from pse_quant.migrations import migration_manager
    try:
        return migration_manager.run_backfill(name, batch_size=batch_size, max_batches=max_batches)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/migrations/{name}/verify", summary="Verify mathematical parity between old and new columns")
def verify_migration_parity(name: str = Path(..., min_length=2, max_length=128)):
    """Audits 100% of rows to guarantee mathematical parity before allowing phase transition."""
    from pse_quant.migrations import migration_manager
    try:
        return migration_manager.verify_parity(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
