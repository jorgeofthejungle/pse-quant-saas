# Domain Docs

## Layout — single-context

This repo uses a single global context:

| File / directory | Purpose |
|-----------------|---------|
| `CONTEXT.md` (repo root) | Domain language, key concepts, bounded contexts |
| `docs/adr/` | Architecture Decision Records |

Neither exists yet. Create `CONTEXT.md` at the repo root when you're ready to document domain language. Create `docs/adr/0001-*.md` for the first architectural decision.

## How skills use these files

- **`improve-codebase-architecture`** — reads `CONTEXT.md` to understand domain boundaries before suggesting refactors.
- **`diagnose`** — reads `CONTEXT.md` for domain terminology when naming the problem.
- **`tdd`** — reads `CONTEXT.md` to align test names with domain language.
- **`grill-with-docs`** — reads both `CONTEXT.md` and `docs/adr/` to challenge plans against existing decisions.

## ADR format

Preferred format for `docs/adr/NNNN-short-title.md`:

```
# NNNN. Short title

**Date:** YYYY-MM-DD
**Status:** Accepted | Superseded by #NNNN | Deprecated

## Context
## Decision
## Consequences
```
