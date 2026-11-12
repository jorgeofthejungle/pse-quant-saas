# StockPilot PH — PSE Quant SaaS (v2 Rebuild)
### Institutional-Grade Philippine Investment Research Platform & Hands-On System Design Workbench

[![Backend Tests](https://img.shields.io/badge/Backend%20Tests-275%2F275%20Passing-brightgreen?style=flat-square)](https://github.com/jorgeofthejungle/pse-quant-saas)
[![Next.js 16](https://img.shields.io/badge/Next.js-16.4.5%20Turbopack-black?style=flat-square&logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI%200.115+-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python)](https://python.org/)
[![SQLite FTS5](https://img.shields.io/badge/Search-SQLite%20FTS5%20BM25-003B57?style=flat-square&logo=sqlite)](https://www.sqlite.org/fts5.html)
[![System Design](https://img.shields.io/badge/System%20Design%20Labs-18%20Completed-blueviolet?style=flat-square)](#-the-system-design-workbench-18-labs)

**StockPilot PH** is a full-stack, institutional-grade quantitative investment research platform engineered specifically for the **Philippine Stock Exchange (PSE)**. It combines deterministic multi-factor equity scoring, intrinsic valuation modeling (DDM, DCF, EPS-PE), automated Margin of Safety screening, and real-time event streaming—all serving as a **live System Design Workbench** showcasing high-throughput, fault-tolerant distributed architecture.

---

## 🏛️ System Architecture Overview

StockPilot PH is strictly built around a **4-Layer Decoupled Architecture** governed by formal contracts codified in `docs/architecture/GUARDRAILS.md`:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: PRESENTATION TIER (Next.js 16 + React 19 + Tailwind CSS)               │
│  - Screener, Executive Dashboard, Fact Cards, Watchlists, SSE Live Subscribers   │
│  - Strict Invariant: Zero quantitative math or valuation modeling in UI          │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ HTTP / JSON / SSE (Traced via X-Correlation-ID)
┌────────────────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 2: API GATEWAY & INGRESS RUNTIME (FastAPI + Asynchronous ASGI)             │
│  - TracingMiddleware (ContextVar propagation, p50/p95/p99 latency tracking)      │
│  - DynamicEdgeCacheMiddleware (Multi-region POPs, SHA-256 ETag, 304 revalidation)│
│  - FeatureFlagEngine (Deterministic canary rollouts, multi-tier targeting, kill)  │
│  - ChaosMiddleware (Controlled latency injection, 503 drops, <1ms kill-switch)   │
│  - TokenBucket Rate Limiting (RFC 6585 429 headers, Tiered Client Quotas)        │
│  - Webhook Ingestion & Fast-ACK Idempotency (HMAC SHA-256, atomic deduplication) │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
┌────────────────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 3: CORE VALUATION, SEARCH & STREAMING ENGINES                             │
│  - 3-Layer Fundamental Scoring (Health, Improvement, Persistence)                │
│  - Intrinsic Value & Margin of Safety Blend (DDM, DCF, EPS-PE with risk premia)  │
│  - Full-Text Search Engine (FTS5 + Asymmetric Okapi BM25 Ranking)                │
│  - Real-Time StreamHub (W3C Server-Sent Events with keep-alive pings)            │
│  - WebSocketSwarmManager (Bi-directional quote streaming, drop-oldest queue)      │
│  - Distributed Leased Worker Swarm (SKIP LOCKED queue, heartbeat lease renewal)  │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
┌────────────────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 4: PERSISTENCE, REPLICAS & DISASTER RECOVERY                              │
│  - DatabasePoolManager (Dual-engine Reader Replica / Writer connection routing)   │
│  - Zero-Downtime Expand-Contract Database Migration Framework                    │
│  - Disaster Recovery Engine (Online hot backup, streaming gzip, SHA-256 hash)    │
│  - CacheEngine L1 (Single-flight mutex locks against stampede / dog-piling)      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧪 The System Design Workbench (18 Labs)

Every tier of the platform has been systematically built, stress-tested, and verified through **18 progressive System Design Labs**, with **275 / 275 automated backend tests passing**:

| Lab | Architectural Component | Core Pattern / Algorithm | Verification Metric |
| :---: | :--- | :--- | :--- |
| **01** | **Golden Dataset Math Lock** | Deterministic Ground Truth Fixtures | Zero-drift floating-point valuation lock |
| **02** | **Clean Architecture UI Decoupling** | Fallback-Safe Presentation Contracts | AST code scan & 24/24 SSG offline builds |
| **03** | **Asynchronous Payment Webhooks** | Fast-ACK & Atomic Idempotency Ledger | PayMongo HMAC SHA-256 idempotency |
| **04** | **Multi-Tier Token Bucket Limiter** | TokenBucket with RFC 6585 Headers | Thread-safe burst handling & client tiers |
| **05** | **Scraper Resiliency & DLQ** | Circuit Breaker (Hystrix) + Full Jitter | Auto-trip to OPEN & poison-pill isolation |
| **06** | **Multi-Tier Cache-Aside** | Single-Flight Mutex Locking | Zero cache stampedes across 30 threads |
| **07** | **Event-Driven Alert Fanout** | Decoupled Pub-Sub & Cooldown Ledger | 4-hour anti-fatigue deduplication |
| **08** | **Read Replicas & Connection Pools** | Dual-Engine Writer / Reader Routing | Pool queue telemetry & failover safety |
| **09** | **Distributed Task Queue** | `SKIP LOCKED` Worker Lease Swarm | Heartbeat renewers & zombie task salvage |
| **10** | **Distributed Tracing & Telemetry** | Ambient `ContextVar` + Sliding Reservoir | End-to-end `X-Correlation-ID` & p95 latency |
| **11** | **Real-Time SSE Streaming** | W3C EventSource Hub + Drop-Oldest | Sub-50ms push & 5s proxy keep-alive pings |
| **12** | **Zero-Downtime DB Migrations** | 5-Phase Expand-Contract State Machine | 100% Mathematical Parity Gate before drop |
| **13** | **Full-Text Search Engine (FTS5)** | Asymmetric Okapi BM25 Ranking | Sub-5ms prefix search & exact ticker pin |
| **14** | **Disaster Recovery & Snapshots** | Hot SQLite Online Backup + Gzip SHA-256 | RTO < 2s atomic restore & bit-rot audit |
| **15** | **Chaos Engineering & Fault Injection** | Controlled Latency & Error Injection | Sub-1ms Emergency Kill-Switch & 503 drops |
| **16** | **Feature Flags & Canary Delivery** | Deterministic Sticky Hashing & Canary | Monotonic rollouts (0-100%) & audit ledger |
| **17** | **WebSocket Market Data Swarm** | Bi-Directional Pub-Sub + Drop-Oldest | Selective ticker fan-out & backpressure |
| **18** | **Multi-Region Ingress & Edge Cache** | RFC 7234 Cache Policies + SHA-256 ETag | Sub-ms 304 revalidation & surrogate purge |

---

## 📈 Quantitative Valuation & Research Methodology

### 1. Deterministic 3-Layer Fundamental Scoring
StockPilot PH evaluates every publicly listed Philippine company using a sector-aware 0–100 fundamental scoring algorithm. **Zero randomness, zero AI hallucinations—strictly deterministic**:

* **Health (30–35%)**: Balance sheet strength, ROE, net margins, debt-to-equity, and free cash flow stability (calibrated to PSE market percentiles). Tailored by sector (e.g. banks use regulatory capital limits; REITs use FFO yields).
* **Improvement (25–30%)**: Recency-weighted fundamental trajectory over 3 years (50% newest, 30% prior, 20% oldest).
* **Persistence (35–45%)**: Consistency of growth, direction stability, and multi-year positive streak bonuses.

### 2. Tri-Model Intrinsic Valuation & Margin of Safety
Calculates conservative intrinsic business values using three risk-adjusted valuation models:
* **Dividend Discount Model (DDM)**: Terminal Gordon Growth Model for dividend champions.
* **Discounted Cash Flow (DCF)**: 10-year free cash flow projections with terminal multiples.
* **Normalized EPS × Fair PE Multiple**: P/E multiple model adjusted for sector benchmarks.

**Discount Rate Structure**: Risk-free rate (PH 10Y T-Bond ~6.5%) + Damodaran Equity Risk Premium (5.0%) + Company Size Premium (0–5%) + Sector Risk Premium (0–2%).

$$\text{Margin of Safety (MoS)} = \frac{\text{Intrinsic Value} - \text{Market Price}}{\text{Intrinsic Value}} \times 100\%$$

---

## 🚀 Quickstart Guide

### Prerequisites
* **Python 3.12+**
* **Node.js 20+** / npm 10+
* **SQLite 3.35+** (built into Python 3.12 with FTS5 support)

### 1. Backend Setup (FastAPI Gateway & Quant Engine)
```bash
# Clone the repository
git clone https://github.com/jorgeofthejungle/pse-quant-saas.git
cd pse-quant-saas/backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run all 275 automated tests
python -m pytest tests/ --ignore=tests/test_e2e_live.py -v

# Start development server
uvicorn pse_quant.api.main:app --reload --port 8000
```
API Documentation will be live at: `http://127.0.0.1:8000/docs`

### 2. Frontend Setup (Next.js 16 Presentation Tier)
```bash
cd ../frontend

# Install dependencies
npm install

# Run production build (verifies 24/24 static & dynamic routes)
npm run build

# Start production server
npm start
# or development server: npm run dev
```
Investor Dashboard will be live at: `http://localhost:3000`

---

## 🔌 Core API Reference

### Public & Discovery Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/stocks` | List top-ranked equities filtered by portfolio, sector, min score, or min MoS. |
| `GET` | `/api/v1/stocks/{ticker}` | Deep-dive stock profile with valuation breakdown and 5-year financials. |
| `GET` | `/api/v1/stocks/bargains` | Screen stocks trading at high positive Margin of Safety discounts. |
| `GET` | `/api/v1/search?q={query}` | Sub-5ms FTS5 typeahead search across tickers, names, and colloquial aliases. |

### Real-Time Server-Sent Events (SSE)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/stream/tasks/{id}` | Real-time task execution milestones and progress bar updates. |
| `GET` | `/api/v1/stream/alerts` | Live portfolio Margin of Safety breach and price limit notifications. |
| `GET` | `/api/v1/stream/market` | Real-time market tick and price movement push feed. |

### Admin & Operations Endpoints (Protected via `X-Admin-Key`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/admin/snapshots/create` | Trigger hot point-in-time database backup (Gzip + SHA-256). |
| `POST` | `/api/v1/admin/snapshots/{id}/verify` | Execute cryptographic SHA-256 and `PRAGMA integrity_check` audit. |
| `POST` | `/api/v1/admin/snapshots/{id}/restore` | Atomic live database restoration with automated safety fallback. |
| `GET` | `/api/v1/admin/migrations` | Inspect status of active 5-phase Expand-Contract schema migrations. |
| `POST` | `/api/v1/admin/migrations/{name}/advance`| Advance migration phase with 100% mathematical parity verification. |
| `GET` | `/api/v1/admin/telemetry/live` | Unified live pulse aggregating latency, DB pools, cache ratios, and queue depth. |
| `POST` | `/api/v1/admin/search/rebuild` | Drop and rebuild SQLite FTS5 inverted search index. |

---

## 🛡️ Architecture & Integrity Documentation

For detailed architectural specifications, formulas, and data contracts, refer to the living documentation suite:
* **[CONTRACTS.md](docs/architecture/CONTRACTS.md)** — Comprehensive specifications for all 16 architectural contracts, schemas, and mathematical bounds.
* **[SYSTEM_MAP.md](docs/architecture/SYSTEM_MAP.md)** — Detailed Mermaid.js topology diagrams, data flows, and sequence charts for Levels 1 through 14.
* **[GUARDRAILS.md](docs/architecture/GUARDRAILS.md)** — Core architectural boundaries and mandatory pre-code verification gates.

---

## ⚖️ Disclaimer

StockPilot PH is an automated financial research, quantitative modeling, and educational software system. It does not constitute investment advice, financial planning, or securities endorsement. All intrinsic valuation calculations and Margin of Safety metrics are mathematical references based on historical filings and public market data.

---

**StockPilot PH** • Engineered with precision for Philippine Equities.
