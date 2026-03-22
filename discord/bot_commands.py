# ============================================================
# bot_commands.py — Discord Bot Analysis Logic
# PSE Quant SaaS — Discord Bot
# ============================================================
# Builds Discord embed dicts for each slash command.
# Reads from SQLite (read-only) — safe to call from async context
# since all DB calls are synchronous and fast.
# ============================================================

import sys
import os
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in ['db', 'engine', 'scraper']:
    sys.path.insert(0, str(ROOT / p))
sys.path.insert(0, str(ROOT))

# ── Colour constants ──────────────────────────────────────────
COLOUR_GREEN  = 0x27AE60
COLOUR_BLUE   = 0x2980B9
COLOUR_ORANGE = 0xE67E22
COLOUR_RED    = 0xE74C3C
COLOUR_GREY   = 0x95A5A6
COLOUR_GOLD   = 0xF39C12


def _grade(score: float) -> str:
    """Converts a 0-100 score to a letter grade."""
    if score >= 80:
        return 'A'
    if score >= 65:
        return 'B'
    if score >= 50:
        return 'C'
    if score >= 35:
        return 'D'
    return 'F'


def _grade_colour(score: float) -> int:
    g = _grade(score)
    return {
        'A': COLOUR_GREEN,
        'B': COLOUR_BLUE,
        'C': COLOUR_ORANGE,
        'D': COLOUR_RED,
        'F': COLOUR_RED,
    }.get(g, COLOUR_GREY)


def _mos_label(mos_pct) -> str:
    if mos_pct is None:
        return 'N/A'
    if mos_pct >= 30:
        return f'+{mos_pct:.1f}% — STRONG BUY ZONE'
    if mos_pct >= 15:
        return f'+{mos_pct:.1f}% — BUY ZONE'
    if mos_pct >= -5:
        return f'{mos_pct:+.1f}% — FAIRLY VALUED'
    return f'{mos_pct:+.1f}% — ABOVE IV'


