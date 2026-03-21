# ============================================================
# routes_manual_entry.py — Manual Financial Data Entry
# PSE Quant SaaS — Dashboard blueprint
# ============================================================
# Allows admin to enter or correct financial data for any
# stock/year — primarily for cases where PSE Edge is missing
# data (e.g. GSMI 2022, GLO 2022).
# ============================================================

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in ['db', 'engine', 'scraper']:
    sys.path.insert(0, str(ROOT / p))
sys.path.insert(0, str(ROOT))

from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, jsonify)

manual_entry_bp = Blueprint('manual_entry', __name__)

# ── Field definitions (label, db_column, unit hint) ──────────
FIELDS = [
    ('revenue',     'Revenue',       'PHP M'),
    ('net_income',  'Net Income',    'PHP M'),
    ('equity',      'Equity',        'PHP M'),
    ('total_debt',  'Total Debt',    'PHP M'),
    ('cash',        'Cash',          'PHP M'),
    ('operating_cf','Operating CF',  'PHP M'),
    ('capex',       'CAPEX',         'PHP M'),
    ('ebitda',      'EBITDA',        'PHP M'),
    ('eps',         'EPS',           'PHP/share'),
    ('dps',         'DPS',           'PHP/share'),
]


def _get_all_tickers_with_financials() -> list:
    """Returns list of tickers that have rows in financials, plus all stocks."""
    import database as db
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM financials ORDER BY ticker"
    ).fetchall()
    conn.close()
    return [r['ticker'] for r in rows]


def _get_financials_all_years(ticker: str) -> list:
    """Returns all financial rows for a ticker, newest first."""
    import database as db
    conn = db.get_connection()
    rows = conn.execute("""
        SELECT year, revenue, net_income, equity, total_debt, cash,
               operating_cf, capex, ebitda, eps, dps, updated_at
        FROM financials
        WHERE ticker = ?
        ORDER BY year DESC
    """, (ticker.upper(),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_stock_name(ticker: str) -> str | None:
    """Returns company name for a ticker, or None if not found."""
    import database as db
    conn = db.get_connection()
    row = conn.execute(
        "SELECT name FROM stocks WHERE ticker = ?", (ticker.upper(),)
    ).fetchone()
    conn.close()
    return row['name'] if row else None


# ── Routes ────────────────────────────────────────────────────

@manual_entry_bp.route('/')
def index():
    """List page: search stocks, jump to entry form."""
    tickers = _get_all_tickers_with_financials()
    query = request.args.get('ticker', '').strip().upper()
    if query:
        return redirect(url_for('manual_entry.entry_form', ticker=query))
    return render_template('manual_entry.html',
                           tickers=tickers,
                           ticker=None,
                           financials=[],
                           stock_name=None,
                           fields=FIELDS)


@manual_entry_bp.route('/<ticker>')
def entry_form(ticker: str):
    """Entry form for a specific ticker — shows all years with edit forms."""
    ticker = ticker.upper()
    tickers = _get_all_tickers_with_financials()
    financials = _get_financials_all_years(ticker)
    stock_name = _get_stock_name(ticker)
    return render_template('manual_entry.html',
                           tickers=tickers,
                           ticker=ticker,
                           financials=financials,
                           stock_name=stock_name,
                           fields=FIELDS)


@manual_entry_bp.route('/<ticker>/<int:year>', methods=['POST'])
def save_financials(ticker: str, year: int):
    """Save one year of financials for a ticker (force=True overwrites existing)."""
    import database as db
    ticker = ticker.upper()

    # Parse form — only include non-empty numeric values
    kwargs = {}
    parse_errors = []
    for field, _label, _unit in FIELDS:
        raw = request.form.get(field, '').strip()
        if raw == '':
            kwargs[field] = None
            continue
        try:
            kwargs[field] = float(raw)
        except ValueError:
            parse_errors.append(f"'{field}' is not a valid number (got: {raw!r})")

    if parse_errors:
        flash('Save failed — ' + '; '.join(parse_errors), 'error')
        return redirect(url_for('manual_entry.entry_form', ticker=ticker))

    # All values are None — nothing to save
    if all(v is None for v in kwargs.values()):
        flash('No values entered — nothing was saved.', 'warning')
        return redirect(url_for('manual_entry.entry_form', ticker=ticker))

    try:
        db.upsert_financials(
            ticker, year,
            revenue=kwargs.get('revenue'),
            net_income=kwargs.get('net_income'),
            equity=kwargs.get('equity'),
            total_debt=kwargs.get('total_debt'),
            cash=kwargs.get('cash'),
            operating_cf=kwargs.get('operating_cf'),
            capex=kwargs.get('capex'),
            ebitda=kwargs.get('ebitda'),
            eps=kwargs.get('eps'),
            dps=kwargs.get('dps'),
            force=True,
        )
        # Log to activity_log
        filled = [f for f, v in kwargs.items() if v is not None]
        detail = f"Fields saved: {', '.join(filled)}"
        try:
            db.log_activity(
                category='manual_entry',
                action=f'Manual financials saved: {ticker} {year}',
                detail=detail,
                status='ok',
            )
        except Exception:
            pass  # log failure should not block save

        flash(f'Saved {ticker} {year} successfully ({len(filled)} field(s) written).', 'success')
    except Exception as exc:
        flash(f'Database error: {exc}', 'error')

    return redirect(url_for('manual_entry.entry_form', ticker=ticker))


@manual_entry_bp.route('/api/financials/<ticker>')
def api_financials(ticker: str):
    """JSON: all financial rows for a ticker from DB."""
    rows = _get_financials_all_years(ticker.upper())
    return jsonify({'ticker': ticker.upper(), 'rows': rows})
