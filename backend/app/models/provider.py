from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any, Protocol

import httpx

from app.models.prompt import build_messages
from app.schemas import (
    MarketSnapshot,
    ModelCallResult,
    ModelDecision,
    ModelProfile,
    PortfolioState,
    SymbolSnapshot,
)

_LOGGER = logging.getLogger(__name__)
_LOG_EXCERPT_LIMIT = 500


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


def _json_object_candidates(text: str) -> Iterator[str]:
    """Yield each balanced ``{...}`` span, ignoring braces inside string literals."""
    index = 0
    while (start := text.find("{", index)) != -1:
        depth = 0
        in_string = False
        escaped = False
        end = -1
        for position in range(start, len(text)):
            char = text[position]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = position
                    break
        if end == -1:
            return
        yield text[start : end + 1]
        index = end + 1


def _content_as_json(content: Any) -> str:
    """Pull the decision object out of a reply that may carry prose or fences.

    A provider that does not honour ``response_format`` wraps the object in a
    code fence, or leads with reasoning before it. Scanning for the first
    balanced object carrying an ``action`` key survives both without spending a
    repair round trip, and skips a ``<think>`` block that contains its own
    braces.
    """
    if isinstance(content, dict):
        return json.dumps(content)
    if not isinstance(content, str):
        raise ValueError("model response content is not text or JSON")
    fallback: str | None = None
    for candidate in _json_object_candidates(content):
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if not isinstance(parsed, dict):
            continue
        if "action" in parsed:
            return candidate
        if fallback is None:
            fallback = candidate
    if fallback is None:
        raise ValueError("model response contains no complete JSON object")
    return fallback


def _response_content(body: dict[str, Any]) -> Any:
    """Best-effort read of the reply text, for logging a failure we could not parse."""
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, TypeError, IndexError):
        return None


def _for_log(content: Any) -> str:
    if content is None:
        return "<no content>"
    text = content if isinstance(content, str) else repr(content)
    return text[:_LOG_EXCERPT_LIMIT] + ("..." if len(text) > _LOG_EXCERPT_LIMIT else "")


class _TruncatedModelResponse(ValueError):
    pass


def _decision_from_response(body: dict[str, Any]) -> ModelDecision:
    choice = body["choices"][0]
    if not isinstance(choice, dict):
        raise ValueError("model response choice is not an object")
    # Never execute an answer the provider says it did not finish, even if its
    # content happens to be syntactically valid JSON.
    if choice.get("finish_reason") == "length":
        raise _TruncatedModelResponse("model output reached its token limit")
    return ModelDecision.model_validate_json(_content_as_json(choice["message"]["content"]))


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

    async def _request(
        self, model_id: str, messages: list[dict[str, str]], max_tokens: int = 1024,
    ) -> dict[str, Any]:
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": model_id,
                "messages": messages,
                "temperature": 0,
                "max_tokens": max_tokens,
                # JSON mode is a hint, not a guarantee: providers vary in whether
                # they enforce it, so validation stays local and a malformed
                # reply gets one repair attempt. Deliberately no
                # "require_parameters" here, since it drops every provider that
                # does not advertise JSON mode and can leave a small model with
                # no route at all, turning the whole cycle into a 404.
                "response_format": {"type": "json_object"},
                "provider": {"allow_fallbacks": True},
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
        last_content: Any = None
        try:
            try:
                body = await self._request(profile.provider_model_id, messages)
                last_content = _response_content(body)
                decision = _decision_from_response(body)
            except (ValueError, KeyError, TypeError, IndexError):
                # Start from the original state so malformed prose and partial
                # JSON do not become an assistant example for the next answer.
                repair_messages = [
                    messages[0],
                    {
                        "role": "user",
                        "content": messages[1]["content"] + (
                            "\n\nThe previous response was incomplete or invalid. "
                            "Make the decision again from the state above. Return exactly "
                            "one complete JSON object matching decision_schema. Use a short "
                            "reason under 240 characters. No comments, markdown, or preamble."
                        ),
                    },
                ]
                body = await self._request(
                    profile.provider_model_id, repair_messages, max_tokens=2048,
                )
                last_content = _response_content(body)
                decision = _decision_from_response(body)

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
        except _TruncatedModelResponse:
            elapsed = int((time.perf_counter() - started) * 1000)
            _LOGGER.warning(
                "%s hit its output limit twice; raising max_tokens or disabling "
                "reasoning output may be required",
                profile.provider_model_id,
            )
            return _hold(
                "The hosted model response was cut off, so no trade was placed.",
                error="Hosted model response exceeded its output limit after one retry.",
                latency_ms=elapsed,
            )
        except (KeyError, TypeError, ValueError, IndexError):
            elapsed = int((time.perf_counter() - started) * 1000)
            # provider_error is public API, so it stays short; the raw reply goes
            # to the log, where it is the only way to tell a schema violation
            # from prose that never contained a decision at all.
            _LOGGER.warning(
                "%s returned an unparsable decision; raw content: %s",
                profile.provider_model_id,
                _for_log(last_content),
            )
            return _hold(
                "The hosted model returned an unusable response, so no trade was placed.",
                error="Hosted model returned an invalid decision after one retry.",
                latency_ms=elapsed,
            )
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            # The status alone cannot distinguish a retired model id from a
            # routing rejection; OpenRouter explains which in the response body.
            response = getattr(exc, "response", None)
            if response is None:
                _LOGGER.warning("%s request failed: %s", profile.provider_model_id, exc)
            else:
                _LOGGER.warning(
                    "%s request failed: %s | response body: %s",
                    profile.provider_model_id,
                    exc,
                    _for_log(response.text),
                )
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
