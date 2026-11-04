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
    sector: Mapped[str] = mapped_column(String(64), nullable=False, default="Unknown")
    is_reit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bank: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, suspended, delisted
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
    tier: Mapped[str] = mapped_column(String(32), default="free")  # free, paid, admin
    status: Mapped[str] = mapped_column(String(32), default="active")
    notification_prefs: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, default=lambda: {"weekly_report": True, "daily_brief": True, "price_alerts": True}
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    watchlists: Mapped[list[Watchlist]] = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")


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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email_type: Mapped[str] = mapped_column(String(64), nullable=False)  # weekly_report, daily_brief, alert, transactional
    status: Mapped[str] = mapped_column(String(32), default="sent")  # sent, failed, bounced
    resend_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
