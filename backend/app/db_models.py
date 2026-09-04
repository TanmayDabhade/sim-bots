from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ModelProfileRecord(Base):
    __tablename__ = "model_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16))
    provider_model_id: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    portfolio: Mapped[PortfolioRecord] = relationship(back_populates="model", uselist=False)


class PortfolioRecord(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("model_profiles.id", ondelete="CASCADE"), unique=True, index=True
    )
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("100000"))
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("100000"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    model: Mapped[ModelProfileRecord] = relationship(back_populates="portfolio")
    positions: Mapped[list[PositionRecord]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PositionRecord(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))

    portfolio: Mapped[PortfolioRecord] = relationship(back_populates="positions")


class ArenaRunRecord(Base):
    __tablename__ = "arena_runs"
    __table_args__ = (UniqueConstraint("run_at", "mode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="running")
    market_status: Mapped[str] = mapped_column(String(16), default="DEMO")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionRecord(Base):
    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("arena_run_id", "model_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arena_run_id: Mapped[int] = mapped_column(ForeignKey("arena_runs.id", ondelete="CASCADE"))
    model_id: Mapped[int] = mapped_column(ForeignKey("model_profiles.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str | None] = mapped_column(String(12), nullable=True)
    target_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24))
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrderRecord(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arena_run_id: Mapped[int] = mapped_column(ForeignKey("arena_runs.id", ondelete="CASCADE"))
    model_id: Mapped[int] = mapped_column(ForeignKey("model_profiles.id", ondelete="CASCADE"))
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"))
    side: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    target_weight: Mapped[float] = mapped_column(Float)
    reference_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TradeRecord(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("model_profiles.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(12))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    fill_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EquitySnapshotRecord(Base):
    __tablename__ = "equity_snapshots"
    __table_args__ = (UniqueConstraint("model_id", "captured_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arena_run_id: Mapped[int] = mapped_column(ForeignKey("arena_runs.id", ondelete="CASCADE"))
    model_id: Mapped[int] = mapped_column(ForeignKey("model_profiles.id", ondelete="CASCADE"))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    positions_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    return_pct: Mapped[float] = mapped_column(Float)
    benchmark_return_pct: Mapped[float] = mapped_column(Float)


class MarketBarRecord(Base):
    __tablename__ = "market_bars"
    __table_args__ = (UniqueConstraint("symbol", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    volume: Mapped[int] = mapped_column(Integer)
