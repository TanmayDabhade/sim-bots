from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Literal

import pandas as pd
import yfinance as yf

from app.market.indicators import build_symbol_snapshot
from app.schemas import MarketSnapshot

DownloadFunction = Callable[..., pd.DataFrame]


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    wanted = ["Open", "High", "Low", "Close", "Volume"]
    available = [column for column in wanted if column in frame.columns]
    normalized = frame.loc[:, available].copy().dropna(how="all")
    index = pd.DatetimeIndex(normalized.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    normalized.index = index
    return normalized.sort_index()


def normalize_download(raw: pd.DataFrame, symbols: Sequence[str]) -> dict[str, pd.DataFrame]:
    if raw.empty:
        raise ValueError("Yahoo Finance returned no bars")
    result: dict[str, pd.DataFrame] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        first_level = set(raw.columns.get_level_values(0))
        second_level = set(raw.columns.get_level_values(1))
        for symbol in symbols:
            if symbol in first_level:
                result[symbol] = _normalize_frame(raw[symbol])
            elif symbol in second_level:
                result[symbol] = _normalize_frame(raw.xs(symbol, axis=1, level=1))
    elif len(symbols) == 1:
        result[symbols[0]] = _normalize_frame(raw)

    missing = [symbol for symbol in symbols if symbol not in result or result[symbol].empty]
    if missing:
        raise ValueError(f"Yahoo Finance returned no usable bars for: {', '.join(missing)}")
    return result


class YahooFinanceProvider:
    def __init__(
        self,
        downloader: DownloadFunction = yf.download,
        retries: int = 3,
    ) -> None:
        self._downloader = downloader
        self._retries = max(1, retries)
        self._cache: dict[str, pd.DataFrame] | None = None

    async def get_history(
        self, symbols: Sequence[str], period: str, interval: str
    ) -> dict[str, pd.DataFrame]:
        last_error: Exception | None = None
        for attempt in range(self._retries):
            try:
                raw = await asyncio.to_thread(
                    self._downloader,
                    tickers=list(symbols),
                    period=period,
                    interval=interval,
                    group_by="ticker",
                    auto_adjust=True,
                    repair=False,
                    threads=True,
                    progress=False,
                    timeout=15,
                )
                history = normalize_download(raw, symbols)
                self._cache = {symbol: frame.copy() for symbol, frame in history.items()}
                return history
            except Exception as exc:  # upstream failures vary by yfinance release
                last_error = exc
                if attempt + 1 < self._retries:
                    await asyncio.sleep(0.25 * (2**attempt))
        assert last_error is not None
        raise last_error

    async def get_snapshot(
        self, symbols: Sequence[str], period: str, interval: str
    ) -> MarketSnapshot:
        status: Literal["LIVE", "STALE"] = "LIVE"
        try:
            history = await self.get_history(symbols, period, interval)
        except Exception:
            if self._cache is None:
                raise
            history = self._cache
            status = "STALE"

        snapshots = [build_symbol_snapshot(history[symbol], symbol) for symbol in symbols]
        return MarketSnapshot(
            as_of=max(item.as_of for item in snapshots),
            status=status,
            symbols=snapshots,
        )

    @property
    def cached_history(self) -> dict[str, pd.DataFrame] | None:
        if self._cache is None:
            return None
        return {symbol: frame.copy() for symbol, frame in self._cache.items()}
