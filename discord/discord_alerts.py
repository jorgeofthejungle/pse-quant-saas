# ============================================================
# discord_alerts.py — Real-Time Alert Messages
# PSE Quant SaaS
# ============================================================
# Dividend, price, earnings, re-score, and opportunistic alerts.
# Each function sends one targeted Discord embed.
# ============================================================

from datetime import datetime
from discord.discord_core import (
    _post_webhook, WEBHOOKS,
    COLOUR_DIVIDEND, COLOUR_ALERT, COLOUR_INFO, COLOUR_SHORTLIST,
    COLOUR_OPPORTUNITY, COLOUR_HALF_POS, COLOUR_CAUTION,
    PORTFOLIO_COLOURS, PORTFOLIO_EMOJI, DISCLAIMER, SIGNAL_DISCLAIMER,
)


def send_dividend_alert(
    webhook_url:     str,
    ticker:          str,
    company:         str,
    dps:             float,
    ex_date:         str,
    record_date:     str,
    pay_date:        str,
    portfolio_score: float = None,
) -> bool:
    """
    Sends a dividend declaration alert.
    Triggered when PSE Edge publishes a new dividend announcement.
    """
    score_line = (
        f"\n**Current dividend score:** {portfolio_score}/100"
        if portfolio_score is not None else ''
    )

    embed = {
        'title':       f"Dividend Declaration -- {ticker}",
        'description': f"**{company}** has declared a cash dividend.\n{score_line}",
        'color':       COLOUR_DIVIDEND,
        'fields': [
            {'name': 'Dividend Per Share', 'value': f"PHP{dps:.4f}",  'inline': True},
            {'name': 'Ex-Date',            'value': ex_date,          'inline': True},
            {'name': 'Record Date',        'value': record_date,      'inline': True},
            {'name': 'Payment Date',       'value': pay_date,         'inline': True},
        ],
        'footer': {'text': DISCLAIMER},
    }
    return _post_webhook(webhook_url, {'embeds': [embed]})


def send_price_alert(
    webhook_url:     str,
    ticker:          str,
    company:         str,
    current_price:   float,
    mos_price:       float,
    intrinsic_value: float,
    portfolio_type:  str,
    score:           float,
) -> bool:
    """
    Sends an alert when a stock's price drops at or below its MoS buy price.
    This is a factual price observation -- not a recommendation.
    """
    gap_pct = ((mos_price - current_price) / mos_price) * 100

    embed = {
        'title': f"Price Alert -- {ticker}  ({portfolio_type.upper()})",
        'description': (
            f"**{company}** is now trading AT OR BELOW the calculated "
            f"Margin of Safety buy price.\n\n"
            f"This is a mathematical observation, not a recommendation."
        ),
        'color': COLOUR_ALERT,
        'fields': [
            {'name': 'Current Price',    'value': f"PHP{current_price:.2f}",              'inline': True},
            {'name': 'MoS Buy Price',    'value': f"PHP{mos_price:.2f}",                  'inline': True},
            {'name': 'Intrinsic Value',  'value': f"PHP{intrinsic_value:.2f}",            'inline': True},
            {'name': 'Price vs MoS',     'value': f"{gap_pct:.1f}% below MoS threshold", 'inline': True},
            {'name': f'{portfolio_type.upper()} Score', 'value': f"{score}/100",          'inline': True},
        ],
        'footer': {'text': DISCLAIMER},
    }
    return _post_webhook(webhook_url, {'embeds': [embed]})


