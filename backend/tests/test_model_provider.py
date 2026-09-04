import json
from datetime import UTC, datetime

import httpx
import pytest

from app.models.provider import DemoModelProvider, OpenRouterModelProvider
from app.schemas import (
    MarketSnapshot,
    ModelProfile,
    PortfolioState,
    SymbolSnapshot,
)


def snapshot() -> MarketSnapshot:
    now = datetime(2026, 8, 3, 15, 0, tzinfo=UTC)
    return MarketSnapshot(
        as_of=now,
        status="LIVE",
        symbols=[
            SymbolSnapshot(
                symbol="NVDA",
                as_of=now,
                price=180.0,
                change_1d=0.03,
                change_1h=0.02,
                volume=1_000_000,
                sma_20=175.0,
                sma_50=170.0,
                rsi_14=62.0,
            ),
            SymbolSnapshot(
                symbol="SPY",
                as_of=now,
                price=600.0,
                change_1d=0.005,
                change_1h=0.001,
                volume=2_000_000,
                sma_20=598.0,
                sma_50=590.0,
                rsi_14=55.0,
            ),
        ],
    )


def profile(slug: str = "qwen") -> ModelProfile:
    return ModelProfile(
        slug=slug,
        name=slug.title(),
        color="#123456",
        provider_model_id=f"vendor/{slug}",
    )


def portfolio() -> PortfolioState:
    return PortfolioState(model_slug="qwen", cash=100_000.0, starting_cash=100_000.0, positions=[])


@pytest.mark.asyncio
async def test_openrouter_returns_validated_decision_and_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "vendor/qwen"
        assert body["temperature"] == 0
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "BUY",
                                    "symbol": "NVDA",
                                    "target_weight": 0.15,
                                    "confidence": 0.74,
                                    "reason": "Relative momentum is strongest.",
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 321, "completion_tokens": 45},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterModelProvider("secret", client=client)

    result = await provider.decide(profile(), snapshot(), portfolio())

    assert result.decision.action == "BUY"
    assert result.decision.symbol == "NVDA"
    assert result.prompt_tokens == 321
    assert result.completion_tokens == 45
    assert result.error is None
    await client.aclose()


@pytest.mark.asyncio
async def test_openrouter_repairs_one_malformed_response() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "not json"
        if calls == 2:
            content = json.dumps(
                {
                    "action": "HOLD",
                    "symbol": None,
                    "target_weight": None,
                    "confidence": 0.4,
                    "reason": "No valid opportunity.",
                }
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterModelProvider("secret", client=client)

    result = await provider.decide(profile(), snapshot(), portfolio())

    assert calls == 2
    assert result.decision.action == "HOLD"
    assert result.error is None
    await client.aclose()


@pytest.mark.asyncio
async def test_openrouter_failure_becomes_recorded_hold() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterModelProvider("secret", client=client)

    result = await provider.decide(profile(), snapshot(), portfolio())

    assert result.decision.action == "HOLD"
    assert result.error == "hosted model request timed out"
    await client.aclose()


@pytest.mark.asyncio
async def test_demo_models_produce_valid_model_specific_decisions() -> None:
    provider = DemoModelProvider()

    results = [
        await provider.decide(profile(slug), snapshot(), portfolio())
        for slug in ("qwen", "gemma", "phi", "llama")
    ]

    assert all(result.error is None for result in results)
    assert {result.decision.target_weight for result in results} == {0.08, 0.1, 0.12, 0.15}
