"""
pse_quant/scheduler.py — Automated Execution & Scheduled Jobs Engine
Handles periodic synchronization for Philippine equity market events:
  1. Daily Post-Market Quotes & Scoring Sync (16:00 PHT / 08:00 UTC)
  2. Morning Pre-Market Watchlist Alerts & Investor Briefing (08:30 PHT / 00:30 UTC)
  3. Weekly Quantitative Research PDF Digest (Monday 08:00 PHT / 00:00 UTC)
"""

from __future__ import annotations
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_session
from pse_quant.db.models import PipelineRun
from pse_quant.services.stock_service import StockService
from pse_quant.services.customer_service import CustomerService

logger = logging.getLogger("pse_quant.scheduler")

# Timezone offset: Philippine Standard Time (PHT) is UTC+8
PHT_OFFSET = timedelta(hours=8)
PHT_TZ = timezone(PHT_OFFSET, name="PHT")


def get_current_pht() -> datetime:
    """Returns current datetime in Philippine Standard Time (PHT)."""
    return datetime.now(PHT_TZ)


def execute_job(job_name: str, session: Session | None = None) -> dict[str, Any]:
    """
    Executes a specific named automated pipeline task.
    Supports:
      - 'quotes_sync': scrapes daily quotes, refreshes prices, recalculates scores
      - 'morning_alerts': evaluates active member watchlists and dispatches MoS alerts
      - 'weekly_report': compiles executive ReportLab PDF and emails weekly digest
    """
    clean_job = job_name.lower().strip()
    logger.info(f"[Scheduler] Executing scheduled job: '{clean_job}' at {get_current_pht().isoformat()}")

    def _run(s: Session) -> dict[str, Any]:
        run_record = PipelineRun(
            run_type=f"scheduled_{clean_job}",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        s.add(run_record)
        s.commit()

        try:
            if clean_job in ("quotes_sync", "quotes", "market_close"):
                updated_count = StockService.collect_quotes_only(session=s)
                ranked = StockService.recompute_scores(session=s)
                summary = {
                    "job": "quotes_sync",
                    "quotes_updated": updated_count,
                    "ranked_categories": {k: len(v) for k, v in ranked.items()},
                }
            elif clean_job in ("morning_alerts", "alerts", "pre_market"):
                alerts = CustomerService.evaluate_and_dispatch_alerts(session=s)
                summary = {
                    "job": "morning_alerts",
                    "alerts_dispatched_count": len(alerts),
                    "alerts": alerts,
                }
            elif clean_job in ("weekly_report", "digest", "monday_briefing"):
                res = CustomerService.dispatch_weekly_digest(session=s)
                summary = {
                    "job": "weekly_report",
                    "digest_result": res,
                }
            else:
                raise ValueError(f"Unknown scheduled job name: '{clean_job}'")

            run_record.status = "completed"
            run_record.summary_json = summary
            run_record.completed_at = datetime.now(timezone.utc)
            s.commit()
            logger.info(f"[Scheduler] Job '{clean_job}' completed successfully: {summary}")
            return {"status": "completed", "job": clean_job, "summary": summary}

        except Exception as e:
            logger.exception(f"[Scheduler] Job '{clean_job}' failed: {e}")
            run_record.status = "failed"
            run_record.error_message = str(e)
            run_record.completed_at = datetime.now(timezone.utc)
            s.commit()
            return {"status": "failed", "job": clean_job, "error": str(e)}

    if session:
        return _run(session)
    else:
        with get_session() as s:
            return _run(s)


# In-memory execution ledger to prevent double-execution within the same operational window
_LAST_EXECUTED: dict[str, Any] = {}


def run_scheduler_tick() -> list[dict[str, Any]]:
    """
    Checks the current PHT wall-clock against scheduled operational windows.
    Returns list of job execution results for tasks triggered in this tick.
    Guarantees exactly-once execution per calendar date per job.
    """
    now_pht = get_current_pht()
    today_pht = now_pht.date()
    weekday = now_pht.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    hour = now_pht.hour
    minute = now_pht.minute

    executed = []

    # 1. Weekday Post-Market Quotes Sync (16:00 - 16:05 PHT, Mon-Fri)
    if weekday in range(0, 5) and hour == 16 and minute in range(0, 5):
        if _LAST_EXECUTED.get("quotes_sync") != today_pht:
            logger.info("[Scheduler] Post-market sync window detected.")
            res = execute_job("quotes_sync")
            _LAST_EXECUTED["quotes_sync"] = today_pht
            executed.append(res)

    # 2. Weekday Morning Pre-Market Alerts (08:30 - 08:35 PHT, Mon-Fri)
    if weekday in range(0, 5) and hour == 8 and minute in range(30, 35):
        if _LAST_EXECUTED.get("morning_alerts") != today_pht:
            logger.info("[Scheduler] Pre-market alert evaluation window detected.")
            res = execute_job("morning_alerts")
            _LAST_EXECUTED["morning_alerts"] = today_pht
            executed.append(res)

    # 3. Monday Morning Research Digest (08:00 - 08:05 PHT, Monday only)
    if weekday == 0 and hour == 8 and minute in range(0, 5):
        if _LAST_EXECUTED.get("weekly_report") != today_pht:
            logger.info("[Scheduler] Monday quantitative report broadcast window detected.")
            res = execute_job("weekly_report")
            _LAST_EXECUTED["weekly_report"] = today_pht
            executed.append(res)

    return executed


def run_scheduler_daemon(poll_interval: int = 60, max_iterations: int | None = None) -> None:
    """
    Continuous background daemon runner.
    Polls every `poll_interval` seconds and triggers scheduled market jobs.
    """
    logger.info(f"[*] Starting StockPilot PH Automated Job Daemon (PHT: {get_current_pht().strftime('%Y-%m-%d %H:%M:%S')})")
    iterations = 0

    while True:
        try:
            executed = run_scheduler_tick()
            if executed:
                logger.info(f"[Scheduler] Tick triggered {len(executed)} jobs: {executed}")
        except Exception as e:
            logger.error(f"[Scheduler Error] Exception during scheduler tick: {e}")

        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            logger.info("[Scheduler] Max iterations reached, exiting daemon loop.")
            break

        time.sleep(poll_interval)
