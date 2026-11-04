# feedback/scheduler_feedback.py — Feedback scheduler job wrappers
# Thin wrappers for feedback loop jobs. These are called by scheduler.py.
# No logic here — just delegates to the actual feedback modules.

from datetime import date


def run_snapshot_job() -> None:
    """Take monthly score snapshot (defaults to today)."""
    print("[feedback] run_snapshot_job: starting...")
    try:
        from feedback.snapshot import take_monthly_snapshot
        take_monthly_snapshot()
        print("[feedback] run_snapshot_job: done.")
    except Exception as exc:
        print(f"[feedback] run_snapshot_job ERROR: {exc}")


def run_monthly_scorecard_job() -> None:
    """Run monthly scorecard (defaults to previous month)."""
    print("[feedback] run_monthly_scorecard_job: starting...")
    try:
        from feedback.monthly_scorecard import run_monthly_scorecard
        run_monthly_scorecard()
        print("[feedback] run_monthly_scorecard_job: done.")
    except Exception as exc:
        print(f"[feedback] run_monthly_scorecard_job ERROR: {exc}")


def run_track_record_job() -> None:
    """Compute track record (defaults to today)."""
    print("[feedback] run_track_record_job: starting...")
    try:
        from feedback.track_record import compute_track_record
        compute_track_record()
        print("[feedback] run_track_record_job: done.")
    except Exception as exc:
        print(f"[feedback] run_track_record_job ERROR: {exc}")


def run_quarterly_review_job() -> None:
    """Run quarterly review."""
    print("[feedback] run_quarterly_review_job: starting...")
    try:
        from feedback.quarterly_review import run_quarterly_review
        run_quarterly_review()
        print("[feedback] run_quarterly_review_job: done.")
    except Exception as exc:
        print(f"[feedback] run_quarterly_review_job ERROR: {exc}")


def run_psei_daily_scrape() -> None:
    """Fetch today's PSEi closing price."""
    date_str = date.today().isoformat()
    print(f"[feedback] run_psei_daily_scrape: fetching PSEi close for {date_str}...")
    try:
        from scraper.pse_index import fetch_psei_close
        result = fetch_psei_close(date_str)
        print(f"[feedback] run_psei_daily_scrape: result={result}")
    except Exception as exc:
        print(f"[feedback] run_psei_daily_scrape ERROR: {exc}")
