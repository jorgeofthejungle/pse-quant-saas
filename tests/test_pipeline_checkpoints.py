import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock

import main


# ============================================================
# Helpers
# ============================================================

def _make_stock(ticker='TEST'):
    return {
        'ticker':          ticker,
        'name':            ticker + ' Corp',
        'sector':          'Holdings',
        'is_reit':         False,
        'is_bank':         False,
        'score':           70.0,
        'rank':            1,
        'score_breakdown': {},
        'current_price':   10.0,
        'dividend_yield':  5.0,
        'net_income_3y':   [1000, 900, 800],
        'dividends_5y':    [0.5, 0.5, 0.5, 0.5, 0.5],
        'payout_ratio':    40.0,
        'de_ratio':        0.5,
        'operating_cf':    1200,
        'fcf_3y':          [1100, 1000, 900],
        'category':        'High Yield',
    }


def _one_stock():
    return [_make_stock('TEST')]


def _ranked(stocks):
    for i, s in enumerate(stocks):
        s['rank'] = i + 1
    return stocks


# ============================================================
# test_filter_zero_eligible_calls_send_ops_alert
# ============================================================

def test_filter_zero_eligible_calls_send_ops_alert():
    """When filter_unified_batch returns ([], [...]), send_ops_alert is called with stage 'Filter: zero eligible stocks'."""
    stocks = _one_stock()

    with patch.object(main, 'load_stocks', return_value=stocks), \
         patch.object(main, 'validate_all', return_value=(stocks, [{'valid': True, 'warnings': []}])), \
         patch.object(main, 'compute_sector_stats', return_value={}), \
         patch.object(main, 'filter_unified_batch', return_value=([], [{'ticker': 'TEST', 'reason': 'negative equity'}])), \
         patch.object(main, 'send_ops_alert') as mock_alert:
        result = main.run_pipeline(dry_run=True)

    mock_alert.assert_called_once()
    call_args = mock_alert.call_args
    stage = call_args[0][0] if call_args[0] else call_args.kwargs.get('stage', '')
    assert stage == 'Filter: zero eligible stocks', (
        f"Expected stage 'Filter: zero eligible stocks', got {stage!r}"
    )
    assert result is False, f"Expected run_pipeline to return False, got {result!r}"


# ============================================================
# test_pdf_crash_calls_send_ops_alert
# ============================================================

def test_pdf_crash_calls_send_ops_alert():
    """When generate_report raises, send_ops_alert is called with stage 'PDF Generation' and the error message."""
    stocks = _one_stock()
    ranked = _ranked(list(stocks))

    with patch.object(main, 'load_stocks', return_value=stocks), \
         patch.object(main, 'validate_all', return_value=(stocks, [{'valid': True, 'warnings': []}])), \
         patch.object(main, 'compute_sector_stats', return_value={}), \
         patch.object(main, 'filter_unified_batch', return_value=(stocks, [])), \
         patch.object(main, 'rank_stocks_v2', return_value=ranked), \
         patch('db.db_scores.save_scores_v2'), \
         patch.object(main, '_enrich_mos', side_effect=lambda s: s), \
         patch.object(main, '_try_enrich_with_sentiment'), \
         patch.object(main, 'generate_report', side_effect=RuntimeError('template broken')), \
         patch.object(main, 'send_ops_alert') as mock_alert:
        try:
            main.run_pipeline(dry_run=True)
        except Exception:
            pass

    mock_alert.assert_called_once()
    call_args = mock_alert.call_args
    stage = call_args[0][0] if call_args[0] else call_args.kwargs.get('stage', '')
    error = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get('error', '')
    assert stage == 'PDF Generation', (
        f"Expected stage 'PDF Generation', got {stage!r}"
    )
    assert error == 'template broken', (
        f"Expected error 'template broken', got {error!r}"
    )


# ============================================================
# test_pdf_crash_does_not_suppress_exception
# ============================================================

def test_pdf_crash_does_not_suppress_exception():
    """When generate_report raises, run_pipeline must NOT return True."""
    stocks = _one_stock()
    ranked = _ranked(list(stocks))

    with patch.object(main, 'load_stocks', return_value=stocks), \
         patch.object(main, 'validate_all', return_value=(stocks, [{'valid': True, 'warnings': []}])), \
         patch.object(main, 'compute_sector_stats', return_value={}), \
         patch.object(main, 'filter_unified_batch', return_value=(stocks, [])), \
         patch.object(main, 'rank_stocks_v2', return_value=ranked), \
         patch('db.db_scores.save_scores_v2'), \
         patch.object(main, '_enrich_mos', side_effect=lambda s: s), \
         patch.object(main, '_try_enrich_with_sentiment'), \
         patch.object(main, 'generate_report', side_effect=RuntimeError('template broken')), \
         patch.object(main, 'send_ops_alert'):
        raised = False
        returned_true = False
        try:
            result = main.run_pipeline(dry_run=True)
            if result is True:
                returned_true = True
        except Exception:
            raised = True

    assert raised or not returned_true, (
        "run_pipeline() returned True after generate_report raised — must re-raise or return False"
    )


