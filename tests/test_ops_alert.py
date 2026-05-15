import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock

from discord.discord_ops import send_ops_alert


# ============================================================
# test_no_post_when_webhook_not_set
# ============================================================

def test_no_post_when_webhook_not_set():
    """When DISCORD_WEBHOOK_OPS is not set (WEBHOOKS['ops'] == ''), _post_webhook is never called."""
    # Patch WEBHOOKS in discord_ops' own namespace (where it was imported into)
    with patch('discord.discord_ops.WEBHOOKS', {'ops': ''}):
        with patch('discord.discord_ops._post_webhook') as mock_post_fn:
            send_ops_alert('TestStage', 'some error')
            mock_post_fn.assert_not_called()


# ============================================================
# test_post_called_with_stage_and_error
# ============================================================

def test_post_called_with_stage_and_error():
    """When webhook is set, POST is called and body contains an embed with Stage and Error fields."""
    fake_url = 'https://discord.com/api/webhooks/fake/ops'
    mock_response = MagicMock()
    mock_response.status_code = 204

    with patch('discord.discord_ops.WEBHOOKS', {'ops': fake_url}):
        with patch('discord.discord_core.requests.post', return_value=mock_response) as mock_post:
            send_ops_alert('Load: no stocks in DB', 'load_stocks() returned an empty list')

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    # POST url is first positional arg
    posted_url = call_kwargs[0][0] if call_kwargs[0] else call_kwargs.kwargs.get('url', '')
    assert posted_url == fake_url, f"Expected URL {fake_url!r}, got {posted_url!r}"

    # Extract the JSON payload
    payload = call_kwargs.kwargs.get('json') or (call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None)
    assert payload is not None, "No JSON payload found in POST call"

    embeds = payload.get('embeds', [])
    assert len(embeds) == 1, f"Expected 1 embed, got {len(embeds)}"
    embed = embeds[0]

    fields = {f['name']: f['value'] for f in embed.get('fields', [])}
    assert 'Stage' in fields, f"No 'Stage' field in embed fields: {fields}"
    assert 'Error' in fields, f"No 'Error' field in embed fields: {fields}"
    assert fields['Stage'] == 'Load: no stocks in DB'
    assert 'load_stocks() returned an empty list' in fields['Error']


# ============================================================
# test_error_truncated_at_1000_chars
# ============================================================

def test_error_truncated_at_1000_chars():
    """When error string is >1000 chars, embed Error field is truncated to 1000 chars."""
    fake_url = 'https://discord.com/api/webhooks/fake/ops'
    long_error = 'X' * 2000
    mock_response = MagicMock()
    mock_response.status_code = 204

    with patch('discord.discord_ops.WEBHOOKS', {'ops': fake_url}):
        with patch('discord.discord_core.requests.post', return_value=mock_response) as mock_post:
            send_ops_alert('SomeStage', long_error)

    payload = mock_post.call_args.kwargs.get('json')
    embed = payload['embeds'][0]
    fields = {f['name']: f['value'] for f in embed.get('fields', [])}

    assert len(fields['Error']) == 1000, (
        f"Expected Error field truncated to 1000 chars, got {len(fields['Error'])}"
    )
    # Other embed structure must remain intact
    assert 'title' in embed
    assert 'Stage' in fields


# ============================================================
# test_exception_from_post_does_not_propagate
# ============================================================

def test_exception_from_post_does_not_propagate():
    """When requests.post raises any exception, send_ops_alert returns without raising."""
    fake_url = 'https://discord.com/api/webhooks/fake/ops'

    with patch('discord.discord_ops.WEBHOOKS', {'ops': fake_url}):
        with patch('discord.discord_core.requests.post', side_effect=Exception('network error')):
            # Must not raise
            send_ops_alert('SomeStage', 'some error')


# ============================================================
# test_embed_colour_is_alert_red
# ============================================================

def test_embed_colour_is_alert_red():
    """When POST is called, embed colour is COLOUR_ALERT (0xE74C3C)."""
    fake_url = 'https://discord.com/api/webhooks/fake/ops'
    mock_response = MagicMock()
    mock_response.status_code = 204

    with patch('discord.discord_ops.WEBHOOKS', {'ops': fake_url}):
        with patch('discord.discord_core.requests.post', return_value=mock_response) as mock_post:
            send_ops_alert('SomeStage', 'some error')

    payload = mock_post.call_args.kwargs.get('json')
    embed = payload['embeds'][0]
    assert embed.get('color') == 0xE74C3C, (
        f"Expected colour 0xE74C3C, got {embed.get('color')!r}"
    )


# ============================================================
# test_pipeline_calls_send_ops_alert_on_empty_load
# ============================================================

def test_pipeline_calls_send_ops_alert_on_empty_load():
    """When load_stocks() returns [], run_pipeline calls send_ops_alert with the correct stage."""
    import main

    # Patch send_ops_alert in main's namespace (where it was imported into via
    # `from discord.discord_ops import send_ops_alert`)
    with patch.object(main, 'load_stocks', return_value=[]):
        with patch.object(main, 'send_ops_alert') as mock_alert:
            try:
                main.run_pipeline(dry_run=True)
            except Exception:
                pass  # DB / other errors are acceptable in unit context

    mock_alert.assert_called_once()
    call_args = mock_alert.call_args
    stage = call_args[0][0] if call_args[0] else call_args.kwargs.get('stage', '')
    assert stage == 'Load: no stocks in DB', (
        f"Expected stage 'Load: no stocks in DB', got {stage!r}"
    )


# ============================================================
# Run
# ============================================================

if __name__ == '__main__':
    tests = [
        test_no_post_when_webhook_not_set,
        test_post_called_with_stage_and_error,
        test_error_truncated_at_1000_chars,
        test_exception_from_post_does_not_propagate,
        test_embed_colour_is_alert_red,
        test_pipeline_calls_send_ops_alert_on_empty_load,
    ]

    passed = 0
    failed = 0
    print()
    print('=' * 55)
    print('  OPS ALERT TESTS')
    print('=' * 55)
    for fn in tests:
        try:
            fn()
            print(f'  PASS  {fn.__name__}')
            passed += 1
        except AssertionError as e:
            print(f'  FAIL  {fn.__name__}: {e}')
            failed += 1
        except Exception as e:
            print(f'  ERROR {fn.__name__}: {type(e).__name__}: {e}')
            failed += 1

    print()
    print(f'  Results: {passed} passed, {failed} failed')
    print('=' * 55)
    if failed:
        raise SystemExit(1)