def send_earnings_alert(
    webhook_url:      str,
    ticker:           str,
    company:          str,
    period:           str,
    net_income:       float,
    net_income_prior: float,
    eps:              float,
    disclosure_url:   str = None,
) -> bool:
    """
    Sends an alert when new earnings data is filed on PSE Edge.

    Parameters:
        period           -- e.g. "Q3 2024" or "FY 2024"
        net_income       -- Net income in millions (PHP M)
        net_income_prior -- Prior period net income for YoY comparison
        eps              -- Earnings per share
        disclosure_url   -- Link to the PSE Edge filing (optional)
    """
    yoy_change = ((net_income - net_income_prior) / abs(net_income_prior)) * 100 \
        if net_income_prior and net_income_prior != 0 else None

    yoy_str   = f"{yoy_change:+.1f}% YoY" if yoy_change is not None else "YoY N/A"
    direction = "up" if (yoy_change or 0) >= 0 else "down"

    fields = [
        {'name': 'Period',     'value': period,                                      'inline': True},
        {'name': 'Net Income', 'value': f"PHP{net_income:,.1f}M  ({direction}) {yoy_str}", 'inline': True},
        {'name': 'EPS',        'value': f"PHP{eps:.2f}",                             'inline': True},
    ]

    if disclosure_url:
        fields.append({
            'name':   'Filing',
            'value':  f"[View on PSE Edge]({disclosure_url})",
            'inline': False,
        })

    embed = {
        'title':       f"Earnings Filed -- {ticker}",
        'description': (
            f"**{company}** has filed new earnings results on PSE Edge.\n"
            f"Scores will be updated on the next scheduled run."
        ),
        'color':   COLOUR_INFO,
        'fields':  fields,
        'footer':  {'text': DISCLAIMER},
    }
    return _post_webhook(webhook_url, {'embeds': [embed]})


def send_rescore_notice(
    webhook_url:    str,
    portfolio_type: str,
    changes:        list,
) -> bool:
    """
    Sends a notice when new data triggers a re-score and rank changes.

    Parameters:
        changes -- list of dicts: [
            {'ticker': 'BDO', 'old_rank': 4, 'new_rank': 2,
             'old_score': 68.5, 'new_score': 74.2},
            ...
        ]
    """
    emoji  = PORTFOLIO_EMOJI.get(portfolio_type, '📋')
    colour = PORTFOLIO_COLOURS.get(portfolio_type, COLOUR_INFO)

    fields = []
    for c in changes[:10]:
        old_r = c.get('old_rank', '?')
        new_r = c.get('new_rank', '?')
        arrow = 'up' if (isinstance(new_r, int) and isinstance(old_r, int) and new_r < old_r) else 'down'
        fields.append({
            'name':  f"{arrow}  {c['ticker']}",
            'value': (
                f"Rank: #{old_r} -> #{new_r}\n"
                f"Score: {c.get('old_score', '?'):.1f} -> {c.get('new_score', '?'):.1f}"
            ),
            'inline': True,
        })

    embed = {
        'title':       f"{emoji}  Re-Score Complete -- {portfolio_type.upper()}",
        'description': (
            f"New financial data triggered a re-score. "
            f"**{len(changes)} stock(s)** changed rank."
        ),
        'color':   colour,
        'fields':  fields,
        'footer':  {'text': DISCLAIMER},
    }
    return _post_webhook(webhook_url, {'embeds': [embed]})


