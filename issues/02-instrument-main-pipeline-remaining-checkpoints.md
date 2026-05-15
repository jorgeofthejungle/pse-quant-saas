---
label: ready-for-agent
type: AFK
---

## Overview

Add the three remaining ops alert checkpoints to the main pipeline orchestrator, completing failure visibility for the full daily run.

The three failure modes to instrument:

1. **Zero eligible stocks** — after the health filter step, if no stocks pass the unified filter, call `send_ops_alert` with stage `"Filter: zero eligible stocks"`.
2. **PDF generation crash** — wrap the report generation step in a try/except; on any exception call `send_ops_alert` with stage `"PDF Generation"` and the exception message, then re-raise (or return False) so the pipeline exits cleanly.
3. **Discord delivery failure** — after the report delivery step, if the delivery function returns False, call `send_ops_alert` with stage `"Discord Delivery"`.

In all three cases: the error argument is the exception message or a descriptive string — no traceback, no stack frames.

**Demo path:** force each failure mode in turn (empty filter result, broken PDF template, bad webhook URL) and confirm the red embed fires for each. The pipeline should not crash due to the alert itself.

## Acceptance criteria

- [ ] When the health filter returns zero eligible stocks, `send_ops_alert` fires with stage `"Filter: zero eligible stocks"`
- [ ] When PDF generation raises an exception, `send_ops_alert` fires with stage `"PDF Generation"` and the exception message (not a traceback)
- [ ] When Discord report delivery returns False, `send_ops_alert` fires with stage `"Discord Delivery"`
- [ ] A failure in `send_ops_alert` itself does not prevent the pipeline from completing its remaining steps or exiting with the expected return value
- [ ] Per-stock degradation (individual MoS failures, individual sentiment skips) does not trigger any alert — those remain silent
- [ ] All existing tests continue to pass

## Blocking dependencies

- Blocked by #01 (ops alert module must exist before instrumentation)
