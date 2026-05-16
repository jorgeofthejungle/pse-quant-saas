# tests/test_pending_pdf_state.py — plain-assert runner, no pytest
#
# Run with:  .venv/bin/python tests/test_pending_pdf_state.py
#
# Tests for _write_pending_pdf / _read_pending_pdf round-trip behaviour,
# backward compat with old trigger-only format, non-serializable fallback,
# and the date-check gate.

import sys
import os
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scheduler_jobs.state as state_module
from scheduler_jobs.state import (
    _write_pending_pdf,
    _read_pending_pdf,
)

TODAY = datetime.now().strftime('%Y-%m-%d')
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_stock(ticker, score=70.0):
    return {
        'ticker':        ticker,
        'name':          ticker + ' Corp',
        'score':         score,
        'rank':          1,
        'mos_pct':       15.0,
        'intrinsic':     12.0,
        'dividend_yield': 5.0,
    }


def _patch_state_dir(tmp_path: Path):
    """
    Monkeypatches _STATE_DIR and _PENDING_PDF_PATH in state_module so that
    all file I/O goes to tmp_path for this test.
    Returns a context manager stack (caller must use `with`).
    """
    pending_path = tmp_path / 'pending_pdf.json'
    return patch.multiple(
        state_module,
        _STATE_DIR=tmp_path,
        _PENDING_PDF_PATH=pending_path,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_round_trip_with_ranked_sections():
    """
    Write a payload with ranked_sections and assert _read_pending_pdf returns it intact.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sections = {
            'dividend': [_make_stock('AAA', 80.0), _make_stock('BBB', 75.0)],
            'value':    [_make_stock('CCC', 72.0)],
        }

        with _patch_state_dir(tmp_path):
            _write_pending_pdf(sections, 'top-5 changed', TODAY)
            result = _read_pending_pdf()

        assert result is not None, "_read_pending_pdf should return data for today"
        assert result['date'] == TODAY
        assert result['reason'] == 'top-5 changed'
        assert 'ranked_sections' in result, "ranked_sections key must be present"
        assert result['ranked_sections'] is not None, "ranked_sections must not be None"

        dividend = result['ranked_sections'].get('dividend', [])
        value    = result['ranked_sections'].get('value', [])
        assert len(dividend) == 2, f"Expected 2 dividend stocks, got {len(dividend)}"
        assert len(value) == 1,    f"Expected 1 value stock, got {len(value)}"
        assert dividend[0]['ticker'] == 'AAA'
        assert value[0]['ticker']    == 'CCC'


def test_tickers_backward_compat():
    """
    _write_pending_pdf must populate 'tickers' from the first portfolio section.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sections = {
            'dividend': [_make_stock('AAA'), _make_stock('BBB')],
            'value':    [_make_stock('CCC')],
        }

        with _patch_state_dir(tmp_path):
            _write_pending_pdf(sections, 'first run', TODAY)
            result = _read_pending_pdf()

        assert result is not None
        tickers = result.get('tickers', [])
        # tickers comes from the first section (dividend)
        assert 'AAA' in tickers, f"Expected 'AAA' in tickers, got {tickers}"
        assert 'BBB' in tickers, f"Expected 'BBB' in tickers, got {tickers}"


def test_old_format_returns_none_for_ranked_sections():
    """
    A state file written without ranked_sections (old trigger-only format)
    should return None for that key — must not raise.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pending_path = tmp_path / 'pending_pdf.json'
        pending_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the old-format payload directly (no ranked_sections key)
        old_payload = {
            'date':    TODAY,
            'reason':  'top-5 changed',
            'tickers': ['AAA', 'BBB'],
        }
        with open(pending_path, 'w', encoding='utf-8') as f:
            json.dump(old_payload, f)

        with patch.multiple(
            state_module,
            _STATE_DIR=tmp_path,
            _PENDING_PDF_PATH=pending_path,
        ):
            result = _read_pending_pdf()

        assert result is not None, "Old-format file for today should still be returned"
        assert result.get('ranked_sections') is None, (
            f"ranked_sections should be None for old format, got: {result.get('ranked_sections')!r}"
        )
        assert result['tickers'] == ['AAA', 'BBB']


def test_non_serializable_values_fallback_gracefully():
    """
    When a stock dict contains non-JSON-serializable values (e.g. datetime objects),
    _write_pending_pdf must not raise and must write a valid JSON file.
    """
    from datetime import datetime as dt_class

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        stock_with_datetime = _make_stock('DDD', 60.0)
        stock_with_datetime['last_updated'] = dt_class.now()  # not JSON-serializable

        sections = {
            'dividend': [stock_with_datetime],
            'value':    [_make_stock('EEE', 55.0)],
        }

        # Must not raise
        with _patch_state_dir(tmp_path):
            _write_pending_pdf(sections, 'top-5 changed', TODAY)

        # Must have written a valid JSON file
        pending_path = tmp_path / 'pending_pdf.json'
        assert pending_path.exists(), "pending_pdf.json must be written even on fallback"

        with open(pending_path, encoding='utf-8') as f:
            data = json.load(f)   # must not raise — file must be valid JSON

        assert data.get('date') == TODAY
        assert data.get('reason') == 'top-5 changed'

        # Either ranked_sections is present (with None replacing the datetime)
        # OR the file is trigger-only (graceful fallback) — both are acceptable.
        if 'ranked_sections' in data and data['ranked_sections'] is not None:
            dividend = data['ranked_sections'].get('dividend', [])
            if dividend:
                # The datetime field should have been replaced with None
                assert dividend[0].get('last_updated') is None, (
                    "Non-serializable 'last_updated' should be None after safety filter"
                )


def test_write_never_raises_on_bad_input():
    """
    _write_pending_pdf must never raise regardless of input.
    Passes an entirely non-serializable object as a stock dict value.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Create a stock with a value that defeats even the safety filter
        class Unserializable:
            def __repr__(self): return '<Unserializable>'

        bad_stock = {'ticker': 'BAD', 'score': 50.0, 'bad_field': Unserializable()}
        sections = {'dividend': [bad_stock], 'value': []}

        # Must not raise under any circumstances
        with _patch_state_dir(tmp_path):
            _write_pending_pdf(sections, 'test', TODAY)

        # File should still have been written (trigger-only or full)
        pending_path = tmp_path / 'pending_pdf.json'
        assert pending_path.exists(), "pending_pdf.json must be written even with bad input"
        with open(pending_path, encoding='utf-8') as f:
            json.load(f)  # must be valid JSON


def test_read_returns_none_for_yesterday():
    """
    _read_pending_pdf() must return None for a file dated yesterday (date-check gate).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pending_path = tmp_path / 'pending_pdf.json'
        pending_path.parent.mkdir(parents=True, exist_ok=True)

        old_payload = {
            'date':            YESTERDAY,
            'reason':          'top-5 changed',
            'tickers':         ['AAA'],
            'ranked_sections': {'dividend': [_make_stock('AAA')], 'value': []},
        }
        with open(pending_path, 'w', encoding='utf-8') as f:
            json.dump(old_payload, f)

        with patch.multiple(
            state_module,
            _STATE_DIR=tmp_path,
            _PENDING_PDF_PATH=pending_path,
        ):
            result = _read_pending_pdf()

        assert result is None, (
            f"Expected None for yesterday's state file, got: {result!r}"
        )


def test_read_returns_none_when_file_missing():
    """
    _read_pending_pdf() returns None when pending_pdf.json does not exist.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pending_path = tmp_path / 'pending_pdf.json'
        # Do not create the file

        with patch.multiple(
            state_module,
            _STATE_DIR=tmp_path,
            _PENDING_PDF_PATH=pending_path,
        ):
            result = _read_pending_pdf()

        assert result is None, "Expected None when file is absent"


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        test_round_trip_with_ranked_sections,
        test_tickers_backward_compat,
        test_old_format_returns_none_for_ranked_sections,
        test_non_serializable_values_fallback_gracefully,
        test_write_never_raises_on_bad_input,
        test_read_returns_none_for_yesterday,
        test_read_returns_none_when_file_missing,
    ]

    passed = 0
    failed = 0
    print()
    print('=' * 60)
    print('  PENDING PDF STATE TESTS')
    print('=' * 60)

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
    print('=' * 60)
    if failed:
        raise SystemExit(1)
