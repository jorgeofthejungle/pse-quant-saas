# ============================================================
# publisher.py — Public Facade (re-exports all Discord functions)
# PSE Quant SaaS
# ============================================================
# All callers import from here -- internal structure is hidden.
# Sub-modules:
#   discord_core.py    -- webhook HTTP layer & shared constants
#   discord_reports.py -- send_report()
#   discord_alerts.py  -- all send_*_alert() functions
# ============================================================

from discord.discord_core import (
    _post_webhook, _post_webhook_with_file,
    WEBHOOKS, DISCLAIMER, SIGNAL_DISCLAIMER,
    COLOUR_DIVIDEND, COLOUR_VALUE, COLOUR_HYBRID, COLOUR_ALERT, COLOUR_INFO,
    COLOUR_OPPORTUNITY, COLOUR_HALF_POS, COLOUR_CAUTION, COLOUR_SHORTLIST,
    PORTFOLIO_COLOURS, PORTFOLIO_EMOJI, MAX_FILE_BYTES,
)
from discord.discord_reports import send_report
from discord.discord_alerts  import (
    send_dividend_alert, send_price_alert, send_earnings_alert,
    send_rescore_notice, send_opportunistic_alert, send_sentiment_signal,
    send_shortlist_change, send_expiry_notification,
)

__all__ = [
    'send_report',
    'send_dividend_alert', 'send_price_alert', 'send_earnings_alert',
    'send_rescore_notice', 'send_opportunistic_alert', 'send_sentiment_signal',
    'send_shortlist_change', 'send_expiry_notification',
    'test_webhook',
    'WEBHOOKS', 'DISCLAIMER', 'SIGNAL_DISCLAIMER',
]


def test_webhook(webhook_url: str, channel_name: str) -> bool:
    """
    Sends a simple test message to verify the webhook URL works.
    Call this once after setting up each webhook in .env.
    """
    payload = {
        'content': (
            f"PSE Quant SaaS webhook connected successfully.\n"
            f"Channel: **{channel_name}**\n"
            f"Reports and alerts for this portfolio will appear here."
        )
    }
    success = _post_webhook(webhook_url, payload)
    if success:
        print(f"Webhook test passed: {channel_name}")
    else:
        print(f"Webhook test FAILED: {channel_name} -- check the URL in .env")
    return success
