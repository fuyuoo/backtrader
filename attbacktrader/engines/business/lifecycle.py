"""Business-level execution lifecycle state for strategy runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class LifecycleState(str, Enum):
    FLAT = "FLAT"
    ENTRY_LOCKED_T1 = "ENTRY_LOCKED_T1"
    OPEN_ADDABLE = "OPEN_ADDABLE"
    OPEN_NO_ADD_ON = "OPEN_NO_ADD_ON"
    EXIT_WATCH = "EXIT_WATCH"
    PENDING_FULL_EXIT = "PENDING_FULL_EXIT"
    CLOSED = "CLOSED"
    OPEN_AT_END = "OPEN_AT_END"


class ScaleOutStage(str, Enum):
    FIVE_PERCENT = "FIVE_PERCENT"
    FIFTEEN_PERCENT = "FIFTEEN_PERCENT"


@dataclass(frozen=True)
class LifecycleLot:
    trade_date: date
    quantity: int
    price: float


@dataclass(frozen=True)
class LifecycleExecutionEvent:
    trade_date: date
    symbol: str
    side: str
    status: str
    reason_code: str
    requested_quantity: int
    executed_quantity: int
    price: float
    blocked_by: str | None = None
    position_quantity_after: int | None = None
    remaining_cost_value_after: float | None = None
    remaining_cost_basis_after: float | None = None
    cost_recovered_after: bool | None = None

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"


@dataclass(frozen=True)
class LifecycleClosedTrade:
    symbol: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    quantity: int
    exit_reason: str
    original_entry_price: float | None = None
    remaining_cost_basis_at_exit: float | None = None
    entry_quantity: int | None = None


@dataclass(frozen=True)
class LifecycleEndRunResult:
    end_date: date
    symbol: str
    open_position_excluded_quantity: int
    forced_exit_event: LifecycleExecutionEvent | None = None


@dataclass(frozen=True)
class LifecyclePositionSnapshot:
    trade_date: date
    symbol: str
    state: LifecycleState
    total_quantity: int
    sellable_quantity: int
    adjusted_remaining_cost_basis: float | None
    ever_profitable: bool
    cost_recovered: bool
    pending_exit_reason: str | None = None


class ExecutionLifecycleComponent:
    def __init__(self, *, symbol: str, board_lot_size: int = 100) -> None:
        if not symbol:
            raise ValueError("symbol cannot be empty")
        if board_lot_size <= 0:
            raise ValueError("board_lot_size must be positive")

        self.symbol = symbol
        self.board_lot_size = board_lot_size
        self.state = LifecycleState.FLAT
        self._lots: list[LifecycleLot] = []
        self._remaining_cost_value = 0.0
        self._completed_scale_out_stages: set[ScaleOutStage] = set()
        self._closed_trades: list[LifecycleClosedTrade] = []
        self._primary_entry_date: date | None = None
        self._primary_entry_price: float | None = None
        self._total_entry_quantity = 0
        self.pending_exit_reason: str | None = None
        self.ever_profitable = False
        self.cost_recovered = False

    @property
    def total_quantity(self) -> int:
        return sum(lot.quantity for lot in self._lots)

    @property
    def adjusted_remaining_cost_basis(self) -> float | None:
        if self.total_quantity <= 0:
            return None
        return self._remaining_cost_value / self.total_quantity

    @property
    def closed_trades_count(self) -> int:
        return len(self._closed_trades)

    @property
    def closed_trades(self) -> tuple[LifecycleClosedTrade, ...]:
        return tuple(self._closed_trades)

    def snapshot(self, *, trade_date: date) -> LifecyclePositionSnapshot:
        return LifecyclePositionSnapshot(
            trade_date=trade_date,
            symbol=self.symbol,
            state=self.state,
            total_quantity=self.total_quantity,
            sellable_quantity=self.sellable_quantity(trade_date),
            adjusted_remaining_cost_basis=self.adjusted_remaining_cost_basis,
            ever_profitable=self.ever_profitable,
            cost_recovered=self.cost_recovered,
            pending_exit_reason=self.pending_exit_reason,
        )

    def buy(self, *, trade_date: date, price: float, quantity: int, reason_code: str) -> LifecycleExecutionEvent:
        quantity = self._round_down_to_board_lot(quantity)
        if quantity <= 0:
            return LifecycleExecutionEvent(
                trade_date=trade_date,
                symbol=self.symbol,
                side="buy",
                status="rejected",
                reason_code=reason_code,
                requested_quantity=quantity,
                executed_quantity=0,
                price=price,
                blocked_by="BOARD_LOT_TOO_SMALL",
                **self._event_position_state(),
            )

        if self.total_quantity <= 0:
            self._primary_entry_date = trade_date
            self._primary_entry_price = price
            self._total_entry_quantity = 0
        self._lots.append(LifecycleLot(trade_date=trade_date, quantity=quantity, price=price))
        self._remaining_cost_value += quantity * price
        self._total_entry_quantity += quantity
        self.state = LifecycleState.ENTRY_LOCKED_T1
        return LifecycleExecutionEvent(
            trade_date=trade_date,
            symbol=self.symbol,
            side="buy",
            status="accepted",
            reason_code=reason_code,
            requested_quantity=quantity,
            executed_quantity=quantity,
            price=price,
            **self._event_position_state(),
        )

    def sellable_quantity(self, trade_date: date) -> int:
        return sum(lot.quantity for lot in self._lots if lot.trade_date < trade_date)

    def advance_day(self, *, trade_date: date, close_price: float) -> None:
        if self.state in {LifecycleState.FLAT, LifecycleState.CLOSED, LifecycleState.PENDING_FULL_EXIT}:
            return
        if self.total_quantity <= 0:
            self.state = LifecycleState.FLAT
            return
        cost_basis = self.adjusted_remaining_cost_basis
        if cost_basis is not None and close_price > cost_basis:
            self.ever_profitable = True
        if any(lot.trade_date == trade_date for lot in self._lots):
            self.state = LifecycleState.ENTRY_LOCKED_T1
            return
        if self.sellable_quantity(trade_date) <= 0:
            self.state = LifecycleState.ENTRY_LOCKED_T1
            return
        self.state = LifecycleState.OPEN_NO_ADD_ON if self.ever_profitable or self.cost_recovered else LifecycleState.OPEN_ADDABLE

    def can_add_on(self, trade_date: date) -> bool:
        return self.state == LifecycleState.OPEN_ADDABLE and self.sellable_quantity(trade_date) > 0

    def can_scale_out(self, trade_date: date) -> bool:
        return self.state == LifecycleState.OPEN_NO_ADD_ON and self.sellable_quantity(trade_date) > 0

    def can_full_exit(self, trade_date: date) -> bool:
        return self.state == LifecycleState.EXIT_WATCH and self.sellable_quantity(trade_date) > 0

    def enter_exit_watch(self, *, trade_date: date, reason_code: str) -> None:
        if self.total_quantity > 0 and self.state != LifecycleState.PENDING_FULL_EXIT:
            self.state = LifecycleState.EXIT_WATCH

    def confirm_full_exit(
        self,
        *,
        trade_date: date,
        price: float,
        reason_code: str,
        blocked_by: str | None = None,
    ) -> LifecycleExecutionEvent:
        requested_quantity = self.total_quantity
        if blocked_by is not None:
            self.state = LifecycleState.PENDING_FULL_EXIT
            self.pending_exit_reason = reason_code
            return self._rejected_sell_event(
                trade_date=trade_date,
                price=price,
                requested_quantity=requested_quantity,
                reason_code=reason_code,
                blocked_by=blocked_by,
            )
        executable_quantity = self.sellable_quantity(trade_date)
        executable_quantity = self._round_down_to_board_lot(executable_quantity)
        if executable_quantity <= 0:
            self.state = LifecycleState.PENDING_FULL_EXIT
            self.pending_exit_reason = reason_code
            return self._rejected_sell_event(
                trade_date=trade_date,
                price=price,
                requested_quantity=requested_quantity,
                reason_code=reason_code,
                blocked_by="T_PLUS_ONE_SELL_BLOCKED",
            )

        entry_date = self._entry_date(fallback=trade_date)
        original_entry_price = self._primary_entry_price
        closing_cost_basis = self.adjusted_remaining_cost_basis
        entry_price = original_entry_price if original_entry_price is not None else closing_cost_basis or 0.0
        entry_quantity = self._total_entry_quantity or requested_quantity
        self._remove_quantity_from_lots(executable_quantity, trade_date=trade_date)
        self._remaining_cost_value = max(0.0, self._remaining_cost_value - executable_quantity * price)
        if self.total_quantity <= 0:
            self._closed_trades.append(
                LifecycleClosedTrade(
                    symbol=self.symbol,
                    entry_date=entry_date,
                    exit_date=trade_date,
                    entry_price=entry_price,
                    exit_price=price,
                    quantity=executable_quantity,
                    exit_reason=reason_code,
                    original_entry_price=entry_price,
                    remaining_cost_basis_at_exit=closing_cost_basis,
                    entry_quantity=entry_quantity,
                )
            )
            self._remaining_cost_value = 0.0
            self._primary_entry_date = None
            self._primary_entry_price = None
            self._total_entry_quantity = 0
            self.state = LifecycleState.CLOSED
            self.pending_exit_reason = None
        else:
            self.state = LifecycleState.PENDING_FULL_EXIT
            self.pending_exit_reason = reason_code
        return LifecycleExecutionEvent(
            trade_date=trade_date,
            symbol=self.symbol,
            side="sell",
            status="accepted",
            reason_code=reason_code,
            requested_quantity=requested_quantity,
            executed_quantity=executable_quantity,
            price=price,
            **self._event_position_state(),
        )

    def retry_pending_exit(
        self,
        *,
        trade_date: date,
        price: float,
        blocked_by: str | None = None,
    ) -> LifecycleExecutionEvent:
        if self.state != LifecycleState.PENDING_FULL_EXIT:
            return self._rejected_sell_event(
                trade_date=trade_date,
                price=price,
                requested_quantity=self.total_quantity,
                reason_code=self.pending_exit_reason or "NO_PENDING_EXIT",
                blocked_by="NO_PENDING_EXIT",
            )
        return self.confirm_full_exit(
            trade_date=trade_date,
            price=price,
            reason_code=self.pending_exit_reason or "PENDING_FULL_EXIT",
            blocked_by=blocked_by,
        )

    def finish_run(
        self,
        *,
        end_date: date,
        price: float,
        reason_code: str,
        blocked_by: str | None = None,
    ) -> LifecycleEndRunResult:
        open_quantity = self.total_quantity
        if open_quantity <= 0:
            return LifecycleEndRunResult(end_date=end_date, symbol=self.symbol, open_position_excluded_quantity=0)

        self.state = LifecycleState.OPEN_AT_END
        if blocked_by is not None:
            return LifecycleEndRunResult(
                end_date=end_date,
                symbol=self.symbol,
                open_position_excluded_quantity=open_quantity,
                forced_exit_event=self._rejected_sell_event(
                    trade_date=end_date,
                    price=price,
                    requested_quantity=open_quantity,
                    reason_code=reason_code,
                    blocked_by=blocked_by,
                ),
            )

        entry_date = self._entry_date(fallback=end_date)
        original_entry_price = self._primary_entry_price
        closing_cost_basis = self.adjusted_remaining_cost_basis
        entry_price = original_entry_price if original_entry_price is not None else closing_cost_basis or 0.0
        entry_quantity = self._total_entry_quantity or open_quantity
        self._lots = []
        self._remaining_cost_value = 0.0
        self._primary_entry_date = None
        self._primary_entry_price = None
        self._total_entry_quantity = 0
        self._closed_trades.append(
            LifecycleClosedTrade(
                symbol=self.symbol,
                entry_date=entry_date,
                exit_date=end_date,
                entry_price=entry_price,
                exit_price=price,
                quantity=open_quantity,
                exit_reason=reason_code,
                original_entry_price=entry_price,
                remaining_cost_basis_at_exit=closing_cost_basis,
                entry_quantity=entry_quantity,
            )
        )
        self.state = LifecycleState.CLOSED
        return LifecycleEndRunResult(
            end_date=end_date,
            symbol=self.symbol,
            open_position_excluded_quantity=open_quantity,
            forced_exit_event=LifecycleExecutionEvent(
                trade_date=end_date,
                symbol=self.symbol,
                side="sell",
                status="accepted",
                reason_code=reason_code,
                requested_quantity=open_quantity,
                executed_quantity=open_quantity,
                price=price,
                **self._event_position_state(),
            ),
        )

    def scale_out(
        self,
        *,
        trade_date: date,
        price: float,
        stage: ScaleOutStage,
        reason_code: str,
    ) -> LifecycleExecutionEvent:
        if stage in self._completed_scale_out_stages:
            return self._rejected_sell_event(
                trade_date=trade_date,
                price=price,
                requested_quantity=0,
                reason_code=reason_code,
                blocked_by="SCALE_OUT_STAGE_ALREADY_COMPLETED",
            )

        requested_quantity = self._scale_out_target_quantity(stage)
        executable_quantity = min(requested_quantity, self.sellable_quantity(trade_date))
        executable_quantity = self._round_down_to_board_lot(executable_quantity)
        if executable_quantity <= 0:
            return self._rejected_sell_event(
                trade_date=trade_date,
                price=price,
                requested_quantity=requested_quantity,
                reason_code=reason_code,
                blocked_by="SCALE_OUT_TOO_SMALL",
            )

        self._remove_quantity_from_lots(executable_quantity, trade_date=trade_date)
        self._remaining_cost_value -= executable_quantity * price
        if self.total_quantity <= 0:
            self._remaining_cost_value = 0.0
            self.state = LifecycleState.CLOSED
        elif self._remaining_cost_value <= 0:
            self.cost_recovered = True
            self.state = LifecycleState.OPEN_NO_ADD_ON
        else:
            self.state = LifecycleState.OPEN_NO_ADD_ON
        self._completed_scale_out_stages.add(stage)
        return LifecycleExecutionEvent(
            trade_date=trade_date,
            symbol=self.symbol,
            side="sell",
            status="accepted",
            reason_code=reason_code,
            requested_quantity=requested_quantity,
            executed_quantity=executable_quantity,
            price=price,
            **self._event_position_state(),
        )

    def is_scale_out_stage_completed(self, stage: ScaleOutStage) -> bool:
        return stage in self._completed_scale_out_stages

    def _round_down_to_board_lot(self, quantity: int) -> int:
        return quantity - (quantity % self.board_lot_size)

    def _entry_date(self, *, fallback: date) -> date:
        if self._primary_entry_date is not None:
            return self._primary_entry_date
        if not self._lots:
            return fallback
        return min(lot.trade_date for lot in self._lots)

    def _scale_out_target_quantity(self, stage: ScaleOutStage) -> int:
        if stage == ScaleOutStage.FIVE_PERCENT:
            return self._round_down_to_board_lot(self.total_quantity // 3)
        return self._round_down_to_board_lot(self.total_quantity // 2)

    def _remove_quantity_from_lots(self, quantity: int, *, trade_date: date) -> None:
        remaining = quantity
        new_lots: list[LifecycleLot] = []
        for lot in self._lots:
            if remaining <= 0 or lot.trade_date >= trade_date:
                new_lots.append(lot)
                continue
            removed = min(lot.quantity, remaining)
            kept = lot.quantity - removed
            remaining -= removed
            if kept > 0:
                new_lots.append(LifecycleLot(trade_date=lot.trade_date, quantity=kept, price=lot.price))
        self._lots = new_lots

    def _rejected_sell_event(
        self,
        *,
        trade_date: date,
        price: float,
        requested_quantity: int,
        reason_code: str,
        blocked_by: str,
    ) -> LifecycleExecutionEvent:
        return LifecycleExecutionEvent(
            trade_date=trade_date,
            symbol=self.symbol,
            side="sell",
            status="rejected",
            reason_code=reason_code,
            requested_quantity=requested_quantity,
            executed_quantity=0,
            price=price,
            blocked_by=blocked_by,
            **self._event_position_state(),
        )

    def _event_position_state(self) -> dict[str, float | int | bool | None]:
        return {
            "position_quantity_after": self.total_quantity,
            "remaining_cost_value_after": self._remaining_cost_value if self.total_quantity > 0 else 0.0,
            "remaining_cost_basis_after": self.adjusted_remaining_cost_basis,
            "cost_recovered_after": self.cost_recovered,
        }
