# ============================================================
# routes_paymongo.py — PayMongo Payment Link + Webhook
# PSE Quant SaaS — Dashboard
# ============================================================
# Flow (manual):
#   1. Click "Generate Link" → PayMongo API creates link
#   2. Link URL displayed — Josh sends via Discord DM
#   3. Member pays via GCash/Maya/card on PayMongo's checkout page
#   4. Webhook auto-confirms on payment (4.1) OR Josh clicks "Mark as Paid"
#
# Webhook setup (PayMongo dashboard):
#   URL: https://<your-domain>/paymongo/webhook
#   Events: link.payment.paid
#   Secret: set PAYMONGO_WEBHOOK_SECRET in .env
# ============================================================

import sys
import os
import json
import hashlib
import hmac
from pathlib import Path
from flask import Blueprint, request, jsonify
from dashboard.security import rate_limit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'db'))

from db.db_settings import get_setting

paymongo_bp = Blueprint('paymongo', __name__)

PAYMONGO_API = 'https://api.paymongo.com/v1'


def _get_auth():
    """Returns (secret_key, is_configured)."""
    key = os.getenv('PAYMONGO_SECRET_KEY', '')
    return key, bool(key)


@paymongo_bp.route('/create-link', methods=['POST'])
@rate_limit(limit=10)
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

    # Amount in centavos — DB setting takes priority over .env
    if plan == 'annual':
        centavos    = int(get_setting('annual_price_centavos',
                                       os.getenv('ANNUAL_PRICE_CENTAVOS', 299900)))
        description = 'PSE Quant SaaS - Annual Subscription'
    else:
        centavos    = int(get_setting('monthly_price_centavos',
                                       os.getenv('MONTHLY_PRICE_CENTAVOS', 29900)))
        description = 'PSE Quant SaaS - Monthly Subscription'

    # Encode member_id in remarks so webhook can auto-confirm payment
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


@paymongo_bp.route('/webhook', methods=['POST'])
def webhook():
    """
    PayMongo webhook — auto-confirms payments when a link is paid.

    Setup in PayMongo dashboard:
      URL:    https://<your-domain>/paymongo/webhook
      Events: link.payment.paid
      Secret: PAYMONGO_WEBHOOK_SECRET in .env
    """
    from dashboard.db_members import get_member, extend_member, record_payment, log_activity

    raw_body   = request.get_data()
    sig_header = request.headers.get('Paymongo-Signature', '')
    wh_secret  = os.getenv('PAYMONGO_WEBHOOK_SECRET', '')

    # ── Signature verification ────────────────────────────────
    if wh_secret:
        if not _verify_paymongo_signature(raw_body, sig_header, wh_secret):
            log_activity('payment', 'webhook_signature_fail',
                         f'Bad signature from {request.remote_addr}', status='error')
            return jsonify({'ok': False, 'error': 'Invalid signature'}), 400

    # ── Parse event ───────────────────────────────────────────
    try:
        event = json.loads(raw_body)
    except Exception:
        return jsonify({'ok': False, 'error': 'Invalid JSON'}), 400

    event_type = (event.get('data', {})
                       .get('attributes', {})
                       .get('type', ''))

    if event_type != 'link.payment.paid':
        # Acknowledge other events silently
        return jsonify({'ok': True, 'message': f'Event {event_type!r} ignored'}), 200

    # ── Extract link attributes ────────────────────────────────
    link_attrs = (event.get('data', {})
                       .get('attributes', {})
                       .get('data', {})
                       .get('attributes', {}))

    amount_centavos = link_attrs.get('amount', 0)
    remarks         = link_attrs.get('remarks', '')
    payment_id      = (event.get('data', {})
                            .get('attributes', {})
                            .get('data', {})
                            .get('id', ''))

    # ── Identify member from remarks (mid:<id>) ────────────────
    member_id = _extract_member_id(remarks)
    if not member_id:
        log_activity('payment', 'webhook_no_member',
                     f'Could not find mid: in remarks={remarks!r}',
                     status='warning')
        return jsonify({'ok': True, 'message': 'No member ID in remarks — manual review needed'}), 200

    member = get_member(member_id)
    if not member:
        log_activity('payment', 'webhook_member_not_found',
                     f'member_id={member_id} from remarks={remarks!r}',
                     status='error')
        return jsonify({'ok': False, 'error': f'Member {member_id} not found'}), 200

    # ── Determine plan + amount ────────────────────────────────
    amount_php = amount_centavos / 100
    annual_threshold = int(os.getenv('ANNUAL_PRICE_CENTAVOS', 99900))
    plan = 'annual' if amount_centavos >= annual_threshold else 'monthly'
    days = 365 if plan == 'annual' else 30

    record_payment(
        member_id      = member_id,
        amount         = amount_php,
        plan           = plan,
        payment_method = 'paymongo',
        payment_id     = payment_id,
    )
    # Mark member as paid tier
    _set_member_tier(member_id, 'paid')

    log_activity(
        'payment', 'webhook_auto_confirmed',
        f'{member["discord_name"]} · PHP{amount_php:.2f} · {plan} · pid={payment_id}',
    )
    return jsonify({'ok': True, 'message': 'Payment confirmed'}), 200


def _verify_paymongo_signature(raw_body: bytes, sig_header: str, secret: str) -> bool:
    """
    Verifies the PayMongo webhook signature.
    Header format: t=<timestamp>,te=<hmac>,li=<hmac>
    HMAC = HMAC_SHA256(secret, f"{timestamp}.{raw_body}")
    """
    if not sig_header:
        return False
    parts = {}
    for chunk in sig_header.split(','):
        if '=' in chunk:
            k, v = chunk.split('=', 1)
            parts[k.strip()] = v.strip()

    timestamp = parts.get('t', '')
    sig_te    = parts.get('te', '')
    sig_li    = parts.get('li', '')

    if not timestamp or not (sig_te or sig_li):
        return False

    message  = f'{timestamp}.'.encode() + raw_body
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

    # Accept either test (te) or live (li) signature
    return (sig_te and hmac.compare_digest(expected, sig_te)) or \
           (sig_li and hmac.compare_digest(expected, sig_li))


def _extract_member_id(remarks: str) -> int | None:
    """Extracts numeric member ID from 'mid:<id>' in remarks string."""
    import re
    m = re.search(r'mid:(\d+)', remarks or '')
    return int(m.group(1)) if m else None


def _set_member_tier(member_id: int, tier: str):
    """Sets the tier column on a member record."""
    from db.db_connection import get_connection
    conn = get_connection()
    conn.execute("UPDATE members SET tier = ? WHERE id = ?", (tier, member_id))
    conn.commit()
    conn.close()


@paymongo_bp.route('/config')
def config():
    """JSON: PayMongo configuration status (for settings page)."""
    _, configured = _get_auth()
    wh_secret_set = bool(os.getenv('PAYMONGO_WEBHOOK_SECRET', ''))
    return jsonify({
        'configured':       configured,
        'webhook_secret':   wh_secret_set,
        'monthly_php':      int(os.getenv('MONTHLY_PRICE_CENTAVOS', 9900)) / 100,
        'annual_php':       int(os.getenv('ANNUAL_PRICE_CENTAVOS', 99900)) / 100,
    })
