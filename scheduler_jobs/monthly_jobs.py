# scheduler_jobs/monthly_jobs.py — Monthly dividend calendar + model performance reports
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'db'))

import database as db


def run_monthly_dividend_calendar():
    """
    Posts the monthly dividend calendar to #deep-analysis.
    Shows top dividend-paying stocks by yield + recent PSE Edge announcements.
    Runs on the 1st of each month.
    """
    from publisher import WEBHOOKS, send_dividend_calendar
    from db.db_connection import get_connection
    import datetime as _dt

    month_str    = datetime.now().strftime('%B %Y')
    current_year = _dt.date.today().year

    print(f"\n[monthly_calendar] Building dividend calendar for {month_str}...")

    conn = get_connection()
    try:
        payer_rows = conn.execute("""
            SELECT f.ticker,
                   s.name,
                   f.dps,
                   f.year,
                   p.close AS price,
                   round(f.dps / p.close * 100.0, 2) AS yield_pct
            FROM financials f
            JOIN (
                SELECT ticker, MAX(year) AS max_year
                FROM financials
                WHERE dps > 0 AND year < %s
                GROUP BY ticker
            ) latest ON f.ticker = latest.ticker AND f.year = latest.max_year
            JOIN stocks s ON f.ticker = s.ticker
            JOIN (
                SELECT t.ticker, p2.close
                FROM (SELECT ticker, MAX(date) AS max_date FROM prices GROUP BY ticker) t
                JOIN prices p2 ON p2.ticker = t.ticker AND p2.date = t.max_date
            ) p ON f.ticker = p.ticker
            WHERE f.dps > 0
              AND s.status = 'active'
              AND p.close > 0
              AND f.year < %s
              AND (f.dps / p.close * 100.0) BETWEEN 0.5 AND 20.0
              AND (
                  s.is_reit = 1
                  OR (f.eps > 0 AND (f.dps / f.eps) <= 2.0)
                  OR (f.eps IS NOT NULL AND f.eps <= 0)
                  OR (f.eps IS NULL AND (f.dps / p.close * 100.0) <= 10.0)
                  OR (
                      f.eps IS NULL
                      AND (f.dps / p.close * 100.0) > 10.0
                      AND EXISTS (
                          SELECT 1 FROM financials f2
                          WHERE f2.ticker = f.ticker
                            AND f2.dps > 0
                            AND f2.year < f.year
                            AND f2.year >= f.year - 4
                      )
                  )
              )
            ORDER BY yield_pct DESC
            LIMIT 15
        """, (current_year, current_year)).fetchall()

        payers = [dict(r) for r in payer_rows]

        cutoff    = (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d')
        disc_rows = conn.execute("""
            SELECT ticker, date, title FROM disclosures
            WHERE (type LIKE '%dividend%' OR title LIKE '%dividend%')
            AND date >= %s
            ORDER BY date DESC
            LIMIT 10
        """, (cutoff,)).fetchall()
        recent_disc = [dict(r) for r in disc_rows]
    finally:
        conn.close()

    url = WEBHOOKS.get('deep_analysis', '')
    ok  = send_dividend_calendar(url, month_str, payers, recent_disc)
    print(f"  Dividend calendar {'sent' if ok else 'FAILED'} for {month_str}.")


def run_monthly_model_performance():
    """
    Compares current vs last month's unified scores and posts a
    performance snapshot to #deep-analysis.
    Runs on the 1st of each month.
    """
    from publisher import WEBHOOKS, send_model_performance
    from db.db_connection import get_connection

    month_str = datetime.now().strftime('%B %Y')
    print(f"\n[monthly_perf] Building model performance for {month_str}...")

    conn = get_connection()
    try:
        date_rows = conn.execute(
            "SELECT DISTINCT run_date FROM scores_v2 ORDER BY run_date DESC LIMIT 60"
        ).fetchall()

        if not date_rows:
            print("  [monthly_perf] No scores_v2 data — run scoring first.")
            return

        latest_date  = date_rows[0]['run_date']
        latest_dt    = datetime.strptime(latest_date, '%Y-%m-%d')
        target_prior = latest_dt - timedelta(days=28)

        prior_date = None
        for row in date_rows[1:]:
            dt = datetime.strptime(row['run_date'], '%Y-%m-%d')
            if dt <= target_prior:
                prior_date = row['run_date']
                break

        curr_rows = conn.execute("""
            SELECT sv.ticker, sv.score, sv.rank, sv.category, s.name
            FROM scores_v2 sv
            LEFT JOIN stocks s ON sv.ticker = s.ticker
            WHERE sv.run_date = %s AND sv.rank IS NOT NULL
            ORDER BY sv.rank
            LIMIT 20
        """, (latest_date,)).fetchall()

        current = [dict(r) for r in curr_rows]

        prior = {}
        if prior_date:
            prior_rows = conn.execute(
                "SELECT ticker, score, rank FROM scores_v2 WHERE run_date = %s AND rank IS NOT NULL",
                (prior_date,)
            ).fetchall()
            prior = {r['ticker']: {'score': r['score'], 'rank': r['rank']} for r in prior_rows}
    finally:
        conn.close()

    url = WEBHOOKS.get('deep_analysis', '')
    ok  = send_model_performance(url, month_str, current, prior, latest_date, prior_date)
    print(f"  Model performance {'sent' if ok else 'FAILED'} for {month_str}.")


def run_monthly_jobs():
    """
    Runs both monthly reports on the 1st of each month:
      1. Dividend Calendar  → #deep-analysis
      2. Model Performance  → #deep-analysis
    """
    print(f"\n{'='*55}")
    print(f"  Monthly Reports — {datetime.now().strftime('%B %Y')}")
    print(f"{'='*55}")
    run_monthly_dividend_calendar()
    run_monthly_model_performance()
    print(f"\n  Monthly reports complete.")
