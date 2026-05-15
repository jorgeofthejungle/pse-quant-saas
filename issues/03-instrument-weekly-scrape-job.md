---
label: ready-for-agent
type: AFK
---

## Overview

Instrument the weekly full-scrape job so that a scraper failure fires an ops alert, giving the operator visibility before Monday's rankings run on stale data.

The weekly scrape job currently swallows scraper exceptions with a `print()` and returns silently. Update the exception handler so that when `scrape_all_and_save()` raises, `send_ops_alert` is called with stage `"Weekly Scrape"` and the exception message before the function returns.

This is the only checkpoint needed in the weekly job — the subsequent steps (stale-data re-fetch, conglomerate autofill, DPS cleanup, data quality audit) are non-fatal degradation and must remain silent.

**Demo path:** point `DISCORD_WEBHOOK_OPS` at the ops channel, trigger the weekly scrape job with a broken scraper import, and confirm the red embed fires. The job should still exit cleanly — the alert does not change control flow.

## Acceptance criteria

- [ ] When `scrape_all_and_save()` raises any exception, `send_ops_alert` fires with stage `"Weekly Scrape"` and the exception message
- [ ] The weekly job exits cleanly after the alert — the alert does not re-raise or alter the exit path
- [ ] Failures in subsequent non-fatal steps (stale re-fetch, autofill, DPS cleanup, quality audit) do not trigger any alert
- [ ] A failure in `send_ops_alert` itself does not prevent the weekly job from completing its remaining steps
- [ ] All existing tests continue to pass

## Blocking dependencies

- Blocked by #01 (ops alert module must exist before instrumentation)
