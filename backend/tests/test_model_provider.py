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
        payload = json.loads(body["messages"][1]["content"].split("\n", 1)[1])
        schema = payload["decision_schema"]
        assert {"action", "confidence", "reason"} <= set(schema["required"])
        assert schema["properties"]["action"]["enum"] == ["BUY", "SELL", "HOLD"]
        assert "target_weight" in schema["properties"]
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
async def test_openrouter_retries_truncation_with_more_room_and_a_fresh_prompt() -> None:
    requests: list[dict] = []
    truncated = '{"action":"BUY","reason":"' + 'unfinished explanation ' * 80

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        content = truncated if len(requests) == 1 else json.dumps({
            "action": "BUY", "symbol": "NVDA", "target_weight": 0.15,
            "confidence": 0.74, "reason": "Relative momentum is strongest.",
        })
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "length" if len(requests) == 1 else "stop",
            "message": {"content": content},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenRouterModelProvider("secret", client=client).decide(
            profile(), snapshot(), portfolio(),
        )

    assert result.error is None
    assert result.decision.action == "BUY"
    assert len(requests) == 2
    assert requests[0]["max_tokens"] >= 1024
    assert requests[1]["max_tokens"] > requests[0]["max_tokens"]
    assert truncated not in json.dumps(requests[1]["messages"])
    assert all(message["role"] != "assistant" for message in requests[1]["messages"])


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    '{"action":"BUY","reason":"cut off',
    json.dumps({
        "action": "BUY", "symbol": "NVDA", "target_weight": 0.15,
        "confidence": 0.74, "reason": "Momentum is strongest.",
    }),
])
async def test_openrouter_never_accepts_a_length_limited_response(content: str) -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "length", "message": {"content": content},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenRouterModelProvider("secret", client=client).decide(
            profile(), snapshot(), portfolio(),
        )

    assert calls == 2
    assert result.decision.action == "HOLD"
    assert result.error == "Hosted model response exceeded its output limit after one retry."


@pytest.mark.asyncio
async def test_openrouter_invalid_retry_reports_a_short_error_without_raw_output() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop",
            "message": {"content": '"> // Corrected JSON response: still not valid'},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenRouterModelProvider("secret", client=client).decide(
            profile(), snapshot(), portfolio(),
        )

    assert calls == 2
    assert result.decision.action == "HOLD"
    assert result.error == "Hosted model returned an invalid decision after one retry."


@pytest.mark.asyncio
@pytest.mark.parametrize("choices", [[None], []])
async def test_openrouter_invalid_choices_become_hold(choices: list) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": choices})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenRouterModelProvider("secret", client=client).decide(
            profile(), snapshot(), portfolio(),
        )

    assert result.decision.action == "HOLD"
    assert result.error == "Hosted model returned an invalid decision after one retry."


@pytest.mark.asyncio
async def test_demo_models_produce_valid_model_specific_decisions() -> None:
    provider = DemoModelProvider()

    results = [
        await provider.decide(profile(slug), snapshot(), portfolio())
        for slug in ("qwen", "gemma", "phi", "llama")
    ]

    assert all(result.error is None for result in results)
    assert {result.decision.target_weight for result in results} == {0.08, 0.1, 0.12, 0.15}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        pytest.param(
            '```json\n{"action":"HOLD","symbol":null,"target_weight":null,'
            '"confidence":0.5,"reason":"Flat."}\n```',
            id="fenced-multiline",
        ),
        pytest.param(
            '```json {"action":"HOLD","symbol":null,"target_weight":null,'
            '"confidence":0.5,"reason":"Flat."} ```',
            id="fenced-single-line",
        ),
        pytest.param(
            'Let me think. RSI is 55, so nothing is compelling.\n'
            '{"action":"HOLD","symbol":null,"target_weight":null,'
            '"confidence":0.5,"reason":"Flat."}',
            id="prose-preamble",
        ),
        pytest.param(
            '<think>Compare {SPY} against {QQQ} first.</think>'
            '{"action":"HOLD","symbol":null,"target_weight":null,'
            '"confidence":0.5,"reason":"Flat."}',
            id="reasoning-block-with-braces",
        ),
        pytest.param(
            '{"action":"HOLD","symbol":null,"target_weight":null,'
            '"confidence":0.5,"reason":"Flat."}\nHope that helps!',
            id="trailing-prose",
        ),
    ],
)
async def test_openrouter_extracts_json_without_spending_a_repair(content: str) -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": content},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenRouterModelProvider("secret", client=client).decide(
            profile(), snapshot(), portfolio(),
        )

    assert calls == 1
    assert result.decision.action == "HOLD"
    assert result.error is None


@pytest.mark.asyncio
async def test_openrouter_normalizes_a_hold_that_carries_a_symbol() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({
                "action": "HOLD", "symbol": "SPY", "target_weight": 0,
                "confidence": 0.4, "reason": "Waiting for confirmation.",
            })},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenRouterModelProvider("secret", client=client).decide(
            profile(), snapshot(), portfolio(),
        )

    assert calls == 1
    assert result.error is None
    assert result.decision.action == "HOLD"
    assert result.decision.symbol is None
    assert result.decision.target_weight is None


@pytest.mark.asyncio
async def test_openrouter_does_not_restrict_routing_to_json_capable_providers() -> None:
    bodies: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({
                "action": "HOLD", "symbol": None, "target_weight": None,
                "confidence": 0.5, "reason": "Flat.",
            })},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await OpenRouterModelProvider("secret", client=client).decide(
            profile(), snapshot(), portfolio(),
        )

    assert "require_parameters" not in bodies[0]["provider"]


@pytest.mark.asyncio
async def test_openrouter_logs_the_response_body_behind_an_http_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={
            "error": {"message": "No allowed providers are available for the selected model."},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with caplog.at_level("WARNING"):
            result = await OpenRouterModelProvider("secret", client=client).decide(
                profile(), snapshot(), portfolio(),
            )

    assert result.decision.action == "HOLD"
    assert "No allowed providers" in caplog.text
    assert "vendor/qwen" in caplog.text


@pytest.mark.asyncio
async def test_openrouter_logs_raw_content_when_parsing_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop",
            "message": {"content": "I am unable to decide right now."},
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with caplog.at_level("WARNING"):
            result = await OpenRouterModelProvider("secret", client=client).decide(
                profile(), snapshot(), portfolio(),
            )

    assert result.error == "Hosted model returned an invalid decision after one retry."
    assert "I am unable to decide right now." in caplog.text
