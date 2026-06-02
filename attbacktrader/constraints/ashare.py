"""China A-share trading constraints modeled in the business layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ConstraintBlockReason(str, Enum):
    SUSPENDED = "SUSPENDED"
    LIMIT_UP_BUY_BLOCKED = "LIMIT_UP_BUY_BLOCKED"
    LIMIT_DOWN_SELL_BLOCKED = "LIMIT_DOWN_SELL_BLOCKED"
    BOARD_LOT_TOO_SMALL = "BOARD_LOT_TOO_SMALL"
    CASH_NOT_ENOUGH = "CASH_NOT_ENOUGH"
    T_PLUS_ONE_SELL_BLOCKED = "T_PLUS_ONE_SELL_BLOCKED"


@dataclass(frozen=True)
class ExecutionRequest:
    symbol: str
    trade_date: date
    side: OrderSide
    quantity: int
    price: float
    position_open_date: date | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.price <= 0:
            raise ValueError("price must be positive")


@dataclass(frozen=True)
class AShareMarketState:
    symbol: str
    trade_date: date
    is_suspended: bool = False
    is_limit_up: bool = False
    is_limit_down: bool = False

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol cannot be empty")


@dataclass(frozen=True)
class ConstraintDecision:
    accepted: bool
    requested_quantity: int
    executable_quantity: int
    blocked_by: tuple[ConstraintBlockReason, ...] = ()
    required_cash: float = 0.0

    @property
    def rejected(self) -> bool:
        return not self.accepted


@dataclass(frozen=True)
class ChinaAShareConstraintSet:
    board_lot_size: int = 100
    t_plus_one: bool = True

    def __post_init__(self) -> None:
        if self.board_lot_size <= 0:
            raise ValueError("board_lot_size must be positive")

    def evaluate(
        self,
        request: ExecutionRequest,
        *,
        market_state: AShareMarketState,
        available_cash: float,
    ) -> ConstraintDecision:
        if request.symbol != market_state.symbol:
            raise ValueError("request and market_state symbols must match")
        if request.trade_date != market_state.trade_date:
            raise ValueError("request and market_state dates must match")
        if available_cash < 0:
            raise ValueError("available_cash cannot be negative")

        blocked_by: list[ConstraintBlockReason] = []
        executable_quantity = request.quantity

        if market_state.is_suspended:
            blocked_by.append(ConstraintBlockReason.SUSPENDED)

        if request.side == OrderSide.BUY and market_state.is_limit_up:
            blocked_by.append(ConstraintBlockReason.LIMIT_UP_BUY_BLOCKED)

        if request.side == OrderSide.SELL and market_state.is_limit_down:
            blocked_by.append(ConstraintBlockReason.LIMIT_DOWN_SELL_BLOCKED)

        if (
            self.t_plus_one
            and request.side == OrderSide.SELL
            and request.position_open_date == request.trade_date
        ):
            blocked_by.append(ConstraintBlockReason.T_PLUS_ONE_SELL_BLOCKED)

        executable_quantity = _round_down_to_board_lot(executable_quantity, self.board_lot_size)
        if executable_quantity <= 0:
            blocked_by.append(ConstraintBlockReason.BOARD_LOT_TOO_SMALL)

        required_cash = 0.0
        if request.side == OrderSide.BUY and executable_quantity > 0:
            max_affordable_quantity = _round_down_to_board_lot(
                int(available_cash // request.price),
                self.board_lot_size,
            )
            if max_affordable_quantity <= 0:
                blocked_by.append(ConstraintBlockReason.CASH_NOT_ENOUGH)
                executable_quantity = 0
            else:
                executable_quantity = min(executable_quantity, max_affordable_quantity)
                if executable_quantity < _round_down_to_board_lot(request.quantity, self.board_lot_size):
                    blocked_by.append(ConstraintBlockReason.CASH_NOT_ENOUGH)

            required_cash = executable_quantity * request.price

        accepted = not blocked_by
        if blocked_by:
            executable_quantity = 0
            required_cash = 0.0

        return ConstraintDecision(
            accepted=accepted,
            requested_quantity=request.quantity,
            executable_quantity=executable_quantity,
            blocked_by=tuple(blocked_by),
            required_cash=required_cash,
        )


def _round_down_to_board_lot(quantity: int, board_lot_size: int) -> int:
    return quantity - (quantity % board_lot_size)
