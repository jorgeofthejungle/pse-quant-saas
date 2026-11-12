"""
pse_quant/db/models.py — Modern SQLAlchemy 2.0 Declarative Models
Relational schema for PSE Quant SaaS (PostgreSQL).
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional, Any
from sqlalchemy import (
    String,
    Float,
    Integer,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    JSON,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Stock(Base):
    __tablename__ = "stocks"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(64), nullable=False, default="Unknown", index=True)
    is_reit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bank: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)  # active, suspended, delisted
    cmpy_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    fiscal_year_end_month: Mapped[int] = mapped_column(Integer, default=12)
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    financials: Mapped[list[Financial]] = relationship("Financial", back_populates="stock", cascade="all, delete-orphan")
    prices: Mapped[list[Price]] = relationship("Price", back_populates="stock", cascade="all, delete-orphan")
    scores: Mapped[list[Score]] = relationship("Score", back_populates="stock", cascade="all, delete-orphan")
    watchlists: Mapped[list[Watchlist]] = relationship("Watchlist", back_populates="stock", cascade="all, delete-orphan")


class Financial(Base):
    __tablename__ = "financials"
    __table_args__ = (
        UniqueConstraint("ticker", "year", name="uq_financials_ticker_year"),
        Index("idx_financials_ticker_year", "ticker", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), ForeignKey("stocks.ticker", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_debt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    operating_cf: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    capex: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ebitda: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    depreciation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    amortization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    stock: Mapped[Stock] = relationship("Stock", back_populates="financials")


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("ticker", "trade_date", name="uq_prices_ticker_date"),
        Index("idx_prices_ticker_date", "ticker", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), ForeignKey("stocks.ticker", ondelete="CASCADE"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    market_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock: Mapped[Stock] = relationship("Stock", back_populates="prices")


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("ticker", "run_date", "portfolio_type", name="uq_scores_ticker_date_portfolio"),
        Index("idx_scores_run_date_portfolio", "run_date", "portfolio_type"),
        Index("idx_scores_portfolio_rank", "portfolio_type", "rank"),
        Index("idx_scores_ticker", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), ForeignKey("stocks.ticker", ondelete="CASCADE"), nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    portfolio_type: Mapped[str] = mapped_column(String(32), default="unified")  # unified, dividend, value
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    breakdown_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock: Mapped[Stock] = relationship("Stock", back_populates="scores")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        Index("idx_pipeline_runs_started", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(64), nullable=False)  # daily_score, weekly_scrape, email_digest
    status: Mapped[str] = mapped_column(String(32), default="running")  # running, completed, held, failed
    summary_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="member")  # member, admin
    tier: Mapped[str] = mapped_column(String(32), default="free")    # free, paid, pro
    status: Mapped[str] = mapped_column(String(32), default="active")
    api_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    notification_prefs: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, default=lambda: {"weekly_report": True, "daily_brief": True, "price_alerts": True}
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    watchlists: Mapped[list[Watchlist]] = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list[UserNotification]] = relationship("UserNotification", back_populates="user", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), default="monthly")  # monthly, annual, lifetime
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, past_due, cancelled
    amount_php: Mapped[float] = mapped_column(Float, default=499.0)
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship("User", back_populates="subscriptions")


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", name="uq_watchlists_user_ticker"),
        Index("idx_watchlists_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), ForeignKey("stocks.ticker", ondelete="CASCADE"), nullable=False)
    target_mos_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship("User", back_populates="watchlists")
    stock: Mapped[Stock] = relationship("Stock", back_populates="watchlists")


class EmailLog(Base):
    __tablename__ = "email_logs"
    __table_args__ = (
        Index("idx_email_logs_sent", "sent_at"),
        Index("idx_email_logs_recipient", "recipient_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email_type: Mapped[str] = mapped_column(String(64), nullable=False)  # weekly_report, daily_brief, alert, transactional
    status: Mapped[str] = mapped_column(String(32), default="sent")  # sent, failed, bounced
    resend_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── OaaS & Causal Alert Engine Models ─────────────────────────

class OaasMacroState(Base):
    __tablename__ = "oaas_macro_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    regime_title: Mapped[str] = mapped_column(String(255), default="Neutral Macro Flow")
    z_bsp_rate: Mapped[float] = mapped_column(Float, default=0.0)
    z_us10y_yield: Mapped[float] = mapped_column(Float, default=0.0)
    z_brent_crude: Mapped[float] = mapped_column(Float, default=0.0)
    z_usd_php: Mapped[float] = mapped_column(Float, default=0.0)
    z_msci_flow: Mapped[float] = mapped_column(Float, default=0.0)
    php_10y_bval_rate: Mapped[float] = mapped_column(Float, default=0.0585)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(64), default="hybrid_auto")  # hybrid_auto, admin_override
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class OaasRun(Base):
    __tablename__ = "oaas_runs"
    __table_args__ = (
        Index("idx_oaas_runs_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(64), default="daily_triage")  # daily_triage, weekly_brief, dry_run
    regime_title: Mapped[str] = mapped_column(String(255), nullable=False)
    macro_state_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("oaas_macro_states.id", ondelete="SET NULL"), nullable=True)
    tickers_evaluated_count: Mapped[int] = mapped_column(Integer, default=0)
    alerts_triggered_count: Mapped[int] = mapped_column(Integer, default=0)
    top_allocations_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    quarantined_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    full_matrix_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    dispatched_emails_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OaasAlert(Base):
    __tablename__ = "oaas_alerts"
    __table_args__ = (
        Index("idx_oaas_alerts_ticker", "ticker"),
        Index("idx_oaas_alerts_cooldown", "cooldown_until"),
        Index("idx_oaas_alerts_created", "dispatched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("oaas_runs.id", ondelete="CASCADE"), nullable=True)
    ticker: Mapped[str] = mapped_column(String(16), ForeignKey("stocks.ticker", ondelete="CASCADE"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)  # INSTANT_ALERT, INSTANT_DISTRIBUTION_WARNING
    direction: Mapped[str] = mapped_column(String(32), default="BUY")    # BUY, AVOID, DUMP_WARNING
    reference_price: Mapped[float] = mapped_column(Float, nullable=False)
    displacement_pct: Mapped[float] = mapped_column(Float, nullable=False)
    gate_threshold_pct: Mapped[float] = mapped_column(Float, nullable=False)
    net_hurdle_pct: Mapped[float] = mapped_column(Float, nullable=False)
    friction_bps: Mapped[float] = mapped_column(Float, nullable=False)
    board_lot: Mapped[int] = mapped_column(Integer, default=10)
    executable_shares: Mapped[int] = mapped_column(Integer, default=0)
    executable_ticket_php: Mapped[float] = mapped_column(Float, default=0.0)
    limit_low: Mapped[float] = mapped_column(Float, default=0.0)
    limit_high: Mapped[float] = mapped_column(Float, default=0.0)
    stop_loss: Mapped[float] = mapped_column(Float, default=0.0)
    crowd_participation_pct: Mapped[float] = mapped_column(Float, default=0.0)
    cooldown_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, cooldown, expired, cancelled
    dispatched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Payment Webhooks & Idempotency Ledger ─────────────────────

class PaymentEvent(Base):
    """
    Immutable ledger of inbound payment gateway events (PayMongo, Maya, Stripe).
    Guarantees strict at-least-once idempotency: duplicate webhook deliveries
    are recorded and acknowledged with HTTP 200 without executing duplicate fulfillments.
    """
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_payment_events_provider_event_id"),
        Index("idx_payment_events_provider_status", "provider", "status"),
        Index("idx_payment_events_customer_email", "customer_email"),
        Index("idx_payment_events_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), default="paymongo")  # paymongo, maya, stripe
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)    # payment.paid, payment.failed
    status: Mapped[str] = mapped_column(String(32), default="pending")     # pending, processed, duplicate, failed
    amount_php: Mapped[float] = mapped_column(Float, default=0.0)
    amount_centavos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="PHP")
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    @property
    def effective_amount_php(self) -> float:
        """Returns normalized amount in PHP, prioritizing fixed-precision centavos if present."""
        if self.amount_centavos is not None:
            return round(self.amount_centavos / 100.0, 2)
        return round(self.amount_php, 2)

    def set_amount(self, php_amount: float) -> None:
        """Dual-writes to both floating-point PHP and fixed-precision centavos."""
        self.amount_php = round(php_amount, 2)
        self.amount_centavos = int(round(php_amount * 100))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)



# ── Scraper Resilience & Dead-Letter Ledger ────────────────────

class ScraperDeadLetter(Base):
    """
    Persistent dead-letter queue (DLQ) for malformed, corrupt, or repeated-failure
    PSE Edge scraper payloads. Isolates poison-pill records so the broader batch
    ETL can continue uninterrupted.
    """
    __tablename__ = "scraper_dead_letters"
    __table_args__ = (
        Index("idx_scraper_dead_letters_ticker", "ticker"),
        Index("idx_scraper_dead_letters_status_stage", "status", "stage"),
        Index("idx_scraper_dead_letters_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)  # directory, quote, financials, validation
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    error_reason: Mapped[str] = mapped_column(String, nullable=False)
    payload_preview: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, reprocessed, ignored
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ── Event-Driven In-App Notification Ledger ───────────────────

class UserNotification(Base):
    """
    Persistent notification ledger fanned out from domain events
    (Margin of Safety triggers, Price limits, Macro regime shifts).
    """
    __tablename__ = "user_notifications"
    __table_args__ = (
        Index("idx_user_notifications_user_read", "user_id", "is_read"),
        Index("idx_user_notifications_ticker_created", "ticker", "created_at"),
        Index("idx_user_notifications_dedup", "user_id", "ticker", "alert_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)  # MOS_BREACH, PRICE_LIMIT, MACRO_REGIME_SHIFT
    severity: Mapped[str] = mapped_column(String(32), default="opportunity")  # info, opportunity, warning
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship("User", back_populates="notifications")



# ── Distributed Task Queue & Leased Worker Ledger ─────────────

class TaskRecord(Base):
    """
    Persistent task ledger for distributed background jobs (ETL sync, PDF compilation,
    email digests, quant valuation batching). Guarantees reliable execution via
    worker leases, heartbeats, and automatic zombie reclamation.
    """
    __tablename__ = "background_tasks"
    __table_args__ = (
        Index("idx_bg_tasks_status_priority", "status", "priority", "created_at"),
        Index("idx_bg_tasks_lease", "status", "lease_expires_at"),
        Index("idx_bg_tasks_task_name", "task_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5, index=True)
    payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    result_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)



# ── Zero-Downtime Migration State Ledger ───────────────────────

class SchemaMigrationLedger(Base):
    """
    Persistent audit ledger tracking phased Expand-Contract database migrations.
    Guarantees observable progress, phase advancement gates, and zero-downtime execution.
    """
    __tablename__ = "schema_migrations_ledger"
    __table_args__ = (
        Index("idx_migrations_name", "migration_name", unique=True),
        Index("idx_migrations_phase", "phase"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    migration_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), default="EXPAND", nullable=False)  # EXPAND, DUAL_WRITE, BACKFILL, READ_NEW, CONTRACT, COMPLETED
    rows_backfilled: Mapped[int] = mapped_column(Integer, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    verified_parity: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ── Disaster Recovery & Database Snapshot Manifest Ledger ──────

class DatabaseSnapshotManifest(Base):
    """
    Persistent audit ledger tracking verified point-in-time database snapshots.
    Guarantees observable recovery points, SHA-256 cryptographic verification,
    and storage compression metrics.
    """
    __tablename__ = "database_snapshots"
    __table_args__ = (
        Index("idx_snapshots_created", "created_at"),
        Index("idx_snapshots_status", "status"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    filepath: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_bytes: Mapped[int] = mapped_column(Integer, default=0)
    compressed_bytes: Mapped[int] = mapped_column(Integer, default=0)
    compression_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    tables_count: Mapped[int] = mapped_column(Integer, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="completed")  # completed, restored, corrupt, pruned
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    restored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ── Feature Flags & Progressive Canary Delivery Models ────────

class FeatureFlagRecord(Base):
    """
    Persistent relational record for dynamic feature flags.
    Controls canary rollouts, multi-tier targeting, and emergency kill-switches.
    """
    __tablename__ = "feature_flags"
    __table_args__ = (
        Index("idx_feature_flags_enabled", "is_enabled"),
    )

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=0)
    allowed_tiers_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    allowed_entities_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    denied_entities_json: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    variants_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FeatureFlagAuditRecord(Base):
    """
    Append-only audit trail capturing all feature flag mutations, percentage updates,
    and emergency kill-switch activations.
    """
    __tablename__ = "feature_flag_audits"
    __table_args__ = (
        Index("idx_ff_audit_key", "flag_key"),
        Index("idx_ff_audit_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flag_key: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # CREATE, UPDATE, KILL_SWITCH, ENABLE, DELETE
    details_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

