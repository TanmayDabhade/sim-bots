import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.arena.scheduler import is_market_open, start_scheduler


def test_market_calendar_accepts_an_open_session() -> None:
    assert is_market_open(datetime(2026, 9, 1, 14, 0, tzinfo=UTC)) is True


def test_market_calendar_rejects_a_weekend() -> None:
    assert is_market_open(datetime(2026, 9, 5, 14, 0, tzinfo=UTC)) is False


def test_market_calendar_rejects_holiday_and_closing_bell() -> None:
    assert not is_market_open(datetime(2026, 9, 7, 14, 0, tzinfo=UTC))
    assert not is_market_open(datetime(2026, 9, 8, 20, 0, tzinfo=UTC))


@pytest.mark.asyncio
async def test_scheduler_starts_first_cycle_without_waiting_for_interval() -> None:
    started = asyncio.Event()

    class Service:
        async def run_once(self, at: datetime, mode: str) -> None:
            assert mode == "live"
            started.set()

    with patch("app.arena.scheduler.is_market_open", return_value=True):
        scheduler = start_scheduler(Service(), 1)  # type: ignore[arg-type]
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
        finally:
            scheduler.shutdown(wait=False)
