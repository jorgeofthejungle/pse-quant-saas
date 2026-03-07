# ============================================================
# scheduler.py — PUBLIC FACADE + CLI Entry Point
# PSE Quant SaaS — Phase 4
# ============================================================
# Runs every weekday at 4:00 PM PHT (after market close).
#
# Sub-modules:
#   scheduler_data.py — load_sample_stocks(), _load_stocks(),
#                       FILTERS / SCORERS / PORTFOLIO_NAMES maps
#   scheduler_jobs.py — run_daily_job(), _score_and_rank(),
#                       _top5_changed(), _build_changes()
#
# Usage:
#   py scheduler.py              # starts live scheduler (blocking)
#   py scheduler.py --run-now    # runs one cycle immediately (for testing)
# ============================================================

import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'alerts'))

import database as db

from scheduler_data import (
    load_sample_stocks, _load_stocks,
    FILTERS, SCORERS, PORTFOLIO_NAMES, SCRAPER_AVAILABLE,
)
from scheduler_jobs import (
    run_daily_job, _score_and_rank, _top5_changed, _build_changes,
)

try:
    from alerts.alert_engine import run_alert_check
except ImportError:
    from alert_engine import run_alert_check

from config import DAILY_ALERT_HOUR, DAILY_ALERT_MINUTE

__all__ = [
    'run_daily_job', '_score_and_rank', '_top5_changed', '_build_changes',
    'load_sample_stocks', '_load_stocks',
    'FILTERS', 'SCORERS', 'PORTFOLIO_NAMES',
    'run_alert_check',
    'start_scheduler', 'main',
]


def start_scheduler():
    """
    Starts the APScheduler background scheduler with two jobs:
      - Alert check:  every weekday at 6:30 AM PHT (before market open)
      - Scoring run:  every weekday at 4:00 PM PHT (after market close)
    Blocks until interrupted (Ctrl+C).
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("APScheduler not installed. Run: py -m pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone='Asia/Manila')

    scheduler.add_job(
        run_alert_check,
        CronTrigger(day_of_week='mon-fri',
                    hour=DAILY_ALERT_HOUR, minute=DAILY_ALERT_MINUTE),
        id='daily_alert_check',
        name='PSE Alert Check (price/dividend/earnings)',
        misfire_grace_time=600,
    )
    scheduler.add_job(
        run_daily_job,
        CronTrigger(day_of_week='mon-fri', hour=16, minute=0),
        id='daily_pse_run',
        name='PSE Daily Score & Report',
        misfire_grace_time=600,
    )

    print("=" * 55)
    print("  PSE QUANT SAAS — Scheduler Started")
    print(f"  Alert check:  weekdays {DAILY_ALERT_HOUR:02d}:{DAILY_ALERT_MINUTE:02d} PHT")
    print("  Score & report: weekdays 16:00 PHT")
    print("  Press Ctrl+C to stop")
    print("=" * 55)

    for job in scheduler.get_jobs():
        print(f"  [{job.name}]  next: {job.next_run_time}")
    print()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


def main():
    parser = argparse.ArgumentParser(
        description='PSE Quant SaaS — Daily Scheduler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  py scheduler.py                         # start live scheduler\n'
            '  py scheduler.py --run-now               # run score cycle immediately\n'
            '  py scheduler.py --run-alerts            # run alert check immediately\n'
            '  py scheduler.py --run-alerts --dry-run  # alert check, no Discord\n'
        )
    )
    parser.add_argument(
        '--run-now',
        action='store_true',
        help='Run one full scoring cycle immediately (for testing)',
    )
    parser.add_argument(
        '--run-alerts',
        action='store_true',
        help='Run the alert check immediately (for testing)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Combined with --run-alerts: detect alerts without sending to Discord',
    )
    args = parser.parse_args()

    db.init_db()

    if args.run_alerts:
        print("Running alert check now...")
        run_alert_check(dry_run=args.dry_run)
    elif args.run_now:
        print("Running one full daily cycle now...")
        run_daily_job()
    else:
        start_scheduler()


if __name__ == '__main__':
    main()
