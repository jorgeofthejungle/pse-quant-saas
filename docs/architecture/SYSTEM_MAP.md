# PSE Quant SaaS — System Map (C4 Architecture)

## Level 1: System Context
The high-level relationship between the investor, the StockPilot PH SaaS system, and external financial data sources.

```mermaid
C4Context
    title System Context Diagram - PSE Quant SaaS (StockPilot PH)
    Person(user, "Retail / Seasoned Investor", "Reviews vetted investment picks, inspects audited Fact Cards, audits tickers, and downloads A4 PDF dossiers.")
    System(saas, "PSE Quant SaaS (StockPilot PH)", "Ingests audited PSE financial statements, computes 3-layer fundamental scores and 3-model intrinsic valuations, and serves Done-For-You research dossiers.")
    System_Ext(pse_edge, "PSE Edge (edge.pse.com.ph)", "Official source of listed company disclosures, audited annual/quarterly financial reports, and live quotes.")

    Rel(user, saas, "Configures goal filters, requests ticker hype checks, and downloads dossiers", "HTTPS / Next.js Web")
    Rel(saas, pse_edge, "Ingests audited statements, quotes, and cash dividend history", "HTTPS / Scraper ETL")
```

---

## Level 2: Container Diagram (Boundary Isolation)
Enforces strict decoupling between presentation, transport, computation, and storage.

```mermaid
C4Container
    title Container Diagram - Boundary Isolation
    Container(ui, "Dashboard & Dossier UI", "Next.js 16 / React / Tailwind", "Renders Done-For-You Fact Cards, PWYC checkout, screener, and watchlist. Imports NO calculation math.")
    Container(api, "API Gateway / Routes", "FastAPI / SlowAPI Rate Limiter", "Validates payloads, enforces rate limits, handles PWYC receipts, and orchestrates report generation.")
    Container(quant, "Quant, Valuation & Fact Engine", "Pure Python (Core)", "Deterministic 3-layer scoring, 3-model valuation (DDM, DCF, EPS-PE), margin of safety, and Taglish Fact Card compiler.")
    ContainerDb(db, "Persistence Layer", "SQLite / SQLAlchemy (pse_local.db)", "Stores company directory, multi-year audited financial statements, historical prices, and computed scores.")

    Rel(ui, api, "Fetches investment menus, Fact Cards, and PDF downloads", "JSON / HTTPS")
    Rel(api, quant, "Invokes pure scoring, valuation, and fact compilation functions")
    Rel(quant, api, "Returns computed Fact Cards, Seasoned Numbers, and valuation metrics")
    Rel(api, db, "Reads & writes company financials, quotes, and scores", "SQLAlchemy ORM")
```

---

## Level 3: Asynchronous Payment Webhook & Idempotency Sequence

Demonstrates the sub-50ms Fast-ACK boundary and asynchronous background fulfillment worker.

```mermaid
sequenceDiagram
    autonumber
    actor Investor as Paying Investor
    participant Gateway as PayMongo / Maya Gateway
    participant Route as FastAPI Webhook Handler (/payments/webhook)
    participant PaymentSvc as PaymentService
    participant DB as SQLite / PostgreSQL (PaymentEvents)
    participant Worker as BackgroundTasks Fulfillment Worker
    participant Resend as Resend SMTP / ReportLab PDF

    Investor->>Gateway: Submits GCash / Card payment (₱49+)
    Gateway->>Route: POST /api/v1/payments/webhook (Payload + HMAC Header)
    Note over Route,PaymentSvc: Cryptographic Guard (<5ms)
    Route->>PaymentSvc: verify_webhook_signature(raw_body, signature_header)
    alt Invalid HMAC Signature
        PaymentSvc-->>Route: False
        Route-->>Gateway: HTTP 401 Unauthorized (Blocked)
    else Valid HMAC Signature
        PaymentSvc-->>Route: True
        Route->>PaymentSvc: record_and_claim_event(provider, event_id, amount, email)
        PaymentSvc->>DB: SELECT * FROM payment_events WHERE event_id = ?
        alt Duplicate Delivery (Gateway Retry)
            DB-->>PaymentSvc: Existing Event Found (Status: processed/pending)
            PaymentSvc-->>Route: (event, claimed=False)
            Route-->>Gateway: HTTP 200 {"status": "ok", "idempotent": true} (<15ms)
        else First Arrival (New Event)
            PaymentSvc->>DB: INSERT INTO payment_events (status="pending")
            PaymentSvc-->>Route: (event, claimed=True)
            Route->>Worker: Schedule process_payment_fulfillment(provider, event_id)
            Route-->>Gateway: HTTP 200 {"status": "received", "idempotent": false} (<25ms)
            
            Note over Worker,Resend: Asynchronous Decoupled Worker
            Worker->>DB: Upgrade User tier="paid" & Subscription active
            Worker->>Resend: Generate ReportLab PDF & Dispatch Email
            Worker->>DB: UPDATE payment_events SET status="processed"
        end
    end
```

