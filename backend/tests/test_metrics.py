from datetime import UTC, datetime, timedelta

import pytest

from app.portfolio.metrics import calculate_metrics
from app.schemas import EquityPoint, TradeSummary


def test_metrics_report_return_drawdown_and_win_rate() -> None:
    start = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
    points = [
        EquityPoint(timestamp=start + timedelta(minutes=15 * index), equity=value)
        for index, value in enumerate([100_000.0, 105_000.0, 102_000.0, 110_000.0])
    ]
    trades = [
        TradeSummary(realized_pnl=400.0),
        TradeSummary(realized_pnl=-100.0),
        TradeSummary(realized_pnl=0.0),
    ]

    metrics = calculate_metrics(points, trades)

    assert metrics.return_pct == pytest.approx(0.1)
    assert metrics.pnl == pytest.approx(10_000.0)
    assert metrics.max_drawdown == pytest.approx(-0.0285714286)
    assert metrics.trade_count == 3
    assert metrics.win_rate == pytest.approx(1 / 3)
    assert metrics.sharpe is not None


def test_metrics_are_empty_without_equity_points() -> None:
    metrics = calculate_metrics([], [])

    assert metrics.return_pct == 0.0
    assert metrics.pnl == 0.0
    assert metrics.max_drawdown == 0.0
    assert metrics.sharpe is None
    assert metrics.win_rate is None
