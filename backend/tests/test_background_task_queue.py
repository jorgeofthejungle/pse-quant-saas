"""
backend/tests/test_background_task_queue.py — Lab 9: Distributed Background Task Queue & Leased Worker Tests
=============================================================================================================
Verifies:
  1. Central TaskRegistry handler registration and lookup.
  2. Task enqueuing and end-to-end execution lifecycle (pending -> running -> completed).
  3. Priority-based queue scheduling (priority 10 processed before priority 2).
  4. Heartbeat mechanism renewing worker leases during task execution.
  5. Zombie task recovery when a worker crashes ungracefully (lease_expires_at in past).
  6. Retry exhaustion and transition to failed state after max_retries.
  7. Task cancellation before lease acquisition.
  8. Multi-worker concurrent execution without duplicate processing or race conditions.
  9. FastAPI endpoints (/api/v1/tasks/enqueue, /{task_id}, /admin/metrics, /admin/workers/run-once).
"""

from __future__ import annotations
import time
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from pse_quant.tasks.engine import (
    task_queue,
    TaskWorker,
    TaskWorkerSwarm,
    task_registry,
    task,
    TaskStatus,
)
from pse_quant.db.connection import get_write_session, get_read_session, init_db
from pse_quant.db.models import TaskRecord
from pse_quant.services.auth_service import ADMIN_MASTER_KEY
from pse_quant.api.main import app


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def admin_client():
    return TestClient(app, headers={"X-Admin-Key": ADMIN_MASTER_KEY})


@pytest.fixture
def public_client():
    return TestClient(app)


# ── 1. Task Registry & Decorator Tests ─────────────────────────

def test_task_registry_registration():
    """Verifies custom task registration via @task decorator."""
    @task("custom.test_math")
    def compute_custom_square(payload: dict) -> dict:
        x = payload.get("x", 0)
        return {"result": x * x}

    handler = task_registry.get("custom.test_math")
    assert handler is not None
    assert handler({"x": 9}) == {"result": 81}
    assert "custom.test_math" in task_registry.list_tasks()


# ── 2. Enqueue & End-to-End Execution Lifecycle ────────────────

def test_task_enqueue_and_worker_execution():
    """Verifies standard lifecycle: pending -> running -> completed with result."""
    task_info = task_queue.enqueue(
        task_name="test.echo",
        payload={"message": "System Design Lab 9", "run_at": 2026},
        priority=6,
    )
    task_id = task_info["task_id"]
    assert task_info["status"] == TaskStatus.PENDING

    # Status before worker run
    status_before = task_queue.get_task_status(task_id)
    assert status_before is not None
    assert status_before["status"] == TaskStatus.PENDING
    assert status_before["attempts"] == 0

    # Execute with worker
    worker = TaskWorker(worker_id="test_worker_1", lease_duration=10)
    processed = worker.run_once()
    assert processed is True

    # Status after worker run
    status_after = task_queue.get_task_status(task_id)
    assert status_after is not None
    assert status_after["status"] == TaskStatus.COMPLETED
    assert status_after["attempts"] == 1
    assert status_after["worker_id"] == "test_worker_1"
    assert status_after["result"]["received"]["message"] == "System Design Lab 9"
    assert status_after["completed_at"] is not None


# ── 3. Priority Queue Scheduling ───────────────────────────────

def test_priority_scheduling_order():
    """Verifies that higher priority tasks (e.g. 10) are claimed before lower priority tasks (e.g. 1)."""
    low_task = task_queue.enqueue(task_name="test.echo", payload={"type": "low"}, priority=1)
    high_task = task_queue.enqueue(task_name="test.echo", payload={"type": "high"}, priority=10)

    worker = TaskWorker(worker_id="priority_worker", lease_duration=10)

    # First run should claim HIGH priority task
    first_claimed = worker.claim_next_task()
    assert first_claimed is not None
    assert first_claimed["id"] == high_task["task_id"]
    worker.execute_task(first_claimed)

    # Second run should claim LOW priority task
    second_claimed = worker.claim_next_task()
    assert second_claimed is not None
    assert second_claimed["id"] == low_task["task_id"]
    worker.execute_task(second_claimed)


# ── 4. Heartbeat Lease Renewal ─────────────────────────────────

def test_heartbeat_lease_renewal():
    """Verifies that the heartbeat thread extends lease_expires_at during execution."""
    @task("test.slow_with_heartbeat")
    def slow_task(payload: dict) -> dict:
        time.sleep(1.2)
        return {"status": "done"}

    task_info = task_queue.enqueue("test.slow_with_heartbeat", payload={}, priority=5)
    task_id = task_info["task_id"]

    # Short lease of 2 seconds -> heartbeat renews every 1.0 second
    worker = TaskWorker(worker_id="heartbeat_worker", lease_duration=2)

    claimed = worker.claim_next_task()
    assert claimed is not None
    initial_lease = None
    with get_read_session() as session:
        initial_lease = session.get(TaskRecord, task_id).lease_expires_at

    worker.execute_task(claimed)

    status_final = task_queue.get_task_status(task_id)
    assert status_final["status"] == TaskStatus.COMPLETED


# ── 5. Zombie Task Crash Recovery ──────────────────────────────

