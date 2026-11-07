# AI Product Builder Guardrails (`pse-quant-saas`)

## 1. Core Architecture Boundaries (DO NOT BLEND)

- **Layer 1 (UI & Dashboard State):**
  - Scope: React components, Tailwind styling, charts, filter toggles, visual Fact Cards.
  - Invariant: Zero quantitative math or valuation modeling in React components. UI only renders API payloads.

- **Layer 2 (API Gateway & Transport Contracts):**
  - Scope: FastAPI routes, Pydantic schemas, SlowAPI rate limiters, auth guards, PDF response generation.
  - Invariant: Transport and validation only. No direct database mutations inside presentation logic.

- **Layer 3 (Quant, Valuation & Fact Engine):**
  - Scope: 3-Layer Fundamental Scoring (`health`, `improvement`, `persistence`), Intrinsic Valuation (`DDM`, `DCF`, `EPS-PE`), Margin of Safety, and `FactCard` compiler.
  - Invariant: Pure, deterministic functions. No network requests or database sessions inside formula logic.

- **Layer 4 (Data Ingestion & Persistence):**
  - Scope: PSE Edge scraping ETL, SQLite / SQLAlchemy models (`Stock`, `Price`, `Financial`, `Score`), database migrations.
  - Invariant: Immutable historical financial statements and price quotes. Strictly relational referential integrity.

---

## 2. Mandatory Pre-Code Gate

Before writing or modifying any code file for a new feature or refactor:
1. **Visual Data Flow**: Output a Mermaid.js `sequenceDiagram` or `erDiagram` mapping the exact data flow across layers.
2. **Explicit Target Scope**: List the exact file paths you plan to modify (`git diff --stat` target scope).
3. **Verification Plan**: State the exact test command (e.g., `pytest`, `npm run build`) that will prove the change works before committing.

---

## 3. Strict Safety & Blast-Radius Locks

- **NO SILENT MIGRATIONS**: You are STRICTLY FORBIDDEN from modifying database schemas (e.g., SQLAlchemy ORM models in `backend/pse_quant/db/models.py`) or quant valuation formulas during UI styling or component bugfix tasks without an explicit override command.
- **NO DEPENDENCY BLOOM**: Do not install new pip or npm packages without explicit user authorization.
- **ISOLATION & DETERMINISM**: All core financial calculations must remain deterministic and testable via frozen Golden Dataset fixtures.
