"""
Tests for engine.mos.enrich_mos()

Run: .venv/bin/python tests/test_enrich_mos.py
"""
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'db'))

from engine.mos import (
    enrich_mos,
    calc_ddm,
    calc_eps_pe,
    calc_dcf,
    calc_hybrid_intrinsic,
    calc_mos_pct,
)
from config import IV_WEIGHTS, CONGLOMERATE_DISCOUNT

PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'

errors = []


# ── Helpers ────────────────────────────────────────────────────

def _make_stock(**overrides):
    """Return a minimal stock dict with sensible defaults."""
    base = {
        'ticker':          'TST',
        'dps_last':         1.0,
        'dividend_cagr_5y': 0.05,
        'fcf_per_share':    5.0,
        'revenue_cagr':     0.08,
        'current_price':   30.0,
        'sector':          'Industrial',
    }
    base.update(overrides)
    return base


def _fake_financials(eps_list):
    """Return a list of financial dicts with the given EPS values."""
    return [{'eps': e} for e in eps_list]


# ── Test 1: valid inputs produce correct fields ────────────────

def test_valid_stock_fields():
    """
    enrich_mos() sets intrinsic_value, mos_price, mos_pct correctly
    when financials and stock data are fully present.
    """
    eps_values = [3.0, 3.5, 4.0]
    stock = _make_stock()

    # Compute expected values using the same functions
    eps_3y  = eps_values[:3]
    ddm_iv, _ = calc_ddm(stock['dps_last'], stock['dividend_cagr_5y'])
    eps_iv, _ = calc_eps_pe(eps_3y)
    dcf_iv, _ = calc_dcf(stock['fcf_per_share'], stock['revenue_cagr'])
    expected_iv, _ = calc_hybrid_intrinsic(ddm_iv, eps_iv, dcf_iv, weights=IV_WEIGHTS)
    expected_mos_price = round(expected_iv * 0.70, 2) if expected_iv else None
    expected_mos_pct   = calc_mos_pct(expected_iv, stock['current_price'])

    with patch('database.get_financials', return_value=_fake_financials(eps_values)):
        result = enrich_mos([stock])

    s = result[0]
    ok_iv    = s['intrinsic_value'] == expected_iv
    ok_price = s['mos_price']       == expected_mos_price
    ok_pct   = s['mos_pct']         == expected_mos_pct

    print(f'  [{PASS if ok_iv    else FAIL}] valid stock intrinsic_value: '
          f'expected {expected_iv}, got {s["intrinsic_value"]}')
    print(f'  [{PASS if ok_price else FAIL}] valid stock mos_price: '
          f'expected {expected_mos_price}, got {s["mos_price"]}')
    print(f'  [{PASS if ok_pct   else FAIL}] valid stock mos_pct: '
          f'expected {expected_mos_pct}, got {s["mos_pct"]}')

    for label, ok in [('intrinsic_value', ok_iv), ('mos_price', ok_price), ('mos_pct', ok_pct)]:
        if not ok:
            errors.append(f'valid_stock_{label}')


# ── Test 2: missing dps_last and fcf_per_share → all None ─────

def test_missing_inputs_yields_none():
    """
    When dps_last and fcf_per_share are absent (None), DDM and DCF both
    return None. If EPS data is also empty, all three fields are None.
    """
    stock = _make_stock(dps_last=None, fcf_per_share=None)

    with patch('database.get_financials', return_value=[]):
        result = enrich_mos([stock])

    s = result[0]
    ok_iv    = s['intrinsic_value'] is None
    ok_price = s['mos_price']       is None
    ok_pct   = s['mos_pct']         is None

    print(f'  [{PASS if ok_iv    else FAIL}] missing inputs intrinsic_value is None '
          f'(got {s["intrinsic_value"]})')
    print(f'  [{PASS if ok_price else FAIL}] missing inputs mos_price is None '
          f'(got {s["mos_price"]})')
    print(f'  [{PASS if ok_pct   else FAIL}] missing inputs mos_pct is None '
          f'(got {s["mos_pct"]})')

    for label, ok in [('intrinsic_value', ok_iv), ('mos_price', ok_price), ('mos_pct', ok_pct)]:
        if not ok:
            errors.append(f'missing_inputs_{label}')


# ── Test 3: holding firm gets conglomerate discount ────────────

