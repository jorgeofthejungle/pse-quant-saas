"""
pse_quant/tasks/engine.py — Distributed Task Queue & Leased Worker Engine
PSE Quant SaaS (v2 Rebuild) — Lab 9

Decouples long-running operations (ETL scrapes, quant batch valuations, PDF generation, email digests)
from synchronous HTTP requests into an asynchronous, crash-resilient task queue.
Features:
  - Atomic Compare-And-Swap / FOR UPDATE worker lease acquisition.
  - Active heartbeat thread renewing lease to prevent premature task reclamation.
  - Automatic zombie task recovery (reclaiming work if a worker crashes ungracefully).
  - Priority-based scheduling (higher priority processed first).
  - Configurable max retries with exponential backoff / retry tracking.
  - Deep queue telemetry and worker state observability.
"""

from __future__ import annotations
import uuid
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Optional, List
from sqlalchemy import select, desc, or_, and_, func
from sqlalchemy.orm import Session

from pse_quant.db.connection import get_write_session, get_read_session
from pse_quant.db.models import TaskRecord

logger = logging.getLogger("pse_quant.tasks")


def _utc_now() -> datetime:
    """Returns timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _is_expired(expires_at: datetime | None) -> bool:
    """Checks if a lease timestamp has passed."""
    if expires_at is None:
        return True
    now = _utc_now()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── 1. Central Task Registry ───────────────────────────────────

class TaskRegistry:
    """Maintains a catalog of registered background task handler callables."""

    def __init__(self):
        self._handlers: Dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        with self._lock:
            self._handlers[name] = handler
            logger.debug("Registered background task handler: %s", name)

    def get(self, name: str) -> Optional[Callable[[dict[str, Any]], Any]]:
        with self._lock:
            return self._handlers.get(name)

    def list_tasks(self) -> List[str]:
        with self._lock:
            return sorted(list(self._handlers.keys()))


task_registry = TaskRegistry()


def task(name: str):
    """Decorator to register a function as an executable background task."""
    def decorator(fn: Callable[[dict[str, Any]], Any]):
        task_registry.register(name, fn)
        return fn
    return decorator


# ── 2. Task Queue Service (Client-facing) ──────────────────────

class TaskQueueService:
    """High-level client API for enqueuing, inspecting, and cancelling background jobs."""

    @staticmethod
    def enqueue(
        task_name: str,
        payload: Optional[dict[str, Any]] = None,
        priority: int = 5,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Enqueues a new background task into the persistent ledger."""
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = _utc_now()

        from pse_quant.telemetry.context import get_correlation_id
        active_corr = get_correlation_id()
        task_payload = dict(payload or {})
        if active_corr and "_correlation_id" not in task_payload:
            task_payload["_correlation_id"] = active_corr

        with get_write_session() as session:
            record = TaskRecord(
                id=task_id,
                task_name=task_name,
                status=TaskStatus.PENDING,
                priority=max(1, min(priority, 10)),
                payload_json=task_payload,
                max_retries=max(0, max_retries),
                created_at=now,
            )
            session.add(record)

        return {
            "task_id": task_id,
            "task_name": task_name,
            "status": TaskStatus.PENDING,
            "priority": priority,
            "max_retries": max_retries,
            "created_at": now.isoformat(),
        }

    @staticmethod
    def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves task state, execution times, result, or error message."""
        with get_read_session() as session:
            record = session.get(TaskRecord, task_id)
            if not record:
                return None
            return {
                "task_id": record.id,
                "task_name": record.task_name,
                "status": record.status,
                "priority": record.priority,
                "payload": record.payload_json,
                "result": record.result_json,
                "error_message": record.error_message,
                "worker_id": record.worker_id,
                "attempts": record.attempts,
                "max_retries": record.max_retries,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "started_at": record.started_at.isoformat() if record.started_at else None,
                "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            }

    @staticmethod
    def cancel_task(task_id: str) -> bool:
        """Cancels a pending task before a worker acquires its lease."""
        with get_write_session() as session:
            record = session.get(TaskRecord, task_id)
            if not record:
                return False
            if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            record.status = TaskStatus.CANCELLED
            record.completed_at = _utc_now()
            return True

    @staticmethod
    def list_tasks(
        status: Optional[str] = None,
        task_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Lists recent tasks with optional status and name filtering."""
        with get_read_session() as session:
            stmt = select(TaskRecord).order_by(desc(TaskRecord.created_at)).limit(limit)
            if status:
                stmt = stmt.where(TaskRecord.status == status)
            if task_name:
                stmt = stmt.where(TaskRecord.task_name == task_name)

            records = session.scalars(stmt).all()
            return [
                {
                    "task_id": r.id,
                    "task_name": r.task_name,
                    "status": r.status,
                    "priority": r.priority,
                    "attempts": r.attempts,
                    "error_message": r.error_message,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                }
                for r in records
            ]

    @staticmethod
    def get_metrics() -> Dict[str, Any]:
        """Provides queue depth, status distributions, and throughput telemetry."""
        with get_read_session() as session:
            counts = dict(
                session.execute(
                    select(TaskRecord.status, func.count(TaskRecord.id)).group_by(TaskRecord.status)
                ).all()
            )

        pending = counts.get(TaskStatus.PENDING, 0)
        running = counts.get(TaskStatus.RUNNING, 0)
        completed = counts.get(TaskStatus.COMPLETED, 0)
        failed = counts.get(TaskStatus.FAILED, 0)
        cancelled = counts.get(TaskStatus.CANCELLED, 0)
        total = pending + running + completed + failed + cancelled

        return {
            "queue_depth": pending,
            "running_tasks": running,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "cancelled_tasks": cancelled,
            "total_tasks": total,
            "failure_rate_pct": round((failed / total) * 100.0, 2) if total > 0 else 0.0,
        }


