# ============================================================
# bot_admin.py — /admin Command Logic
# PSE Quant SaaS — Discord Bot
# ============================================================
# Josh-only commands. Gated by ADMIN_DISCORD_ID in .env.
# All commands are DM-only.
#
# /admin list              — all active members + expiry dates
# /admin pending           — unconfirmed/pending members
# /admin confirm <name>    — activate a pending member + send welcome DM
# /admin extend <name> <days> — extend a member's subscription
# /admin status <name>     — full details for one member
# ============================================================

from __future__ import annotations

import sys
from datetime import datetime, date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'dashboard'))
sys.path.insert(0, str(ROOT))

COLOUR_GREEN  = 0x27AE60
COLOUR_BLUE   = 0x2980B9
COLOUR_ORANGE = 0xE67E22
COLOUR_RED    = 0xE74C3C
COLOUR_GREY   = 0x95A5A6
COLOUR_GOLD   = 0xF39C12


def _find_member(query: str) -> dict | None:
    """
    Finds a member by partial name (case-insensitive) or exact discord_id.
    Returns the first match, or None.
    """
    try:
        from dashboard.db_members import get_all_members
    except ImportError:
        return None
    all_members = get_all_members()
    q = query.strip().lower()
    # Exact discord_id match first
    for m in all_members:
        if str(m.get('discord_id', '')) == q:
            return m
    # Partial name match
    for m in all_members:
        if q in (m.get('discord_name') or '').lower():
            return m
    return None


def get_admin_list_embed() -> dict:
    """Returns embed showing all active members with expiry dates."""
    try:
        from dashboard.db_members import get_all_members
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    active  = get_all_members(status_filter='active')
    today   = date.today()

    if not active:
        return {
            'title':       'StockPilot — Member List',
            'description': 'No active members yet.',
            'color':       COLOUR_GREY,
            'fields':      [],
            'footer':      {'text': 'StockPilot PH · Admin'},
        }

    lines = []
    for m in active:
        name    = m.get('discord_name', '?')
        plan    = m.get('plan', 'monthly').title()
        expiry  = m.get('expiry_date', 'Unknown')
        did     = m.get('discord_id') or '—'
        try:
            days_left = (datetime.strptime(expiry, '%Y-%m-%d').date() - today).days
            expiry_str = f'{expiry} ({days_left}d)'
        except Exception:
            expiry_str = expiry
        lines.append(f'**{name}** · {plan} · Expires: {expiry_str} · ID: `{did}`')

    return {
        'title':       f'StockPilot — Active Members ({len(active)})',
        'description': '\n'.join(lines),
        'color':       COLOUR_BLUE,
        'fields':      [],
        'footer':      {'text': 'StockPilot PH · Admin · /admin confirm <name> to activate pending'},
    }


def get_admin_pending_embed() -> dict:
    """Returns embed showing all pending members awaiting confirmation."""
    try:
        from dashboard.db_members import get_all_members
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    pending = get_all_members(status_filter='pending')

    if not pending:
        return {
            'title':       'StockPilot — Pending Members',
            'description': 'No pending members.',
            'color':       COLOUR_GREY,
            'fields':      [],
            'footer':      {'text': 'StockPilot PH · Admin'},
        }

    lines = []
    for m in pending:
        name  = m.get('discord_name', '?')
        did   = m.get('discord_id') or '—'
        notes = m.get('notes') or ''
        lines.append(f'**{name}** · ID: `{did}`' + (f'\n_{notes}_' if notes else ''))

    return {
        'title':       f'StockPilot — Pending Members ({len(pending)})',
        'description': '\n'.join(lines),
        'color':       COLOUR_ORANGE,
        'fields': [{
            'name':   'To confirm',
            'value':  '`/admin confirm <name>` — activates member and sends welcome DM',
            'inline': False,
        }],
        'footer': {'text': 'StockPilot PH · Admin'},
    }


