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


---

## Level 9: Distributed Background Task Queue & Leased Worker Architecture

```mermaid
flowchart TD
    subgraph ClientLayer["Clients & API Gateway"]
        AdminReq["Admin Scraper / Valuation Trigger"]
        UserReq["Customer PDF Factsheet Request"]
        CronTrigger["Automated Weekly Digest Dispatch"]
        TaskRoute["FastAPI Task Router<br/>POST /api/v1/tasks/enqueue<br/>(HTTP 202 Fast-ACK)"]
    end

    subgraph QueueEngine["Distributed Queue Engine (pse_quant.tasks)"]
        QueueSvc["TaskQueueService<br/>- enqueue()<br/>- get_status()<br/>- cancel()"]
        Registry["TaskRegistry<br/>- etl.sync_all<br/>- etl.scrape_quotes<br/>- etl.recompute_scores<br/>- reports.generate_pdf<br/>- email.dispatch_digest"]
    end

    subgraph LedgerStorage["Relational Ledger (PostgreSQL / SQLite)"]
        TaskLedger[("background_tasks (TaskRecord)<br/>- id: task_xyz<br/>- status: PENDING / RUNNING / COMPLETED / FAILED<br/>- priority: 1-10<br/>- worker_id: worker_1<br/>- lease_expires_at: timestamp<br/>- attempts: 1 / 3")]
    end

    subgraph Swarm["Autonomous Leased Worker Swarm"]
        Worker1["TaskWorker 1<br/>- FOR UPDATE SKIP LOCKED<br/>- Heartbeat Daemon (15s)<br/>- Execute Handler"]
        Worker2["TaskWorker 2<br/>- FOR UPDATE SKIP LOCKED<br/>- Heartbeat Daemon (15s)<br/>- Execute Handler"]
        ZombieDetector["Zombie Recovery Sweeper<br/>(reclaims dead worker leases)"]
    end

    AdminReq -->|"Trigger Sync"| TaskRoute
    UserReq -->|"Request PDF"| TaskRoute
    CronTrigger -->|"Weekly Digest"| TaskRoute

    TaskRoute -->|"enqueue()"| QueueSvc
    QueueSvc -->|"INSERT status='pending'"| TaskLedger
    TaskRoute -->|"202 Accepted {task_id}"| UserReq

    Worker1 -->|"1. Atomic Lease Claim"| TaskLedger
    Worker2 -->|"1. Atomic Lease Claim"| TaskLedger
    Worker1 -->|"2. Invoke registered task"| Registry
    Worker2 -->|"2. Invoke registered task"| Registry
    Worker1 -.->|"3. Periodic Heartbeat"| TaskLedger
    Worker2 -.->|"3. Periodic Heartbeat"| TaskLedger
    Worker1 -->|"4. Mark COMPLETED / FAILED"| TaskLedger
    Worker2 -->|"4. Mark COMPLETED / FAILED"| TaskLedger

    ZombieDetector -->|"Salvage expired leases"| TaskLedger
```

### Leased Worker Lifecycle, Heartbeat & Zombie Salvage Sequence

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client / Admin
    participant Gateway as FastAPI (/api/v1/tasks)
    participant Ledger as DB Ledger (background_tasks)
    participant Worker1 as Worker 1 (Crashed)
    participant Worker2 as Worker 2 (Healthy)
    participant Handler as Task Handler

    Client->>Gateway: POST /tasks/enqueue {task_name: 'reports.generate_pdf', priority: 8}
    Gateway->>Ledger: INSERT status='pending', priority=8
    Gateway-->>Client: 202 Accepted {task_id: 'task_889'}

    Worker1->>Ledger: SELECT FOR UPDATE: Claim highest priority pending
    Ledger-->>Worker1: Lease granted (status='running', worker='w1', lease_expires_at=now+30s)
    
    Worker1->>Handler: Start PDF generation
    Note over Worker1: Worker 1 crashes abruptly (OOM / Pod reboot)
    Note over Ledger: 30 seconds pass: lease_expires_at < now (Zombie detected)

    Worker2->>Ledger: SELECT FOR UPDATE: Detect expired lease
    Ledger-->>Worker2: Zombie lease salvaged (worker='w2', attempts=2, lease_expires_at=now+30s)
    
    par Active Heartbeat & Task Execution
        Worker2->>Handler: Execute PDF generation
        loop Every 15 seconds
            Worker2->>Ledger: Heartbeat: Renew lease_expires_at = now + 30s
        end
        Handler-->>Worker2: PDF Generated successfully
    end

    Worker2->>Ledger: UPDATE status='completed', result_json={'pdf_path': '...'}
    
    Client->>Gateway: GET /tasks/task_889
    Gateway->>Ledger: SELECT status, result_json FROM background_tasks
    Ledger-->>Gateway: status='completed', result_json
    Gateway-->>Client: 200 OK {status: 'completed', result: {...}}
