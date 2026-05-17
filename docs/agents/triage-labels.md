# Triage Labels

Five canonical labels drive the triage state machine for this repo.

| Role | Label string | Meaning |
|------|-------------|---------|
| Needs evaluation | `needs-triage` | Maintainer must assess before any action |
| Waiting on reporter | `needs-info` | Blocked on clarification from the issue author |
| AFK-ready | `ready-for-agent` | Fully specified; an agent can execute with no human context |
| Human required | `ready-for-human` | Requires human judgment or privileged action |
| Won't fix | `wontfix` | Will not be actioned; close after applying |

## Rules

- An issue carries exactly one of these labels at any time.
- `ready-for-agent` issues must have: clear acceptance criteria, no unresolved dependencies, and all context an agent needs to run cold.
- `ready-for-human` issues may have open questions or require product judgment.
- Removing `needs-triage` without applying another label is an error.
