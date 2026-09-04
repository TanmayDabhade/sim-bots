from datetime import UTC

import pandas as pd
import pytest

from app.market.indicators import build_symbol_snapshot


def price_frame(rows: int = 50) -> pd.DataFrame:
    index = pd.date_range("2026-08-03 13:30", periods=rows, freq="15min", tz=UTC)
    return pd.DataFrame(
        {
            "Open": [float(value) for value in range(1, rows + 1)],
            "High": [float(value) + 0.5 for value in range(1, rows + 1)],
            "Low": [float(value) - 0.5 for value in range(1, rows + 1)],
            "Close": [float(value) for value in range(1, rows + 1)],
            "Volume": [1000 + value for value in range(rows)],
        },
        index=index,
    )


def test_snapshot_calculates_indicators_from_ordered_bars() -> None:
    snapshot = build_symbol_snapshot(price_frame(), "NVDA")

    assert snapshot.symbol == "NVDA"
    assert snapshot.price == 50.0
    assert snapshot.volume == 1049
    assert snapshot.sma_20 == 40.5
    assert snapshot.sma_50 == 25.5
    assert snapshot.change_1h == pytest.approx(0.0869565217)
    assert snapshot.change_1d == pytest.approx(1.0833333333)
    assert snapshot.rsi_14 == 100.0
    assert snapshot.as_of.tzinfo is not None


def test_snapshot_marks_indicators_unavailable_without_enough_bars() -> None:
    snapshot = build_symbol_snapshot(price_frame(10), "AAPL")

    assert snapshot.sma_20 is None
    assert snapshot.sma_50 is None
    assert snapshot.rsi_14 is None
    assert snapshot.change_1d is None


def test_snapshot_rejects_empty_frames() -> None:
    with pytest.raises(ValueError, match="AAPL has no usable bars"):
        build_symbol_snapshot(pd.DataFrame(), "AAPL")
