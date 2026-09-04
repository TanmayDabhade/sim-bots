from datetime import UTC, datetime

from app.arena.scheduler import is_market_open


def test_market_calendar_accepts_an_open_session() -> None:
    assert is_market_open(datetime(2026, 9, 1, 14, 0, tzinfo=UTC)) is True


def test_market_calendar_rejects_a_weekend() -> None:
    assert is_market_open(datetime(2026, 9, 5, 14, 0, tzinfo=UTC)) is False
