"""
pse_quant/tasks — Distributed Task Queue & Leased Worker Package
PSE Quant SaaS (v2 Rebuild) — Lab 9
"""

from pse_quant.tasks.engine import (
    task_queue,
    TaskQueueService,
    TaskWorker,
    TaskWorkerSwarm,
    task_registry,
    task,
    TaskStatus,
    global_worker_swarm,
)
import pse_quant.tasks.registry  # Auto-load registered task handlers

__all__ = [
    "task_queue",
    "TaskQueueService",
    "TaskWorker",
    "TaskWorkerSwarm",
    "task_registry",
    "task",
    "TaskStatus",
    "global_worker_swarm",
]
