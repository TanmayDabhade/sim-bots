from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import typer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.arena.replay import build_replay_snapshots
from app.arena.service import ArenaService, DuplicateArenaRunError
from app.config import get_settings
from app.database import Base, get_engine
from app.db_models import MarketBarRecord
from app.market.provider import YahooFinanceProvider
from app.models.provider import DemoModelProvider, OpenRouterModelProvider
from app.repositories import seed_models_and_portfolios
from app.trading.risk import ALLOWED_SYMBOLS

cli = typer.Typer(no_args_is_help=True)


def _factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def _model_provider() -> DemoModelProvider | OpenRouterModelProvider:
    settings = get_settings()
    if settings.model_provider == "openrouter":
        return OpenRouterModelProvider(settings.openrouter_api_key, settings.openrouter_base_url)
    return DemoModelProvider()


def _persist_history(session: Session, history: Mapping[str, pd.DataFrame]) -> None:
    for symbol, frame in history.items():
        existing = set(
            session.scalars(
                select(MarketBarRecord.timestamp).where(MarketBarRecord.symbol == symbol)
            ).all()
        )
        for timestamp, row in frame.iterrows():
            aware = pd.Timestamp(timestamp).to_pydatetime()
            if aware.tzinfo is None:
                aware = aware.replace(tzinfo=UTC)
            if aware in existing:
                continue
            session.add(
                MarketBarRecord(
                    symbol=symbol,
                    timestamp=aware,
                    open=Decimal(str(row["Open"])),
                    high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])),
                    close=Decimal(str(row["Close"])),
                    volume=max(0, int(row["Volume"])),
                )
            )
    session.commit()


@cli.command("init-db")
def init_db() -> None:
    Base.metadata.create_all(get_engine())
    with _factory()() as session:
        seed_models_and_portfolios(session)
    typer.echo("Initialized four model portfolios.")


@cli.command()
def seed(steps: int = typer.Option(8, min=1, max=32)) -> None:
    async def run() -> None:
        settings = get_settings()
        provider = YahooFinanceProvider()
        history = await provider.get_history(
            sorted(ALLOWED_SYMBOLS), settings.market_period, settings.market_interval
        )
        with _factory()() as session:
            _persist_history(session, history)
        service = ArenaService(_factory(), provider, _model_provider(), settings)
        completed = 0
        for snapshot in build_replay_snapshots(history, steps):
            try:
                await service.run_once(snapshot.as_of, mode="replay", snapshot=snapshot)
                completed += 1
            except DuplicateArenaRunError:
                continue
        typer.echo(f"Completed {completed} replay cycles from Yahoo Finance data.")

    asyncio.run(run())


@cli.command("arena-once")
def arena_once() -> None:
    async def run() -> None:
        settings = get_settings()
        provider = YahooFinanceProvider()
        service = ArenaService(_factory(), provider, _model_provider(), settings)
        result = await service.run_once(
            datetime.now(UTC).replace(microsecond=0), mode=settings.model_provider
        )
        typer.echo(result.model_dump_json())

    asyncio.run(run())


if __name__ == "__main__":
    cli()
