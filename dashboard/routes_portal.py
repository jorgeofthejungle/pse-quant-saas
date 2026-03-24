# ============================================================
# routes_portal.py — Public Educational Portal
# PSE Quant SaaS — Dashboard
# ============================================================
# Public-facing pages — no admin login required.
# Free tier: How It Works + sample JFC analysis + glossary.
# URL prefix: /portal  (registered in app.py)
# ============================================================

import sys
import os
import random
from pathlib import Path
from flask import Blueprint, render_template

ROOT = Path(__file__).resolve().parent.parent
for p in ['db', 'engine', 'scraper']:
    sys.path.insert(0, str(ROOT / p))
sys.path.insert(0, str(ROOT))

portal_bp = Blueprint('portal', __name__)

FALLBACK_TICKER = 'JFC'


def _pick_sample_ticker() -> str:
    """Pick a random stock from the latest top-10 rankings. Falls back to JFC."""
    try:
        import database as db
        scores = db.get_last_scores_v2() or []
        if scores:
            top10 = sorted(scores, key=lambda x: x.get('score', 0) or 0, reverse=True)[:10]
            return random.choice(top10)['ticker']
    except Exception:
        pass
    return FALLBACK_TICKER


def _get_sample_analysis() -> dict:
    """
    Runs the full analysis for the sample stock.
    Returns the same dict shape as routes_stocks._get_stock_analysis().
    Silently returns an error dict if data is unavailable.
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

    ticker = _pick_sample_ticker()
    stock  = build_stock_dict_from_db(ticker)
    if not stock:
        return {'error': f'{ticker} data not available. Run the scraper first.'}

    eligible, filter_reason = filter_unified(stock)
    fin_history = db.get_financials(ticker, years=10)
    final_score, breakdown = score_unified(stock, financials_history=fin_history)

    eps_3y = [f['eps'] for f in fin_history if f.get('eps') is not None][:3]
    ddm_iv, _ = calc_ddm(stock.get('dps_last'), stock.get('dividend_cagr_5y'))
    eps_iv, _ = calc_eps_pe(eps_3y)
    dcf_iv, _ = calc_dcf(stock.get('fcf_per_share'), stock.get('revenue_cagr'))
    iv, _     = calc_hybrid_intrinsic(ddm_iv, eps_iv, dcf_iv, weights=(0.30, 0.35, 0.35))
    if stock.get('sector') == 'Holding Firms' and iv:
        iv = round(iv * 0.80, 2)

    price     = stock.get('current_price')
    mos_pct   = calc_mos_pct(iv, price)       if iv and price else None
    mos_price = calc_mos_price(iv, 'unified') if iv           else None

    if mos_pct is None:
        mos_signal, mos_color = 'N/A', 'muted'
    elif mos_pct >= 30:
        mos_signal, mos_color = 'DEEP DISCOUNT', 'green'
    elif mos_pct >= 15:
        mos_signal, mos_color = 'DISCOUNTED', 'blue'
    elif mos_pct >= -5:
        mos_signal, mos_color = 'FAIRLY VALUED', 'orange'
    else:
        mos_signal, mos_color = 'ABOVE ESTIMATE', 'red'

    score = round(final_score, 1)
    if score >= 80:
        grade = 'A'
    elif score >= 65:
        grade = 'B'
    elif score >= 50:
        grade = 'C'
    elif score >= 35:
        grade = 'D'
    else:
        grade = 'F'

    layers = breakdown.get('layers', {})

    return {
        'error':        None,
        'stock':        stock,
        'score':        score,
        'grade':        grade,
        'breakdown':    breakdown,
        'layers':       layers,
        'eligible':     eligible,
        'filter_reason': filter_reason,
        'iv':           round(iv, 2)        if iv        else None,
        'mos_pct':      round(mos_pct, 1)   if mos_pct is not None else None,
        'mos_price':    round(mos_price, 2) if mos_price else None,
        'mos_signal':   mos_signal,
        'mos_color':    mos_color,
    }


PRICING = {
    'monthly':      99,
    'annual':       999,
    'annual_mo':    83,    # per-month equivalent when billed annually
    'annual_save':  189,   # savings vs 12 months of monthly (12×99 − 999)
}

DISCORD_INVITE_URL = os.getenv('DISCORD_INVITE_URL', '#')

@portal_bp.route('/')
def index():
    analysis = _get_sample_analysis()
    ticker   = analysis.get('stock', {}).get('ticker', FALLBACK_TICKER) if analysis.get('stock') else FALLBACK_TICKER

    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'db'))
        import database as db
        conn = db.get_connection()
        row  = conn.execute("SELECT COUNT(*) AS n FROM stocks WHERE status = 'active'").fetchone()
        conn.close()
        stock_count = row['n'] if row else 223
    except Exception:
        stock_count = 223

    return render_template(
        'portal.html',
        analysis           = analysis,
        ticker             = ticker,
        pricing            = PRICING,
        discord_invite_url = DISCORD_INVITE_URL,
        stock_count        = stock_count,
    )


@portal_bp.route('/glossary')
def glossary():
    return render_template('portal_glossary.html')