---

## Level 4: Multi-Tier Token Bucket Rate Limiting Architecture

Eliminates the fixed-window boundary burst problem by tracking continuous token replenishment $\Delta t \times r$ bounded by burst capacity $C$.

```mermaid
flowchart TD
    Req([Inbound HTTP Request]) --> ExemptCheck{Is Exempt Path?<br/>/health, /docs}
    ExemptCheck -- Yes --> PassToApp([Route Handler])
    ExemptCheck -- No --> Fingerprint[Resolve Fingerprint & Tier]
    
    Fingerprint --> AuthBranch{Identity Type?}
    AuthBranch -- "X-Admin-Key" --> TierAdmin[Tier: ADMIN<br/>Burst: 1000, 50 t/s]
    AuthBranch -- "Bearer JWT (role=admin)" --> TierAdmin
    AuthBranch -- "Bearer JWT (tier=paid)" --> TierPaid[Tier: PAID<br/>Burst: 300, 5 t/s]
    AuthBranch -- "Bearer JWT (tier=free)" --> TierFree[Tier: FREE<br/>Burst: 60, 1 t/s]
    AuthBranch -- "Unauthenticated IP" --> TierAnon[Tier: ANONYMOUS<br/>Burst: 20, 0.5 t/s]

    TierAdmin --> FetchBucket[Fetch or Create TokenBucket]
    TierPaid --> FetchBucket
    TierFree --> FetchBucket
    TierAnon --> FetchBucket

    FetchBucket --> MathStep["Calculate Refill:<br/>tokens = min(C, tokens + Δt * r)"]
    MathStep --> TokenCheck{tokens >= 1.0?}

    TokenCheck -- "Yes (Tokens Available)" --> ConsumeToken["tokens -= 1.0<br/>Calculate X-RateLimit headers"]
    ConsumeToken --> InjectHeaders[Inject X-RateLimit Headers]
    InjectHeaders --> PassToApp

    TokenCheck -- "No (Depleted)" --> Throttled["Calculate Retry-After:<br/>(1.0 - tokens) / r"]
    Throttled --> Reject[Return HTTP 429 Too Many Requests<br/>With Retry-After & X-RateLimit headers]
```


---

## Level 5: Scraper ETL Circuit Breaker State Machine & Dead-Letter Flow

Protects the quant engine from cascading halts caused by upstream PSE Edge timeouts and isolates malformed corporate filings into durable dead-letter storage.

```mermaid
stateDiagram-v2
    [*] --> CLOSED

    state CLOSED {
        [*] --> ExecutingRequests
        ExecutingRequests --> Success: HTTP 200
        Success --> ExecutingRequests: Reset failure count
        ExecutingRequests --> Failure: 5xx / Connection Timeout
        Failure --> CheckThreshold: failures += 1
        CheckThreshold --> ExecutingRequests: failures < 5
    }

    CLOSED --> OPEN: Consecutive failures >= 5
    
    state OPEN {
        [*] --> FastFailImmediate: <1ms Return None
        FastFailImmediate --> CooldownTimer: Wait 30 seconds
    }

    OPEN --> HALF_OPEN: Cooldown Expired (30s)

    state HALF_OPEN {
        [*] --> SendCanaryProbe: Single test request
        SendCanaryProbe --> CanarySuccess: HTTP 200
        SendCanaryProbe --> CanaryFail: 5xx / Timeout
    }

    HALF_OPEN --> CLOSED: CanarySuccess (Healthy again)
    HALF_OPEN --> OPEN: CanaryFail (Outage persists)
```

