from __future__ import annotations

import json
import time
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.models.prompt import build_messages
from app.schemas import (
    MarketSnapshot,
    ModelCallResult,
    ModelDecision,
    ModelProfile,
    PortfolioState,
    SymbolSnapshot,
)


class ModelProvider(Protocol):
    async def decide(
        self,
        profile: ModelProfile,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
    ) -> ModelCallResult: ...


def _hold(reason: str, error: str | None = None, latency_ms: int = 0) -> ModelCallResult:
    return ModelCallResult(
        decision=ModelDecision(
            action="HOLD",
            symbol=None,
            target_weight=None,
            confidence=0.0,
            reason=reason,
        ),
        latency_ms=latency_ms,
        error=error,
    )


def _content_as_json(content: Any) -> str:
    if isinstance(content, dict):
        return json.dumps(content)
    if not isinstance(content, str):
        raise ValueError("model response content is not text or JSON")
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1])
        if stripped.lstrip().startswith("json"):
            stripped = stripped.lstrip()[4:].lstrip()
    return stripped


class OpenRouterModelProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=60.0)

    async def _request(self, model_id: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": model_id,
                "messages": messages,
                "temperature": 0,
                "max_tokens": 300,
                # All four configured OpenRouter models support JSON mode. Some
                # providers do not enforce JSON Schema, so validation remains
                # local and malformed responses receive one repair attempt.
                "response_format": {"type": "json_object"},
                "provider": {"require_parameters": True, "allow_fallbacks": True},
            },
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return body

    async def decide(
        self,
        profile: ModelProfile,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
    ) -> ModelCallResult:
        if not self._api_key:
            return _hold(
                "Hosted inference is not configured.",
                error="OPENROUTER_API_KEY is missing",
            )
        started = time.perf_counter()
        messages = build_messages(snapshot, portfolio)
        try:
            body = await self._request(profile.provider_model_id, messages)
            content = body["choices"][0]["message"]["content"]
            try:
                decision = ModelDecision.model_validate_json(_content_as_json(content))
            except (ValidationError, ValueError, json.JSONDecodeError):
                repair_messages = [
                    *messages,
                    {"role": "assistant", "content": str(content)},
                    {
                        "role": "user",
                        "content": (
                            "Repair the response. Return only valid JSON matching the schema."
                        ),
                    },
                ]
                body = await self._request(profile.provider_model_id, repair_messages)
                content = body["choices"][0]["message"]["content"]
                decision = ModelDecision.model_validate_json(_content_as_json(content))

            usage = body.get("usage") or {}
            return ModelCallResult(
                decision=decision,
                latency_ms=int((time.perf_counter() - started) * 1000),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )
        except httpx.TimeoutException:
            elapsed = int((time.perf_counter() - started) * 1000)
            return _hold(
                "The hosted model timed out, so no trade was placed.",
                error="hosted model request timed out",
                latency_ms=elapsed,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValidationError, ValueError) as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return _hold(
                "The hosted model returned an unusable response, so no trade was placed.",
                error=f"hosted model failure: {exc}",
                latency_ms=elapsed,
            )


class DemoModelProvider:
    target_weights = {"qwen": 0.15, "gemma": 0.12, "phi": 0.10, "llama": 0.08}

    def _pick_symbol(self, slug: str, symbols: list[SymbolSnapshot]) -> SymbolSnapshot:
        if slug == "qwen":
            return max(symbols, key=lambda item: item.change_1h or -999.0)
        if slug == "gemma":
            return min(symbols, key=lambda item: item.rsi_14 if item.rsi_14 is not None else 50.0)
        if slug == "phi":
            return max(
                symbols,
                key=lambda item: item.price / item.sma_50 if item.sma_50 else 0.0,
            )
        return next((item for item in symbols if item.symbol == "SPY"), symbols[0])

    async def decide(
        self,
        profile: ModelProfile,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
    ) -> ModelCallResult:
        selected = self._pick_symbol(profile.slug, snapshot.symbols)
        target = self.target_weights[profile.slug]
        position = portfolio.position_for(selected.symbol)
        current_weight = 0.0 if position is None else position.market_value / portfolio.equity
        if selected.change_1h is not None and selected.change_1h < -0.01 and position is not None:
            decision = ModelDecision(
                action="SELL",
                symbol=selected.symbol,
                target_weight=0.0,
                confidence=0.62,
                reason="Demo rule exits after a sharp one-hour reversal.",
            )
        elif abs(current_weight - target) < 0.02:
            decision = ModelDecision(
                action="HOLD",
                symbol=None,
                target_weight=None,
                confidence=0.58,
                reason="Demo allocation is already near its target.",
            )
        else:
            decision = ModelDecision(
                action="BUY",
                symbol=selected.symbol,
                target_weight=target,
                confidence=0.66,
                reason=f"Demo rule selected {selected.symbol} from price and trend indicators.",
            )
        return ModelCallResult(decision=decision, latency_ms=0)
