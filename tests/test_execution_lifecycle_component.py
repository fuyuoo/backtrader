from __future__ import annotations

from datetime import date

from attbacktrader.engines.business.lifecycle import ExecutionLifecycleComponent, LifecycleState, ScaleOutStage


SYMBOL = "000001.SZ"


def test_lgs_01_entry_locks_new_lot_for_t_plus_one() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    trade_date = date(2024, 1, 2)

    event = lifecycle.buy(
        trade_date=trade_date,
        price=10.0,
        quantity=300,
        reason_code="BAOMA_ENTRY",
    )

    assert event.accepted is True
    assert event.side == "buy"
    assert event.executed_quantity == 300
    assert lifecycle.state == LifecycleState.ENTRY_LOCKED_T1
    assert lifecycle.total_quantity == 300
    assert lifecycle.sellable_quantity(trade_date) == 0
    assert lifecycle.can_add_on(trade_date) is False
    assert lifecycle.can_scale_out(trade_date) is False
    assert lifecycle.can_full_exit(trade_date) is False


def test_lgs_02_add_on_moves_addable_position_back_to_t_plus_one_lock() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    entry_date = date(2024, 1, 2)
    add_on_date = date(2024, 1, 3)
    lifecycle.buy(trade_date=entry_date, price=10.0, quantity=300, reason_code="BAOMA_ENTRY")
    lifecycle.advance_day(trade_date=add_on_date, close_price=10.0)

    assert lifecycle.state == LifecycleState.OPEN_ADDABLE
    assert lifecycle.can_add_on(add_on_date) is True

    event = lifecycle.buy(
        trade_date=add_on_date,
        price=12.0,
        quantity=100,
        reason_code="BAOMA_ADD_ON",
    )

    assert event.accepted is True
    assert lifecycle.state == LifecycleState.ENTRY_LOCKED_T1
    assert lifecycle.total_quantity == 400
    assert lifecycle.sellable_quantity(add_on_date) == 300
    assert lifecycle.can_add_on(add_on_date) is False

    lifecycle.advance_day(trade_date=add_on_date, close_price=12.0)

    assert lifecycle.state == LifecycleState.ENTRY_LOCKED_T1
    assert lifecycle.can_scale_out(add_on_date) is False


def test_lgs_03_ever_profitable_position_permanently_disables_add_on() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    lifecycle.buy(
        trade_date=date(2024, 1, 2),
        price=10.0,
        quantity=300,
        reason_code="BAOMA_ENTRY",
    )

    lifecycle.advance_day(trade_date=date(2024, 1, 3), close_price=11.0)

    assert lifecycle.state == LifecycleState.OPEN_NO_ADD_ON
    assert lifecycle.ever_profitable is True
    assert lifecycle.can_add_on(date(2024, 1, 3)) is False

    lifecycle.advance_day(trade_date=date(2024, 1, 4), close_price=9.0)

    assert lifecycle.state == LifecycleState.OPEN_NO_ADD_ON
    assert lifecycle.ever_profitable is True
    assert lifecycle.can_add_on(date(2024, 1, 4)) is False


def test_lgs_04_scale_out_reduces_quantity_and_recomputes_remaining_cost_basis() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    lifecycle.buy(
        trade_date=date(2024, 1, 2),
        price=10.0,
        quantity=600,
        reason_code="BAOMA_ENTRY",
    )
    lifecycle.advance_day(trade_date=date(2024, 1, 3), close_price=11.0)

    first = lifecycle.scale_out(
        trade_date=date(2024, 1, 3),
        price=11.0,
        stage=ScaleOutStage.FIVE_PERCENT,
        reason_code="SCALE_OUT_5",
    )

    assert first.accepted is True
    assert first.executed_quantity == 200
    assert first.position_quantity_after == 400
    assert first.remaining_cost_basis_after == 9.5
    assert first.remaining_cost_value_after == 3800.0
    assert lifecycle.total_quantity == 400
    assert lifecycle.adjusted_remaining_cost_basis == 9.5
    assert lifecycle.is_scale_out_stage_completed(ScaleOutStage.FIVE_PERCENT) is True

    second = lifecycle.scale_out(
        trade_date=date(2024, 1, 4),
        price=12.0,
        stage=ScaleOutStage.FIFTEEN_PERCENT,
        reason_code="SCALE_OUT_15",
    )

    assert second.accepted is True
    assert second.executed_quantity == 200
    assert second.position_quantity_after == 200
    assert second.remaining_cost_basis_after == 7.0
    assert second.remaining_cost_value_after == 1400.0
    assert lifecycle.total_quantity == 200
    assert lifecycle.adjusted_remaining_cost_basis == 7.0
    assert lifecycle.is_scale_out_stage_completed(ScaleOutStage.FIFTEEN_PERCENT) is True


