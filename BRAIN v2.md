# BRAIN.md — AI Development Governor (v10)

> Superpowers-native, constraint-driven, self-improving system

---

## CORE SYSTEM

This project uses a layered AI workflow:

* **BRAIN.md** → governance, constraints, decision control
* **CLAUDE.md** → project specification (source of truth)
* **LEARN.md** → persistent learning and memory
* **Superpowers** → execution engine (planning, coding, testing, debugging)

---

## ROLE OF SUPERPOWERS

Superpowers is the **primary execution system**.

It is responsible for:

* Brainstorming and clarification
* Planning and task breakdown
* Implementation (via subagents)
* Test-driven development (RED → GREEN → REFACTOR)
* Debugging and validation
* Code review

### HARD RULE

Do NOT duplicate or override Superpowers workflows.

* Do not redefine planning, debugging, or TDD processes
* Do not bypass skill activation
* Do not replace its execution logic

BRAIN.md provides **constraints**, not execution.

---

## ROLE OF BRAIN.md

BRAIN.md is the **governor layer**.

Responsibilities:

* Enforce quality and constraints
* Maintain long-term consistency
* Prevent repeated mistakes
* Ensure root-cause resolution
* Guide decision-making, not execution
* Control system behavior across sessions

---

## PRIORITY ORDER

If conflicts occur, follow this order:

1. CLAUDE.md (source of truth)
2. BRAIN.md constraints
3. LEARN.md lessons
4. Superpowers execution decisions

Resolve conflicts in this hierarchy.

---

## PROJECT INITIALIZATION

If no `CLAUDE.md` exists:

### Step 1 — Use Superpowers

* Run brainstorming
* Refine requirements
* Generate design

---

### Step 2 — Create Core Files

#### CLAUDE.md

* Becomes the source of truth

#### LEARN.md

```md id="init01"
# LEARN.md — Project Learning Log

## PURPOSE
Capture lessons to improve decisions and avoid repeated mistakes.

---

## ENTRIES
(New entries below)
```

---

### Step 3 — Proceed

Follow Superpowers workflow:

clarify → design → plan → execute → test → validate

---

## CLARIFICATION RULE (CRITICAL)

Before implementation:

* Ensure the problem is clearly defined
* Ask questions if ambiguity exists
* Do not proceed based on assumptions

If unclear → clarify first, then act

---

## SCOPE CONTROL

Do not expand scope beyond the defined task.

* Avoid adding features not specified
* Avoid premature optimization
* Stick to current objective unless explicitly expanded

---

## FAILURE HANDLING

If repeated failures occur:

* Stop and reassess assumptions
* Revisit CLAUDE.md for misalignment
* Check LEARN.md for missed lessons
* Simplify the approach before retrying

Do not continue blind iteration.

---

## EXECUTION AWARENESS

Continuously verify that execution aligns with intent.

* Ensure current actions match the original objective
* Detect silent deviations from CLAUDE.md
* Correct course early if misalignment appears

Do not assume correctness — verify alignment during execution.

---

## LEARNING LOOP (PERSISTENT SYSTEM)

This system simulates long-term memory.

---

### WHEN TO LOG

Update LEARN.md when:

* A bug is fixed
* A failure required multiple attempts
* A better approach is discovered
* A key design decision is made
* Ambiguity is resolved

---

### ENTRY FORMAT

```md id="entry01"
## [Title]

**Context:**  
...

**Problem:**  
...

**Root Cause:**  
...

**Solution:**  
...

**Outcome:**  
...

**Rule:**  
...
```

---

### USAGE

Before non-trivial work:

* Check LEARN.md for relevant lessons

During work:

* If stuck → consult LEARN.md

After work:

* Log meaningful insights

---

### RULE

Avoid repeating mistakes documented in LEARN.md.

If repetition occurs:

* Identify why retrieval or application failed
* Improve the rule or clarity of the entry

---

## ROOT-CAUSE ENFORCEMENT (NO BAND-AID FIXES)

Superficial fixes are NOT allowed.

---

### RULE

All issues must be resolved at the **root cause level**.

---

### EXECUTION

Use Superpowers debugging and TDD workflows.

Constraints:

* Do not stop at symptom-level fixes
* Do not silence errors without understanding cause
* Do not apply temporary fixes without resolution

---

### PROHIBITED

* Quick patches that hide issues
* Ignoring failing tests
* Adding logic to mask deeper problems
* “Temporary fixes” without follow-up

---

### REQUIRED

* Identify underlying cause
* Apply structural fixes where possible
* Ensure issue cannot recur under same conditions

---

### VALIDATION

A fix is complete only if:

* Root cause is resolved
* Behavior is correct under expected conditions
* Tests confirm correctness

---

### LEARNING REQUIREMENT

Log every meaningful root-cause fix in LEARN.md.

---

## SUPERPOWERS INTERACTION RULES

---

### 1. TRUST THE WORKFLOW

When a Superpowers skill activates:

* Follow it
* Do not bypass or shortcut it

---

### 2. VALIDATE OUTPUT

After execution:

Check:

* Strict alignment with CLAUDE.md (source of truth)
* Compliance with system constraints
* No repetition of known mistakes

If issues exist:

* Fix immediately
* Log if relevant

---

### 3. HANDLE FAST COMMANDS

For short prompts (e.g., “fix this”, “optimize this”):

* Use minimal Superpowers workflow
* Keep scope localized
* Do not assume missing context
* Do not skip validation or testing

---

### 4. PREVENT DRIFT

Superpowers optimizes for correct and efficient execution.

BRAIN.md ensures:

* consistency
* stability
* long-term quality

---

## DECISION GUARDRAILS

* Prefer simple solutions (YAGNI)
* Avoid unnecessary complexity
* Protect working systems
* Validate assumptions before acting

---

## TESTING PRINCIPLE

Tests are validation tools, not absolute truth.

* Passing tests do not guarantee correctness
* If behavior is wrong, investigate both code and tests
* Update tests when necessary

---

## FILE RULES

* Keep files clear and manageable
* Avoid unnecessary refactoring
* Maintain readability and structure

---

## SECURITY RULES

* No hardcoded secrets
* Use `.env` for sensitive data
* Validate all inputs
* Use safe and parameterized operations

---

## REPORTING

Report only:

* Milestones
* Critical issues
* Key learnings (if relevant)

---

## PROACTIVE BEHAVIOR

After major steps:

* Suggest improvements
* Identify risks
* Detect missing constraints

---

## CORE PRINCIPLE

* Superpowers executes
* BRAIN.md governs
* LEARN.md improves

---

## SYSTEM LOOP

Clarify → Plan → Execute → Test → Validate → Fix Root Cause → Learn → Improve

---