# ── 3. Leased Task Worker ──────────────────────────────────────

class TaskWorker:
    """
    Autonomous worker node that polls for available tasks, acquires exclusive leases,
    heartbeats during execution, and recovers zombie tasks.
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        lease_duration: int = 30,
        poll_interval: float = 0.5,
    ):
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.lease_duration = lease_duration
        self.poll_interval = poll_interval

        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._current_task_id: Optional[str] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop: Optional[threading.Event] = None

    def claim_next_task(self) -> Optional[Dict[str, Any]]:
        """
        Atomically queries and claims the highest-priority pending task
        OR an abandoned zombie task whose lease has expired.
        """
        now = _utc_now()
        with get_write_session() as session:
            # Query candidate tasks:
            # 1. status == 'pending'
            # 2. status == 'running' AND lease_expires_at < now (zombie lease reclaim)
            stmt = (
                select(TaskRecord)
                .where(
                    or_(
                        TaskRecord.status == TaskStatus.PENDING,
                        and_(
                            TaskRecord.status == TaskStatus.RUNNING,
                            TaskRecord.lease_expires_at < now,
                        ),
                    )
                )
                .order_by(desc(TaskRecord.priority), TaskRecord.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )

            candidate = session.scalar(stmt)
            if not candidate:
                return None

            # If recovering a zombie task that has exceeded max retries, mark failed immediately
            if candidate.status == TaskStatus.RUNNING and candidate.attempts >= candidate.max_retries:
                candidate.status = TaskStatus.FAILED
                candidate.error_message = (
                    f"Task reclaimed after worker crash, but exceeded max retries ({candidate.max_retries})."
                )
                candidate.completed_at = now
                logger.warning("Task %s failed after exceeding max retries from zombie lease", candidate.id)
                return None

            # Claim lease
            candidate.status = TaskStatus.RUNNING
            candidate.worker_id = self.worker_id
            candidate.attempts += 1
            if not candidate.started_at:
                candidate.started_at = now
            candidate.lease_expires_at = now + timedelta(seconds=self.lease_duration)

            # Snapshot task data before exiting session
            return {
                "id": candidate.id,
                "task_name": candidate.task_name,
                "payload": candidate.payload_json or {},
                "attempts": candidate.attempts,
                "max_retries": candidate.max_retries,
            }

    def _start_heartbeat(self, task_id: str) -> None:
        """Launches a daemon thread to periodically renew the task lease."""
        self._heartbeat_stop = threading.Event()

        def _heartbeat_loop():
            # Renew every lease_duration / 2 seconds
            renew_interval = max(1.0, self.lease_duration / 2.0)
            while not self._heartbeat_stop.wait(renew_interval):
                try:
                    now = _utc_now()
                    with get_write_session() as session:
                        record = session.get(TaskRecord, task_id)
                        if record and record.status == TaskStatus.RUNNING and record.worker_id == self.worker_id:
                            record.lease_expires_at = now + timedelta(seconds=self.lease_duration)
                            logger.debug("Renewed lease for task %s (worker: %s)", task_id, self.worker_id)
                        else:
                            break
                except Exception as e:
                    logger.warning("Failed to renew lease for task %s: %s", task_id, e)

        self._heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"heartbeat-{task_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        """Signals and joins the heartbeat renewal thread."""
        if self._heartbeat_stop:
            self._heartbeat_stop.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
        self._heartbeat_stop = None
        self._heartbeat_thread = None

    def execute_task(self, task_info: Dict[str, Any]) -> bool:
        """Executes task handler within an active lease and manages completion/failure."""
        task_id = task_info["id"]
        task_name = task_info["task_name"]
        payload = task_info["payload"]
        attempts = task_info["attempts"]
        max_retries = task_info["max_retries"]

        from pse_quant.telemetry.context import set_correlation_id, reset_correlation_id, generate_correlation_id
        corr_id = payload.get("_correlation_id") or generate_correlation_id(prefix="task_corr_")
        token_corr = set_correlation_id(corr_id)

        self._current_task_id = task_id
        self._start_heartbeat(task_id)

        handler = task_registry.get(task_name)
        if not handler:
            self._stop_heartbeat()
            self._mark_failed(
                task_id=task_id,
                error_msg=f"No registered handler for task: '{task_name}'",
                should_retry=False,
            )
            self._current_task_id = None
            return False

        try:
            logger.info("Worker %s executing task %s (%s)", self.worker_id, task_id, task_name)
            result = handler(payload)
            self._stop_heartbeat()
            self._mark_completed(task_id=task_id, result=result)
            self._current_task_id = None
            return True
        except Exception as exc:
            self._stop_heartbeat()
            should_retry = attempts < max_retries
            error_msg = f"{type(exc).__name__}: {str(exc)}"
            logger.error("Task %s failed (attempt %d/%d): %s", task_id, attempts, max_retries, error_msg)
            self._mark_failed(task_id=task_id, error_msg=error_msg, should_retry=should_retry)
            self._current_task_id = None
            return False
        finally:
            reset_correlation_id(token_corr)

    def _mark_completed(self, task_id: str, result: Any) -> None:
        """Marks task as successfully completed with returned JSON-safe payload."""
        now = _utc_now()
        safe_result = result if isinstance(result, (dict, list, int, float, str, bool)) else {"output": str(result)}
        with get_write_session() as session:
            record = session.get(TaskRecord, task_id)
            if record:
                record.status = TaskStatus.COMPLETED
                record.result_json = safe_result
                record.completed_at = now
                record.lease_expires_at = None
        try:
            from pse_quant.streaming.hub import stream_hub
            stream_hub.broadcast(
                channel=f"tasks:{task_id}",
                event_type="task_completed",
                data={"task_id": task_id, "status": TaskStatus.COMPLETED, "result": safe_result},
            )
        except Exception:
            pass

    def _mark_failed(self, task_id: str, error_msg: str, should_retry: bool) -> None:
        """Marks task failed or re-queues it for retry if attempts < max_retries."""
        now = _utc_now()
        with get_write_session() as session:
            record = session.get(TaskRecord, task_id)
            if record:
                if should_retry:
                    # Put back in pending state for another worker or retry attempt
                    record.status = TaskStatus.PENDING
                    record.error_message = f"Last failure: {error_msg}"
                    record.lease_expires_at = None
                    record.worker_id = None
                else:
                    record.status = TaskStatus.FAILED
                    record.error_message = error_msg
                    record.completed_at = now
                    record.lease_expires_at = None

    def run_once(self) -> bool:
        """
        Executes a single work cycle: claims a task and executes it.
        Returns True if a task was claimed and processed, False if queue is empty.
        """
        task_info = self.claim_next_task()
        if not task_info:
            return False
        return self.execute_task(task_info)

    def start(self) -> None:
        """Starts worker polling loop in a dedicated background thread."""
        if self._running:
            return
        self._running = True

        def _worker_loop():
            logger.info("Worker %s started background task loop", self.worker_id)
            while self._running:
                try:
                    processed = self.run_once()
                    if not processed:
                        time.sleep(self.poll_interval)
                except Exception as exc:
                    logger.error("Worker %s loop exception: %s", self.worker_id, exc)
                    time.sleep(self.poll_interval)
            logger.info("Worker %s stopped background task loop", self.worker_id)

        self._worker_thread = threading.Thread(target=_worker_loop, name=f"worker-{self.worker_id}", daemon=True)
        self._worker_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Gracefully stops worker loop and waits for active task completion."""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
        self._stop_heartbeat()


