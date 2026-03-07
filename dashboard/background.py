# ============================================================
# background.py — Non-Blocking Pipeline Job Runner
# PSE Quant SaaS — Dashboard
# ============================================================
# Wraps pipeline functions in a daemon thread so the Flask
# server stays responsive during long-running jobs.
# Only one job runs at a time (single-user local tool).
# ============================================================

import sys
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.db_members import log_activity

# ── Global job state (safe for single-user localhost) ────────

_job = {
    'running':  False,
    'type':     None,     # 'scoring' | 'alerts'
    'started':  None,
    'finished': None,
    'result':   None,
    'error':    None,
}
_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────

def get_status() -> dict:
    """Returns a snapshot of the current job state."""
    with _lock:
        return dict(_job)


def is_running() -> bool:
    with _lock:
        return _job['running']


def run_scoring(portfolio: str = 'all', dry_run: bool = False) -> tuple[bool, str]:
    """
    Launches the full scoring pipeline in a background thread.
    portfolio: 'all', 'pure_dividend', 'dividend_growth', 'value'
    Returns (started: bool, message: str).
    """
    return _launch('scoring', _do_scoring, portfolio, dry_run)


def run_alerts(dry_run: bool = False) -> tuple[bool, str]:
    """Launches the alert check in a background thread."""
    return _launch('alerts', _do_alerts, dry_run)


# ── Internal helpers ──────────────────────────────────────────

def _launch(job_type: str, target, *args) -> tuple[bool, str]:
    with _lock:
        if _job['running']:
            return False, f"A '{_job['type']}' job is already running."
        _job.update(
            running=True, type=job_type,
            started=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            finished=None, result=None, error=None,
        )

    t = threading.Thread(target=_wrapper, args=(job_type, target) + args,
                         daemon=True)
    t.start()
    return True, f"{job_type.capitalize()} job started."


def _wrapper(job_type: str, target, *args):
    try:
        result = target(*args)
        with _lock:
            _job.update(
                running=False,
                finished=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                result=str(result) if result is not None else 'Complete',
            )
        log_activity('pipeline', f'{job_type}_complete',
                     _job['result'], status='ok')
    except Exception as exc:
        with _lock:
            _job.update(
                running=False,
                finished=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                error=str(exc),
            )
        log_activity('pipeline', f'{job_type}_error', str(exc), status='error')


def _do_scoring(portfolio: str, dry_run: bool):
    """Calls run_daily_job() or a single-portfolio variant."""
    from scheduler_jobs import run_daily_job
    # run_daily_job handles all portfolios internally
    run_daily_job()
    return 'Scoring complete'


def _do_alerts(dry_run: bool):
    try:
        from alerts.alert_engine import run_alert_check
    except ImportError:
        from alert_engine import run_alert_check
    run_alert_check(dry_run=dry_run)
    return 'Alert check complete'