def test_holding_firm_discount():
    """
    A stock in 'Holding Firms' sector should have its IV reduced by
    CONGLOMERATE_DISCOUNT (20%) before mos_price and mos_pct are derived.
    """
    eps_values = [3.0, 3.5, 4.0]
    stock_hf  = _make_stock(sector='Holding Firms')
    stock_reg = _make_stock(sector='Industrial')

    with patch('database.get_financials', return_value=_fake_financials(eps_values)):
        result_hf  = enrich_mos([stock_hf])

    with patch('database.get_financials', return_value=_fake_financials(eps_values)):
        result_reg = enrich_mos([stock_reg])

    iv_hf  = result_hf[0]['intrinsic_value']
    iv_reg = result_reg[0]['intrinsic_value']

    # Both should have a non-None IV
    if iv_reg is None or iv_hf is None:
        ok_discount = False
        print(f'  [{FAIL}] holding firm discount: IV is None (reg={iv_reg}, hf={iv_hf})')
        errors.append('holding_firm_discount_iv_none')
        return

    expected_iv_hf = round(iv_reg * (1 - CONGLOMERATE_DISCOUNT), 2)
    ok_discount    = iv_hf == expected_iv_hf

    # mos_price should also reflect the discounted IV
    expected_mos_price_hf = round(expected_iv_hf * 0.70, 2)
    ok_mos_price = result_hf[0]['mos_price'] == expected_mos_price_hf

    print(f'  [{PASS if ok_discount  else FAIL}] holding firm IV discounted: '
          f'expected {expected_iv_hf}, got {iv_hf}')
    print(f'  [{PASS if ok_mos_price else FAIL}] holding firm mos_price discounted: '
          f'expected {expected_mos_price_hf}, got {result_hf[0]["mos_price"]}')

    if not ok_discount:
        errors.append('holding_firm_discount')
    if not ok_mos_price:
        errors.append('holding_firm_mos_price')


# ── Test 4: no exception raised even on bad data ───────────────

def test_no_exception_on_bad_data():
    """
    enrich_mos() must never raise — it catches per-stock exceptions silently.
    """
    stock = _make_stock()

    def _bad_financials(*args, **kwargs):
        raise RuntimeError("DB is down")

    raised = False
    try:
        with patch('database.get_financials', side_effect=_bad_financials):
            result = enrich_mos([stock])
        s = result[0]
        ok = (s['intrinsic_value'] is None
              and s['mos_price']   is None
              and s['mos_pct']     is None)
    except Exception:
        raised = True
        ok     = False

    print(f'  [{PASS if not raised else FAIL}] no exception raised on DB failure')
    print(f'  [{PASS if ok         else FAIL}] fields are None after DB failure '
          f'(iv={stock.get("intrinsic_value")}, price={stock.get("mos_price")})')

    if raised:
        errors.append('exception_raised_on_bad_data')
    if not ok:
        errors.append('fields_not_none_after_bad_data')


# ── Test 5: returns the same list object ──────────────────────

def test_returns_same_list():
    """enrich_mos() should return the same list object (mutates in-place)."""
    stock = _make_stock()
    stocks = [stock]

    with patch('database.get_financials', return_value=[]):
        result = enrich_mos(stocks)

    ok = result is stocks
    print(f'  [{PASS if ok else FAIL}] returns same list object')
    if not ok:
        errors.append('returns_same_list')


# ── Runner ─────────────────────────────────────────────────────

if __name__ == '__main__':
    print()
    print('=' * 60)
    print('  test_enrich_mos — engine.mos.enrich_mos()')
    print('=' * 60)

    print('\n[1] Valid inputs produce correct intrinsic_value, mos_price, mos_pct')
    test_valid_stock_fields()

    print('\n[2] Missing dps_last and fcf_per_share with no EPS data → all None')
    test_missing_inputs_yields_none()

    print('\n[3] Holding Firms sector gets conglomerate discount applied to IV')
    test_holding_firm_discount()

    print('\n[4] No exception raised when DB call fails — fields set to None')
    test_no_exception_on_bad_data()

    print('\n[5] Returns the same list (in-place mutation)')
    test_returns_same_list()

    print()
    print('=' * 60)
    if errors:
        print(f'  FAILED: {len(errors)} test(s): {", ".join(errors)}')
    else:
        print('  All tests passed.')
    print('=' * 60)
    print()

    sys.exit(1 if errors else 0)
