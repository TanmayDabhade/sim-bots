from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pandas_market_calendars as market_calendars
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.arena.service import ArenaService, DuplicateArenaRunError


def is_market_open(at: datetime) -> bool:
    aware = at if at.tzinfo is not None else at.replace(tzinfo=UTC)
    calendar = market_calendars.get_calendar("NYSE")
    local_date = aware.astimezone(calendar.tz).date()
    schedule = calendar.schedule(start_date=local_date, end_date=local_date)
    if schedule.empty:
        return False
    opened = pd.Timestamp(schedule.iloc[0]["market_open"]).to_pydatetime()
    closed = pd.Timestamp(schedule.iloc[0]["market_close"]).to_pydatetime()
    return bool(opened <= aware <= closed)


def start_scheduler(service: ArenaService, interval_minutes: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=UTC)

    async def cycle() -> None:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        if not is_market_open(now):
            return
        try:
            await service.run_once(now, mode="live")
        except DuplicateArenaRunError:
            return

    scheduler.add_job(
        cycle,
        "interval",
        minutes=interval_minutes,
        id="arena-cycle",
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    return scheduler
