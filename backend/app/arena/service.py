from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db_models import (
    ArenaRunRecord,
    DecisionRecord,
    EquitySnapshotRecord,
    MarketBarRecord,
    ModelProfileRecord,
    OrderRecord,
    PortfolioRecord,
    PositionRecord,
    TradeRecord,
)
from app.models.provider import ModelProvider
from app.schemas import (
    ArenaRunResult,
    MarketSnapshot,
    ModelProfile,
    PortfolioState,
    PositionState,
)
from app.trading.broker import apply_fill
from app.trading.risk import ALLOWED_SYMBOLS, evaluate_decision

EASTERN = ZoneInfo("America/New_York")


class DuplicateArenaRunError(RuntimeError):
    pass


class MarketProvider(Protocol):
    async def get_snapshot(
        self, symbols: list[str], period: str, interval: str
    ) -> MarketSnapshot: ...


class ArenaService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        market_provider: MarketProvider,
        model_provider: ModelProvider,
        settings: Settings | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._market_provider = market_provider
        self._model_provider = model_provider
        self._settings = settings or get_settings()

    def _portfolio_state(
        self, portfolio: PortfolioRecord, snapshot: MarketSnapshot, slug: str
    ) -> PortfolioState:
        positions = [
            PositionState(
                symbol=position.symbol,
                quantity=float(position.quantity),
                avg_cost=float(position.avg_cost),
                current_price=snapshot.price_for(position.symbol) or float(position.avg_cost),
            )
            for position in portfolio.positions
        ]
        return PortfolioState(
            model_slug=slug,
            cash=float(portfolio.cash),
            starting_cash=float(portfolio.starting_cash),
            positions=positions,
        )

    def _save_portfolio(
        self, session: Session, record: PortfolioRecord, state: PortfolioState
    ) -> None:
        record.cash = Decimal(str(state.cash))
        existing = {position.symbol: position for position in record.positions}
        active_symbols = {position.symbol for position in state.positions}
        for position in state.positions:
            stored = existing.get(position.symbol)
            if stored is None:
                stored = PositionRecord(portfolio_id=record.id, symbol=position.symbol)
                session.add(stored)
            stored.quantity = Decimal(str(position.quantity))
            stored.avg_cost = Decimal(str(position.avg_cost))
        for symbol, stored in existing.items():
            if symbol not in active_symbols:
                session.delete(stored)
        session.flush()

    def _trades_today(self, session: Session, model_id: int, at: datetime) -> int:
        local_date = at.astimezone(EASTERN).date()
        start = datetime.combine(local_date, time.min, EASTERN).astimezone(UTC)
        end = datetime.combine(local_date, time.max, EASTERN).astimezone(UTC)
        count = session.scalar(
            select(func.count())
            .select_from(TradeRecord)
            .where(
                TradeRecord.model_id == model_id,
                TradeRecord.executed_at >= start,
                TradeRecord.executed_at <= end,
            )
        )
        return int(count or 0)

    def _save_market_points(self, session: Session, snapshot: MarketSnapshot) -> None:
        for item in snapshot.symbols:
            existing = session.scalar(
                select(MarketBarRecord).where(
                    MarketBarRecord.symbol == item.symbol,
                    MarketBarRecord.timestamp == item.as_of,
                )
            )
            price = Decimal(str(item.price))
            if existing is None:
                session.add(
                    MarketBarRecord(
                        symbol=item.symbol,
                        timestamp=item.as_of,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=item.volume,
                    )
                )
            else:
                existing.close = price
                existing.volume = item.volume
        session.flush()

    def _benchmark_return(
        self,
        session: Session,
        snapshot: MarketSnapshot,
        run_at: datetime,
    ) -> float:
        current = snapshot.price_for("SPY")
        if current is None:
            return 0.0
        first_run_at = session.scalar(
            select(ArenaRunRecord.run_at).order_by(ArenaRunRecord.run_at.asc()).limit(1)
        )
        if first_run_at is None:
            return 0.0
        normalized_first = (
            first_run_at.replace(tzinfo=UTC)
            if first_run_at.tzinfo is None
            else first_run_at.astimezone(UTC)
        )
        normalized_current = (
            run_at.replace(tzinfo=UTC) if run_at.tzinfo is None else run_at.astimezone(UTC)
        )
        if normalized_first == normalized_current:
            return 0.0
        first = session.scalar(
            select(MarketBarRecord.close)
            .where(
                MarketBarRecord.symbol == "SPY",
                MarketBarRecord.timestamp <= first_run_at,
            )
            .order_by(MarketBarRecord.timestamp.desc())
            .limit(1)
        )
        return 0.0 if first is None else (current / float(first)) - 1.0

    async def run_once(
        self,
        at: datetime,
        mode: str,
        snapshot: MarketSnapshot | None = None,
    ) -> ArenaRunResult:
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        if snapshot is None:
            snapshot = await self._market_provider.get_snapshot(
                sorted(ALLOWED_SYMBOLS),
                self._settings.market_period,
                self._settings.market_interval,
            )

        with self._session_factory() as session:
            existing = session.scalar(
                select(ArenaRunRecord).where(
                    ArenaRunRecord.run_at == at,
                    ArenaRunRecord.mode == mode,
                )
            )
            if existing is not None:
                raise DuplicateArenaRunError(f"arena run at {at.isoformat()} already exists")

            run = ArenaRunRecord(
                run_at=at,
                mode=mode,
                status="running",
                market_status=snapshot.status,
            )
            session.add(run)
            session.flush()
            self._save_market_points(session, snapshot)
            benchmark_return = self._benchmark_return(session, snapshot, run.run_at)

            models = session.scalars(
                select(ModelProfileRecord).order_by(ModelProfileRecord.id)
            ).all()
            trade_count = 0
            for model in models:
                portfolio_record = session.scalar(
                    select(PortfolioRecord).where(PortfolioRecord.model_id == model.id)
                )
                if portfolio_record is None:
                    raise RuntimeError(f"portfolio missing for {model.slug}")
                state = self._portfolio_state(portfolio_record, snapshot, model.slug)
                profile = ModelProfile(
                    slug=model.slug,
                    name=model.name,
                    color=model.color,
                    provider_model_id=model.provider_model_id,
                )
                call = await self._model_provider.decide(profile, snapshot, state)
                risk = evaluate_decision(
                    call.decision,
                    state,
                    snapshot.price_for(call.decision.symbol) if call.decision.symbol else None,
                    self._trades_today(session, model.id, at),
                )
                decision_status = (
                    "error" if call.error else ("approved" if risk.approved else "held")
                )
                decision = DecisionRecord(
                    arena_run_id=run.id,
                    model_id=model.id,
                    action=call.decision.action,
                    symbol=call.decision.symbol,
                    target_weight=call.decision.target_weight,
                    confidence=call.decision.confidence,
                    reason=call.decision.reason,
                    status=decision_status,
                    rejection_reason=None if risk.approved else risk.reason,
                    provider_error=call.error,
                    latency_ms=call.latency_ms,
                    prompt_tokens=call.prompt_tokens,
                    completion_tokens=call.completion_tokens,
                    created_at=at,
                )
                session.add(decision)
                session.flush()

                if risk.approved and risk.intent is not None:
                    intent = risk.intent
                    order = OrderRecord(
                        arena_run_id=run.id,
                        model_id=model.id,
                        decision_id=decision.id,
                        side=intent.side,
                        symbol=intent.symbol,
                        quantity=Decimal(str(intent.quantity)),
                        target_weight=intent.target_weight,
                        reference_price=Decimal(str(intent.reference_price)),
                        status="filled",
                    )
                    session.add(order)
                    session.flush()
                    fill = apply_fill(state, intent, intent.reference_price)
                    self._save_portfolio(session, portfolio_record, fill.portfolio)
                    session.add(
                        TradeRecord(
                            order_id=order.id,
                            model_id=model.id,
                            symbol=intent.symbol,
                            side=intent.side,
                            quantity=Decimal(str(intent.quantity)),
                            fill_price=Decimal(str(fill.fill_price)),
                            realized_pnl=Decimal(str(fill.realized_pnl)),
                            executed_at=at,
                        )
                    )
                    trade_count += 1
                    state = fill.portfolio

                positions_value = sum(position.market_value for position in state.positions)
                total_value = state.cash + positions_value
                session.add(
                    EquitySnapshotRecord(
                        arena_run_id=run.id,
                        model_id=model.id,
                        captured_at=at,
                        cash=Decimal(str(state.cash)),
                        positions_value=Decimal(str(positions_value)),
                        total_value=Decimal(str(total_value)),
                        return_pct=(total_value / state.starting_cash) - 1.0,
                        benchmark_return_pct=benchmark_return,
                    )
                )

            run.status = "completed"
            session.commit()
            return ArenaRunResult(
                run_id=run.id,
                run_at=run.run_at,
                mode=run.mode,
                status=run.status,
                decision_count=len(models),
                trade_count=trade_count,
            )
