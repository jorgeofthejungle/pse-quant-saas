---
label: ready-for-human
type: HITL
---

## Overview

The daily scheduler job contains multiple `except Exception` blocks that currently only `print()`. Audit each one to determine which represent pipeline-killing failures (warranting an ops alert) versus expected degradation that should stay silent.

This is an exploratory slice requiring human judgment: the boundary between "fatal" and "degraded-but-acceptable" is a product decision, not an engineering one. The output is a list of blocks to instrument (to be implemented as a follow-up AFK slice), not code changes.

**Questions to answer per exception block:**
- Does this failure mean the daily output (rankings, PDF, Discord delivery) is missing or materially wrong?
- Is this something the operator needs to act on before the next scheduled run?
- Or is it a non-fatal degradation that the pipeline recovers from automatically?

**Demo path:** read through `scheduler_jobs/daily_jobs.py`, annotate each `except Exception` block with a proposed classification (alert / silent), and post the annotated list as a comment on this issue for review.

## Acceptance criteria

- [ ] Every `except Exception` block in the daily jobs module is reviewed
- [ ] Each block is classified as: (a) should fire `send_ops_alert` with a proposed stage name, or (b) should remain silent with a brief rationale
- [ ] The classification list is posted as an issue comment for operator sign-off
- [ ] A follow-up AFK issue is created to implement any approved alert instrumentations

## Blocking dependencies

- Blocked by #01 (ops alert module must be available for the follow-up implementation slice)
