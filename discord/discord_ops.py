# ============================================================
# discord_ops.py — Ops Alert Channel
# PSE Quant SaaS
# ============================================================
# Sends internal pipeline failure alerts to the private ops
# Discord channel. Failures are silently swallowed — callers
# never need to handle errors from this module.
#
# Public API:
#   send_ops_alert(stage, error) -> None
# ============================================================

from datetime import datetime, timezone

from discord.discord_core import WEBHOOKS, COLOUR_ALERT, _post_webhook


def send_ops_alert(stage: str, error: str) -> None:
    """
    Posts a red embed to the ops Discord channel signalling a pipeline failure.

    Args:
        stage: Short label for the pipeline stage where the failure occurred.
        error: Description of the failure. Truncated to 1000 characters.

    Silently swallows all failures — callers never need to handle exceptions
    from this function.
    """
    url = WEBHOOKS.get('ops', '')
    if not url:
        return

    truncated_error = error[:1000]
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    payload = {
        'embeds': [
            {
                'title': 'Pipeline Failure',
                'color': COLOUR_ALERT,
                'fields': [
                    {'name': 'Stage',     'value': stage,           'inline': False},
                    {'name': 'Error',     'value': truncated_error, 'inline': False},
                    {'name': 'Timestamp', 'value': timestamp,       'inline': False},
                ],
            }
        ]
    }

    try:
        _post_webhook(url, payload)
    except Exception:
        pass
