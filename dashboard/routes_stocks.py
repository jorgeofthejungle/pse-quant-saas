# ============================================================
# routes_stocks.py — Stock Lookup & Analysis Page
# PSE Quant SaaS — Dashboard blueprint
# ============================================================

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in ['db', 'engine', 'scraper']:
    sys.path.insert(0, str(ROOT / p))
sys.path.insert(0, str(ROOT))

from flask import Blueprint, render_template, jsonify, request
from dashboard.security import rate_limit, sanitize_ticker

stocks_bp = Blueprint('stocks', __name__)


def _get_stock_analysis(ticker: str) -> dict:
    """
    Build full analysis dict for a single ticker.
    Returns dict with keys: stock, score, breakdown, mos, filter, financials, error.
    """
    try:
        import database as db
        from scraper.pse_stock_builder import build_stock_dict_from_db
        from engine.filters_v2 import filter_unified
        from engine.scorer_v2 import score_unified
        from engine.mos import (calc_ddm, calc_eps_pe, calc_dcf,
                                calc_hybrid_intrinsic, calc_mos_pct, calc_mos_price)
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    stock = build_stock_dict_from_db(ticker.upper())
    # Attach segment data for holding firms — enables conglomerate scoring
    try:
        from db.db_conglomerates import get_latest_segments
        from engine.conglomerate_scorer import CONGLOMERATE_TICKERS
        if ticker.upper() in CONGLOMERATE_TICKERS:
            segs = get_latest_segments(ticker.upper())
            if segs:
                stock['segment_data'] = segs
    except Exception:
        pass

    if not stock:
        # Check if ticker exists at all
        conn = db.get_connection()
        row = conn.execute(
            "SELECT ticker, name, status FROM stocks WHERE ticker = ?",
            (ticker.upper(),)
        ).fetchone()
        conn.close()
        if row:
            return {'error': f"{ticker.upper()} exists in DB but has no price or financial data yet. "
                             f"Run the weekly scrape to populate it."}
        return {'error': f"Ticker '{ticker.upper()}' not found in database."}

    # Filter check
    eligible, filter_reason = filter_unified(stock)

    # Score
    fin_history = db.get_financials(ticker.upper(), years=10)
    final_score, breakdown = score_unified(stock, financials_history=fin_history)

    # MoS — compute each component then blend
    eps_3y = [f['eps'] for f in fin_history if f.get('eps') is not None][:3]
    ddm_iv, _ = calc_ddm(stock.get('dps_last'), stock.get('dividend_cagr_5y'))
    eps_iv, _ = calc_eps_pe(eps_3y)
    dcf_iv, _ = calc_dcf(stock.get('fcf_per_share'), stock.get('revenue_cagr'))
    iv, _     = calc_hybrid_intrinsic(ddm_iv, eps_iv, dcf_iv,
                                      weights=(0.30, 0.35, 0.35))
    # Apply conglomerate IV discount — calculated if segment data exists, else flat 20%
    if stock.get('sector') == 'Holding Firms' and iv:
        cong_data = breakdown.get('conglomerate', {})
        discount  = cong_data.get('discount_pct', 20.0) / 100.0
        iv = round(iv * (1.0 - discount), 2)
    price     = stock['current_price']
    mos_pct   = calc_mos_pct(iv, price)         if iv and price else None
    mos_price = calc_mos_price(iv, 'unified')   if iv else None

    # Sentiment (from cache — no live fetch here)
    sentiment = db.get_sentiment(ticker.upper())

    # Financial history rows (for display)
    fin_rows = [
        {
            'year':       f['year'],
            'revenue':    f.get('revenue'),
            'net_income': f.get('net_income'),
            'eps':        f.get('eps'),
            'dps':        f.get('dps'),
            'roe':        round(f['net_income'] / f['equity'] * 100, 1)
                          if f.get('net_income') and f.get('equity') and f['equity'] > 0
                          else None,
        }
        for f in fin_history
    ]

    # MoS signal label
    if mos_pct is None:
        mos_signal = 'N/A'
        mos_color  = 'muted'
    elif mos_pct >= 30:
        mos_signal = 'DEEP DISCOUNT'
        mos_color  = 'green'
    elif mos_pct >= 15:
        mos_signal = 'DISCOUNTED'
        mos_color  = 'blue'
    elif mos_pct >= -5:
        mos_signal = 'FAIRLY VALUED'
        mos_color  = 'orange'
    else:
        mos_signal = 'ABOVE ESTIMATE'
        mos_color  = 'red'

    return {
        'error':        None,
        'stock':        stock,
        'score':        round(final_score, 1),
        'breakdown':    breakdown,
        'eligible':     eligible,
        'filter_reason': filter_reason,
        'iv':           round(iv, 2) if iv else None,
        'mos_pct':      round(mos_pct, 1) if mos_pct is not None else None,
        'mos_price':    round(mos_price, 2) if mos_price else None,
        'mos_signal':   mos_signal,
        'mos_color':    mos_color,
        'financials':   fin_rows,
        'sentiment':    sentiment,
    }


