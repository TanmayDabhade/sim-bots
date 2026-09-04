from __future__ import annotations

from app.schemas import FillResult, OrderIntent, PortfolioState, PositionState

SLIPPAGE = 0.0003


def apply_fill(portfolio: PortfolioState, intent: OrderIntent, market_price: float) -> FillResult:
    updated = portfolio.model_copy(deep=True)
    position = updated.position_for(intent.symbol)

    if intent.side == "BUY":
        fill_price = market_price * (1.0 + SLIPPAGE)
        cost = intent.quantity * fill_price
        if cost > updated.cash + 1e-8:
            raise ValueError("buy cost exceeds cash")
        old_quantity = 0.0 if position is None else position.quantity
        old_cost = 0.0 if position is None else position.quantity * position.avg_cost
        new_quantity = old_quantity + intent.quantity
        average_cost = (old_cost + cost) / new_quantity
        updated.cash -= cost
        if position is None:
            updated.positions.append(
                PositionState(
                    symbol=intent.symbol,
                    quantity=new_quantity,
                    avg_cost=average_cost,
                    current_price=market_price,
                )
            )
        else:
            position.quantity = new_quantity
            position.avg_cost = average_cost
            position.current_price = market_price
        return FillResult(portfolio=updated, fill_price=fill_price, realized_pnl=0.0)

    if position is None or intent.quantity > position.quantity + 1e-8:
        raise ValueError("sell quantity exceeds position")
    fill_price = market_price * (1.0 - SLIPPAGE)
    proceeds = intent.quantity * fill_price
    realized_pnl = (fill_price - position.avg_cost) * intent.quantity
    updated.cash += proceeds
    position.quantity -= intent.quantity
    position.current_price = market_price
    if position.quantity <= 1e-8:
        updated.positions = [item for item in updated.positions if item.symbol != intent.symbol]
    return FillResult(portfolio=updated, fill_price=fill_price, realized_pnl=realized_pnl)