def get_stock_embed(ticker: str, discord_id: str = None) -> dict:
    """
    Returns a Discord embed dict for a stock analysis.
    Free tier: grade + name + sector only.
    Paid tier: full analysis (score, IV, MoS, 4-layer breakdown, metrics).
    Returns {'error': str} on failure.
    """
    try:
        import database as db
        from scraper.pse_stock_builder import build_stock_dict_from_db
        from engine.filters_v2 import filter_unified
        from engine.scorer_v2 import score_unified
        from engine.mos import (calc_ddm, calc_eps_pe, calc_dcf,
                                 calc_hybrid_intrinsic, calc_mos_pct)
        from dashboard.access_control import check_access
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    is_paid = check_access(discord_id, 'stock_lookup') if discord_id else False
    t = ticker.upper().strip()

    # Resolve ticker
    conn = db.get_connection()
    row = conn.execute(
        "SELECT ticker, name, sector FROM stocks WHERE ticker = ? AND status = 'active'",
        (t,)
    ).fetchone()
    conn.close()
    if not row:
        return {'error': f"Ticker **{t}** not found. Use `/top10` to see ranked stocks."}

    name   = row['name']
    sector = row['sector'] or 'Unknown'

    # ── Free tier: grade only ──────────────────────────────────
    if not is_paid:
        # Run score so we can show the grade, but reveal nothing else
        stock = build_stock_dict_from_db(t)
        if stock:
            fin_history = db.get_financials(t, years=10)
            final_score, _ = score_unified(stock, financials_history=fin_history)
            grade = _grade(round(final_score, 1))
        else:
            grade = '?'
        return {
            'title':       f'{t} — {name}',
            'description': f'**{name}** · {sector}',
            'color':       COLOUR_GREY,
            'fields': [
                {
                    'name':   'Grade',
                    'value':  f'**{grade}** — Subscribe to see the full score, intrinsic value, MoS, and 4-layer breakdown.',
                    'inline': False,
                },
            ],
            'footer': {
                'text': 'StockPilot PH · Use /subscribe to unlock full analysis (₱99/mo).',
            },
        }

    stock = build_stock_dict_from_db(t)
    if not stock:
        return {'error': f"**{t}** exists but has no price or financial data yet."}

    # Filter
    eligible, filter_reason = filter_unified(stock)

    # Score
    fin_history = db.get_financials(t, years=10)
    final_score, breakdown = score_unified(stock, financials_history=fin_history)
    score = round(final_score, 1)
    grade = _grade(score)

    # MoS
    eps_3y = [f['eps'] for f in fin_history if f.get('eps') is not None][:3]
    ddm_iv, _  = calc_ddm(stock.get('dps_last'), stock.get('dividend_cagr_5y'))
    eps_iv, _  = calc_eps_pe(eps_3y)
    dcf_iv, _  = calc_dcf(stock.get('fcf_per_share'), stock.get('revenue_cagr'))
    iv, _      = calc_hybrid_intrinsic(ddm_iv, eps_iv, dcf_iv, weights=(0.30, 0.35, 0.35))
    if stock.get('sector') == 'Holding Firms' and iv:
        iv = round(iv * 0.80, 2)
    price   = stock.get('current_price')
    mos_pct = calc_mos_pct(iv, price) if iv and price else None

    # Build embed fields
    fields = []

    # Score + grade
    fields.append({
        'name':   'Score / Grade',
        'value':  f'**{score}** / 100 — Grade **{grade}**',
        'inline': True,
    })

    # Current price + IV
    price_str = f'₱{price:.2f}' if price else 'N/A'
    iv_str    = f'₱{iv:.2f}'   if iv    else 'N/A'
    fields.append({
        'name':   'Price → IV',
        'value':  f'{price_str} → {iv_str}',
        'inline': True,
    })

    # MoS
    fields.append({
        'name':   'Margin of Safety',
        'value':  _mos_label(mos_pct if mos_pct is not None else None),
        'inline': False,
    })

    # Filter status
    filter_icon = '✅' if eligible else '⚠️'
    filter_text = 'Passes all quality filters' if eligible else filter_reason
    fields.append({
        'name':   f'{filter_icon} Filter',
        'value':  filter_text,
        'inline': False,
    })

    # 4-layer breakdown (condensed — one line each)
    layer_lines = []
    layers = breakdown.get('layers', {})
    for layer_key, layer_data in layers.items():
        if not isinstance(layer_data, dict):
            continue
        layer_score  = round(layer_data.get('score') or 0, 1)
        layer_weight = int((layer_data.get('weight') or 0) * 100)
        label = layer_key.replace('_', ' ').title()
        layer_lines.append(f'**{label}** ({layer_weight}%): {layer_score}/100')

    if layer_lines:
        fields.append({
            'name':   '4-Layer Breakdown',
            'value':  '\n'.join(layer_lines),
            'inline': False,
        })

    # Key metrics
    roe   = stock.get('roe')
    de    = stock.get('de_ratio')
    yield_ = stock.get('dividend_yield')
    metrics_parts = []
    if roe   is not None: metrics_parts.append(f'ROE: {roe:.1f}%')
    if de    is not None: metrics_parts.append(f'D/E: {de:.2f}x')
    if yield_ is not None and yield_ > 0: metrics_parts.append(f'Yield: {yield_:.2f}%')
    if metrics_parts:
        fields.append({
            'name':   'Key Metrics',
            'value':  ' · '.join(metrics_parts),
            'inline': False,
        })

    # Description: top explanation from highest-weight layer
    description = (
        f"**{name}** · {sector}\n"
        f"*Score is a mathematical ranking — not a buy/sell recommendation.*"
    )

    return {
        'title':       f'{t} — {name}',
        'description': description,
        'color':       _grade_colour(score),
        'fields':      fields,
        'footer':      {
            'text': 'StockPilot PH · Data: PSE Edge · '
                    'Intrinsic value is a mathematical estimate, not a price target.'
        },
    }


