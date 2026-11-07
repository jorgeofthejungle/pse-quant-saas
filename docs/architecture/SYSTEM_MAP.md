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
