# scheduler_jobs/backfill_jobs.py — One-time historical financial data backfill
def run_backfill():
    """One-time historical backfill: fetch 2018-2023 financials for all active tickers."""
    from scraper.pse_financial_reports import backfill_historical_financials
    from scraper.pse_session           import make_session
    from db.database import get_all_tickers, get_all_cmpy_ids

    tickers  = get_all_tickers(active_only=True)
    cmpy_ids = get_all_cmpy_ids()
    session  = make_session()

    total      = len(tickers)
    cumulative = {'fetched': 0, 'skipped': 0, 'errors': 0}

    def _write_backfill_progress(msg: str):
        try:
            import db.db_connection as _dbc
            conn = _dbc.get_connection()
            conn.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES(%s,%s,NOW()) "
                "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at",
                ('backfill_progress', msg),
            )
            conn.commit()
        except Exception:
            pass

    _write_backfill_progress(f'0/{total} — starting...')

    for i, ticker in enumerate(tickers):
        cmpy_id = cmpy_ids.get(ticker)
        if not cmpy_id:
            cumulative['skipped'] += 1
            continue
        stats = backfill_historical_financials(session, cmpy_id, ticker)
        for k in cumulative:
            cumulative[k] += stats.get(k, 0)
        done = i + 1
        msg  = (f'{done}/{total} — {ticker} '
                f'(fetched={cumulative["fetched"]}, '
                f'errors={cumulative["errors"]})')
        _write_backfill_progress(msg)
        if done % 10 == 0 or done == total:
            print(f'  Backfill progress: {msg}')

    _write_backfill_progress(f'Done — {total} tickers, {cumulative["fetched"]} years fetched')
    print(f"  Backfill complete: {total} tickers processed, "
          f"{cumulative['fetched']} years fetched")