# ============================================================
# test_discord_delivery_false_calls_send_ops_alert
# ============================================================

def test_discord_delivery_false_calls_send_ops_alert():
    """When send_report returns False, send_ops_alert is called with stage 'Discord Delivery'."""
    stocks = _one_stock()
    ranked = _ranked(list(stocks))

    with patch.object(main, 'load_stocks', return_value=stocks), \
         patch.object(main, 'validate_all', return_value=(stocks, [{'valid': True, 'warnings': []}])), \
         patch.object(main, 'compute_sector_stats', return_value={}), \
         patch.object(main, 'filter_unified_batch', return_value=(stocks, [])), \
         patch.object(main, 'rank_stocks_v2', return_value=ranked), \
         patch('db.db_scores.save_scores_v2'), \
         patch.object(main, '_enrich_mos', side_effect=lambda s: s), \
         patch.object(main, '_try_enrich_with_sentiment'), \
         patch.object(main, 'generate_report'), \
         patch.object(main, 'send_report', return_value=False), \
         patch.object(main, 'WEBHOOKS', {'rankings': 'https://discord.com/api/webhooks/fake/rankings'}), \
         patch.object(main, '_send_opportunistic_alerts'), \
         patch.object(main, 'send_ops_alert') as mock_alert:
        main.run_pipeline(dry_run=False)

    mock_alert.assert_called_once()
    call_args = mock_alert.call_args
    stage = call_args[0][0] if call_args[0] else call_args.kwargs.get('stage', '')
    assert stage == 'Discord Delivery', (
        f"Expected stage 'Discord Delivery', got {stage!r}"
    )


# ============================================================
# test_per_stock_mos_failure_no_alert
# ============================================================

def test_per_stock_mos_failure_no_alert():
    """Individual MoS failures per-stock must NOT trigger send_ops_alert."""
    stocks = _one_stock()
    ranked = _ranked(list(stocks))

    def _mos_raises(stock_list):
        # Simulate _enrich_mos blowing up per-stock but returning silently (as designed)
        for s in stock_list:
            # MoS calc for each stock would raise, but the outer _enrich_mos catches it
            s['intrinsic_value'] = None
            s['mos_price'] = None
            s['mos_pct'] = None
        return stock_list

    with patch.object(main, 'load_stocks', return_value=stocks), \
         patch.object(main, 'validate_all', return_value=(stocks, [{'valid': True, 'warnings': []}])), \
         patch.object(main, 'compute_sector_stats', return_value={}), \
         patch.object(main, 'filter_unified_batch', return_value=(stocks, [])), \
         patch.object(main, 'rank_stocks_v2', return_value=ranked), \
         patch('db.db_scores.save_scores_v2'), \
         patch.object(main, '_enrich_mos', side_effect=_mos_raises), \
         patch.object(main, '_try_enrich_with_sentiment'), \
         patch.object(main, 'generate_report'), \
         patch.object(main, 'send_report', return_value=True), \
         patch.object(main, 'WEBHOOKS', {'rankings': 'https://discord.com/api/webhooks/fake/rankings'}), \
         patch.object(main, '_send_opportunistic_alerts'), \
         patch.object(main, 'send_ops_alert') as mock_alert:
        main.run_pipeline(dry_run=False)

    mock_alert.assert_not_called(), (
        f"send_ops_alert was called unexpectedly for per-stock MoS failure: {mock_alert.call_args_list}"
    )


# ============================================================
# Run
# ============================================================

if __name__ == '__main__':
    tests = [
        test_filter_zero_eligible_calls_send_ops_alert,
        test_pdf_crash_calls_send_ops_alert,
        test_pdf_crash_does_not_suppress_exception,
        test_discord_delivery_false_calls_send_ops_alert,
        test_per_stock_mos_failure_no_alert,
    ]

    passed = 0
    failed = 0
    print()
    print('=' * 55)
    print('  PIPELINE CHECKPOINT TESTS')
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