```mermaid
flowchart TD
    ETL[Batch Scraper Loop: 278 Stocks] --> FetchStock[Fetch Stock Quote / Filing]
    FetchStock --> CBCheck{Circuit Breaker<br/>State?}
    CBCheck -- OPEN --> SkipFast[Fail-Fast & Pause Batch]
    CBCheck -- CLOSED / HALF-OPEN --> EdgeReq[Execute Request to PSE Edge]
    
    EdgeReq --> Outcome{Response Valid?}
    Outcome -- "Valid (200)" --> UpsertDB[(Upsert Stock/Financials)]
    Outcome -- "Malformed / Corrupt / 5xx" --> DLQ[DeadLetterService.record_dead_letter]
    
    DLQ --> DB_DLQ[(scraper_dead_letters Table)]
    DB_DLQ --> NextStock[Continue to Next Stock]
    UpsertDB --> NextStock
    NextStock --> ETL
```


---

## Level 6: Cache-Aside Architecture & Single-Flight Mutex Sequence

Eliminates redundant database queries and quant recalculations on read endpoints while guaranteeing single-flight origin fetching under concurrent cache stampedes.

```mermaid
sequenceDiagram
    autonumber
    actor InvestorA as Investor Client A
    actor InvestorB as Investor Client B
    participant API as FastAPI Gateway
    participant Cache as CacheEngine (L1 Memory)
    participant Lock as Key-Specific Mutex Lock
    participant DB as SQLite DB & Quant Engine

    InvestorA->>API: GET /api/v1/stocks/AREIT
    InvestorB->>API: GET /api/v1/stocks/AREIT (Simultaneous)
    
    API->>Cache: get("stock:profile:AREIT")
    alt Cache Hit (Common Path)
        Cache-->>API: Return Cached Profile (<0.1ms)
        API-->>InvestorA: HTTP 200 (Instant Response)
    else Cache Miss (Stampede Prevention)
        Cache-->>API: None (Miss)
        API->>Lock: Acquire Lock("stock:profile:AREIT")
        Note over InvestorA,Lock: Investor A acquires lock; Investor B blocks waiting
        API->>Cache: Double-Check get("stock:profile:AREIT")
        alt Populated by predecessor
            Cache-->>API: Return Value
        else Still Miss
            API->>DB: SELECT * FROM stocks, prices, financials WHERE ticker='AREIT'
            DB-->>API: Raw Statement Rows
            API->>API: enrich_stock_valuation() [Quant Math]
            API->>Cache: set("stock:profile:AREIT", profile, TTL=300s + Jitter)
        end
        Lock-->>API: Release Lock
        Note over InvestorB,Lock: Investor B acquires lock, finds cached entry, exits in <0.1ms
        API-->>InvestorA: HTTP 200
        API-->>InvestorB: HTTP 200
    end
```


---

## Level 7: Event-Driven Alert Fanout & Deduplication Cooldown Sequence

Decouples quant scoring calculation from notification channels via an in-memory Pub-Sub Event Bus and suppresses alert storms through a 4-hour deduplication window.

```mermaid
sequenceDiagram
    autonumber
    participant Scraper as ETL Pipeline / Scraper
    participant Quant as Quant Valuation Engine
    participant Bus as In-Memory EventBus
    participant Fanout as AlertFanoutService
    participant DB as SQLite DB (Watchlist & Notifications)
    participant UI as Member Dashboard (Badge & Alerts)

    Scraper->>Quant: compute_scores_and_rankings()
    Quant->>Bus: publish(QuantValuationEvent("AREIT", price=32.50, MoS=30.6%))
    Bus->>Fanout: handle_quant_valuation(event)
    
    Fanout->>DB: SELECT * FROM watchlists WHERE ticker = 'AREIT'
    DB-->>Fanout: [Investor A: Target 20%, Investor B: Target 35%]
    
    Note over Fanout: Filter: Investor B skipped (30.6% < 35%)
    Note over Fanout: Candidate: Investor A qualified (30.6% >= 20%)
    
    Fanout->>DB: Check Cooldown: SELECT * FROM user_notifications WHERE user=A AND ticker='AREIT' AND created_at >= now - 4h
    alt Within 4-Hour Cooldown Window
        DB-->>Fanout: Existing Alert Found
        Note over Fanout: Suppress Alert: Prevent alert fatigue from price bounce
    else Outside Cooldown Window
        DB-->>Fanout: No Recent Alert
        Fanout->>DB: INSERT INTO user_notifications (user_id=A, ticker='AREIT', type='MOS_BREACH')
        DB-->>UI: Real-time Badge Increment (+1 Unread Alert)
    end
```


