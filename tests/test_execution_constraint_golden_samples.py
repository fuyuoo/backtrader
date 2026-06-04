from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from attbacktrader.data import DailyBar, TradabilityStatus
from attbacktrader.engines import ExecutionAuditEvent
from attbacktrader.engines.backtrader import BacktraderAShareSettings, run_trend_template_v1_portfolio_backtrader
from attbacktrader.reports import build_evidence_validation
from attbacktrader.strategies import TradeIntent, TradeIntentType


@pytest.mark.parametrize(
    ("reason", "stake", "cash", "tradability"),
    (
        ("BOARD_LOT_TOO_SMALL", 99, 10000.0, ()),
        ("CASH_NOT_ENOUGH", 100, 999.0, ()),
        ("SUSPENDED", 100, 10000.0, (TradabilityStatus("000001.SZ", date(2024, 1, 1), is_suspended=True),)),
        ("LIMIT_UP_BUY_BLOCKED", 100, 10000.0, (TradabilityStatus("000001.SZ", date(2024, 1, 1), is_limit_up=True),)),
    ),
)
def test_execution_constraint_golden_buy_rejections_are_validated(reason, stake, cash, tradability) -> None:
    engine_result = run_trend_template_v1_portfolio_backtrader(
        {"000001.SZ": _bars((10.0, 11.0, 12.0))},
        initial_cash=cash,
        stake=stake,
        entry_method=_DateEntry(date(2024, 1, 1)),
        profit_taking_method=_DateExit(date(2024, 1, 3)),
        stop_loss_method=_NeverStop(),
        tradability_by_symbol={"000001.SZ": tradability},
        ashare_settings=BacktraderAShareSettings(enabled=True, board_lot_size=100),
    )
    validation = build_evidence_validation(_validation_result(engine_result))
    rejected = next(event for event in engine_result.execution_audit if event.event_type == "rejected")
    blocked_intent = next(intent for intent in engine_result.strategy_result.intents if intent.blocked_by)

    assert rejected.side == "buy"
    assert rejected.blocked_by == reason
    assert rejected.executable_quantity == 0
    assert blocked_intent.blocked_by == reason
    assert engine_result.strategy_result.closed_trades == ()
    assert validation.status == "ok"


def test_execution_constraint_golden_limit_down_sell_rejection_keeps_position_open() -> None:
    engine_result = run_trend_template_v1_portfolio_backtrader(
        {"000001.SZ": _bars((10.0, 9.0, 8.0))},
        initial_cash=10000.0,
        stake=100,
        entry_method=_DateEntry(date(2024, 1, 1)),
        profit_taking_method=_DateExit(date(2024, 1, 2)),
        stop_loss_method=_NeverStop(),
        tradability_by_symbol={
            "000001.SZ": (TradabilityStatus("000001.SZ", date(2024, 1, 2), is_limit_down=True),)
        },
        ashare_settings=BacktraderAShareSettings(enabled=True, board_lot_size=100),
    )
    validation = build_evidence_validation(_validation_result(engine_result))
    rejected = next(event for event in engine_result.execution_audit if event.event_type == "rejected")
    blocked_intent = next(intent for intent in engine_result.strategy_result.intents if intent.blocked_by)

    assert rejected.side == "sell"
    assert rejected.blocked_by == "LIMIT_DOWN_SELL_BLOCKED"
    assert rejected.executable_quantity == 0
    assert blocked_intent.blocked_by == "LIMIT_DOWN_SELL_BLOCKED"
    assert engine_result.strategy_result.closed_trades == ()
    assert len(engine_result.strategy_result.open_positions) == 1
    assert validation.status == "ok"


def test_execution_constraint_golden_t_plus_one_sell_rejection_evidence_is_validated() -> None:
    trade_date = date(2024, 1, 1)
    result = SimpleNamespace(
        symbols=("000001.SZ",),
        closed_trades=(),
        signal_audit=(
            TradeIntent(
                TradeIntentType.EXIT_LOSS,
                "000001.SZ",
                trade_date,
                "same_day_exit",
                "SAME_DAY_EXIT",
                blocked_by="T_PLUS_ONE_SELL_BLOCKED",
            ),
        ),
        execution_audit=(
            ExecutionAuditEvent(
                event_date=trade_date,
                signal_date=trade_date,
                symbol="000001.SZ",
                side="sell",
                event_type="rejected",
                status="rejected",
                reason_code="SAME_DAY_EXIT",
                requested_quantity=100,
                executable_quantity=0,
                signal_price=10.0,
                blocked_by="T_PLUS_ONE_SELL_BLOCKED",
            ),
        ),
        open_positions=(),
        equity_curve=(),
        position_snapshots=(),
        final_value=None,
        final_cash=None,
        report=SimpleNamespace(
            returns=SimpleNamespace(final_equity=None),
            trade_quality=SimpleNamespace(trade_count=0),
        ),
    )

    validation = build_evidence_validation(result)

    assert validation.status == "ok"


@dataclass(frozen=True)
class _DateEntry:
    entry_date: date
    method_name: str = "date_entry"
    required_indicators = frozenset()

    def evaluate(self, *, symbol, trade_date, row=None, previous_row=None) -> TradeIntent:
        if trade_date == self.entry_date:
            return TradeIntent(TradeIntentType.ENTER, symbol, trade_date, self.method_name, "DATE_ENTRY")
        return TradeIntent(TradeIntentType.HOLD, symbol, trade_date, self.method_name, "WAITING_ENTRY")


@dataclass(frozen=True)
class _DateExit:
    exit_date: date
    method_name: str = "date_exit"
    required_indicators = frozenset()

    def evaluate(self, *, symbol, trade_date, row=None, previous_row=None) -> TradeIntent:
        if trade_date == self.exit_date:
            return TradeIntent(TradeIntentType.EXIT_PROFIT, symbol, trade_date, self.method_name, "DATE_EXIT")
        return TradeIntent(TradeIntentType.HOLD, symbol, trade_date, self.method_name, "NO_EXIT")


@dataclass(frozen=True)
class _NeverStop:
    method_name: str = "never_stop"
    required_indicators = frozenset()

    def evaluate(self, *, symbol, trade_date, row=None, previous_row=None, entry_price=None, current_price=None) -> TradeIntent:
        return TradeIntent(TradeIntentType.HOLD, symbol, trade_date, self.method_name, "NO_STOP")


def _validation_result(engine_result):
    return SimpleNamespace(
        symbols=("000001.SZ",),
        closed_trades=engine_result.strategy_result.closed_trades,
        signal_audit=engine_result.strategy_result.intents,
        execution_audit=engine_result.execution_audit,
        open_positions=engine_result.strategy_result.open_positions,
        equity_curve=engine_result.equity_curve,
        position_snapshots=engine_result.position_snapshots,
        final_value=engine_result.final_value,
        final_cash=engine_result.final_cash,
        report=SimpleNamespace(
            returns=SimpleNamespace(final_equity=engine_result.final_value),
            trade_quality=SimpleNamespace(trade_count=len(engine_result.strategy_result.closed_trades)),
        ),
    )


def _bars(closes: tuple[float, ...]) -> tuple[DailyBar, ...]:
    start_date = date(2024, 1, 1)
    return tuple(
        DailyBar(
            symbol="000001.SZ",
            trade_date=start_date + timedelta(days=index),
            open=close,
            high=close + 0.5,
            low=max(0.1, close - 0.5),
            close=close,
            volume=1000,
        )
        for index, close in enumerate(closes)
    )
