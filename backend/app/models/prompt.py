from __future__ import annotations

import json

from app.schemas import MarketSnapshot, PortfolioState

SYSTEM_PROMPT = """You manage a simulated long-only stock portfolio in a model competition.
Choose exactly one action: BUY, SELL, or HOLD. BUY and SELL express a desired
portfolio target weight between 0 and 0.20. You may use only the supplied
symbols and data. No leverage or shorting is permitted. Return only JSON that
matches the supplied schema. Keep the reason under 500 characters."""


def build_messages(snapshot: MarketSnapshot, portfolio: PortfolioState) -> list[dict[str, str]]:
    payload = {
        "market": snapshot.model_dump(mode="json"),
        "portfolio": portfolio.model_dump(mode="json"),
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Make one decision from this point-in-time state:\n"
            + json.dumps(payload, separators=(",", ":")),
        },
    ]