def _resolve_ticker(query: str) -> str | None:
    """
    Given a query string, returns the matching ticker.
    Tries exact ticker match first, then partial name match.
    Returns None if nothing found.
    """
    import database as db
    q = query.strip()
    conn = db.get_connection()
    # Exact ticker match
    row = conn.execute(
        "SELECT ticker FROM stocks WHERE ticker = ? AND status = 'active'",
        (q.upper(),)
    ).fetchone()
    if row:
        conn.close()
        return row['ticker']
    # Name contains search (case-insensitive)
    row = conn.execute(
        "SELECT ticker FROM stocks WHERE UPPER(name) LIKE ? AND status = 'active' ORDER BY ticker LIMIT 1",
        (f'%{q.upper()}%',)
    ).fetchone()
    conn.close()
    return row['ticker'] if row else None


@stocks_bp.route('/stocks')
def index():
    query  = request.args.get('ticker', '').strip()
    ticker = ''
    result = None
    if query:
        ticker = _resolve_ticker(query) or query.upper()
        result = _get_stock_analysis(ticker)
        # If exact ticker not found but we searched by name, show what was searched
        if result.get('error') and _resolve_ticker(query) is None:
            result['error'] = f"No stock matching '{query}' found in database."
    return render_template('stocks.html', ticker=ticker, query=query, result=result)


@stocks_bp.route('/api/stocks/search')
@rate_limit(limit=60)
def api_search():
    """Autocomplete: returns [{ticker, name}] matching the query."""
    import database as db
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    conn = db.get_connection()
    rows = conn.execute("""
        SELECT ticker, name FROM stocks
        WHERE status = 'active'
          AND (UPPER(ticker) LIKE ? OR UPPER(name) LIKE ?)
        ORDER BY
          CASE WHEN UPPER(ticker) = ? THEN 0
               WHEN UPPER(ticker) LIKE ? THEN 1
               ELSE 2 END,
          ticker
        LIMIT 10
    """, (
        f'{q.upper()}%', f'%{q.upper()}%',
        q.upper(), f'{q.upper()}%'
    )).fetchall()
    conn.close()
    return jsonify([{'ticker': r['ticker'], 'name': r['name']} for r in rows])


@stocks_bp.route('/api/stock/<ticker>')
@rate_limit(limit=30)
def api_stock(ticker):
    clean = sanitize_ticker(ticker)
    if not clean:
        return jsonify({'error': 'Invalid ticker format.'}), 400
    result = _get_stock_analysis(clean)
    if result.get('stock'):
        s = result['stock']
        result['stock'] = {k: v for k, v in s.items()
                           if isinstance(v, (str, int, float, bool, type(None), list))}
    return jsonify(result)
