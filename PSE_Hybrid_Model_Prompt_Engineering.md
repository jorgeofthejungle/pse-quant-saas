# PROMPT ENGINEERING: Hybrid Deterministic Model — Alternative Solution to PSE Edge Data Limitation

**Document Purpose:** This prompt engineering directive instructs Claude Code on how to proceed when PSE Edge data is insufficient to satisfy the deterministic equation. This is the approved alternative solution agreed upon in session.

---

## CONTEXT & PROBLEM STATEMENT

The deterministic financial model requires specific input variables that **PSE Edge alone cannot fully provide**. Rather than halting execution or filling gaps with assumptions, Claude Code is instructed to execute a **Hybrid Sourced-Data Approach** — a structured, objective method that sources missing variables from verified external data points.

---

## CORE DIRECTIVE TO CLAUDE CODE

> **When PSE Edge data is insufficient, do NOT assume. Do NOT estimate without a source. Instead, execute the Variable Verification Protocol below.**

---

## VARIABLE VERIFICATION PROTOCOL

### Step 1 — Scrape & Extract from PSE Edge
- Pull all available financial data from PSE Edge for the target company
- Pull all official disclosures from the Philippine Stock Exchange (PSE) portal
- Map extracted values against every required variable in the deterministic equation
- Tag each populated field with: `source`, `date_of_data`, `confidence: HIGH`

### Step 2 — Flag Missing Variables
- Any variable not satisfied by PSE Edge data must be marked: `STATUS: MISSING`
- Do NOT populate missing fields with estimates or defaults
- Generate a **Missing Variables Report** listing each gap explicitly

### Step 3 — Source Resolution (Tiered)
For each missing variable, attempt resolution in strict tier order:

| Tier | Source | Trust Level |
|------|--------|-------------|
| Tier 1 | PSE Edge audited filings / PSE official disclosures | ✅ HARD DATA |
| Tier 2 | Company IR pages, earnings call transcripts, investor presentations, management guidance | ✅ OFFICIAL FORWARD GUIDANCE |
| Tier 3 | BSP (Bangko Sentral ng Pilipinas), PSA (Philippine Statistics Authority), sector regulators (ERC, DICT, etc.), Bloomberg/Reuters | ✅ VERIFIED EXTERNAL |
| Tier 4 | Peer company disclosed figures, published industry benchmarks | ⚠️ BENCHMARK — must be explicitly labeled |

- Attempt Tier 2 before Tier 3. Attempt Tier 3 before Tier 4.
- If a variable cannot be sourced from Tier 1–4, it **remains blank**. No exceptions.

### Step 4 — Generate Verification Report
Output a structured report with the following schema for every variable:

```
Variable Name     : [name]
Required For      : [which part of the equation]
Value             : [sourced value OR "BLANK — NOT SOURCED"]
Source            : [exact source name and URL if applicable]
Date of Data      : [date]
Tier              : [1 / 2 / 3 / 4]
Confidence        : [HIGH / MEDIUM / LOW / UNRESOLVED]
Flag              : [none / BENCHMARK / ESTIMATED / MISSING]
```

---

## OBJECTIVITY RULES — NON-NEGOTIABLE

Claude Code must adhere to these rules without exception:

1. **No assumptions.** If a value cannot be traced to a real, citable source, it does not enter the model.
2. **No invented proxies.** Do not substitute a similar-sounding metric for the required variable without explicit approval.
3. **No silent gap-filling.** Every blank must be surfaced in the report — never hidden.
4. **Benchmark data must be labeled.** Tier 4 data is permissible only when flagged visibly as a benchmark, not as a company-specific figure.
5. **Date-stamp everything.** Stale data (beyond agreed lookback window) must be flagged as potentially outdated.
6. **One source per value.** Do not blend multiple sources into a single value without documenting the blending logic explicitly.

---

## OUTPUT BEHAVIOR

After executing the protocol, Claude Code must return:

1. **Populated Variables List** — all values successfully sourced, with citations
2. **Missing Variables Report** — all unresolved gaps, clearly listed
3. **Model Readiness Assessment:**
   - `READY` — all required variables sourced
   - `PARTIAL` — model can run with caveats; list which variables are missing and their impact
   - `BLOCKED` — critical variables unresolved; model cannot run without human decision on how to handle gaps

---

## ESCALATION PROTOCOL

If the result is `PARTIAL` or `BLOCKED`, Claude Code must **stop and surface the gaps** to the human operator for a decision. Claude Code does not proceed autonomously past this point.

The human operator will then decide:
- Accept a Tier 4 benchmark as a temporary substitute (with explicit acknowledgment)
- Source the variable manually and provide it as an override input
- Exclude the variable and redefine the equation scope

---

## SUMMARY PRINCIPLE

> **This model prioritizes truth over completeness. A blank field is more honest than a fabricated one. Claude Code's role is to find, verify, and report — not to fill gaps on its own judgment.**

---

*Prompt Engineering authored from live session discussion. Approved approach for handling PSE Edge data limitations in the deterministic financial model project.*