```


---

## Level 10: Distributed Tracing, Correlation IDs & Latency Observability Architecture

```mermaid
flowchart TD
    subgraph Client["Next.js Presentation Tier"]
        UI["React Screener / Fact Card Component"]
        TracedFetch["lib/api.ts (tracedFetch)<br/>Injects X-Correlation-ID: corr_fe_..."]
    end

    subgraph Ingress["FastAPI Gateway & Tracing Middleware"]
        TracingMW["TracingMiddleware<br/>1. Ingests or generates correlation_id<br/>2. Starts time.perf_counter()<br/>3. Injects X-Correlation-ID & X-Response-Time-Ms"]
        CtxVar["ContextVar ambient storage<br/>(correlation_id_ctx, trace_metadata_ctx)"]
    end

    subgraph ObservabilityCore["Observability & Structured Logging Engine"]
        Formatter["StructuredJsonFormatter<br/>{timestamp, level, correlation_id, path, duration_ms}"]
        Tracker["LatencyTracker (Circular Reservoir)<br/>Calculates p50, p95, p99 & recent traces"]
        LogSink[("Structured Log Sink<br/>(Console / Loki / Datadog)")]
    end

    subgraph BackendTier["Internal Services & Persistence"]
        DBPool["Dual Engine Pool (Reader / Writer)"]
        TaskQueue["TaskQueueService (attaches _correlation_id)"]
        Worker["TaskWorker (restores correlation_id in background)"]
    end

    subgraph TelemetryEndpoints["Observability API"]
        AdminAPI["GET /api/v1/admin/telemetry/latency<br/>GET /api/v1/admin/telemetry/traces<br/>GET /api/v1/admin/telemetry/live"]
    end

    UI --> TracedFetch
    TracedFetch -->|"HTTP + X-Correlation-ID"| TracingMW
    TracingMW -->|"set_correlation_id()"| CtxVar

    TracingMW --> DBPool
    TracingMW --> TaskQueue
    TaskQueue -->|"payload['_correlation_id']"| Worker
    Worker -->|"set_correlation_id()"| CtxVar

    CtxVar -.->|"Extracts correlation_id"| Formatter
    Formatter --> LogSink

    TracingMW -->|"record_request(duration_ms)"| Tracker
    Tracker --> AdminAPI
```

### End-to-End Distributed Trace Flow

```mermaid
sequenceDiagram
    autonumber
    participant UI as Next.js (Browser)
    participant MW as TracingMiddleware
    participant Ctx as ContextVar Storage
    participant Route as FastAPI Route Handler
    participant Log as StructuredJsonFormatter
    participant Task as Background Task Worker
    participant DB as Dual DB Pool

    UI->>MW: GET /api/v1/stocks/ALI [X-Correlation-ID: corr_fe_1001]
    MW->>Ctx: set_correlation_id('corr_fe_1001')
    MW->>MW: start_time = time.perf_counter()
    
    MW->>Route: get_stock_profile("ALI")
    Route->>Log: logger.info("Stock profile requested")
    Log-->>Log: Formats JSON: {"correlation_id": "corr_fe_1001", "msg": "..."}
    
    Route->>DB: Query Stock, Price, Financials
    DB-->>Route: Stock Profile Data
    
    opt Trigger Background PDF Generation
        Route->>Task: enqueue("reports.generate_pdf", payload)
        Note over Task: TaskRecord saved with _correlation_id = 'corr_fe_1001'
        Task->>Ctx: Worker thread binds 'corr_fe_1001' during PDF compilation
    end

    Route-->>MW: 200 OK (8.4ms)
    MW->>MW: duration_ms = (perf_counter() - start_time) * 1000.0
    MW->>MW: Record in LatencyTracker (p50, p95, p99)
    MW-->>UI: Response 200 OK<br/>X-Correlation-ID: corr_fe_1001<br/>X-Response-Time-Ms: 8.42ms
