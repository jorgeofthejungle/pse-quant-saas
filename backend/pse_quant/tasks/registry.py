"""
pse_quant/tasks/registry.py — Registered Background Tasks
PSE Quant SaaS (v2 Rebuild) — Lab 9

Registers asynchronous tasks for ETL data scraping, quant score recomputation,
weekly email digests, and PDF research report generation.
"""

from __future__ import annotations
import logging
from typing import Any, Dict
from pse_quant.tasks.engine import task
from pse_quant.db.connection import get_write_session, get_read_session

logger = logging.getLogger("pse_quant.tasks.registry")


@task("etl.sync_all")
def handle_sync_all(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Executes full PSE Edge directory sync, quotes refresh, and financial statement sync."""
    from pse_quant.services.stock_service import StockService
    tickers = payload.get("tickers")
    clean_tickers = [t.strip().upper() for t in tickers] if tickers else None

    with get_write_session() as session:
        run_log = StockService.collect_and_sync_all(session=session, tickers=clean_tickers)
        return {
            "status": run_log.status,
            "run_id": run_log.id,
            "summary": run_log.summary_json,
        }


@task("etl.scrape_quotes")
def handle_scrape_quotes(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Refreshes current trading prices, market caps, and cash dividends."""
    from pse_quant.services.stock_service import StockService
    tickers = payload.get("tickers")
    clean_tickers = [t.strip().upper() for t in tickers] if tickers else None

    with get_write_session() as session:
        count = StockService.collect_quotes_only(session=session, tickers=clean_tickers)
        return {"status": "completed", "quotes_updated": count}


@task("etl.recompute_scores")
def handle_recompute_scores(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Recomputes deterministic 3-layer fundamental scores and MoS intrinsic valuations."""
    from pse_quant.services.stock_service import StockService
    portfolio_types = payload.get("portfolio_types")

    with get_write_session() as session:
        ranked = StockService.recompute_scores(session=session, portfolio_types=portfolio_types)
        counts = {p: len(items) for p, items in ranked.items()}
        return {"status": "completed", "portfolio_counts": counts}


@task("email.dispatch_digest")
def handle_email_digest(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generates executive PDF report and dispatches weekly digest emails."""
    from pse_quant.services.customer_service import CustomerService
    recipients = payload.get("recipients")

    with get_write_session() as session:
        result = CustomerService.dispatch_weekly_digest(session=session, target_emails=recipients)
        return result


@task("reports.generate_pdf")
def handle_generate_pdf(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generates an institutional A4 PDF fact sheet for a specific stock."""
    from pse_quant.services.stock_service import StockService
    from pse_quant.reports.pdf_generator import generate_stock_report_pdf

    ticker = payload.get("ticker", "ALI").strip().upper()
    with get_read_session() as session:
        profile = StockService.get_stock_profile(session=session, ticker=ticker)
        if not profile:
            raise ValueError(f"Stock '{ticker}' not found.")
        pdf_path = generate_stock_report_pdf(profile)
        return {
            "status": "completed",
            "ticker": ticker,
            "pdf_path": str(pdf_path),
            "generated_at": profile.get("trade_date"),
        }


# ── Test & Diagnostic Task Handlers ────────────────────────────

@task("test.echo")
def handle_test_echo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Echoes input payload back for connectivity and queue timing verification."""
    return {"status": "echoed", "received": payload}


@task("test.fail")
def handle_test_fail(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates an unrecoverable failure for retry and DLQ verification."""
    reason = payload.get("reason", "Simulated task failure")
    raise RuntimeError(reason)