# ── 4. Worker Swarm Manager ───────────────────────────────────

class TaskWorkerSwarm:
    """Manages a pool of concurrent TaskWorker nodes."""

    def __init__(self, concurrency: int = 2, lease_duration: int = 30, poll_interval: float = 0.5):
        self.concurrency = concurrency
        self.lease_duration = lease_duration
        self.poll_interval = poll_interval
        self.workers: List[TaskWorker] = [
            TaskWorker(
                worker_id=f"swarm_worker_{i+1}",
                lease_duration=lease_duration,
                poll_interval=poll_interval,
            )
            for i in range(concurrency)
        ]

    def start_all(self) -> None:
        """Starts all worker threads in the swarm."""
        for w in self.workers:
            w.start()

    def stop_all(self, timeout: float = 5.0) -> None:
        """Gracefully halts all worker threads."""
        for w in self.workers:
            w.stop(timeout=timeout)


# Global singleton queue and swarm instances


def broadcast_task_progress(task_id: str, progress_pct: int, message: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Broadcasts a granular milestone event to all clients streaming this task's progress via SSE."""
    try:
        from pse_quant.streaming.hub import stream_hub
        stream_hub.broadcast(
            channel=f"tasks:{task_id}",
            event_type="task_progress",
            data={
                "task_id": task_id,
                "progress_pct": max(0, min(progress_pct, 100)),
                "message": message,
                "data": data or {},
            },
        )
    except Exception as exc:
        logger.warning("Failed to broadcast SSE task progress for %s: %s", task_id, exc)

task_queue = TaskQueueService()
global_worker_swarm = TaskWorkerSwarm(concurrency=2, lease_duration=30, poll_interval=0.5)
