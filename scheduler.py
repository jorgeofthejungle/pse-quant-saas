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

import database as db

from scheduler_data import (
    load_sample_stocks, _load_stocks,
    FILTERS, SCORERS, PORTFOLIO_NAMES, SCRAPER_AVAILABLE,
)
from scheduler_jobs import (
    run_daily_job, _score_and_rank, _top5_changed, _build_changes,
)

__all__ = [
    'run_daily_job', '_score_and_rank', '_top5_changed', '_build_changes',
    'load_sample_stocks', '_load_stocks',
    'FILTERS', 'SCORERS', 'PORTFOLIO_NAMES',
    'start_scheduler', 'main',
]


def start_scheduler():
    """
    Starts the APScheduler background scheduler.
    Runs run_daily_job() every weekday at 4:00 PM PHT.
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
        run_daily_job,
        CronTrigger(day_of_week='mon-fri', hour=16, minute=0),
        id='daily_pse_run',
        name='PSE Daily Score & Report',
        misfire_grace_time=600,
    )

    print("=" * 55)
    print("  PSE QUANT SAAS — Scheduler Started")
    print("  Runs every weekday at 4:00 PM PHT")
    print("  Press Ctrl+C to stop")
    print("=" * 55)

    next_run = scheduler.get_jobs()[0].next_run_time
    print(f"  Next scheduled run: {next_run}")
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
            '  py scheduler.py              # start live scheduler\n'
            '  py scheduler.py --run-now    # run one cycle immediately\n'
        )
    )
    parser.add_argument(
        '--run-now',
        action='store_true',
        help='Run one full cycle immediately (for testing)',
    )
    args = parser.parse_args()

    db.init_db()

    if args.run_now:
        print("Running one full daily cycle now...")
        run_daily_job()
    else:
        start_scheduler()


if __name__ == '__main__':
    main()