```


---

## Level 11: Real-Time Server-Sent Events (SSE) Streaming Architecture

```mermaid
flowchart TD
    subgraph Client["Next.js Presentation Tier"]
        UI["React Investor Dashboard & Screener"]
        SSEClient["lib/sse.ts (createEventSource / subscribeToTask)<br/>W3C EventSource + Auto-reconnect"]
    end

    subgraph StreamingGateway["FastAPI Gateway & SSE Streaming Endpoints"]
        TaskStream["GET /api/v1/stream/tasks/{id}"]
        AlertStream["GET /api/v1/stream/alerts"]
        MarketStream["GET /api/v1/stream/market"]
        AdminStream["GET /api/v1/stream/hub/metrics"]
    end

    subgraph SSEHub["Real-Time SSE Engine (pse_quant.streaming)"]
        StreamHubNode["StreamHub<br/>- Channel-based async queues<br/>- Keep-alive ping (: ping) every 5s<br/>- Drop-oldest backpressure<br/>- Disconnect garbage collection"]
    end

    subgraph Producers["Domain Event & Worker Producers"]
        TaskWorker["TaskWorker (broadcast_task_progress)<br/>Emits task_initial, task_progress, task_completed"]
        AlertFanout["AlertFanoutService (Lab 7)<br/>Emits alert_notification on MOS breach"]
        MarketIngest["PSE Edge Scraper & Pricing<br/>Emits market_tick"]
    end

    UI --> SSEClient
    SSEClient -->|"GET /stream/tasks/{id}"| TaskStream
    SSEClient -->|"GET /stream/alerts"| AlertStream
    SSEClient -->|"GET /stream/market"| MarketStream

    TaskStream --> StreamHubNode
    AlertStream --> StreamHubNode
    MarketStream --> StreamHubNode

    TaskWorker -->|"broadcast('tasks:xyz', ...)"| StreamHubNode
    AlertFanout -->|"broadcast('alerts:user:12', ...)"| StreamHubNode
    MarketIngest -->|"broadcast('market:ticks', ...)"| StreamHubNode

    StreamHubNode -->|"Yield chunk (text/event-stream)"| UI
```

### Real-Time Task Progress & Alert SSE Push Sequence

```mermaid
sequenceDiagram
    autonumber
    participant UI as Next.js (Browser EventSource)
    participant API as FastAPI Gateway (/stream)
    participant Hub as StreamHub Channel (tasks:task_100)
    participant Worker as Leased Task Worker
    participant DB as Relational Ledger

    UI->>API: GET /api/v1/stream/tasks/task_100
    API->>Hub: subscribe("tasks:task_100")
    Hub-->>API: Return client async queue
    API-->>UI: HTTP 200 text/event-stream<br/>id: evt_1\nevent: connected\ndata: {"status": "active"}

    Worker->>DB: Claim lease & start execution
    Worker->>Hub: broadcast_task_progress(task_100, 25, "Directory sync complete")
    Hub-->>API: Push formatted SSE block
    API-->>UI: id: evt_2\nevent: task_progress\ndata: {"progress_pct": 25, "message": "Directory sync complete"}

    Worker->>Hub: broadcast_task_progress(task_100, 75, "Financial statements parsed")
    Hub-->>API: Push formatted SSE block
    API-->>UI: id: evt_3\nevent: task_progress\ndata: {"progress_pct": 75, "message": "Financial statements parsed"}

    Worker->>DB: UPDATE status='completed'
    Worker->>Hub: broadcast(task_100, "task_completed", {"status": "completed", "result": {...}})
    Hub-->>API: Push terminal SSE block
    API-->>UI: id: evt_4\nevent: task_completed\ndata: {"status": "completed"}
    
    API->>API: Stream generator breaks cleanly
    API->>Hub: unsubscribe("tasks:task_100")
    UI->>UI: Update UI state to completed
