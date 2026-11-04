import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'discord'))

from scheduler_jobs.weekly_jobs import run_weekly_scrape


# ============================================================
# Helpers
# ============================================================

def _scraper_raises(exc):
    """Return a mock scraper module whose scrape_all_and_save raises exc."""
    m = MagicMock()
    m.scrape_all_and_save.side_effect = exc
    return m


def _run_with_scraper_exception(exc, mock_alert):
    """
    Run run_weekly_scrape() with SCRAPER_AVAILABLE=True and the scraper
    raising exc. Patches out all unrelated I/O so the test is fast and
    deterministic.
    """
    bad_scraper = _scraper_raises(exc)
    with patch('scheduler_jobs.weekly_jobs.SCRAPER_AVAILABLE', True), \
         patch('scheduler_jobs.weekly_jobs._backup_database'), \
         patch('scheduler_jobs.weekly_jobs._record_heartbeat'), \
         patch('scheduler_jobs.weekly_jobs.run_daily_job'), \
         patch.dict(sys.modules, {
             'scraper.pse_edge_scraper': bad_scraper,
             'pse_edge_scraper': bad_scraper,
         }), \
         patch('publisher.send_ops_alert', mock_alert):
        run_weekly_scrape()


# ============================================================
# test_scrape_exception_calls_send_ops_alert
# ============================================================

def test_scrape_exception_calls_send_ops_alert():
    mock_alert = MagicMock()
    _run_with_scraper_exception(RuntimeError("network timeout"), mock_alert)

    mock_alert.assert_called_once()
    stage = mock_alert.call_args[0][0]
    error = mock_alert.call_args[0][1]
    assert stage == "Weekly Scrape", f"Expected 'Weekly Scrape', got {stage!r}"
    assert "network timeout" in error, f"Expected error to contain 'network timeout', got {error!r}"


# ============================================================
# test_scrape_exception_job_exits_cleanly
# ============================================================

def test_scrape_exception_job_exits_cleanly():
    mock_alert = MagicMock()
    raised = False
    try:
        _run_with_scraper_exception(RuntimeError("network timeout"), mock_alert)
    except Exception:
        raised = True
    assert not raised, "run_weekly_scrape() must not propagate scraper exceptions"


# ============================================================
# test_scrape_import_error_calls_send_ops_alert
# ============================================================

def test_scrape_import_error_calls_send_ops_alert():
    """Both scraper import paths fail — alert fires for ImportError too."""
    mock_alert = MagicMock()
    _run_with_scraper_exception(ImportError("scraper missing"), mock_alert)

    mock_alert.assert_called_once()
    stage = mock_alert.call_args[0][0]
    assert stage == "Weekly Scrape", f"Expected 'Weekly Scrape', got {stage!r}"


# ============================================================
# test_stale_fetch_failure_no_alert
# ============================================================

def test_stale_fetch_failure_no_alert():
    """Non-fatal step failures (stale re-fetch) must NOT trigger send_ops_alert."""
    mock_alert = MagicMock()
    good_scraper = MagicMock()
    good_scraper.scrape_all_and_save.return_value = None

    mock_db = MagicMock()
    mock_db.get_all_tickers.return_value = ['DMC', 'ALI']
    mock_db.get_stale_financials_tickers.side_effect = Exception("db unreachable")

    with patch('scheduler_jobs.weekly_jobs.SCRAPER_AVAILABLE', True), \
         patch('scheduler_jobs.weekly_jobs._backup_database'), \
         patch('scheduler_jobs.weekly_jobs._record_heartbeat'), \
         patch('scheduler_jobs.weekly_jobs.run_daily_job'), \
         patch('scheduler_jobs.weekly_jobs.db', mock_db), \
         patch.dict(sys.modules, {
             'scraper.pse_edge_scraper': good_scraper,
             'pse_edge_scraper': good_scraper,
         }), \
         patch('publisher.send_ops_alert', mock_alert), \
         patch('publisher.WEBHOOKS', {'daily_briefing': ''}):
        run_weekly_scrape()

    mock_alert.assert_not_called(), (
        f"send_ops_alert must not fire for non-fatal stale re-fetch failure: "
        f"{mock_alert.call_args_list}"
    )


# ============================================================
# Run
# ============================================================

if __name__ == '__main__':
    tests = [
        test_scrape_exception_calls_send_ops_alert,
        test_scrape_exception_job_exits_cleanly,
        test_scrape_import_error_calls_send_ops_alert,
        test_stale_fetch_failure_no_alert,
    ]

    passed = 0
    failed = 0
    print()
    print('=' * 55)
    print('  WEEKLY SCRAPE ALERT TESTS')
    print('=' * 55)
    for fn in tests:
        try:
            fn()
            print(f'  PASS  {fn.__name__}')
            passed += 1
        except AssertionError as e:
            print(f'  FAIL  {fn.__name__}: {e}')
            failed += 1
        except Exception as e:
            print(f'  ERROR {fn.__name__}: {type(e).__name__}: {e}')
            failed += 1

    print()
    print(f'  Results: {passed} passed, {failed} failed')
    print('=' * 55)
    if failed:
        raise SystemExit(1)