def test_lgs_05_exit_watch_confirmed_full_exit_closes_lifecycle() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    lifecycle.buy(
        trade_date=date(2024, 1, 2),
        price=10.0,
        quantity=300,
        reason_code="BAOMA_ENTRY",
    )
    lifecycle.advance_day(trade_date=date(2024, 1, 3), close_price=9.0)

    lifecycle.enter_exit_watch(trade_date=date(2024, 1, 3), reason_code="MA60_BREAK")

    assert lifecycle.state == LifecycleState.EXIT_WATCH
    assert lifecycle.can_add_on(date(2024, 1, 3)) is False
    assert lifecycle.can_scale_out(date(2024, 1, 3)) is False

    event = lifecycle.confirm_full_exit(
        trade_date=date(2024, 1, 4),
        price=8.5,
        reason_code="MA60_CONFIRMED",
    )

    assert event.accepted is True
    assert event.executed_quantity == 300
    assert lifecycle.state == LifecycleState.CLOSED
    assert lifecycle.total_quantity == 0
    assert lifecycle.closed_trades_count == 1
    closed_trade = lifecycle.closed_trades[0]
    assert closed_trade.entry_date == date(2024, 1, 2)
    assert closed_trade.exit_date == date(2024, 1, 4)
    assert closed_trade.quantity == 300
    assert closed_trade.exit_reason == "MA60_CONFIRMED"


def test_lgs_05b_closed_trade_keeps_primary_entry_date_after_scale_out_and_add_on() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    lifecycle.buy(
        trade_date=date(2024, 1, 2),
        price=10.0,
        quantity=300,
        reason_code="BAOMA_ENTRY",
    )
    lifecycle.buy(
        trade_date=date(2024, 1, 3),
        price=11.0,
        quantity=300,
        reason_code="BAOMA_ADD_ON",
    )
    lifecycle.scale_out(
        trade_date=date(2024, 1, 4),
        price=12.0,
        stage=ScaleOutStage.FIVE_PERCENT,
        reason_code="SCALE_OUT_5",
    )
    lifecycle.scale_out(
        trade_date=date(2024, 1, 5),
        price=12.5,
        stage=ScaleOutStage.FIFTEEN_PERCENT,
        reason_code="SCALE_OUT_15",
    )
    lifecycle.enter_exit_watch(trade_date=date(2024, 1, 5), reason_code="MA60_BREAK")

    lifecycle.confirm_full_exit(
        trade_date=date(2024, 1, 6),
        price=9.0,
        reason_code="MA60_CONFIRMED",
    )

    closed_trade = lifecycle.closed_trades[0]
    assert closed_trade.entry_date == date(2024, 1, 2)
    assert closed_trade.exit_date == date(2024, 1, 6)
    assert closed_trade.entry_price == 10.0
    assert closed_trade.original_entry_price == 10.0
    assert closed_trade.entry_quantity == 600
    assert closed_trade.remaining_cost_basis_at_exit == 7.0
    assert closed_trade.entry_gross_value == 6300.0
    assert closed_trade.exit_gross_value == 6700.0
    assert closed_trade.net_pnl == 400.0
    assert closed_trade.realized_return_pct == 400.0 / 6300.0


