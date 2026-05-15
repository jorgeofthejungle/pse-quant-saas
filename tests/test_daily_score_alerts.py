import sys
import os
from unittest.mock import patch, MagicMock, ANY

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'discord'))

import scheduler_jobs.daily_jobs as djobs
from scheduler_jobs.daily_jobs import run_daily_score, run_daily_report


# ============================================================
# Shared helpers
# ============================================================

def _stock(ticker='TEST'):
    return {
        'ticker': ticker,
        'name': ticker + ' Corp',
        'sector': 'Holdings',
        'score': 70.0,
        'rank': 1,
        'current_price': 10.0,
        'category': 'High Yield',
    }


def _reach_save_block(mock_alert, db_mock=None, scorer_weights=None):
    """
    Run run_daily_score() with all prerequisites mocked so it reaches
    the save-scores block. Returns once the function completes.
    """
    stock = _stock()
    ranked = [stock]
    mock_db = db_mock or MagicMock()

    sw = scorer_weights or {'unified': {}, 'dividend': {}}

    with patch.object(djobs, '_check_price_freshness', return_value=True), \
         patch.object(djobs, 'scrape_daily_prices', None), \
         patch.object(djobs, '_load_stocks', return_value=[stock]), \
         patch.object(djobs, '_run_score_pipeline',
                      return_value=(ranked, [stock], [], [], [stock], {})), \
         patch.object(djobs, '_record_heartbeat'), \
         patch.object(djobs, '_write_pending_pdf'), \
         patch.object(djobs, '_clear_pending_pdf'), \
         patch.object(djobs, '_load_signal_cache', return_value={}), \
         patch.object(djobs, '_save_signal_cache'), \
         patch.object(djobs, 'db', mock_db), \
         patch('publisher.send_ops_alert', mock_alert), \
         patch('publisher.send_rescore_notice'), \
         patch('publisher.WEBHOOKS', {'alerts': '', 'rankings': ''}), \
         patch('config.SCORER_WEIGHTS', sw), \
         patch('engine.scorer_v2.rank_stocks_v2', return_value=ranked), \
         patch('engine.filters_v2.filter_unified_batch', return_value=([stock], [])), \
         patch('engine.sector_stats.compute_sector_stats', return_value={}):
        run_daily_score()


def _reach_report_block(mock_alert, mock_write_held=None, mock_send_report=None,
                        fail_portfolio=None):
    """
    Run run_daily_report() with all prerequisites mocked so it reaches
    the portfolio scoring step. If fail_portfolio is set, rank_stocks_v2
    raises for that portfolio type.
    """
    stock = _stock()
    ranked = [stock]
    mock_db = MagicMock()
    mock_db.get_all_tickers.return_value = ['TEST']

    def _rank_side_effect(eligible, sector_stats=None, financials_map=None,
                          portfolio_type=None):
        if portfolio_type == fail_portfolio:
            raise RuntimeError(f"scorer crash for {portfolio_type}")
        return ranked

    with patch.object(djobs, '_read_pending_pdf',
                      return_value={'date': '2026-05-15', 'reason': 'top-5 changed'}), \
         patch.object(djobs, '_clear_pending_pdf'), \
         patch.object(djobs, '_run_score_pipeline',
                      return_value=(ranked, [stock], [], [], [stock], {})), \
         patch.object(djobs, '_enrich_mos', side_effect=lambda s: s), \
         patch.object(djobs, '_write_held_pdf', mock_write_held or MagicMock()), \
         patch.object(djobs, '_read_held_pdf', return_value=None), \
         patch.object(djobs, '_clear_held_pdf', MagicMock()), \
         patch.object(djobs, 'db', mock_db), \
         patch('publisher.send_ops_alert', mock_alert), \
         patch('publisher.send_report', mock_send_report or MagicMock(return_value=True)), \
         patch('publisher.WEBHOOKS', {'rankings': 'https://discord.com/fake'}), \
         patch('engine.scorer_v2.rank_stocks_v2', side_effect=_rank_side_effect), \
         patch('engine.sector_stats.compute_sector_stats', return_value={}), \
         patch('pdf_generator.generate_report'), \
         patch('os.makedirs'):
        run_daily_report()


# ============================================================
# Block 7a: per-portfolio save failure → send_ops_alert
# ============================================================

def test_block7a_portfolio_save_sends_ops_alert():
    """When per-portfolio scoring/save raises, send_ops_alert fires with stage 'Daily Score: portfolio save failed'."""
    mock_alert = MagicMock()
    mock_db = MagicMock()
    mock_db.save_scores.return_value = None
    mock_db.get_financials.return_value = []
    mock_db.get_all_tickers.return_value = []

    def save_v2(today, ranked, portfolio_type):
        if portfolio_type != 'unified':
            raise Exception(f"write failure for {portfolio_type}")

    mock_db.save_scores_v2.side_effect = save_v2

    _reach_save_block(
        mock_alert,
        db_mock=mock_db,
        scorer_weights={'unified': {}, 'dividend': {}, 'value': {}},
    )

    stages = [c[0][0] for c in mock_alert.call_args_list]
    assert any(s == "Daily Score: portfolio save failed" for s in stages), (
        f"Expected 'Daily Score: portfolio save failed', got: {stages}"
    )


