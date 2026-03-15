# ============================================================
# routes_conglomerates.py — Conglomerate Segment Data Entry
# PSE Quant SaaS — Dashboard
# ============================================================
# Manual entry of segment financials for the Top 5 PH holding
# firms (SM, AC, JGS, GTCAP, DMC).
# URL prefix: /conglomerates  (registered in app.py)
# ============================================================

import sys
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

from db.db_conglomerates import (
    upsert_segment, get_segments, get_latest_segments,
    get_segment_years, delete_segment, get_all_segment_years,
)
from engine.conglomerate_scorer import (
    CONGLOMERATE_TICKERS, score_all_segments, weighted_segment_score,
    compute_conglomerate_discount,
)

conglomerates_bp = Blueprint('conglomerates', __name__)

# Reference segment map — pre-populated in the UI form
SEGMENT_MAP = {
    'SM':    ['Retail (SMSM)', 'Property (SMPH)', 'Banking (BDO)', 'Mining (Atlas)'],
    'AC':    ['Property (ALI)', 'Banking (BPI)', 'Telco (GLO)', 'Energy (ACEN)', 'Water (MWC)'],
    'JGS':   ['Food (URC)', 'Airline (CEB)', 'Petrochemicals', 'Banking', 'Property (RLC)'],
    'GTCAP': ['Banking (MBT)', 'Property (FLI)', 'Automotive', 'Insurance'],
    'DMC':   ['Construction', 'Mining (SCC)', 'Power (DMCPHI)', 'Water', 'Real Estate'],
}

CURRENT_YEAR = datetime.now().year


@conglomerates_bp.route('/')
def index():
    selected_ticker = request.args.get('ticker', CONGLOMERATE_TICKERS[0])
    selected_year   = request.args.get('year', type=int)

    years = get_segment_years(selected_ticker)
    if selected_year is None and years:
        selected_year = years[0]

    segments = get_segments(selected_ticker, year=selected_year) if selected_year else []

    # Compute live scoring preview if segments available
    preview = None
    if segments:
        scored  = score_all_segments(segments)
        w_score = weighted_segment_score(scored)
        preview = {
            'segments':  scored,
            'w_score':   w_score,
            'discount':  compute_conglomerate_discount(scored, w_score),
        }

    # Data coverage summary for all tickers
    coverage = get_all_segment_years()

    return render_template(
        'conglomerates.html',
        tickers         = CONGLOMERATE_TICKERS,
        segment_map     = SEGMENT_MAP,
        selected_ticker = selected_ticker,
        selected_year   = selected_year,
        years           = years,
        segments        = segments,
        preview         = preview,
        coverage        = coverage,
        current_year    = CURRENT_YEAR,
        now             = datetime.now().strftime('%Y-%m-%d %H:%M'),
    )


@conglomerates_bp.route('/save', methods=['POST'])
def save_segment():
    """Upserts a single segment row from form POST."""
    try:
        parent_ticker  = request.form.get('parent_ticker', '').upper()
        segment_name   = request.form.get('segment_name', '').strip()
        segment_ticker = request.form.get('segment_ticker', '').strip() or None
        year           = int(request.form.get('year', CURRENT_YEAR))
        revenue        = _parse_float(request.form.get('revenue'))
        net_income     = _parse_float(request.form.get('net_income'))
        equity         = _parse_float(request.form.get('equity'))
        notes          = request.form.get('notes', '').strip() or None

        if not parent_ticker or not segment_name:
            flash('Parent ticker and segment name are required.', 'error')
            return redirect(url_for('conglomerates.index',
                                    ticker=parent_ticker, year=year))

        upsert_segment(
            parent_ticker  = parent_ticker,
            segment_name   = segment_name,
            year           = year,
            revenue        = revenue,
            net_income     = net_income,
            equity         = equity,
            segment_ticker = segment_ticker,
            notes          = notes,
        )
        flash(f'Saved {segment_name} ({parent_ticker} {year}).', 'success')
    except Exception as e:
        flash(f'Error saving segment: {e}', 'error')

    return redirect(url_for('conglomerates.index',
                             ticker=request.form.get('parent_ticker', ''),
                             year=request.form.get('year', '')))


@conglomerates_bp.route('/delete', methods=['POST'])
def remove_segment():
    """Deletes a segment row."""
    parent_ticker = request.form.get('parent_ticker', '').upper()
    segment_name  = request.form.get('segment_name', '')
    year          = int(request.form.get('year', 0))
    deleted = delete_segment(parent_ticker, segment_name, year)
    if deleted:
        flash(f'Deleted {segment_name} ({parent_ticker} {year}).', 'success')
    else:
        flash('Segment not found.', 'error')
    return redirect(url_for('conglomerates.index',
                             ticker=parent_ticker, year=year))


@conglomerates_bp.route('/api/preview/<ticker>')
def api_preview(ticker: str):
    """JSON: live scoring preview for the latest year of a ticker."""
    ticker  = ticker.upper()
    year    = request.args.get('year', type=int)
    segs    = get_segments(ticker, year=year) if year else get_latest_segments(ticker)
    if not segs:
        return jsonify({'ok': False, 'error': 'No segment data yet.'})
    scored  = score_all_segments(segs)
    w_score = weighted_segment_score(scored)
    return jsonify({
        'ok':       True,
        'ticker':   ticker,
        'year':     segs[0]['year'] if segs else None,
        'w_score':  w_score,
        'discount': compute_conglomerate_discount(scored, w_score),
        'segments': [
            {
                'name':          s['segment_name'],
                'ticker':        s.get('segment_ticker'),
                'revenue_share': round(s['revenue_share'] * 100, 1) if s.get('revenue_share') else None,
                'health_score':  s.get('health_score'),
            }
            for s in scored
        ],
    })


def _parse_float(val) -> float | None:
    """Parses a form string to float, returns None if blank/invalid."""
    if val is None:
        return None
    val = str(val).strip().replace(',', '')
    try:
        return float(val) if val else None
    except ValueError:
        return None