def test_lgs_06_confirmed_full_exit_rejection_enters_pending_exit() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    lifecycle.buy(
        trade_date=date(2024, 1, 2),
        price=10.0,
        quantity=300,
        reason_code="BAOMA_ENTRY",
    )
    lifecycle.advance_day(trade_date=date(2024, 1, 3), close_price=9.0)
    lifecycle.enter_exit_watch(trade_date=date(2024, 1, 3), reason_code="MA60_BREAK")

    event = lifecycle.confirm_full_exit(
        trade_date=date(2024, 1, 4),
        price=8.5,
        reason_code="MA60_CONFIRMED",
        blocked_by="LIMIT_DOWN_SELL_BLOCKED",
    )

    assert event.accepted is False
    assert event.blocked_by == "LIMIT_DOWN_SELL_BLOCKED"
    assert lifecycle.state == LifecycleState.PENDING_FULL_EXIT
    assert lifecycle.total_quantity == 300
    assert lifecycle.pending_exit_reason == "MA60_CONFIRMED"
    assert lifecycle.closed_trades_count == 0


def test_lgs_07_pending_exit_only_retries_sell_until_closed() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    lifecycle.buy(
        trade_date=date(2024, 1, 2),
        price=10.0,
        quantity=300,
        reason_code="BAOMA_ENTRY",
    )
    lifecycle.advance_day(trade_date=date(2024, 1, 3), close_price=9.0)
    lifecycle.enter_exit_watch(trade_date=date(2024, 1, 3), reason_code="MA60_BREAK")
    lifecycle.confirm_full_exit(
        trade_date=date(2024, 1, 4),
        price=8.5,
        reason_code="MA60_CONFIRMED",
        blocked_by="LIMIT_DOWN_SELL_BLOCKED",
    )

    lifecycle.advance_day(trade_date=date(2024, 1, 5), close_price=11.0)

    assert lifecycle.state == LifecycleState.PENDING_FULL_EXIT
    assert lifecycle.can_add_on(date(2024, 1, 5)) is False
    assert lifecycle.can_scale_out(date(2024, 1, 5)) is False

    event = lifecycle.retry_pending_exit(trade_date=date(2024, 1, 5), price=11.0)

    assert event.accepted is True
    assert event.executed_quantity == 300
    assert lifecycle.state == LifecycleState.CLOSED
    assert lifecycle.total_quantity == 0
    assert lifecycle.closed_trades_count == 1


def test_lgs_08_end_run_outputs_forced_liquidation_and_open_position_excluded_views() -> None:
    lifecycle = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    lifecycle.buy(
        trade_date=date(2024, 1, 2),
        price=10.0,
        quantity=300,
        reason_code="BAOMA_ENTRY",
    )
    lifecycle.advance_day(trade_date=date(2024, 1, 3), close_price=9.0)

    result = lifecycle.finish_run(
        end_date=date(2024, 1, 4),
        price=8.0,
        reason_code="END_LIQUIDATION",
    )

    assert result.open_position_excluded_quantity == 300
    assert result.forced_exit_event is not None
    assert result.forced_exit_event.accepted is True
    assert result.forced_exit_event.executed_quantity == 300
    assert lifecycle.state == LifecycleState.CLOSED

    failed = ExecutionLifecycleComponent(symbol=SYMBOL, board_lot_size=100)
    failed.buy(
        trade_date=date(2024, 1, 2),
        price=10.0,
        quantity=300,
        reason_code="BAOMA_ENTRY",
    )

    failed_result = failed.finish_run(
        end_date=date(2024, 1, 4),
        price=8.0,
        reason_code="END_LIQUIDATION",
        blocked_by="END_LIQUIDATION_LIMIT_DOWN",
    )

    assert failed_result.open_position_excluded_quantity == 300
    assert failed_result.forced_exit_event is not None
    assert failed_result.forced_exit_event.accepted is False
    assert failed_result.forced_exit_event.blocked_by == "END_LIQUIDATION_LIMIT_DOWN"
    assert failed.state == LifecycleState.OPEN_AT_END
    assert failed.total_quantity == 300