```


---

## Level 12: Zero-Downtime Database Migrations & Expand-Contract Engine

```mermaid
flowchart TD
    subgraph ClientAndAdmin["Management & Control Plane"]
        AdminCLI["Admin Migration Control<br/>POST /admin/migrations/{name}/advance<br/>POST /admin/migrations/{name}/backfill<br/>GET /admin/migrations/{name}/verify"]
        AdminUI["Admin Dashboard"]
    end

    subgraph Orchestrator["Migration Engine (pse_quant.migrations)"]
        Mgr["MigrationManager<br/>- Phase State Machine<br/>- Parity Gate Auditor<br/>- Throttled Batch Runner"]
        Ledger[("schema_migrations_ledger<br/>Tracks: Phase, Backfilled Rows, Parity Verified")]
    end

    subgraph ExpandContractPhases["Expand-Contract Lifecycle Stages"]
        P1["1. EXPAND<br/>DDL: Non-destructive column addition<br/>(amount_centavos INTEGER, currency VARCHAR)"]
        P2["2. DUAL-WRITE<br/>App writes: amount_php AND amount_centavos<br/>(PaymentEvent.set_amount)"]
        P3["3. BACKFILL<br/>Throttled worker batches historical NULL rows<br/>(batch_size=100, bounded commits)"]
        P4["4. READ-NEW<br/>PARITY AUDIT GATE (100% Match Requirement)<br/>App reads: effective_amount_php (centavos)"]
        P5["5. CONTRACT<br/>Post-deploy DDL drops legacy column<br/>(ALTER TABLE payment_events DROP COLUMN amount_php)"]
    end

    subgraph LiveTables["Relational Persistence"]
        LivePaymentEvents[("payment_events<br/>[Zero downtime during all 5 phases]")]
    end

    AdminCLI --> Mgr
    AdminUI --> Mgr
    Mgr <--> Ledger

    Mgr --> P1
    P1 --> P2
    P2 --> P3
    P3 --> P4
    P4 --> P5

    P1 -.->|"ALTER TABLE ADD COLUMN"| LivePaymentEvents
    P2 -.->|"Simultaneous writes"| LivePaymentEvents
    P3 -.->|"UPDATE in batches"| LivePaymentEvents
    P4 -.->|"Audit select & new read path"| LivePaymentEvents
    P5 -.->|"ALTER TABLE DROP COLUMN"| LivePaymentEvents
```

### Zero-Downtime Phased Migration Sequence & Parity Gate

```mermaid
sequenceDiagram
    autonumber
    participant Admin as System Admin / CI Pipeline
    participant Mgr as MigrationManager
    participant Ledger as schema_migrations_ledger
    participant DB as payment_events Table
    participant App as Active Application Code

    Note over DB: Current: amount_php (Float) only
    Admin->>Mgr: advance_phase(m001, target=EXPAND)
    Mgr->>DB: ALTER TABLE payment_events ADD COLUMN amount_centavos INTEGER
    Mgr->>DB: ALTER TABLE payment_events ADD COLUMN currency VARCHAR(3) DEFAULT 'PHP'
    Mgr->>Ledger: Set phase = 'EXPAND'
    Mgr-->>Admin: Phase EXPAND activated

    Admin->>Mgr: advance_phase(m001, target=DUAL_WRITE)
    Mgr->>Ledger: Set phase = 'DUAL_WRITE'
    Note over App: App writes: event.set_amount(1499.75) -> dual writes both columns

    Admin->>Mgr: run_backfill(m001, batch_size=100)
    loop Until pending rows == 0
        Mgr->>DB: SELECT id, amount_php WHERE amount_centavos IS NULL LIMIT 100
        Mgr->>DB: UPDATE amount_centavos = round(amount_php * 100)
        Mgr->>Ledger: Increment rows_backfilled += 100
    end
    Mgr-->>Admin: Backfill complete (0 remaining)

    Admin->>Mgr: advance_phase(m001, target=READ_NEW)
    Mgr->>DB: Audit 100% parity: amount_centavos == round(amount_php * 100)
    alt Discrepancies > 0
        Mgr-->>Admin: ABORT: Parity gate failed!
    else 100% Parity Clean
        Mgr->>Ledger: Set phase = 'READ_NEW', verified_parity = true
        Mgr-->>Admin: Phase READ_NEW activated
    end

    Note over App: App reads: event.effective_amount_php (from amount_centavos)

    Admin->>Mgr: advance_phase(m001, target=CONTRACT)
    Mgr->>DB: Re-verify parity check
    Mgr->>DB: ALTER TABLE payment_events DROP COLUMN amount_php
    Mgr->>Ledger: Set phase = 'COMPLETED', completed_at = now()
    Mgr-->>Admin: Migration COMPLETED with 0 downtime
```
