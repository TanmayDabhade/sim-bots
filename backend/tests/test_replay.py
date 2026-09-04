from datetime import UTC

import pandas as pd

from app.arena.replay import build_replay_snapshots


def history(last_price: float) -> dict[str, pd.DataFrame]:
    index = pd.date_range("2026-08-03 13:30", periods=55, freq="15min", tz=UTC)
    closes = [100.0 + value for value in range(54)] + [last_price]
    frame = pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": [1000] * 55,
        },
        index=index,
    )
    return {"SPY": frame, "NVDA": frame.copy()}


def test_replay_snapshot_never_reads_a_future_bar() -> None:
    normal = build_replay_snapshots(history(154.0), steps=2)
    changed_future = build_replay_snapshots(history(10_000.0), steps=2)

    assert normal[0].symbols[0].price == 153.0
    assert changed_future[0].symbols[0].price == 153.0
    assert changed_future[1].symbols[0].price == 10_000.0
    assert all(snapshot.status == "REPLAY" for snapshot in changed_future)
