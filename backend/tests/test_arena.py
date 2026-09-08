import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.arena.service import ArenaService, DuplicateArenaRunError
from app.config import Settings
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


@pytest.mark.asyncio
async def test_models_evaluate_same_cycle_concurrently() -> None:
    arrived: set[str] = set()
    all_started = asyncio.Event()

    class ConcurrentProvider(DemoModelProvider):
        async def decide(self, profile, snapshot, portfolio):
            arrived.add(profile.slug)
            if len(arrived) == 4:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=1)
            return await super().decide(profile, snapshot, portfolio)

    service = ArenaService(session_factory(), FakeMarketProvider(), ConcurrentProvider())
    result = await service.run_once(
        datetime(2026, 9, 1, 14, 0, tzinfo=UTC), "demo", market_snapshot()
    )
    assert result.decision_count == 4
    assert result.trade_count == 4


@pytest.mark.asyncio
async def test_failed_cycle_exposes_error_and_successful_retry_clears_it() -> None:
    class UnavailableMarket:
        async def get_snapshot(self, *args):
            raise RuntimeError("Upstream unavailable")

    service = ArenaService(session_factory(), UnavailableMarket(), DemoModelProvider())
    at = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    with pytest.raises(RuntimeError):
        await service.run_once(at, "live")
    assert service.last_error is not None
    assert service.cycle_running is False
    await service.run_once(at, "live", market_snapshot())
    assert service.last_error is None
    assert service.last_completed_at is not None


@pytest.mark.asyncio
async def test_overlapping_cycles_serialize_and_observe_updated_portfolios() -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()
    first_time = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    budgets: list[int | None] = []

    class GatedProvider(DemoModelProvider):
        async def decide(self, profile, snapshot, portfolio):
            budgets.append(portfolio.trades_remaining_today)
            if snapshot.as_of == first_time:
                first_started.set()
                await release_first.wait()
            else:
                second_started.set()
                assert portfolio.cash < 100_000
            return await super().decide(profile, snapshot, portfolio)

    factory = session_factory()
    service = ArenaService(
        factory, FakeMarketProvider(), GatedProvider(), Settings(max_daily_trades=1)
    )
    second_snapshot = market_snapshot().model_copy(
        update={"as_of": first_time + timedelta(minutes=1)}
    )
    first = asyncio.create_task(service.run_once(first_time, "live", market_snapshot()))
    second = None
    try:
        await asyncio.wait_for(first_started.wait(), timeout=1)
        second = asyncio.create_task(
            service.run_once(second_snapshot.as_of, "live", second_snapshot)
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(second_started.wait(), timeout=0.05)
        release_first.set()
        results = await asyncio.gather(first, second)
        assert [result.trade_count for result in results] == [4, 0]
        assert budgets == [1, 1, 1, 1, 0, 0, 0, 0]
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(DecisionRecord)) == 8
    finally:
        release_first.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
