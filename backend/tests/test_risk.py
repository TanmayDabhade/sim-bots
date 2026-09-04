from app.schemas import ModelDecision, PortfolioState, PositionState
from app.trading.risk import evaluate_decision


def empty_portfolio(cash: float = 100_000.0) -> PortfolioState:
    return PortfolioState(model_slug="qwen", cash=cash, starting_cash=100_000.0, positions=[])


def test_buy_target_weight_becomes_share_quantity() -> None:
    result = evaluate_decision(
        ModelDecision(
            action="BUY",
            symbol="NVDA",
            target_weight=0.15,
            confidence=0.8,
            reason="Momentum remains strong.",
        ),
        empty_portfolio(),
        price=100.0,
        trade_count=0,
    )

    assert result.approved is True
    assert result.intent is not None
    assert result.intent.side == "BUY"
    assert result.intent.quantity == 150.0


def test_weight_over_twenty_percent_is_rejected() -> None:
    decision = ModelDecision(
        action="BUY",
        symbol="NVDA",
        target_weight=0.21,
        confidence=0.8,
        reason="Too concentrated.",
    )

    result = evaluate_decision(decision, empty_portfolio(), price=100.0, trade_count=0)

    assert result.approved is False
    assert result.reason == "target weight exceeds 20%"


def test_allocation_change_below_two_percent_is_ignored() -> None:
    decision = ModelDecision(
        action="BUY",
        symbol="NVDA",
        target_weight=0.01,
        confidence=0.8,
        reason="Change is too small.",
    )

    result = evaluate_decision(decision, empty_portfolio(), price=100.0, trade_count=0)

    assert result.approved is False
    assert result.reason == "allocation change is below 2%"


def test_fifth_daily_trade_blocks_another_order() -> None:
    decision = ModelDecision(
        action="BUY",
        symbol="NVDA",
        target_weight=0.1,
        confidence=0.8,
        reason="Daily limit reached.",
    )

    result = evaluate_decision(decision, empty_portfolio(), price=100.0, trade_count=5)

    assert result.approved is False
    assert result.reason == "daily trade limit reached"


def test_sell_without_a_position_is_rejected() -> None:
    decision = ModelDecision(
        action="SELL",
        symbol="NVDA",
        target_weight=0.0,
        confidence=0.8,
        reason="Exit the position.",
    )

    result = evaluate_decision(decision, empty_portfolio(), price=100.0, trade_count=0)

    assert result.approved is False
    assert result.reason == "cannot sell an empty position"


def test_action_must_agree_with_target_weight_direction() -> None:
    portfolio = PortfolioState(
        model_slug="qwen",
        cash=90_000.0,
        starting_cash=100_000.0,
        positions=[
            PositionState(symbol="NVDA", quantity=100.0, avg_cost=90.0, current_price=100.0)
        ],
    )
    decision = ModelDecision(
        action="BUY",
        symbol="NVDA",
        target_weight=0.05,
        confidence=0.8,
        reason="Inconsistent direction.",
    )

    result = evaluate_decision(decision, portfolio, price=100.0, trade_count=0)

    assert result.approved is False
    assert result.reason == "BUY would reduce the position"


def test_hold_never_creates_an_order() -> None:
    decision = ModelDecision(
        action="HOLD",
        symbol=None,
        target_weight=None,
        confidence=0.5,
        reason="No setup is strong enough.",
    )

    result = evaluate_decision(decision, empty_portfolio(), price=None, trade_count=0)

    assert result.approved is False
    assert result.intent is None
    assert result.reason == "model chose HOLD"
