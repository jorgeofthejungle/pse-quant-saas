# ============================================================
# background.py — Non-Blocking Pipeline Job Runner
# PSE Quant SaaS — Dashboard
# ============================================================
# Wraps pipeline functions in a daemon thread so the Flask
# server stays responsive during long-running jobs.
# Only one job runs at a time (single-user local tool).
# ============================================================

import sys
import subprocess
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


def run_scrape(dry_run: bool = False) -> tuple[bool, str]:
    """Launches the full weekly scrape in a background thread."""
    return _launch('scrape', _do_scrape, dry_run)


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


def _do_scrape(dry_run: bool):
    from scheduler_jobs import run_weekly_scrape
    run_weekly_scrape()
    return 'Weekly scrape complete'


def _do_alerts(dry_run: bool):
    try:
        from alerts.alert_engine import run_alert_check
    except ImportError:
        from alert_engine import run_alert_check
    run_alert_check(dry_run=dry_run)
    return 'Alert check complete'


# ── Scheduler process management ─────────────────────────────

_scheduler_proc = None
_scheduler_lock = threading.Lock()


def start_scheduler() -> tuple[bool, str]:
    """Starts py scheduler.py as a subprocess. Returns (ok, message)."""
    global _scheduler_proc
    with _scheduler_lock:
        if _scheduler_proc and _scheduler_proc.poll() is None:
            return False, 'Scheduler is already running.'
        try:
            _scheduler_proc = subprocess.Popen(
                ['py', str(ROOT / 'scheduler.py')],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log_activity('pipeline', 'scheduler_start',
                         f'PID {_scheduler_proc.pid}', status='ok')
            return True, f'Scheduler started (PID {_scheduler_proc.pid}).'
        except Exception as e:
            return False, f'Failed to start scheduler: {e}'


def stop_scheduler() -> tuple[bool, str]:
    """Terminates the scheduler subprocess."""
    global _scheduler_proc
    with _scheduler_lock:
        if not _scheduler_proc or _scheduler_proc.poll() is not None:
            _scheduler_proc = None
            return False, 'Scheduler is not running.'
        try:
            _scheduler_proc.terminate()
            _scheduler_proc.wait(timeout=5)
        except Exception:
            _scheduler_proc.kill()
        pid = _scheduler_proc.pid
        _scheduler_proc = None
        log_activity('pipeline', 'scheduler_stop', f'PID {pid}', status='ok')
        return True, 'Scheduler stopped.'


def get_scheduler_status() -> dict:
    """Returns {running: bool, pid: int|None}."""
    with _scheduler_lock:
        if _scheduler_proc and _scheduler_proc.poll() is None:
            return {'running': True, 'pid': _scheduler_proc.pid}
        return {'running': False, 'pid': None}


# ── Discord bot process management ───────────────────────────

_bot_proc = None
_bot_lock = threading.Lock()


def start_bot() -> tuple[bool, str]:
    """Starts py discord/bot.py as a subprocess. Returns (ok, message)."""
    global _bot_proc
    with _bot_lock:
        if _bot_proc and _bot_proc.poll() is None:
            return False, 'Discord bot is already running.'
        import os
        if not os.getenv('DISCORD_BOT_TOKEN', ''):
            return False, 'DISCORD_BOT_TOKEN not set in .env. Add it to start the bot.'
        try:
            _bot_proc = subprocess.Popen(
                ['py', str(ROOT / 'discord' / 'bot.py')],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log_activity('pipeline', 'bot_start',
                         f'PID {_bot_proc.pid}', status='ok')
            return True, f'Discord bot started (PID {_bot_proc.pid}).'
        except Exception as e:
            return False, f'Failed to start bot: {e}'


def stop_bot() -> tuple[bool, str]:
    """Terminates the Discord bot subprocess."""
    global _bot_proc
    with _bot_lock:
        if not _bot_proc or _bot_proc.poll() is not None:
            _bot_proc = None
            return False, 'Discord bot is not running.'
        try:
            _bot_proc.terminate()
            _bot_proc.wait(timeout=5)
        except Exception:
            _bot_proc.kill()
        pid = _bot_proc.pid
        _bot_proc = None
        log_activity('pipeline', 'bot_stop', f'PID {pid}', status='ok')
        return True, 'Discord bot stopped.'


def get_bot_status() -> dict:
    """Returns {running: bool, pid: int|None}."""
    with _bot_lock:
        if _bot_proc and _bot_proc.poll() is None:
            return {'running': True, 'pid': _bot_proc.pid}
        return {'running': False, 'pid': None}
