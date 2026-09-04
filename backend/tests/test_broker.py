import pytest

from app.schemas import OrderIntent, PortfolioState, PositionState
from app.trading.broker import apply_fill


def test_buy_fill_applies_adverse_slippage_and_updates_average_cost() -> None:
    portfolio = PortfolioState(
        model_slug="qwen", cash=100_000.0, starting_cash=100_000.0, positions=[]
    )
    intent = OrderIntent(
        side="BUY", symbol="NVDA", quantity=100.0, target_weight=0.1, reference_price=100.0
    )

    result = apply_fill(portfolio, intent, market_price=100.0)

    assert result.fill_price == pytest.approx(100.03)
    assert result.portfolio.cash == pytest.approx(89_997.0)
    assert result.portfolio.positions[0].quantity == 100.0
    assert result.portfolio.positions[0].avg_cost == pytest.approx(100.03)
    assert result.realized_pnl == 0.0


def test_sell_fill_applies_adverse_slippage_and_realizes_profit() -> None:
    portfolio = PortfolioState(
        model_slug="qwen",
        cash=91_000.0,
        starting_cash=100_000.0,
        positions=[
            PositionState(symbol="NVDA", quantity=100.0, avg_cost=90.0, current_price=100.0)
        ],
    )
    intent = OrderIntent(
        side="SELL", symbol="NVDA", quantity=40.0, target_weight=0.06, reference_price=100.0
    )

    result = apply_fill(portfolio, intent, market_price=100.0)

    assert result.fill_price == pytest.approx(99.97)
    assert result.portfolio.cash == pytest.approx(94_998.8)
    assert result.portfolio.positions[0].quantity == 60.0
    assert result.portfolio.positions[0].avg_cost == 90.0
    assert result.realized_pnl == pytest.approx(398.8)


def test_sell_cannot_exceed_owned_quantity() -> None:
    portfolio = PortfolioState(
        model_slug="qwen",
        cash=91_000.0,
        starting_cash=100_000.0,
        positions=[PositionState(symbol="NVDA", quantity=10.0, avg_cost=90.0, current_price=100.0)],
    )
    intent = OrderIntent(
        side="SELL", symbol="NVDA", quantity=11.0, target_weight=0.0, reference_price=100.0
    )

    with pytest.raises(ValueError, match="sell quantity exceeds position"):
        apply_fill(portfolio, intent, market_price=100.0)
