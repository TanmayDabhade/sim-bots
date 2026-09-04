from __future__ import annotations

import math
import statistics

from app.schemas import EquityPoint, PerformanceMetrics, TradeSummary


def calculate_metrics(
    equity_points: list[EquityPoint], trades: list[TradeSummary]
) -> PerformanceMetrics:
    if not equity_points:
        return PerformanceMetrics(
            return_pct=0.0,
            pnl=0.0,
            sharpe=None,
            max_drawdown=0.0,
            trade_count=len(trades),
            win_rate=None,
        )

    values = [point.equity for point in equity_points]
    start = values[0]
    end = values[-1]
    return_pct = 0.0 if start == 0 else (end / start) - 1.0

    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value / peak) - 1.0)

    interval_returns = [
        (current / previous) - 1.0
        for previous, current in zip(values, values[1:], strict=False)
        if previous != 0
    ]
    sharpe: float | None = None
    if len(interval_returns) >= 2:
        deviation = statistics.stdev(interval_returns)
        if deviation > 0:
            sharpe = statistics.mean(interval_returns) / deviation * math.sqrt(252)

    win_rate = None
    if trades:
        win_rate = sum(trade.realized_pnl > 0 for trade in trades) / len(trades)

    return PerformanceMetrics(
        return_pct=return_pct,
        pnl=end - start,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        trade_count=len(trades),
        win_rate=win_rate,
    )
