# ============================================================
# bot_subscribe.py — /subscribe and /mystatus Commands
# PSE Quant SaaS — Discord Bot
# ============================================================
# /subscribe — shows pricing and generates a PayMongo payment link
# /mystatus  — shows current subscription tier and expiry
#
# Both commands are DM-only (not premium-gated — free users
# need to be able to subscribe and check their own status).
# ============================================================

from __future__ import annotations

import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COLOUR_GOLD  = 0xF39C12
COLOUR_GREEN = 0x27AE60
COLOUR_GREY  = 0x95A5A6
COLOUR_BLUE  = 0x2980B9


def get_subscribe_embed(discord_id: str, discord_name: str) -> dict:
    """
    Returns a Discord embed dict for /subscribe.
    If user is already subscribed, returns a status embed instead.
    Otherwise, shows pricing and a PayMongo payment link if configured.
    """
    try:
        from dashboard.access_control import get_member_by_discord_id
        from dashboard.db_members import add_member
        from dashboard.paymongo_core import (
            generate_payment_link, get_paymongo_auth, get_pricing,
        )
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    # Already subscribed?
    member = get_member_by_discord_id(discord_id)
    if member and member.get('status') == 'active':
        expiry = member.get('expiry_date', 'Unknown')
        plan   = member.get('plan', 'monthly').title()
        return {
            'title':       'StockPilot PH — Already Subscribed!',
            'description': (
                f"You already have an active **{plan}** subscription.\n"
                f"Expires: **{expiry}**\n\n"
                "Use `/mystatus` to see your full details."
            ),
            'color':  COLOUR_GREEN,
            'fields': [],
            'footer': {'text': 'StockPilot PH · Thank you for subscribing!'},
        }

    # Get pricing
    m_centavos, _ = get_pricing('monthly')
    a_centavos, _ = get_pricing('annual')
    m_php  = m_centavos / 100
    a_php  = a_centavos / 100
    a_save = round((m_php * 12) - a_php)

    # Auto-register as pending so Josh sees them in dashboard
    member_id = None
    if not member:
        try:
            member_id = add_member(
                discord_name = discord_name,
                discord_id   = discord_id,
                plan         = 'monthly',
                notes        = 'Auto-registered via /subscribe command',
            )
            # add_member sets status='active' by default — mark as pending
            from db.db_connection import get_connection
            conn = get_connection()
            conn.execute(
                "UPDATE members SET status = 'pending' WHERE id = ?",
                (member_id,),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
    else:
        member_id = member.get('id')

    # Generate PayMongo links
    _, pm_configured = get_paymongo_auth()

    fields = [
        {
            'name':   '📅 Monthly — ₱{:.0f}/mo'.format(m_php),
            'value':  'Full access for 30 days.',
            'inline': True,
        },
        {
            'name':   '📆 Annual — ₱{:.0f}/yr'.format(a_php),
            'value':  'Full access for 365 days. Save ₱{:.0f}!'.format(a_save),
            'inline': True,
        },
    ]

    if pm_configured and member_id:
        ok_m, url_m, _ = generate_payment_link(member_id, discord_name, 'monthly')
        ok_a, url_a, _ = generate_payment_link(member_id, discord_name, 'annual')
        if ok_m:
            fields.append({
                'name':   '💳 Pay Monthly',
                'value':  f'[Click here to pay ₱{m_php:.0f}]({url_m})',
                'inline': False,
            })
        if ok_a:
            fields.append({
                'name':   '💳 Pay Annually',
                'value':  f'[Click here to pay ₱{a_php:.0f}]({url_a})',
                'inline': False,
            })
    else:
        fields.append({
            'name':   '💬 How to Subscribe',
            'value':  'Message Josh directly or ask in the server to get your payment link.',
            'inline': False,
        })

    fields.append({
        'name':   '✅ What You Get',
        'value':  (
            '• Full rankings with scores (not just grades)\n'
            '• `/stock <ticker>` — instant analysis of any PSE stock\n'
            '• `/top10` — current top 10 with scores and MoS\n'
            '• Weekly Digest every Friday\n'
            '• Real-time dividend, earnings, and price alerts\n'
            '• Stock of the Week every Monday\n'
            '• Access to all premium Discord channels'
        ),
        'inline': False,
    })

    return {
        'title':       'StockPilot PH — Subscribe',
        'description': (
            'Get full access to data-driven PSE stock analysis for **₱{:.0f}/mo**.\n'
            'Cancel anytime.'.format(m_php)
        ),
        'color':  COLOUR_GOLD,
        'fields': fields,
        'footer': {'text': 'StockPilot PH · Scores are for educational purposes only.'},
    }


def get_mystatus_embed(discord_id: str) -> dict:
    """
    Returns a Discord embed dict showing the user's subscription status.
    """
    try:
        from dashboard.access_control import get_member_by_discord_id, get_member_tier
        from dashboard.paymongo_core import get_pricing
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    tier   = get_member_tier(discord_id)
    member = get_member_by_discord_id(discord_id)

    if not member or tier == 'free':
        return {
            'title':       'StockPilot PH — My Status',
            'description': 'You are on the **Free** tier.',
            'color':       COLOUR_GREY,
            'fields': [
                {
                    'name':   'What You Have Access To',
                    'value':  (
                        '• `/help` — commands and glossary\n'
                        '• Grade-only previews via `/stock` (no scores or IV)\n'
                        '• Top 3 grade summary via `/top10`\n'
                        '• Public Discord channels + forum'
                    ),
                    'inline': False,
                },
                {
                    'name':   'Upgrade',
                    'value':  'Use `/subscribe` to unlock full access.',
                    'inline': False,
                },
            ],
            'footer': {'text': 'StockPilot PH · ₱99/mo for full access.'},
        }

    # Paid member
    expiry_str = member.get('expiry_date', 'Unknown')
    plan       = member.get('plan', 'monthly').title()
    status     = member.get('status', 'active').title()

    # Days remaining
    days_left_str = ''
    try:
        expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d').date()
        days_left = (expiry_dt - date.today()).days
        if days_left > 0:
            days_left_str = f'{days_left} days remaining'
        elif days_left == 0:
            days_left_str = 'Expires today!'
        else:
            days_left_str = 'Expired'
    except Exception:
        days_left_str = ''

    m_centavos, _ = get_pricing('monthly')
    m_php = m_centavos / 100

    fields = [
        {'name': 'Plan',   'value': plan,       'inline': True},
        {'name': 'Status', 'value': status,     'inline': True},
        {'name': 'Expires', 'value': f'{expiry_str}\n{days_left_str}', 'inline': True},
        {
            'name':   'Your Premium Access',
            'value':  (
                '• Full rankings + scores in `#full-rankings`\n'
                '• `/stock <ticker>` — full analysis via DM\n'
                '• `/top10` — full top 10 with scores\n'
                '• Weekly Digest every Friday\n'
                '• Stock of the Week every Monday\n'
                '• Real-time alerts + PDF reports'
            ),
            'inline': False,
        },
    ]

    if days_left_str in ('Expires today!', 'Expired') or (
        days_left_str.startswith('') and 'days remaining' in days_left_str
        and int(days_left_str.split()[0]) <= 7
    ):
        fields.append({
            'name':   '⚠️ Renewal',
            'value':  f'Use `/subscribe` to renew for ₱{m_php:.0f}/mo.',
            'inline': False,
        })

    return {
        'title':       'StockPilot PH — My Status',
        'description': 'You are a **StockPilot Premium** member.',
        'color':       COLOUR_GOLD,
        'fields':      fields,
        'footer':      {'text': 'StockPilot PH · Thank you for your support!'},
    }
