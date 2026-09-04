from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from app.market.indicators import build_symbol_snapshot
from app.schemas import MarketSnapshot


def build_replay_snapshots(
    history: Mapping[str, pd.DataFrame], steps: int = 8
) -> list[MarketSnapshot]:
    if not history or steps < 1:
        return []
    common_index: pd.DatetimeIndex | None = None
    for frame in history.values():
        index = pd.DatetimeIndex(frame.index)
        common_index = index if common_index is None else common_index.intersection(index)
    if common_index is None or common_index.empty:
        return []

    timestamps = common_index.sort_values()[-steps:]
    snapshots: list[MarketSnapshot] = []
    for timestamp in timestamps:
        symbols = [
            build_symbol_snapshot(frame.loc[:timestamp], symbol)
            for symbol, frame in history.items()
        ]
        snapshots.append(
            MarketSnapshot(
                as_of=max(symbol.as_of for symbol in symbols),
                status="REPLAY",
                symbols=symbols,
            )
        )
    return snapshots


async def replay_history(
    service: object,
    history: Mapping[str, pd.DataFrame],
    steps: int = 8,
) -> list[object]:
    results = []
    for snapshot in build_replay_snapshots(history, steps):
        result = await service.run_once(snapshot.as_of, mode="replay", snapshot=snapshot)  # type: ignore[attr-defined]
        results.append(result)
    return results
