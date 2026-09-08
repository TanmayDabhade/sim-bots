from __future__ import annotations

import json

from app.schemas import MarketSnapshot, ModelDecision, PortfolioState

SYSTEM_PROMPT = """You manage a simulated long-only stock portfolio in a model competition.
Evaluate intraday opportunities on each cycle using the supplied market indicators
and your current portfolio. Seek profitable trades while preserving capital;
HOLD when the data does not justify changing a position. Do not invent news or prices.
Choose exactly one action: BUY, SELL, or HOLD. BUY and SELL express a desired
portfolio target weight between 0 and 0.20. You may use only the supplied
symbols and data. No leverage or shorting is permitted. BUY must increase a
position; SELL must reduce an existing position. A target of zero exits it.
Changes smaller than 2% of portfolio equity are rejected. Simulated execution
applies 0.03% adverse slippage. Observe the supplied daily trade budget.
For HOLD, set symbol and target_weight to null. Return only JSON matching
decision_schema, including confidence between 0 and 1 and a reason under 500
characters that cites the supplied evidence."""


def build_messages(snapshot: MarketSnapshot, portfolio: PortfolioState) -> list[dict[str, str]]:
    payload = {
        "market": snapshot.model_dump(mode="json"),
        "portfolio": portfolio.model_dump(mode="json"),
        "decision_schema": ModelDecision.model_json_schema(),
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Make one decision from this point-in-time state:\n"
            + json.dumps(payload, separators=(",", ":")),
        },
    ]
