from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pandas as pd

from app.schemas import SymbolSnapshot


def _change(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None
    previous = float(close.iloc[-(periods + 1)])
    if previous == 0:
        return None
    return (float(close.iloc[-1]) / previous) - 1.0


def _sma(close: pd.Series, window: int) -> float | None:
    if len(close) < window:
        return None
    return float(close.iloc[-window:].mean())


def _rsi(close: pd.Series, window: int = 14) -> float | None:
    if len(close) <= window:
        return None
    delta = close.diff().dropna().iloc[-window:]
    gains = delta.clip(lower=0).mean()
    losses = -delta.clip(upper=0).mean()
    if losses == 0 and gains == 0:
        return 50.0
    if losses == 0:
        return 100.0
    relative_strength = float(gains / losses)
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _as_utc(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)
    return cast(datetime, timestamp.to_pydatetime())


def build_symbol_snapshot(frame: pd.DataFrame, symbol: str) -> SymbolSnapshot:
    required = {"Close", "Volume"}
    if frame.empty or not required.issubset(frame.columns):
        raise ValueError(f"{symbol} has no usable bars")

    usable = frame.dropna(subset=["Close"]).sort_index()
    if usable.empty:
        raise ValueError(f"{symbol} has no usable bars")
    close = usable["Close"].astype(float)

    return SymbolSnapshot(
        symbol=symbol,
        as_of=_as_utc(usable.index[-1]),
        price=float(close.iloc[-1]),
        change_1d=_change(close, 26),
        change_1h=_change(close, 4),
        volume=max(0, int(usable["Volume"].iloc[-1])),
        sma_20=_sma(close, 20),
        sma_50=_sma(close, 50),
        rsi_14=_rsi(close, 14),
    )
