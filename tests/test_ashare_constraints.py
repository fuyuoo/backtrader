from datetime import date

import pytest

from attbacktrader.constraints import (
    AShareMarketState,
    ChinaAShareConstraintSet,
    ConstraintBlockReason,
    ExecutionRequest,
    OrderSide,
)


TRADE_DATE = date(2024, 1, 2)


def request(side: OrderSide = OrderSide.BUY, quantity: int = 200, price: float = 10.0) -> ExecutionRequest:
    return ExecutionRequest(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        side=side,
        quantity=quantity,
        price=price,
    )


def market_state(**kwargs: bool) -> AShareMarketState:
    return AShareMarketState(symbol="000001.SZ", trade_date=TRADE_DATE, **kwargs)


def test_accepts_board_lot_buy_with_enough_cash() -> None:
    decision = ChinaAShareConstraintSet().evaluate(
        request(quantity=200, price=10.0),
        market_state=market_state(),
        available_cash=3000.0,
    )

    assert decision.accepted is True
    assert decision.rejected is False
    assert decision.requested_quantity == 200
    assert decision.executable_quantity == 200
    assert decision.required_cash == 2000.0
    assert decision.blocked_by == ()


def test_rejects_suspended_stock() -> None:
    decision = ChinaAShareConstraintSet().evaluate(
        request(quantity=200),
        market_state=market_state(is_suspended=True),
        available_cash=3000.0,
    )

    assert decision.rejected is True
    assert decision.executable_quantity == 0
    assert decision.blocked_by == (ConstraintBlockReason.SUSPENDED,)


def test_rejects_buy_when_limit_up() -> None:
    decision = ChinaAShareConstraintSet().evaluate(
        request(side=OrderSide.BUY),
        market_state=market_state(is_limit_up=True),
        available_cash=3000.0,
    )

    assert decision.rejected is True
    assert ConstraintBlockReason.LIMIT_UP_BUY_BLOCKED in decision.blocked_by


def test_rejects_sell_when_limit_down() -> None:
    decision = ChinaAShareConstraintSet().evaluate(
        request(side=OrderSide.SELL),
        market_state=market_state(is_limit_down=True),
        available_cash=0.0,
    )

    assert decision.rejected is True
    assert ConstraintBlockReason.LIMIT_DOWN_SELL_BLOCKED in decision.blocked_by


def test_rejects_t_plus_one_same_day_sell() -> None:
    decision = ChinaAShareConstraintSet().evaluate(
        request(side=OrderSide.SELL, quantity=200, price=10.0),
        market_state=market_state(),
        available_cash=0.0,
    )

    assert decision.accepted is True

    same_day_sell = ChinaAShareConstraintSet().evaluate(
        ExecutionRequest(
            symbol="000001.SZ",
            trade_date=TRADE_DATE,
            side=OrderSide.SELL,
            quantity=200,
            price=10.0,
            position_open_date=TRADE_DATE,
        ),
        market_state=market_state(),
        available_cash=0.0,
    )

    assert same_day_sell.rejected is True
    assert ConstraintBlockReason.T_PLUS_ONE_SELL_BLOCKED in same_day_sell.blocked_by


def test_rejects_quantity_below_board_lot() -> None:
    decision = ChinaAShareConstraintSet().evaluate(
        request(quantity=99),
        market_state=market_state(),
        available_cash=3000.0,
    )

    assert decision.rejected is True
    assert decision.executable_quantity == 0
    assert decision.blocked_by == (ConstraintBlockReason.BOARD_LOT_TOO_SMALL,)


def test_rejects_buy_when_cash_cannot_afford_one_board_lot() -> None:
    decision = ChinaAShareConstraintSet().evaluate(
        request(quantity=200, price=10.0),
        market_state=market_state(),
        available_cash=999.99,
    )

    assert decision.rejected is True
    assert decision.executable_quantity == 0
    assert decision.blocked_by == (ConstraintBlockReason.CASH_NOT_ENOUGH,)


def test_rejects_buy_when_cash_can_only_partially_fill_request() -> None:
    decision = ChinaAShareConstraintSet().evaluate(
        request(quantity=300, price=10.0),
        market_state=market_state(),
        available_cash=2500.0,
    )

    assert decision.rejected is True
    assert decision.executable_quantity == 0
    assert decision.blocked_by == (ConstraintBlockReason.CASH_NOT_ENOUGH,)


def test_rejects_mismatched_market_state() -> None:
    other_state = AShareMarketState(symbol="600000.SH", trade_date=TRADE_DATE)

    with pytest.raises(ValueError, match="symbols"):
        ChinaAShareConstraintSet().evaluate(
            request(),
            market_state=other_state,
            available_cash=3000.0,
        )
