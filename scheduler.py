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
    run_daily_job, run_daily_score, run_daily_report, run_weekly_scrape,
    _score_and_rank, _top5_changed, _significant_score_change, _build_changes,
)

try:
    from alerts.alert_engine import run_alert_check
    from alerts.disclosure_monitor import run_disclosure_check
except ImportError:
    from alert_engine import run_alert_check
    from disclosure_monitor import run_disclosure_check

from config import (DAILY_ALERT_HOUR, DAILY_ALERT_MINUTE,
                    WEEKLY_SCRAPE_DAY, WEEKLY_SCRAPE_HOUR)
from db.db_settings import get_setting

__all__ = [
    'run_daily_job', 'run_daily_score', 'run_daily_report', 'run_weekly_scrape',
    '_score_and_rank', '_top5_changed', '_significant_score_change', '_build_changes',
    'load_sample_stocks', '_load_stocks',
    'FILTERS', 'SCORERS', 'PORTFOLIO_NAMES',
    'run_alert_check', 'run_disclosure_check',
    'start_scheduler', 'main',
]


def start_scheduler():
    """
    Starts the APScheduler background scheduler with five jobs:
      - Disclosure monitor: every 15 minutes (PSE Edge feed polling)
      - Alert check:        every weekday at 6:30 AM PHT
      - Scoring run:        every weekday at 4:00 PM PHT (score + save, no PDF)
      - Report run:         every weekday at 6:00 PM PHT (PDF if rankings changed)
      - Full scrape:        every Sunday at 10:00 PM PHT
    Blocks until interrupted (Ctrl+C).
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron     import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        print("APScheduler not installed. Run: py -m pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone='Asia/Manila')

    # Read schedule times from DB (dashboard-editable), fallback to config
    alert_h  = int(get_setting('alert_hour',    DAILY_ALERT_HOUR))
    alert_m  = int(get_setting('alert_minute',  DAILY_ALERT_MINUTE))
    score_h  = int(get_setting('score_hour',    17))
    score_m  = int(get_setting('score_minute',  30))
    report_h = int(get_setting('report_hour',   18))   # 6 PM — send PDF
    report_m = int(get_setting('report_minute', 0))

    # 15-minute disclosure feed monitor (runs all day, every day)
    scheduler.add_job(
        run_disclosure_check,
        IntervalTrigger(minutes=15),
        id='disclosure_monitor',
        name='PSE Disclosure Feed Monitor (15-min)',
        misfire_grace_time=120,
    )
    scheduler.add_job(
        run_alert_check,
        CronTrigger(day_of_week='mon-fri', hour=alert_h, minute=alert_m),
        id='daily_alert_check',
        name='PSE Alert Check (price/dividend/earnings)',
        misfire_grace_time=600,
    )
    # 4 PM — score, detect changes, queue PDF if needed (no Discord PDF yet)
    scheduler.add_job(
        run_daily_score,
        CronTrigger(day_of_week='mon-fri', hour=score_h, minute=score_m),
        id='daily_pse_score',
        name='PSE Daily Score (4 PM)',
        misfire_grace_time=600,
    )
    # 6 PM — send PDF to Discord only if rankings changed
    scheduler.add_job(
        run_daily_report,
        CronTrigger(day_of_week='mon-fri', hour=report_h, minute=report_m),
        id='daily_pse_report',
        name='PSE Daily Report (6 PM)',
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
    print(f"  Disclosure monitor: every 15 minutes (all day)")
    print(f"  Alert check:        weekdays {alert_h:02d}:{alert_m:02d} PHT")
    print(f"  Score run:          weekdays {score_h:02d}:{score_m:02d} PHT")
    print(f"  Report run:         weekdays {report_h:02d}:{report_m:02d} PHT")
    print(f"  Full scrape:        {WEEKLY_SCRAPE_DAY.upper()} {WEEKLY_SCRAPE_HOUR:02d}:00 PHT")
    print("  Press Ctrl+C to stop")
    print("=" * 55)

    print("  Scheduler active — waiting for jobs to trigger...")

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
    parser.add_argument(
        '--run-disclosure',
        action='store_true',
        help='Run one disclosure feed check immediately (for testing)',
    )
    parser.add_argument(
        '--run-score',
        action='store_true',
        help='Run the 4 PM scoring phase only (no PDF sent)',
    )
    parser.add_argument(
        '--run-report',
        action='store_true',
        help='Run the 6 PM report phase only (sends PDF if pending)',
    )
    args = parser.parse_args()

    db.init_db()

    if args.run_alerts:
        print("Running alert check now...")
        run_alert_check(dry_run=args.dry_run)
    elif args.run_score:
        print("Running 4 PM scoring phase now...")
        run_daily_score()
    elif args.run_report:
        print("Running 6 PM report phase now...")
        run_daily_report()
    elif args.run_now:
        print("Running one full daily cycle now...")
        run_daily_job()
    elif args.run_weekly:
        print("Running weekly full financial scrape now...")
        run_weekly_scrape()
    elif args.run_disclosure:
        print("Running disclosure feed check now...")
        n = run_disclosure_check(dry_run=args.dry_run)
        print(f"  {n} disclosure(s) {'detected' if args.dry_run else 'sent'}.")
    else:
        start_scheduler()


if __name__ == '__main__':
    main()
