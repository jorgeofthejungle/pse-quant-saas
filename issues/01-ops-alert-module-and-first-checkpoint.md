---
label: ready-for-agent
type: AFK
---

## Overview

Prove the full ops alerting path end-to-end through the most important pipeline failure mode: no stocks loaded from the database.

Create a new deep module in the Discord layer with a single public function `send_ops_alert(stage, error)`. It reads the ops webhook URL from the environment, posts a red Discord embed (title "Pipeline Failure", fields: Stage, Error truncated to 1000 chars, Timestamp), and silently swallows any failure — no caller ever needs to handle its failure. Register the ops webhook key in the shared webhook registry for consistency with the other four channels.

Instrument the pipeline orchestrator so that when `load_stocks()` returns an empty list, `send_ops_alert` is called with stage `"Load: no stocks in DB"` and the situation description as the error string.

Write unit tests that verify external behaviour only — what payload was POSTed to the webhook URL, or that no request was made — not internal implementation details.

Update the Discord channel reference table to document the new private ops channel.

**Demo path:** point `DISCORD_WEBHOOK_OPS` at a private channel, run the pipeline against an empty database, confirm the red embed appears in the ops channel. Run the test suite green.

## Acceptance criteria

- [ ] `send_ops_alert(stage, error)` exists and is the only public symbol exported from the new module
- [ ] When `DISCORD_WEBHOOK_OPS` is not set, `requests.post` is never called
- [ ] When `requests.post` raises any exception, the exception does not propagate to the caller
- [ ] When the webhook is set, the POST body contains an embed with the correct stage and error values in named fields
- [ ] When the error string exceeds 1000 characters, the embed's error field is truncated — the surrounding embed structure remains intact
- [ ] The embed colour is the existing `COLOUR_ALERT` constant (red, `0xE74C3C`) from the shared webhook constants module
- [ ] `DISCORD_WEBHOOK_OPS` is documented as a new env var (alongside the existing four webhook env vars)
- [ ] The ops webhook key is registered in the shared webhook registry dict
- [ ] The pipeline orchestrator calls `send_ops_alert` when `load_stocks()` returns an empty list
- [ ] The Discord channel reference table in the discord subdirectory docs is updated with the new ops channel row
- [ ] All existing tests continue to pass

## Blocking dependencies

None