def get_top10_embed(discord_id: str = None) -> dict:
    """
    Returns a Discord embed dict showing the current top-10 unified rankings.
    Free tier (no active subscription): top-3 only with grades, no scores.
    Paid tier: full top-10 with scores.
    """
    try:
        import database as db
        from dashboard.access_control import check_access
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    is_paid = check_access(discord_id, 'top10') if discord_id else False
    limit   = 10 if is_paid else 3

    scores = db.get_last_scores_v2(portfolio_type='dividend') or []
    if not scores:
        scores = db.get_last_scores_v2(portfolio_type='value') or []

    if not scores:
        return {'error': 'No rankings available yet. Run the scoring pipeline first.'}

    # Deduplicate by ticker — keep highest score per ticker (handles multiple run_dates)
    seen = {}
    for s in scores:
        t = s['ticker']
        if t not in seen or (s.get('score') or 0) > (seen[t].get('score') or 0):
            seen[t] = s
    ranked = sorted(seen.values(), key=lambda x: x.get('score', 0) or 0, reverse=True)[:limit]

    conn = db.get_connection()
    rows = conn.execute("SELECT ticker, name FROM stocks").fetchall()
    conn.close()
    name_map = {r['ticker']: r['name'] for r in rows}

    lines  = []
    medals = [':first_place:', ':second_place:', ':third_place:']
    for i, s in enumerate(ranked):
        t     = s['ticker']
        score = round(s.get('score', 0), 1)
        grade = _grade(score)
        n     = name_map.get(t, t)
        prefix = medals[i] if i < 3 else f'{i + 1}.'
        if is_paid:
            lines.append(f'{prefix} **{t}** — {score} ({grade}) · {n}')
        else:
            lines.append(f'{prefix} **{t}** — Grade {grade} · {n}')

    last_run = 'Unknown'
    try:
        conn = db.get_connection()
        row  = conn.execute("SELECT MAX(run_date) AS rd FROM scores_v2").fetchone()
        conn.close()
        if row and row['rd']:
            last_run = row['rd']
    except Exception:
        pass

    fields = [
        {'name': 'Last Updated', 'value': last_run, 'inline': True},
        {
            'name':   'Scoring Model',
            'value':  'Unified 4-Layer (Health · Improvement · Acceleration · Persistence)',
            'inline': False,
        },
    ]

    if not is_paid:
        fields.append({
            'name':   'Unlock Full Rankings',
            'value':  'Subscribe at StockPilot PH (₱99/mo) to see all top-10 scores.',
            'inline': False,
        })

    return {
        'title':       f'StockPilot PH — Top {"10" if is_paid else "3"} Rankings',
        'description': '\n'.join(lines),
        'color':       COLOUR_GOLD,
        'fields':      fields,
        'footer':      {'text': 'StockPilot PH · Rankings are not investment advice.'},
    }


def get_help_embed() -> dict:
    """Returns a static glossary / help embed."""
    fields = [
        {
            'name':  '📊 /stock <ticker>',
            'value': 'Full analysis for one stock. Example: `/stock DMC`\n'
                     'Shows score, grade, margin of safety, and 4-layer breakdown.\n'
                     '*Premium members only — DM only.*',
            'inline': False,
        },
        {
            'name':  '🏆 /top10',
            'value': 'Current top 10 stocks from the latest scoring run.\n'
                     '*Premium members only — DM only.*',
            'inline': False,
        },
        {
            'name':  '📌 /watchlist show',
            'value': 'View your personal watchlist with current scores.\n*Premium — DM only.*',
            'inline': False,
        },
        {
            'name':  '➕ /watchlist add <ticker>',
            'value': 'Add a stock to your watchlist (max 20). Example: `/watchlist add DMC`\n*Premium — DM only.*',
            'inline': False,
        },
        {
            'name':  '➖ /watchlist remove <ticker>',
            'value': 'Remove a stock from your watchlist.\n*Premium — DM only.*',
            'inline': False,
        },
        {
            'name':  '💳 /subscribe',
            'value': 'See pricing and get your payment link. DM only.',
            'inline': False,
        },
        {
            'name':  '👤 /mystatus',
            'value': 'Check your subscription tier and expiry date. DM only.',
            'inline': False,
        },
        {
            'name':  '📖 Key Terms',
            'value': (
                '**Score (0–100)** — Higher = stronger fundamentals.\n'
                '**Grade** — A (≥80) · B (≥65) · C (≥50) · D (≥35) · F (<35)\n'
                '**IV (Intrinsic Value)** — Mathematical estimate of fair value. Not a price target.\n'
                '**MoS (Margin of Safety)** — Discount between IV and current price. '
                'Larger = more cushion against errors.\n'
                '**ROE** — How efficiently management uses shareholders\' money.\n'
                '**D/E** — How much the company relies on borrowed money.\n'
                '**FCF** — Cash left after running the business and investing in it.'
            ),
            'inline': False,
        },
        {
            'name':  '⚠️ Disclaimer',
            'value': (
                'StockPilot PH scores stocks based on publicly available financial data. '
                'Scores are for educational purposes only and do not constitute investment advice. '
                'Always do your own research before investing.'
            ),
            'inline': False,
        },
    ]

    return {
        'title':       'StockPilot PH — Help & Glossary',
        'description': 'A deterministic fundamental ranking system for Philippine stocks.',
        'color':       COLOUR_BLUE,
        'fields':      fields,
        'footer':      {'text': 'StockPilot PH · Built for Filipino retail investors.'},
    }