def confirm_member_embed(query: str) -> dict:
    """
    Activates a pending member and sends them a welcome DM.
    Returns a confirmation embed.
    """
    try:
        from dashboard.db_members import get_all_members, log_activity
        from discord.discord_dm import send_welcome_dm
        from db.db_connection import get_connection
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    member = _find_member(query)
    if not member:
        return {
            'title':       'Member Not Found',
            'description': f'No member matching **{query}**.\nUse `/admin list` or `/admin pending` to see all members.',
            'color':       COLOUR_RED,
            'fields':      [],
            'footer':      {'text': 'StockPilot PH · Admin'},
        }

    name      = member.get('discord_name', '?')
    discord_id = member.get('discord_id')
    plan      = member.get('plan', 'monthly')

    # Set status active + expiry
    days   = 365 if plan == 'annual' else 30
    expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_connection()
    conn.execute(
        "UPDATE members SET status = 'active', expiry_date = ?, tier = 'paid' WHERE id = ?",
        (expiry, member['id'])
    )
    conn.commit()
    conn.close()

    log_activity('member', 'admin_confirmed', f'{name} confirmed via /admin confirm')

    # Send welcome DM
    dm_status = 'not sent (no Discord ID)'
    if discord_id:
        ok, err = send_welcome_dm(discord_id, name, expiry)
        dm_status = 'sent' if ok else f'failed — {err}'

    return {
        'title':       f'Member Confirmed — {name}',
        'description': f'**{name}** is now active until **{expiry}**.',
        'color':       COLOUR_GREEN,
        'fields': [
            {'name': 'Plan',        'value': plan.title(),  'inline': True},
            {'name': 'Expiry',      'value': expiry,        'inline': True},
            {'name': 'Welcome DM',  'value': dm_status,     'inline': True},
        ],
        'footer': {'text': 'StockPilot PH · Admin'},
    }


def extend_member_embed(query: str, days: int) -> dict:
    """Extends a member's subscription by the given number of days."""
    try:
        from dashboard.db_members import extend_member, log_activity
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    member = _find_member(query)
    if not member:
        return {
            'title':       'Member Not Found',
            'description': f'No member matching **{query}**.',
            'color':       COLOUR_RED,
            'fields':      [],
            'footer':      {'text': 'StockPilot PH · Admin'},
        }

    name = member.get('discord_name', '?')
    extend_member(member['id'], days, source='admin_discord')
    log_activity('member', 'admin_extended', f'{name} +{days} days via /admin extend')

    # Re-fetch to get new expiry
    try:
        from dashboard.db_members import get_member
        updated = get_member(member['id'])
        new_expiry = updated.get('expiry_date', '?') if updated else '?'
    except Exception:
        new_expiry = '?'

    return {
        'title':       f'Subscription Extended — {name}',
        'description': f'Added **{days} days** to **{name}**\'s subscription.',
        'color':       COLOUR_GREEN,
        'fields': [
            {'name': 'New Expiry', 'value': new_expiry, 'inline': True},
        ],
        'footer': {'text': 'StockPilot PH · Admin'},
    }


def get_member_status_embed(query: str) -> dict:
    """Returns a detailed status embed for one member."""
    try:
        from dashboard.db_members import get_member_subscriptions
    except ImportError as e:
        return {'error': f'Import error: {e}'}

    member = _find_member(query)
    if not member:
        return {
            'title':       'Member Not Found',
            'description': f'No member matching **{query}**.',
            'color':       COLOUR_RED,
            'fields':      [],
            'footer':      {'text': 'StockPilot PH · Admin'},
        }

    name      = member.get('discord_name', '?')
    status    = member.get('status', '?').title()
    plan      = member.get('plan', '?').title()
    expiry    = member.get('expiry_date', 'Unknown')
    discord_id = member.get('discord_id') or '—'
    joined    = member.get('joined_date', '?')
    notes     = member.get('notes') or '—'

    # Days remaining
    days_str = ''
    try:
        days_left = (datetime.strptime(expiry, '%Y-%m-%d').date() - date.today()).days
        days_str  = f' ({days_left}d remaining)' if days_left > 0 else ' (expired)'
    except Exception:
        pass

    # Payment count
    try:
        subs = get_member_subscriptions(member['id'])
        payment_count = len(subs)
        total_paid    = sum(s.get('amount', 0) for s in subs)
        payment_str   = f'{payment_count} payment(s) · ₱{total_paid:.2f} total'
    except Exception:
        payment_str = '—'

    colour = COLOUR_GREEN if status == 'Active' else (
        COLOUR_RED if status in ('Expired', 'Cancelled') else COLOUR_ORANGE
    )

    return {
        'title':       f'Member Status — {name}',
        'description': f'Status: **{status}**',
        'color':       colour,
        'fields': [
            {'name': 'Plan',        'value': plan,                  'inline': True},
            {'name': 'Expiry',      'value': expiry + days_str,     'inline': True},
            {'name': 'Joined',      'value': joined,                'inline': True},
            {'name': 'Discord ID',  'value': f'`{discord_id}`',     'inline': True},
            {'name': 'Payments',    'value': payment_str,           'inline': True},
            {'name': 'Notes',       'value': notes,                 'inline': False},
        ],
        'footer': {'text': 'StockPilot PH · Admin'},
    }
