from datetime import UTC

import pandas as pd
import pytest

from app.market.provider import YahooFinanceProvider, normalize_download


def make_frame(start: float) -> pd.DataFrame:
    index = pd.date_range("2026-08-03 13:30", periods=55, freq="15min", tz=UTC)
    values = [start + index_value for index_value in range(55)]
    return pd.DataFrame(
        {
            "Open": values,
            "High": [value + 1 for value in values],
            "Low": [value - 1 for value in values],
            "Close": values,
            "Volume": [1_000_000] * 55,
        },
        index=index,
    )


def test_normalize_download_splits_ticker_first_multi_index() -> None:
    raw = pd.concat({"AAPL": make_frame(100), "MSFT": make_frame(200)}, axis=1)

    result = normalize_download(raw, ["AAPL", "MSFT"])

    assert list(result) == ["AAPL", "MSFT"]
    assert list(result["AAPL"].columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert result["MSFT"]["Close"].iloc[-1] == 254


@pytest.mark.asyncio
async def test_snapshot_uses_cached_history_and_marks_it_stale_after_failure() -> None:
    calls = 0
    raw = pd.concat({"AAPL": make_frame(100), "MSFT": make_frame(200)}, axis=1)

    def download(**_: object) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        if calls == 1:
            return raw
        raise RuntimeError("Yahoo unavailable")

    provider = YahooFinanceProvider(downloader=download, retries=1)
    live = await provider.get_snapshot(["AAPL", "MSFT"], "1mo", "15m")
    stale = await provider.get_snapshot(["AAPL", "MSFT"], "1mo", "15m")

    assert live.status == "LIVE"
    assert stale.status == "STALE"
    assert stale.symbols[0].price == live.symbols[0].price


@pytest.mark.asyncio
async def test_snapshot_raises_when_download_fails_without_cache() -> None:
    def download(**_: object) -> pd.DataFrame:
        raise RuntimeError("Yahoo unavailable")

    provider = YahooFinanceProvider(downloader=download, retries=1)

    with pytest.raises(RuntimeError, match="Yahoo unavailable"):
        await provider.get_snapshot(["AAPL"], "1mo", "15m")


@pytest.mark.asyncio
async def test_download_does_not_enable_optional_scipy_price_repair() -> None:
    raw = make_frame(100)

    def download(**options: object) -> pd.DataFrame:
        assert options["repair"] is False
        return raw

    provider = YahooFinanceProvider(downloader=download, retries=1)

    result = await provider.get_history(["AAPL"], "1mo", "15m")

    assert result["AAPL"]["Close"].iloc[-1] == 154
