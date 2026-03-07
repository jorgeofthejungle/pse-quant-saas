# ============================================================
# routes_paymongo.py — PayMongo Payment Link Generation
# PSE Quant SaaS — Dashboard
# ============================================================
# Flow:
#   1. Click "Generate Link" on member detail page
#   2. Dashboard calls PayMongo API to create a payment link
#   3. Link URL is displayed — Josh copies and sends via Discord DM
#   4. Member pays via GCash/Maya/card on PayMongo's hosted page
#   5. Josh clicks "Mark as Paid" to record the payment manually
# ============================================================

import sys
import os
import json
from pathlib import Path
from flask import Blueprint, request, jsonify

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

paymongo_bp = Blueprint('paymongo', __name__)

PAYMONGO_API = 'https://api.paymongo.com/v1'


def _get_auth():
    """Returns (secret_key, is_configured)."""
    key = os.getenv('PAYMONGO_SECRET_KEY', '')
    return key, bool(key)


@paymongo_bp.route('/create-link', methods=['POST'])
def create_link():
    """
    Generates a PayMongo payment link for a member.
    Expects JSON: {member_id, member_name, plan}
    Returns JSON: {ok, url, error}
    """
    import requests as req

    data       = request.get_json() or {}
    member_id  = data.get('member_id')
    member_name = data.get('member_name', 'Member')
    plan       = data.get('plan', 'monthly')

    secret_key, configured = _get_auth()
    if not configured:
        return jsonify({
            'ok':    False,
            'error': 'PAYMONGO_SECRET_KEY not set in .env. '
                     'Add it to use PayMongo payment links.',
        })

    # Amount in centavos
    if plan == 'annual':
        centavos    = int(os.getenv('ANNUAL_PRICE_CENTAVOS', 299900))
        description = 'PSE Quant SaaS - Annual Subscription'
    else:
        centavos    = int(os.getenv('MONTHLY_PRICE_CENTAVOS', 29900))
        description = 'PSE Quant SaaS - Monthly Subscription'

    payload = {
        'data': {
            'attributes': {
                'amount':      centavos,
                'description': description,
                'remarks':     f'{member_name} ({plan})',
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
            link_url = (resp_data.get('data', {})
                                 .get('attributes', {})
                                 .get('checkout_url', ''))
            pm_id    = resp_data.get('data', {}).get('id', '')
            return jsonify({'ok': True, 'url': link_url, 'payment_id': pm_id})

        error_msg = (resp_data.get('errors', [{}])[0]
                              .get('detail', 'PayMongo API error'))
        return jsonify({'ok': False, 'error': error_msg})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@paymongo_bp.route('/config')
def config():
    """JSON: PayMongo configuration status (for settings page)."""
    _, configured = _get_auth()
    return jsonify({
        'configured':    configured,
        'monthly_php':   int(os.getenv('MONTHLY_PRICE_CENTAVOS', 29900)) / 100,
        'annual_php':    int(os.getenv('ANNUAL_PRICE_CENTAVOS', 299900)) / 100,
    })