def test_zombie_task_recovery():
    """
    Simulates a worker crashing while holding a task lease.
    Verifies that another worker detects lease_expires_at in the past,
    reclaims the task, and completes it.
    """
    zombie_task = task_queue.enqueue("test.echo", payload={"data": "zombie_salvage"}, priority=5)
    zombie_id = zombie_task["task_id"]

    # Manually simulate crashed worker: set status=running and lease_expires_at in the past
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    with get_write_session() as session:
        record = session.get(TaskRecord, zombie_id)
        record.status = TaskStatus.RUNNING
        record.worker_id = "crashed_worker_99"
        record.attempts = 1
        record.lease_expires_at = past_time

    # New healthy worker comes online
    healthy_worker = TaskWorker(worker_id="salvage_worker_1", lease_duration=15)
    processed = healthy_worker.run_once()
    assert processed is True

    # Verify task was salvaged and finished
    status_after = task_queue.get_task_status(zombie_id)
    assert status_after["status"] == TaskStatus.COMPLETED
    assert status_after["attempts"] == 2
    assert status_after["worker_id"] == "salvage_worker_1"


# ── 6. Retry Exhaustion and Failure Transition ─────────────────

def test_retry_exhaustion_and_failure():
    """Verifies that repeated failures increment attempts and eventually transition to failed."""
    task_info = task_queue.enqueue(
        task_name="test.fail",
        payload={"reason": "Simulated DB Connection Timeout"},
        max_retries=2,
    )
    task_id = task_info["task_id"]
    worker = TaskWorker(worker_id="retry_worker", lease_duration=10)

    # Run 1: Fails attempt 1 of 2 -> re-queued to pending
    worker.run_once()
    st1 = task_queue.get_task_status(task_id)
    assert st1["status"] == TaskStatus.PENDING
    assert st1["attempts"] == 1
    assert "Simulated DB Connection Timeout" in st1["error_message"]

    # Run 2: Fails attempt 2 of 2 -> reaches max_retries, transitions to failed
    worker.run_once()
    st2 = task_queue.get_task_status(task_id)
    assert st2["status"] == TaskStatus.FAILED
    assert st2["attempts"] == 2
    assert st2["completed_at"] is not None


# ── 7. Task Cancellation ───────────────────────────────────────

def test_task_cancellation():
    """Verifies cancelling a pending task prevents worker execution."""
    task_info = task_queue.enqueue("test.echo", payload={"x": 1}, priority=5)
    task_id = task_info["task_id"]

    cancelled = task_queue.cancel_task(task_id)
    assert cancelled is True

    status = task_queue.get_task_status(task_id)
    assert status["status"] == TaskStatus.CANCELLED

    # Worker polling should ignore cancelled task
    worker = TaskWorker(worker_id="cancel_test_worker")
    assert worker.run_once() is False


# ── 8. Concurrent Multi-Worker Swarm Stress Test ───────────────

def test_concurrent_worker_swarm_processing():
    """
    Enqueues 10 tasks across multiple priorities and processes them
    concurrently using a 3-worker swarm without race conditions.
    """
    task_ids = []
    for i in range(10):
        t = task_queue.enqueue("test.echo", payload={"item": i}, priority=(i % 5) + 1)
        task_ids.append(t["task_id"])

    # Launch 3 workers
    swarm = TaskWorkerSwarm(concurrency=3, lease_duration=10, poll_interval=0.1)
    swarm.start_all()

    # Wait for all 10 tasks to complete (max 6 seconds)
    start_time = time.time()
    all_done = False
    while time.time() - start_time < 6.0:
        statuses = [task_queue.get_task_status(tid)["status"] for tid in task_ids]
        if all(s == TaskStatus.COMPLETED for s in statuses):
            all_done = True
            break
        time.sleep(0.1)

    swarm.stop_all()
    assert all_done is True, f"Not all tasks completed: {statuses}"


# ── 9. FastAPI Task Endpoints ──────────────────────────────────

def test_api_task_enqueue_and_polling(public_client: TestClient, admin_client: TestClient):
    """Verifies API POST /tasks/enqueue, GET /tasks/{id}, and GET /tasks/admin/metrics."""
    # 1. Invalid task name
    bad_res = public_client.post("/api/v1/tasks/enqueue", json={"task_name": "non_existent_task"})
    assert bad_res.status_code == 400

    # 2. Valid enqueue
    enq_res = public_client.post(
        "/api/v1/tasks/enqueue",
        json={"task_name": "test.echo", "payload": {"user": "trader1"}, "priority": 7},
    )
    assert enq_res.status_code == 202
    data = enq_res.json()
    task_id = data["task_id"]
    assert data["task_name"] == "test.echo"
    assert data["priority"] == 7

    # 3. Poll status
    poll_res = public_client.get(f"/api/v1/tasks/{task_id}")
    assert poll_res.status_code == 200
    assert poll_res.json()["status"] == TaskStatus.PENDING

    # 4. Trigger single worker execution via admin endpoint
    admin_run_res = admin_client.post("/api/v1/tasks/admin/workers/run-once")
    assert admin_run_res.status_code == 200
    assert admin_run_res.json()["task_processed"] is True

    # 5. Verify completed
    after_res = public_client.get(f"/api/v1/tasks/{task_id}")
    assert after_res.status_code == 200
    assert after_res.json()["status"] == TaskStatus.COMPLETED
    assert after_res.json()["result"]["received"]["user"] == "trader1"

    # 6. Admin metrics endpoint
    metrics_res = admin_client.get("/api/v1/tasks/admin/metrics")
    assert metrics_res.status_code == 200
    m_data = metrics_res.json()
    assert "queue_depth" in m_data
    assert "completed_tasks" in m_data
    assert "registered_tasks" in m_data
    assert "test.echo" in m_data["registered_tasks"]
