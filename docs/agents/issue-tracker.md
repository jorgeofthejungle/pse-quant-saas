# Issue Tracker

Issues for this repo live in **GitHub Issues** at `jorgeofthejungle/pse-quant-saas`.

## CLI tool

Skills use the [`gh` CLI](https://cli.github.com/) for all issue operations.

## Common commands

| Operation | Command |
|-----------|---------|
| Create issue | `gh issue create --title "..." --body "..." --label "..."` |
| List issues | `gh issue list --label "..."` |
| View issue | `gh issue view <number>` |
| Edit labels | `gh issue edit <number> --add-label "..." --remove-label "..."` |
| Close issue | `gh issue close <number>` |

## Conventions

- One issue = one vertical slice of deliverable work.
- Issues reference related issues with `Blocked by #N` in the body.
- AFK issues must be fully self-contained — no human context required to execute.