---

## Level 8: Database Read Replicas & Connection Pool Tuning Architecture

```mermaid
flowchart TD
    subgraph Clients["Traffic Sources"]
        Investor["Investor Browsing (Screeners, Fact Cards, Rankings)"]
        ETL["Background Scraper & ETL Workers (278 Equities)"]
        Webhook["Payment Webhook Fast-ACK Background Worker"]
        Admin["Admin Manual Overrides & Management"]
    end

    subgraph Router["Session & Routing Layer (pse_quant.db)"]
        ReadDep["FastAPI Dependency: get_read_db / get_read_session()"]
        WriteDep["FastAPI Dependency: get_db / get_write_session()"]
        PoolMgr["DatabasePoolManager (Telemetry & Atomic Query Counters)"]
    end

    subgraph Pools["SQLAlchemy Connection Pools (QueuePool)"]
        ReaderPool["Reader Pool<br/>size: 25 | overflow: 20<br/>timeout: 10s | recycle: 1800s"]
        WriterPool["Writer Pool<br/>size: 15 | overflow: 10<br/>timeout: 10s | recycle: 1800s"]
    end

    subgraph Storage["Database Instances"]
        ReplicaDB[("Read Replica Database<br/>(High-throughput queries)")]
        PrimaryDB[("Primary Database<br/>(ACID Transactions)")]
    end

    Investor -->|"GET /api/v1/stocks"| ReadDep
    ReadDep -->|"record_read()"| PoolMgr
    ReadDep -->|"ReaderSession()"| ReaderPool
    ReaderPool -->|"Read-only queries"| ReplicaDB

    ETL -->|"Batch upserts"| WriteDep
    Webhook -->|"Fulfill subscription"| WriteDep
    Admin -->|"Financial override"| WriteDep

    WriteDep -->|"record_write()"| PoolMgr
    WriteDep -->|"WriterSession()"| WriterPool
    WriterPool -->|"ACID Commit / Rollback"| PrimaryDB

    PrimaryDB -.->|"Replication Stream"| ReplicaDB

    PoolMgr -.->|"Telemetry (/api/v1/admin/db/pool-metrics)"| Admin
```

### Connection Pool Lifecycle & Contention Isolation Flow

```mermaid
sequenceDiagram
    autonumber
    participant UI as Public Screener (Next.js)
    participant API as FastAPI Gateway
    participant ReadMgr as get_read_session()
    participant WriteMgr as get_write_session()
    participant Worker as Background Scraper ETL
    participant ReaderPool as Reader Pool (Size: 25)
    participant WriterPool as Writer Pool (Size: 15)
    participant DB as Database Cluster

    par Concurrent Scraper Batch Write & Screener Reads
        Worker->>WriteMgr: Start financial batch upsert
        WriteMgr->>WriterPool: Checkout connection
        WriterPool->>DB: BEGIN TRANSACTION (Exclusive table write)
        
        UI->>API: GET /api/v1/stocks (Investor request)
        API->>ReadMgr: Route to read session
        ReadMgr->>ReaderPool: Checkout reader connection
        ReaderPool->>DB: Execute SELECT query on Replica
        DB-->>ReaderPool: Return 50 ranked stocks
        ReaderPool-->>API: Stream JSON response (Sub-50ms)
        API-->>UI: Render screener table
        
        Note over ReadMgr,ReaderPool: Zero pool starvation: Read queries bypass Writer Pool
        
        DB-->>WriterPool: COMMIT TRANSACTION
        WriterPool-->>Worker: Batch upsert complete
    end
```
