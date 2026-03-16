# ============================================================
# discord_core.py — Webhook HTTP Layer & Shared Constants
# PSE Quant SaaS
# ============================================================
# Low-level POST functions and all shared constants used by
# discord_reports.py and discord_alerts.py.
# ============================================================

import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / '.env')

# ── Webhook URLs (loaded from .env) ───────────────────────
WEBHOOKS = {
    'rankings':       os.getenv('DISCORD_WEBHOOK_RANKINGS',       ''),
    'alerts':         os.getenv('DISCORD_WEBHOOK_ALERTS',         ''),
    'deep_analysis':  os.getenv('DISCORD_WEBHOOK_DEEP_ANALYSIS',  ''),
    'daily_briefing': os.getenv('DISCORD_WEBHOOK_DAILY_BRIEFING', ''),
}

# ── Colour codes (Discord embed colours) ──────────────────
COLOUR_DIVIDEND = 0x27AE60   # green
COLOUR_VALUE    = 0x2980B9   # blue
COLOUR_HYBRID   = 0x8E44AD   # purple
COLOUR_ALERT    = 0xE74C3C   # red
COLOUR_INFO     = 0x1B4B6B   # navy

MAX_FILE_BYTES = 8 * 1024 * 1024   # 8 MB

PORTFOLIO_COLOURS = {
    'pure_dividend':   COLOUR_DIVIDEND,
    'dividend_growth': COLOUR_HYBRID,
    'value':           COLOUR_VALUE,
}

PORTFOLIO_EMOJI = {
    'pure_dividend':   '💰',
    'dividend_growth': '📈',
    'value':           '📊',
}

DISCLAIMER = (
    'For research and educational purposes only. '
    'Not investment advice. Always do your own due diligence.'
)

SIGNAL_DISCLAIMER = (
    'Educational signal based on quantitative criteria and AI-classified news sentiment. '
    'This is NOT investment advice. Always do your own research before making any investment decision.'
)

# ── Signal alert colours ───────────────────────────────────
COLOUR_OPPORTUNITY = 0x27AE60   # green — potential opportunity
COLOUR_HALF_POS    = 0xF39C12   # amber — half position signal
COLOUR_CAUTION     = 0xE74C3C   # red   — caution signal
COLOUR_SHORTLIST   = 0xE67E22   # orange — shortlist membership change


def _post_webhook(webhook_url: str, payload: dict) -> bool:
    """
    Sends a JSON payload (no file) to a Discord webhook.
    Returns True on success, False on failure.
    """
    try:
        response = requests.post(webhook_url, json=payload, timeout=15)
        if response.status_code in (200, 204):
            return True
        print(f"Discord error {response.status_code}: {response.text[:200]}")
        return False
    except requests.RequestException as e:
        print(f"Discord request failed: {e}")
        return False


def _post_webhook_with_file(webhook_url: str, file_path: str, payload: dict) -> bool:
    """
    Sends a Discord webhook with a file attachment.
    payload_json is sent alongside the file as multipart form data.
    Returns True on success, False on failure.
    """
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'application/pdf')}
            data  = {'payload_json': json.dumps(payload)}
            response = requests.post(webhook_url, data=data, files=files, timeout=30)
        if response.status_code in (200, 204):
            return True
        print(f"Discord file upload error {response.status_code}: {response.text[:200]}")
        return False
    except requests.RequestException as e:
        print(f"Discord file upload failed: {e}")
        return False
    except FileNotFoundError:
        print(f"PDF not found: {file_path}")
        return False
