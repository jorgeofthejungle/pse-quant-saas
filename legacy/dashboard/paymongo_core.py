# ============================================================
# paymongo_core.py — PayMongo Payment Link Generator
# PSE Quant SaaS
# ============================================================
# Standalone function for creating PayMongo payment links.
# Used by both routes_paymongo.py (Flask) and bot_subscribe.py (Discord bot).
# ============================================================

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAYMONGO_API = 'https://api.paymongo.com/v1'


def get_paymongo_auth() -> tuple[str, bool]:
    """Returns (secret_key, is_configured)."""
    key = os.getenv('PAYMONGO_SECRET_KEY', '')
    return key, bool(key)


def get_pricing(plan: str) -> tuple[int, str]:
    """
    Returns (centavos, description) for the given plan.
    Reads from DB settings first, falls back to .env, then hardcoded defaults.
    """
    try:
        from db.db_settings import get_setting
        if plan == 'annual':
            centavos    = int(get_setting('annual_price_centavos',
                                          os.getenv('ANNUAL_PRICE_CENTAVOS', 99900)))
            description = 'StockPilot PH - Annual Subscription'
        else:
            centavos    = int(get_setting('monthly_price_centavos',
                                          os.getenv('MONTHLY_PRICE_CENTAVOS', 9900)))
            description = 'StockPilot PH - Monthly Subscription'
    except Exception:
        centavos    = 99900 if plan == 'annual' else 9900
        description = f'StockPilot PH - {plan.title()} Subscription'
    return centavos, description


def generate_payment_link(
    member_id:   int | None,
    member_name: str,
    plan:        str = 'monthly',
) -> tuple[bool, str, str]:
    """
    Creates a PayMongo payment link.
    Returns (ok, url_or_error, payment_id).
      ok=True  → url is the checkout URL, payment_id is the PM link ID
      ok=False → url is an error message, payment_id is ''
    """
    import requests as req

    secret_key, configured = get_paymongo_auth()
    if not configured:
        return False, 'PayMongo is not configured. Contact Josh to subscribe.', ''

    centavos, description = get_pricing(plan)
    remarks = f'mid:{member_id} {plan}' if member_id else f'{member_name} ({plan})'

    payload = {
        'data': {
            'attributes': {
                'amount':      centavos,
                'description': description,
                'remarks':     remarks,
            }
        }
    }

    try:
        response = req.post(
            f'{PAYMONGO_API}/links',
            json    = payload,
            auth    = (secret_key, ''),
            timeout = 15,
        )
        resp_data = response.json()

        if response.status_code in (200, 201):
            url = (resp_data.get('data', {})
                            .get('attributes', {})
                            .get('checkout_url', ''))
            pm_id = resp_data.get('data', {}).get('id', '')
            return True, url, pm_id

        error_msg = (resp_data.get('errors', [{}])[0]
                              .get('detail', 'PayMongo API error'))
        return False, error_msg, ''

    except Exception as e:
        return False, str(e), ''