def send_sentiment_signal(
    webhook_url:      str,
    ticker:           str,
    company:          str,
    signal:           str,
    reasoning:        str,
    sentiment_summary: str,
    key_events:       list,
    mos_pct:          float | None,
    overall_score:    float,
    portfolio_type:   str,
) -> bool:
    """
    Sends an educational sentiment signal alert to #pse-alerts.

    Parameters:
        signal     — 'potential_opportunity' | 'half_position' | 'caution'
        reasoning  — one-line deterministic explanation
        mos_pct    — Margin of Safety % (None if unavailable)
        overall_score — 0-100 portfolio score
        portfolio_type — 'pure_dividend' | 'dividend_growth' | 'value'
    """
    url = webhook_url or WEBHOOKS.get('alerts', '')
    if not url:
        print(f"[discord_alerts] DISCORD_WEBHOOK_ALERTS not set -- skipping signal for {ticker}")
        return False

    _SIGNAL_META = {
        'potential_opportunity': {
            'label':  'Potential Opportunity',
            'colour': COLOUR_OPPORTUNITY,
            'prefix': 'Quantitative criteria suggest a potential opportunity.',
        },
        'half_position': {
            'label':  'Half Position Signal',
            'colour': COLOUR_HALF_POS,
            'prefix': 'Positive sentiment with limited margin of safety — signals caution.',
        },
        'caution': {
            'label':  'Caution Signal',
            'colour': COLOUR_CAUTION,
            'prefix': 'Negative news sentiment detected for this stock.',
        },
    }
    meta = _SIGNAL_META.get(signal, {
        'label': signal.title(), 'colour': COLOUR_INFO, 'prefix': '',
    })

    mos_str = f'{mos_pct:.1f}%' if mos_pct is not None else 'N/A'
    portfolio_label = portfolio_type.replace('_', ' ').title()

    events_text = '\n'.join(f'- {e}' for e in (key_events or [])[:3]) or 'No specific events.'

    fields = [
        {'name': 'Signal',          'value': f"**{meta['label']}**",     'inline': True},
        {'name': 'Portfolio Score', 'value': f'{overall_score:.1f}/100', 'inline': True},
        {'name': 'Margin of Safety','value': mos_str,                    'inline': True},
        {'name': 'Reasoning',       'value': reasoning,                  'inline': False},
        {'name': 'News Summary',    'value': sentiment_summary or 'N/A', 'inline': False},
        {'name': 'Key Events',      'value': events_text,                'inline': False},
    ]

    embed = {
        'title':       f"{meta['label']}: {ticker}  ({portfolio_label})",
        'description': (
            f"**{company}** ({ticker})\n\n"
            f"{meta['prefix']}\n\n"
            f"*{SIGNAL_DISCLAIMER}*"
        ),
        'color':   meta['colour'],
        'fields':  fields,
        'footer':  {'text': SIGNAL_DISCLAIMER},
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    return _post_webhook(url, {'embeds': [embed]})


def send_opportunistic_alert(
    ticker:       str,
    company_name: str,
    summary:      str,
    webhook_url:  str = None,
) -> bool:
    """
    Sends an opportunistic watch alert to the #pse-alerts channel.
    Called when sentiment_engine flags a stock with opportunistic_flag=1.
    """
    url = webhook_url or WEBHOOKS.get('alerts', '')
    if not url:
        print("[discord_alerts] DISCORD_WEBHOOK_ALERTS not set -- skipping alert")
        return False

    payload = {
        'embeds': [{
            'title':       f"Opportunistic Watch: {ticker}",
            'description': (
                f"**{company_name}** ({ticker}) has been flagged based on recent news.\n\n"
                f"{summary}\n\n"
                f"*{DISCLAIMER}*"
            ),
            'color': 0x27AE60,
            'footer': {
                'text': (
                    'PSE Quant SaaS -- Sentiment is informational only. '
                    'Not a buy/sell recommendation.'
                )
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }]
    }
    success = _post_webhook(url, payload)
    if success:
        print(f"[discord_alerts] Opportunistic alert sent for {ticker}")
    return success


def send_expiry_notification(
    webhook_url:  str,
    member_name:  str,
    expiry_date:  str,
    days_left:    int,
    renewal_url:  str = None,
) -> bool:
    """
    Sends a subscription expiry reminder to the alerts channel.
    Called 7 days, 1 day, and 0 days before expiry.

    Parameters:
        member_name  -- Discord display name
        expiry_date  -- ISO date string 'YYYY-MM-DD'
        days_left    -- 7, 1, or 0
        renewal_url  -- PayMongo payment link (optional)
    """
    url = webhook_url or WEBHOOKS.get('alerts', '')
    if not url:
        return False

    if days_left == 0:
        urgency  = 'EXPIRED TODAY'
        colour   = COLOUR_ALERT
        msg_line = 'Your StockPilot PH subscription has expired.'
    elif days_left == 1:
        urgency  = 'EXPIRES TOMORROW'
        colour   = COLOUR_ALERT
        msg_line = 'Your StockPilot PH subscription expires tomorrow.'
    else:
        urgency  = f'EXPIRES IN {days_left} DAYS'
        colour   = COLOUR_INFO
        msg_line = f'Your StockPilot PH subscription expires in {days_left} days.'

    fields = [
        {'name': 'Member',      'value': member_name, 'inline': True},
        {'name': 'Expiry Date', 'value': expiry_date, 'inline': True},
    ]
    if renewal_url:
        fields.append({
            'name':   'Renew Now',
            'value':  f'[Click here to renew]({renewal_url})',
            'inline': False,
        })
    else:
        fields.append({
            'name':   'To Renew',
            'value':  'Contact @admin in this server for a renewal link.',
            'inline': False,
        })

    embed = {
        'title':       f'Subscription {urgency}',
        'description': f'{msg_line}\nRenew to keep access to full rankings, PDF reports, and alerts.',
        'color':       colour,
        'fields':      fields,
        'footer':      {'text': 'StockPilot PH · Thank you for your support.'},
        'timestamp':   datetime.utcnow().isoformat() + 'Z',
    }
    return _post_webhook(url, {'embeds': [embed]})


def send_stock_of_week(
    webhook_url: str,
    ticker:      str,
    name:        str,
    sector:      str,
    score:       float,
    grade:       str,
    price:       float | None,
    iv:          float | None,
    mos_pct:     float | None,
    layers:      dict,
    roe:         float | None,
    de_ratio:    float | None,
    div_yield:   float | None,
    score_delta: float | None,
    week_str:    str,
) -> bool:
    """
    Posts the Stock of the Week deep-analysis embed to #deep-analysis (premium).
    Runs every Monday morning after the Sunday weekly scrape + rescore.

    Parameters:
        layers      -- breakdown['layers'] dict from score_unified()
        score_delta -- score change vs last week (None on first run)
        week_str    -- display string e.g. 'Week of Mar 17, 2026'
    """
    url = webhook_url or WEBHOOKS.get('deep_analysis', '')
    if not url:
        print("[discord_alerts] DISCORD_WEBHOOK_DEEP_ANALYSIS not set — skipping SOTW")
        return False

    # ── Pick reason headline ──────────────────────────────────
    if score_delta is not None and score_delta >= 1.0:
        headline = (
            f"**{ticker}** recorded the biggest fundamental improvement this week, "
            f"with its score rising **+{score_delta:.1f} pts**."
        )
    else:
        headline = (
            f"**{ticker}** ranks #1 in this week's unified fundamental scoring "
            f"across all 223 PSE stocks."
        )

    # ── MoS label ─────────────────────────────────────────────
    if mos_pct is None:
        mos_str = 'N/A'
    elif mos_pct >= 30:
        mos_str = f'+{mos_pct:.1f}% — DEEP DISCOUNT'
    elif mos_pct >= 15:
        mos_str = f'+{mos_pct:.1f}% — DISCOUNTED'
    elif mos_pct >= -5:
        mos_str = f'{mos_pct:+.1f}% — FAIRLY VALUED'
    else:
        mos_str = f'{mos_pct:+.1f}% — ABOVE ESTIMATE'

    # ── Colour by grade ───────────────────────────────────────
    grade_colour = {
        'A': 0x27AE60, 'B': 0x2980B9,
        'C': 0xE67E22, 'D': 0xE74C3C, 'F': 0xE74C3C,
    }.get(grade, 0x95A5A6)

    # ── Build fields ──────────────────────────────────────────
    price_str = f'₱{price:.2f}' if price else 'N/A'
    iv_str    = f'₱{iv:.2f}'   if iv    else 'N/A'

    fields = [
        {'name': 'Score / Grade',      'value': f'**{score:.1f}** / 100 — Grade **{grade}**', 'inline': True},
        {'name': 'Price → IV',         'value': f'{price_str} → {iv_str}',                    'inline': True},
        {'name': 'Margin of Safety',   'value': mos_str,                                       'inline': False},
    ]

    if score_delta is not None:
        delta_sign = '+' if score_delta >= 0 else ''
        fields.append({
            'name':   'Score Change This Week',
            'value':  f'{delta_sign}{score_delta:.1f} pts',
            'inline': True,
        })

    # 3-layer breakdown
    layer_lines = []
    for layer_key, layer_data in (layers or {}).items():
        if not isinstance(layer_data, dict):
            continue
        ls = round(layer_data.get('score') or 0, 1)
        lw = int((layer_data.get('weight') or 0) * 100)
        label = layer_key.replace('_', ' ').title()
        expl  = layer_data.get('explanation', '')
        layer_lines.append(f'**{label}** ({lw}%): {ls}/100' + (f'\n_{expl}_' if expl else ''))
    if layer_lines:
        fields.append({
            'name':   '3-Layer Breakdown',
            'value':  '\n'.join(layer_lines),
            'inline': False,
        })

    # Key metrics
    metrics = []
    if roe       is not None: metrics.append(f'ROE: {roe:.1f}%')
    if de_ratio  is not None: metrics.append(f'D/E: {de_ratio:.2f}x')
    if div_yield is not None and div_yield > 0: metrics.append(f'Yield: {div_yield:.2f}%')
    if metrics:
        fields.append({'name': 'Key Metrics', 'value': ' · '.join(metrics), 'inline': False})

    fields.append({
        'name':   '⚠️ Educational Reminder',
        'value':  (
            'This is a mathematical ranking based on fundamental data from PSE Edge. '
            'It is not a buy recommendation. Always do your own research.'
        ),
        'inline': False,
    })

    embed = {
        'title':       f'⭐ Stock of the Week — {ticker}  |  {week_str}',
        'description': (
            f'**{name}** · {sector}\n\n'
            f'{headline}'
        ),
        'color':       grade_colour,
        'fields':      fields,
        'footer':      {
            'text': (
                'StockPilot PH · Scores are educational rankings, not investment advice. '
                'Data sourced from PSE Edge.'
            )
        },
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    return _post_webhook(url, {'embeds': [embed]})


def send_weekly_briefing(
    webhook_url:   str,
    ranked_stocks: list,
    date_str:      str = None,
    invite_url:    str = None,
) -> bool:
    """
    Posts the weekly top-3 grade summary to the public #daily-briefing channel.
    Runs Sunday night after the full financial scrape and rescore.
    Free users see grades only — no scores, IV, or MoS.
    Includes a CTA teaser for premium membership.

    Parameters:
        ranked_stocks -- full ranked list (only top 3 are used)
        date_str      -- display week string, e.g. 'Week of Mar 15, 2026' (auto-generated if None)
        invite_url    -- Discord server invite URL for the CTA
    """
    url = webhook_url or WEBHOOKS.get('daily_briefing', '')
    if not url:
        print("[discord_alerts] DISCORD_WEBHOOK_DAILY_BRIEFING not set -- skipping briefing")
        return False

    if not ranked_stocks:
        print("[discord_alerts] No ranked stocks for weekly briefing -- skipping")
        return False

    if date_str is None:
        date_str = 'Week of ' + datetime.now().strftime('%b %d, %Y')

    def _grade(score: float) -> str:
        if score >= 80: return 'A'
        if score >= 65: return 'B'
        if score >= 50: return 'C'
        if score >= 35: return 'D'
        return 'F'

    medals = ['🥇', '🥈', '🥉']
    top3   = ranked_stocks[:3]

    lines = []
    for i, stock in enumerate(top3):
        ticker = stock.get('ticker', '?')
        name   = stock.get('name', ticker)
        sector = stock.get('sector', '')
        score  = stock.get('score') or 0
        grade  = _grade(score)
        medal  = medals[i] if i < len(medals) else f'#{i+1}'
        sector_str = f'  ·  {sector}' if sector else ''
        lines.append(f"{medal}  **{ticker}** — Grade **{grade}**{sector_str}")

    briefing_text = '\n'.join(lines)

    teaser = (
        '\n\n🔒 **Full rankings** with scores, intrinsic value, and margin of safety '
        'are available to **StockPilot Premium** members.\n'
        '₱99/mo · Cancel anytime.'
    )

    fields = [
        {
            'name':   '📋 This Week\'s Top 3',
            'value':  briefing_text,
            'inline': False,
        },
        {
            'name':   '📈 What Premium Members See',
            'value':  (
                '• Full top 10+ with exact scores (e.g. 83.7/100)\n'
                '• Intrinsic value and margin of safety %\n'
                '• 3-layer breakdown: Health · Improvement · Persistence\n'
                '• `/stock <ticker>` via DM for any PSE stock'
            ),
            'inline': False,
        },
    ]

    embed = {
        'title':       f'📊 StockPilot PH — Weekly Briefing  |  {date_str}',
        'description': (
            'Rankings updated daily at 4 PM PHT using our 3-layer fundamental model '
            'across 223 PSE stocks.'
            + teaser
        ),
        'color':   0x1B4B6B,
        'fields':  fields,
        'footer':  {'text': 'StockPilot PH · Scores are for educational purposes only. Not investment advice.'},
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    return _post_webhook(url, {'embeds': [embed]})


# ── Portfolio name lookup (matches scheduler_data.py) ────────
_PORTFOLIO_NAMES = {
    'pure_dividend':   'PURE DIVIDEND',
    'dividend_growth': 'DIVIDEND GROWTH',
    'value':           'VALUE',
}


def send_shortlist_change(
    webhook_url:    str,
    portfolio_type: str,
    changes:        list,
) -> bool:
    """
    Sends an educational alert when stocks enter or leave a portfolio's
    qualifying shortlist (all stocks that pass filters).

    Parameters:
        changes -- list of dicts from _build_shortlist_changes():
            exit:  {'type': 'exit',  'ticker', 'name', 'reason', 'old_score', 'old_rank'}
            entry: {'type': 'entry', 'ticker', 'name', 'score', 'rank',
                     'strongest_factor', 'strongest_score'}
    """
    url = webhook_url or WEBHOOKS.get('alerts', '')
    if not url:
        print("[discord_alerts] DISCORD_WEBHOOK_ALERTS not set -- skipping shortlist alert")
        return False

    emoji = PORTFOLIO_EMOJI.get(portfolio_type, '')
    name  = _PORTFOLIO_NAMES.get(portfolio_type, portfolio_type.upper())

    exits   = [c for c in changes if c['type'] == 'exit']
    entries = [c for c in changes if c['type'] == 'entry']

    desc_parts = []
    if exits:
        desc_parts.append(f"**{len(exits)}** stock(s) no longer qualify")
    if entries:
        desc_parts.append(f"**{len(entries)}** new stock(s) now qualify")
    desc = '. '.join(desc_parts) + '.' if desc_parts else 'Shortlist updated.'

    fields = []

    for c in exits[:12]:
        ticker = c.get('ticker', '?')
        cname  = c.get('name', ticker)
        reason = c.get('reason', 'No longer meets portfolio criteria.')
        old_s  = c.get('old_score')
        old_r  = c.get('old_rank')
        score_line = f"  Previous score: {old_s:.1f}/100 (rank #{old_r})." if old_s is not None else ''
        fields.append({
            'name':   f"REMOVED: {ticker}",
            'value':  f"{cname} -- {reason}{score_line}",
            'inline': False,
        })

    for c in entries[:12]:
        ticker = c.get('ticker', '?')
        cname  = c.get('name', ticker)
        score  = c.get('score', 0)
        rank   = c.get('rank', '?')
        factor = c.get('strongest_factor', '')
        f_score = c.get('strongest_score')
        highlight = ''
        if factor and f_score is not None:
            factor_label = factor.replace('_', ' ').title()
            highlight = f"  Strongest area: {factor_label} at {f_score:.0f}/100."
        fields.append({
            'name':   f"ADDED: {ticker}",
            'value':  f"{cname} joined at rank #{rank} with score {score:.1f}/100.{highlight}",
            'inline': False,
        })

    embed = {
        'title':       f"{emoji}  Shortlist Update -- {name}",
        'description': (
            f"The qualifying stocks for the {name} portfolio have changed.\n\n"
            f"{desc}\n\n"
            f"*Shortlist changes reflect updated financial data and filter criteria. "
            f"A stock leaving the shortlist means it no longer meets the minimum "
            f"requirements -- it is not a sell signal.*"
        ),
        'color':     COLOUR_SHORTLIST,
        'fields':    fields,
        'footer':    {'text': DISCLAIMER},
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    return _post_webhook(url, {'embeds': [embed]})