# ============================================================
# Block 7b: outer DB save failure → send_ops_alert
# ============================================================

def test_block7b_outer_db_save_sends_ops_alert():
    """When outer db.save_scores raises, send_ops_alert fires with stage 'Daily Score: DB save failed'."""
    mock_alert = MagicMock()
    mock_db = MagicMock()
    mock_db.save_scores.side_effect = Exception("postgres connection lost")

    _reach_save_block(mock_alert, db_mock=mock_db)

    stages = [c[0][0] for c in mock_alert.call_args_list]
    assert any(s == "Daily Score: DB save failed" for s in stages), (
        f"Expected 'Daily Score: DB save failed', got: {stages}"
    )


# ============================================================
# Block 10: bad PDF held — send_report NOT called
# ============================================================

def test_block10_bad_pdf_send_report_not_called():
    """When portfolio scoring fails during PDF gen, send_report must NOT be called."""
    mock_alert = MagicMock()
    mock_send_report = MagicMock(return_value=True)

    _reach_report_block(mock_alert, mock_send_report=mock_send_report, fail_portfolio='dividend')

    mock_send_report.assert_not_called(), (
        f"send_report must not be called when PDF is held: {mock_send_report.call_args_list}"
    )


def test_block10_bad_pdf_sends_ops_alert():
    """When portfolio scoring fails during PDF gen, send_ops_alert fires with 'Daily Report: portfolio scoring failed'."""
    mock_alert = MagicMock()

    _reach_report_block(mock_alert, fail_portfolio='value')

    stages = [c[0][0] for c in mock_alert.call_args_list]
    assert any(s == "Daily Report: portfolio scoring failed" for s in stages), (
        f"Expected 'Daily Report: portfolio scoring failed', got: {stages}"
    )


def test_block10_bad_pdf_writes_held_pdf():
    """When portfolio scoring fails, _write_held_pdf is called with the pdf path."""
    mock_alert = MagicMock()
    mock_write_held = MagicMock()

    _reach_report_block(mock_alert, mock_write_held=mock_write_held, fail_portfolio='dividend')

    mock_write_held.assert_called_once()
    pdf_path_arg = mock_write_held.call_args[0][0]
    assert 'StockPilot' in pdf_path_arg or '.pdf' in pdf_path_arg, (
        f"Expected pdf path in _write_held_pdf call, got: {pdf_path_arg}"
    )


# ============================================================
# run_approve_pdf: sends held PDF and clears hold
# ============================================================

def test_approve_pdf_sends_report_and_clears():
    """run_approve_pdf() reads held PDF, calls send_report, clears the hold."""
    from scheduler_jobs.daily_jobs import run_approve_pdf

    held_data = {
        'pdf_path': '/tmp/StockPilot_PH_Rankings_2026-05-15.pdf',
        'reason': 'Empty sections: dividend',
        'held_at': '2026-05-15T18:00:00',
        'ranked_preview': [{'ticker': 'TEST', 'score': 70.0, 'rank': 1}],
    }
    mock_send_report = MagicMock(return_value=True)
    mock_clear = MagicMock()

    with patch.object(djobs, '_read_held_pdf', return_value=held_data), \
         patch.object(djobs, '_clear_held_pdf', mock_clear), \
         patch('os.path.exists', return_value=True), \
         patch('publisher.send_report', mock_send_report), \
         patch('publisher.WEBHOOKS', {'rankings': 'https://discord.com/fake'}):
        run_approve_pdf()

    mock_send_report.assert_called_once()
    mock_clear.assert_called_once()


def test_approve_pdf_no_held_is_noop():
    """run_approve_pdf() does nothing (and does not raise) when no held PDF exists."""
    from scheduler_jobs.daily_jobs import run_approve_pdf

    mock_send_report = MagicMock()

    with patch.object(djobs, '_read_held_pdf', return_value=None), \
         patch('publisher.send_report', mock_send_report):
        run_approve_pdf()

    mock_send_report.assert_not_called()


# ============================================================
# Run
# ============================================================

if __name__ == '__main__':
    tests = [
        test_block7a_portfolio_save_sends_ops_alert,
        test_block7b_outer_db_save_sends_ops_alert,
        test_block10_bad_pdf_send_report_not_called,
        test_block10_bad_pdf_sends_ops_alert,
        test_block10_bad_pdf_writes_held_pdf,
        test_approve_pdf_sends_report_and_clears,
        test_approve_pdf_no_held_is_noop,
    ]

    passed = 0
    failed = 0
    print()
    print('=' * 55)
    print('  DAILY SCORE ALERT TESTS')
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
