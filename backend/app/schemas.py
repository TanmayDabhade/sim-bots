from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Action = Literal["BUY", "SELL", "HOLD"]
Side = Literal["BUY", "SELL"]


class SymbolSnapshot(BaseModel):
    symbol: str
    as_of: datetime
    price: float = Field(gt=0)
    change_1d: float | None = None
    change_1h: float | None = None
    volume: int = Field(ge=0)
    sma_20: float | None = None
    sma_50: float | None = None
    rsi_14: float | None = Field(default=None, ge=0, le=100)


class MarketSnapshot(BaseModel):
    as_of: datetime
    status: Literal["LIVE", "REPLAY", "STALE", "DEMO"]
    symbols: list[SymbolSnapshot]

    def price_for(self, symbol: str) -> float | None:
        return next((item.price for item in self.symbols if item.symbol == symbol), None)


class ModelProfile(BaseModel):
    slug: str
    name: str
    color: str
    provider_model_id: str


class ModelDecision(BaseModel):
    action: Action
    symbol: str | None = None
    target_weight: float | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_action_fields(self) -> ModelDecision:
        if self.action == "HOLD":
            if self.symbol is not None or self.target_weight is not None:
                raise ValueError("HOLD must not include a symbol or target weight")
            return self
        if self.symbol is None or self.target_weight is None:
            raise ValueError(f"{self.action} requires a symbol and target weight")
        return self


class PositionState(BaseModel):
    symbol: str
    quantity: float = Field(ge=0)
    avg_cost: float = Field(ge=0)
    current_price: float = Field(gt=0)

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price


class PortfolioState(BaseModel):
    model_slug: str
    cash: float = Field(ge=0)
    starting_cash: float = Field(gt=0)
    positions: list[PositionState]

    @property
    def equity(self) -> float:
        return self.cash + sum(position.market_value for position in self.positions)

    def position_for(self, symbol: str) -> PositionState | None:
        return next((position for position in self.positions if position.symbol == symbol), None)


class OrderIntent(BaseModel):
    side: Side
    symbol: str
    quantity: float = Field(gt=0)
    target_weight: float = Field(ge=0, le=0.2)
    reference_price: float = Field(gt=0)


class RiskResult(BaseModel):
    approved: bool
    reason: str
    intent: OrderIntent | None = None


class FillResult(BaseModel):
    portfolio: PortfolioState
    fill_price: float
    realized_pnl: float


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


class TradeSummary(BaseModel):
    realized_pnl: float


class PerformanceMetrics(BaseModel):
    return_pct: float
    pnl: float
    sharpe: float | None
    max_drawdown: float
    trade_count: int
    win_rate: float | None


class ModelCallResult(BaseModel):
    decision: ModelDecision
    latency_ms: int = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    error: str | None = None


class ArenaRunResult(BaseModel):
    run_id: int
    run_at: datetime
    mode: str
    status: str
    decision_count: int
    trade_count: int
