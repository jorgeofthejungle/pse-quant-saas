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
    run_daily_job, run_weekly_scrape,
    _score_and_rank, _top5_changed, _significant_score_change, _build_changes,
)

try:
    from alerts.alert_engine import run_alert_check
except ImportError:
    from alert_engine import run_alert_check

from config import (DAILY_ALERT_HOUR, DAILY_ALERT_MINUTE,
                    WEEKLY_SCRAPE_DAY, WEEKLY_SCRAPE_HOUR)
from db.db_settings import get_setting

__all__ = [
    'run_daily_job', 'run_weekly_scrape',
    '_score_and_rank', '_top5_changed', '_significant_score_change', '_build_changes',
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

    # Read schedule times from DB (dashboard-editable), fallback to config
    alert_h = int(get_setting('alert_hour',   DAILY_ALERT_HOUR))
    alert_m = int(get_setting('alert_minute', DAILY_ALERT_MINUTE))
    score_h = int(get_setting('score_hour',   16))
    score_m = int(get_setting('score_minute', 0))

    scheduler.add_job(
        run_alert_check,
        CronTrigger(day_of_week='mon-fri', hour=alert_h, minute=alert_m),
        id='daily_alert_check',
        name='PSE Alert Check (price/dividend/earnings)',
        misfire_grace_time=600,
    )
    scheduler.add_job(
        run_daily_job,
        CronTrigger(day_of_week='mon-fri', hour=score_h, minute=score_m),
        id='daily_pse_run',
        name='PSE Daily Score & Report',
        misfire_grace_time=600,
    )
    scheduler.add_job(
        run_weekly_scrape,
        CronTrigger(day_of_week=WEEKLY_SCRAPE_DAY,
                    hour=WEEKLY_SCRAPE_HOUR, minute=0),
        id='weekly_full_scrape',
        name='PSE Weekly Full Financial Scrape',
        misfire_grace_time=3600,
    )

    print("=" * 55)
    print("  PSE QUANT SAAS — Scheduler Started")
    print(f"  Alert check:    weekdays {alert_h:02d}:{alert_m:02d} PHT")
    print(f"  Score & report: weekdays {score_h:02d}:{score_m:02d} PHT")
    print(f"  Full scrape:    {WEEKLY_SCRAPE_DAY.upper()} {WEEKLY_SCRAPE_HOUR:02d}:00 PHT")
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
    parser.add_argument(
        '--run-weekly',
        action='store_true',
        help='Run the weekly full financial scrape immediately (for testing)',
    )
    args = parser.parse_args()

    db.init_db()

    if args.run_alerts:
        print("Running alert check now...")
        run_alert_check(dry_run=args.dry_run)
    elif args.run_now:
        print("Running one full daily cycle now...")
        run_daily_job()
    elif args.run_weekly:
        print("Running weekly full financial scrape now...")
        run_weekly_scrape()
    else:
        start_scheduler()


if __name__ == '__main__':
    main()
