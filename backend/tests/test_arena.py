from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.arena.service import ArenaService, DuplicateArenaRunError
from app.database import Base
from app.db_models import (
    DecisionRecord,
    EquitySnapshotRecord,
    MarketBarRecord,
    PortfolioRecord,
    TradeRecord,
)
from app.models.provider import DemoModelProvider
from app.repositories import seed_models_and_portfolios
from app.schemas import MarketSnapshot, SymbolSnapshot


def market_snapshot() -> MarketSnapshot:
    now = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    common = {
        "as_of": now,
        "change_1d": 0.02,
        "change_1h": 0.01,
        "volume": 1_000_000,
        "rsi_14": 55.0,
    }
    return MarketSnapshot(
        as_of=now,
        status="DEMO",
        symbols=[
            SymbolSnapshot(symbol="NVDA", price=180.0, sma_20=175.0, sma_50=170.0, **common),
            SymbolSnapshot(symbol="SPY", price=600.0, sma_20=598.0, sma_50=590.0, **common),
        ],
    )


class FakeMarketProvider:
    async def get_snapshot(self, symbols: list[str], period: str, interval: str) -> MarketSnapshot:
        assert "SPY" in symbols
        assert period == "1mo"
        assert interval == "15m"
        return market_snapshot()


def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed_models_and_portfolios(session)
    return factory


@pytest.mark.asyncio
async def test_one_cycle_persists_four_decisions_trades_and_equity_points() -> None:
    factory = session_factory()
    service = ArenaService(factory, FakeMarketProvider(), DemoModelProvider())

    result = await service.run_once(datetime(2026, 9, 1, 14, 0, tzinfo=UTC), mode="demo")

    with factory() as session:
        decisions = session.scalar(select(func.count()).select_from(DecisionRecord))
        decision_times = session.scalars(select(DecisionRecord.created_at)).all()
        trades = session.scalar(select(func.count()).select_from(TradeRecord))
        equity_points = session.scalar(select(func.count()).select_from(EquitySnapshotRecord))
        balances = session.scalars(select(PortfolioRecord.cash)).all()

    assert result.status == "completed"
    assert result.decision_count == 4
    assert result.trade_count == 4
    assert decisions == 4
    assert {time.replace(tzinfo=UTC) for time in decision_times} == {
        datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    }
    assert trades == 4
    assert equity_points == 4
    assert all(float(balance) < 100_000.0 for balance in balances)


@pytest.mark.asyncio
async def test_duplicate_cycle_timestamp_is_rejected() -> None:
    factory = session_factory()
    service = ArenaService(factory, FakeMarketProvider(), DemoModelProvider())
    timestamp = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    await service.run_once(timestamp, mode="demo")

    with pytest.raises(DuplicateArenaRunError, match="already exists"):
        await service.run_once(timestamp, mode="demo")


@pytest.mark.asyncio
async def test_benchmark_starts_with_first_arena_cycle_not_downloaded_history() -> None:
    factory = session_factory()
    with factory() as session:
        session.add(
            MarketBarRecord(
                symbol="SPY",
                timestamp=datetime(2026, 8, 1, 14, 0, tzinfo=UTC),
                open=500,
                high=500,
                low=500,
                close=500,
                volume=1_000,
            )
        )
        session.commit()
    service = ArenaService(factory, FakeMarketProvider(), DemoModelProvider())
    precise_snapshot = market_snapshot()
    precise_snapshot.symbols[1].price = 600.1234567

    await service.run_once(
        datetime(2026, 9, 1, 14, 0, tzinfo=UTC),
        mode="demo",
        snapshot=precise_snapshot,
    )

    with factory() as session:
        points = session.scalars(select(EquitySnapshotRecord)).all()

    assert {point.benchmark_return_pct for point in points} == {0.0}
