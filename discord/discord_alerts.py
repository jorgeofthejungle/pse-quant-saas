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
    COLOUR_DIVIDEND, COLOUR_ALERT, COLOUR_INFO,
    PORTFOLIO_COLOURS, PORTFOLIO_EMOJI, DISCLAIMER,
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
