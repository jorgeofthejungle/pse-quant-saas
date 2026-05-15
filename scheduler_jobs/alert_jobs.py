# scheduler_jobs/alert_jobs.py — Alert check wrapper + scheduler health check
from datetime import datetime

from .state import _record_heartbeat


def run_alert_check_with_heartbeat(dry_run: bool = False):
    """
    Thin wrapper around run_alert_check() that records a scheduler heartbeat
    on successful completion. Used by the live scheduler so we can track
    that the alert job is still running.
    """
    try:
        from alerts.alert_engine import run_alert_check
    except ImportError:
        try:
            from alert_engine import run_alert_check
        except ImportError as e:
            print(f"  [alert_check] import failed: {e}")
            return
    try:
        run_alert_check(dry_run=dry_run)
    finally:
        _record_heartbeat('alert_check')


def check_scheduler_health() -> dict:
    """
    Returns a status dict showing the last heartbeat time for each scheduled job.
    Used by the dashboard to display scheduler health at a glance.

    Return format:
    {
        'daily_score':   {'last_run': '2026-03-19T17:30:00', 'hours_ago': 23.5, 'ok': True},
        'weekly_scrape': {'last_run': None, 'hours_ago': None, 'ok': False},
        'alert_check':   {'last_run': '2026-03-19T06:30:00', 'hours_ago': 11.0, 'ok': True},
    }
    'ok' is True if last_run is within SCHEDULER_HEARTBEAT_WARN_HOURS hours (or never run yet
    for weekly_scrape, which is tolerated for up to 8 days).
    """
    try:
        from config import SCHEDULER_HEARTBEAT_WARN_HOURS
    except ImportError:
        SCHEDULER_HEARTBEAT_WARN_HOURS = 26

    JOB_WARN_HOURS = {
        'daily_score':   SCHEDULER_HEARTBEAT_WARN_HOURS,
        'weekly_scrape': 24 * 8,   # 8 days — runs once a week
        'alert_check':   SCHEDULER_HEARTBEAT_WARN_HOURS,
    }

    result = {}
    try:
        from db.db_connection import get_connection
        conn = get_connection()
        try:
            for job_name, warn_hours in JOB_WARN_HOURS.items():
                key = f'scheduler_heartbeat_{job_name}'
                row = conn.execute(
                    "SELECT value FROM settings WHERE key = %s", (key,)
                ).fetchone()
                if row and row['value']:
                    last_run = row['value']
                    try:
                        dt        = datetime.fromisoformat(last_run)
                        hours_ago = (datetime.now() - dt).total_seconds() / 3600
                        ok        = hours_ago <= warn_hours
                    except Exception:
                        hours_ago = None
                        ok        = False
                else:
                    last_run  = None
                    hours_ago = None
                    ok        = (job_name == 'weekly_scrape')  # never run yet is OK for weekly

                result[job_name] = {
                    'last_run':  last_run,
                    'hours_ago': round(hours_ago, 1) if hours_ago is not None else None,
                    'ok':        ok,
                }
        finally:
            conn.close()
    except Exception as e:
        print(f"  [check_scheduler_health] DB query failed: {e}")
        for job_name in JOB_WARN_HOURS:
            result.setdefault(job_name, {'last_run': None, 'hours_ago': None, 'ok': False})

    return result
