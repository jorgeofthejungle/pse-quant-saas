# ============================================================
# discord_dm.py — Direct Message Delivery via Discord REST API
# PSE Quant SaaS
# ============================================================
# Sends embeds directly to a Discord user's DM inbox using the
# bot token and Discord REST API — no bot client needed.
#
# Flow:
#   1. POST /users/@me/channels  → open a DM channel
#   2. POST /channels/{id}/messages → send the embed
# ============================================================

import os
import requests
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / '.env')

_BASE_URL = 'https://discord.com/api/v10'


def _bot_headers() -> dict | None:
    """Returns auth headers using DISCORD_BOT_TOKEN, or None if not set."""
    token = os.getenv('DISCORD_BOT_TOKEN', '')
    if not token:
        return None
    return {
        'Authorization': f'Bot {token}',
        'Content-Type':  'application/json',
    }


def send_dm_embed(discord_id: str, embed: dict) -> tuple[bool, str]:
    """
    Sends a Discord embed as a DM to a user.

    Parameters:
        discord_id -- the user's Discord snowflake ID (as a string)
        embed      -- a Discord embed dict (same format as webhook embeds)

    Returns:
        (success: bool, error_message: str)
    """
    headers = _bot_headers()
    if not headers:
        return False, 'DISCORD_BOT_TOKEN not set in .env'

    # Step 1: Open (or reuse) a DM channel
    try:
        r = requests.post(
            f'{_BASE_URL}/users/@me/channels',
            headers=headers,
            json={'recipient_id': discord_id},
            timeout=10,
        )
        if r.status_code not in (200, 201):
            return False, f'DM channel open failed ({r.status_code}): {r.text[:200]}'
        channel_id = r.json().get('id')
        if not channel_id:
            return False, 'DM channel response missing id'
    except requests.RequestException as e:
        return False, f'DM channel request error: {e}'

    # Step 2: Send the embed
    try:
        r = requests.post(
            f'{_BASE_URL}/channels/{channel_id}/messages',
            headers=headers,
            json={'embeds': [embed]},
            timeout=10,
        )
        if r.status_code in (200, 201):
            return True, ''
        return False, f'DM send failed ({r.status_code}): {r.text[:200]}'
    except requests.RequestException as e:
        return False, f'DM send request error: {e}'


def send_welcome_dm(discord_id: str, member_name: str, expiry_date: str) -> tuple[bool, str]:
    """
    Sends a welcome embed to a newly activated premium member.
    Called from bot_admin.py (/admin confirm) and routes_paymongo.py (webhook auto-confirm).
    """
    embed = {
        'title':       'Welcome to StockPilot Premium!',
        'description': (
            f'Hi **{member_name}**! Your subscription is now active.\n\n'
            f'Your access runs until **{expiry_date}**.'
        ),
        'color': 0x27AE60,
        'fields': [
            {
                'name':   'Bot Commands (DM me directly)',
                'value':  (
                    '`/stock <ticker>` — full analysis of any PSE stock\n'
                    '`/top10` — current top 10 with scores and MoS\n'
                    '`/watchlist add/remove/show` — your personal stock watchlist'
                ),
                'inline': False,
            },
            {
                'name':   'Premium Channels',
                'value':  (
                    '`#rankings` — full PDF rankings report (updated when scores change)\n'
                    '`#deep-analysis` — Stock of the Week every Monday'
                ),
                'inline': False,
            },
            {
                'name':   'Weekly Digest',
                'value':  'Every Friday at 5 PM PHT I\'ll DM you a personalised summary — top 5, movers, dividends, and your watchlist.',
                'inline': False,
            },
            {
                'name':   'Need help?',
                'value':  'Use `/help` for a full command guide or ask in the server.',
                'inline': False,
            },
        ],
        'footer': {
            'text': 'StockPilot PH · Scores are educational rankings, not investment advice.'
        },
    }
    return send_dm_embed(discord_id, embed)


def send_dm_text(discord_id: str, content: str) -> tuple[bool, str]:
    """
    Sends a plain text DM to a user.
    Used for simple notifications (e.g. subscription activated).
    """
    headers = _bot_headers()
    if not headers:
        return False, 'DISCORD_BOT_TOKEN not set in .env'

    try:
        r = requests.post(
            f'{_BASE_URL}/users/@me/channels',
            headers=headers,
            json={'recipient_id': discord_id},
            timeout=10,
        )
        if r.status_code not in (200, 201):
            return False, f'DM channel open failed ({r.status_code})'
        channel_id = r.json().get('id')
    except requests.RequestException as e:
        return False, f'Request error: {e}'

    try:
        r = requests.post(
            f'{_BASE_URL}/channels/{channel_id}/messages',
            headers=headers,
            json={'content': content},
            timeout=10,
        )
        if r.status_code in (200, 201):
            return True, ''
        return False, f'DM send failed ({r.status_code}): {r.text[:200]}'
    except requests.RequestException as e:
        return False, f'Request error: {e}'
