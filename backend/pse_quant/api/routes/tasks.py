"""
pse_quant/api/routes/tasks.py — Background Task Queue API Endpoints
PSE Quant SaaS (v2 Rebuild) — Lab 9

Exposes asynchronous task enqueuing, polling, cancellation, and worker queue metrics.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status

from pse_quant.tasks.engine import task_queue, task_registry, TaskWorker
from pse_quant.api.schemas import TaskEnqueueRequest, TaskEnqueueResponse
from pse_quant.api.auth import require_admin

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/enqueue",
    response_model=TaskEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a long-running background task",
)
def enqueue_task(req: TaskEnqueueRequest):
    """Enqueues an asynchronous background job (e.g. ETL sync, PDF generation, email digest)."""
    # Verify task is registered
    if not task_registry.get(req.task_name):
        available = task_registry.list_tasks()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{req.task_name}' is not registered. Available: {available}",
        )

    task_info = task_queue.enqueue(
        task_name=req.task_name,
        payload=req.payload,
        priority=req.priority or 5,
        max_retries=req.max_retries if req.max_retries is not None else 3,
    )
    return task_info


@router.get(
    "/catalog",
    summary="List all registered background task types",
)
def list_task_catalog():
    """Returns the names of all registered background task handlers available for execution."""
    return {"registered_tasks": task_registry.list_tasks()}


@router.get(
    "/admin/metrics",
    summary="Inspect background task queue depth and worker telemetry",
    dependencies=[Depends(require_admin)],
)
def get_task_queue_metrics():
    """Returns queue depth, running tasks, completed/failed counts, and error rate."""
    metrics = task_queue.get_metrics()
    metrics["registered_tasks"] = task_registry.list_tasks()
    return metrics


@router.post(
    "/admin/workers/run-once",
    summary="Trigger an on-demand worker cycle (manual dispatch)",
    dependencies=[Depends(require_admin)],
)
def trigger_worker_run_once():
    """Claims and executes a single pending or zombie task on demand."""
    worker = TaskWorker(worker_id="manual_admin_worker", lease_duration=60)
    processed = worker.run_once()
    return {
        "status": "success",
        "task_processed": processed,
        "queue_metrics": task_queue.get_metrics(),
    }


@router.get(
    "/{task_id}",
    summary="Poll status and results of a background task",
)
def get_task_status(task_id: str = Path(..., min_length=5, max_length=64)):
    """Retrieves current execution status (pending, running, completed, failed), result, or error message."""
    info = task_queue.get_task_status(task_id)
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background task '{task_id}' not found.",
        )
    return info


@router.post(
    "/{task_id}/cancel",
    summary="Cancel a pending background task",
)
def cancel_task(task_id: str = Path(..., min_length=5, max_length=64)):
    """Cancels a pending task before a worker acquires its lease."""
    cancelled = task_queue.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{task_id}' cannot be cancelled (either not found, or already running/completed/failed).",
        )
    return {"status": "success", "task_id": task_id, "message": "Task cancelled successfully."}


@router.get(
    "",
    summary="List recent background tasks",
)
def list_tasks(
    status: Optional[str] = Query(None, pattern="^(pending|running|completed|failed|cancelled)$"),
    task_name: Optional[str] = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=200),
):
    """Lists recent background jobs with optional status and task name filtering."""
    return task_queue.list_tasks(status=status, task_name=task_name, limit=limit)
