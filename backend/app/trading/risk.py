from __future__ import annotations

from app.schemas import ModelDecision, OrderIntent, PortfolioState, RiskResult

ALLOWED_SYMBOLS = {"SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "META", "TSLA", "JPM"}
MAX_TARGET_WEIGHT = 0.20
MIN_ALLOCATION_CHANGE = 0.02
MAX_DAILY_TRADES = 5
BUY_SLIPPAGE_MULTIPLIER = 1.0003


def _rejected(reason: str) -> RiskResult:
    return RiskResult(approved=False, reason=reason)


def evaluate_decision(
    decision: ModelDecision,
    portfolio: PortfolioState,
    price: float | None,
    trade_count: int,
) -> RiskResult:
    if decision.action == "HOLD":
        return _rejected("model chose HOLD")
    if trade_count >= MAX_DAILY_TRADES:
        return _rejected("daily trade limit reached")
    if decision.symbol not in ALLOWED_SYMBOLS:
        return _rejected("symbol is outside the arena")
    if decision.target_weight is None or decision.target_weight > MAX_TARGET_WEIGHT:
        return _rejected("target weight exceeds 20%")
    if price is None or price <= 0:
        return _rejected("market price is unavailable")

    symbol = decision.symbol
    position = portfolio.position_for(symbol)
    current_value = 0.0 if position is None else position.quantity * price
    target_value = portfolio.equity * decision.target_weight
    delta_value = target_value - current_value

    if decision.action == "SELL" and position is None:
        return _rejected("cannot sell an empty position")
    if abs(delta_value) / portfolio.equity < MIN_ALLOCATION_CHANGE:
        return _rejected("allocation change is below 2%")
    if decision.action == "BUY" and delta_value < 0:
        return _rejected("BUY would reduce the position")
    if decision.action == "SELL" and delta_value > 0:
        return _rejected("SELL would increase the position")

    side = decision.action
    desired_quantity = abs(delta_value) / price
    if side == "BUY":
        affordable_quantity = portfolio.cash / (price * BUY_SLIPPAGE_MULTIPLIER)
        quantity = min(desired_quantity, affordable_quantity)
    else:
        quantity = min(desired_quantity, 0.0 if position is None else position.quantity)
    if quantity <= 0:
        return _rejected("order has no executable quantity")

    return RiskResult(
        approved=True,
        reason="approved",
        intent=OrderIntent(
            side=side,
            symbol=symbol,
            quantity=quantity,
            target_weight=decision.target_weight,
            reference_price=price,
        ),
    )
