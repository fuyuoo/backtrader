from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.engines.backtrader import BacktraderAShareSettings, run_trend_template_v1_portfolio_backtrader
from attbacktrader.engines.business import run_trend_template_v1_portfolio_business
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.templates import TrendTemplateV1


@dataclass(frozen=True)
class _DateEntry:
    entry_date: date
    method_name: str = "date_entry"
    required_indicators = frozenset()

    def evaluate(self, *, symbol, trade_date, row=None, previous_row=None) -> TradeIntent:
        if trade_date == self.entry_date:
            return TradeIntent(
                intent_type=TradeIntentType.ENTER,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="DATE_ENTRY",
            )
        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="WAITING_ENTRY",
        )


@dataclass(frozen=True)
class _NeverExit:
    method_name: str
    required_indicators = frozenset()

    def evaluate(
        self,
        *,
        symbol,
        trade_date,
        row=None,
        previous_row=None,
        entry_price=None,
        current_price=None,
    ) -> TradeIntent:
        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="NO_EXIT",
        )


@dataclass(frozen=True)
class _DateAddOn:
    add_on_date: date
    method_name: str = "date_add_on"
    required_indicators = frozenset()

    def evaluate(
        self,
        *,
        symbol,
        trade_date,
        current_quantity=0,
        entry_price=None,
        current_price=None,
        add_on_count=0,
        row=None,
        previous_row=None,
    ) -> TradeIntent:
        if trade_date == self.add_on_date and current_quantity > 0 and add_on_count == 0:
            return TradeIntent(
                intent_type=TradeIntentType.ADD_ON,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="DATE_ADD_ON",
                signal_values={
                    "position_action": "add_on",
                    "current_quantity": current_quantity,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "add_on_count": add_on_count,
                },
            )
        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="NO_ADD_ON",
        )


def test_business_portfolio_executes_add_on_and_updates_position_average_price() -> None:
    bars = _bars("000001.SZ", closes=(10.0, 12.0, 13.0))
    strategy = TrendTemplateV1(
        entry_method=_DateEntry(date(2024, 1, 1)),
        profit_taking_method=_NeverExit("profit"),
        stop_loss_method=_NeverExit("stop"),
        add_on_method=_DateAddOn(date(2024, 1, 2)),
    )

    result = run_trend_template_v1_portfolio_business(
        strategy,
        {"000001.SZ": bars},
        initial_cash=10000.0,
        stake=100,
    )

    add_on_intent = next(intent for intent in result.strategy_result.intents if intent.intent_type == TradeIntentType.ADD_ON)
    open_position = result.strategy_result.open_positions[0]

    assert add_on_intent.signal_values["sizing"]["requested_quantity"] == 100
    assert add_on_intent.signal_values["sizing"]["business_executable_quantity"] == 100
    assert open_position.entry_date == date(2024, 1, 1)
    assert open_position.size == 200
    assert open_position.add_on_count == 1
    assert open_position.entry_price == pytest.approx(11.0)
    assert result.final_cash == pytest.approx(7800.0)
    assert result.final_value == pytest.approx(10400.0)


def test_backtrader_portfolio_executes_add_on_and_updates_position_average_price() -> None:
    bars = _bars("000001.SZ", closes=(10.0, 12.0, 13.0))

    result = run_trend_template_v1_portfolio_backtrader(
        {"000001.SZ": bars},
        initial_cash=10000.0,
        stake=100,
        entry_method=_DateEntry(date(2024, 1, 1)),
        profit_taking_method=_NeverExit("profit"),
        stop_loss_method=_NeverExit("stop"),
        add_on_method=_DateAddOn(date(2024, 1, 2)),
        ashare_settings=BacktraderAShareSettings(enabled=False),
    )

    add_on_intent = next(intent for intent in result.strategy_result.intents if intent.intent_type == TradeIntentType.ADD_ON)
    open_position = result.strategy_result.open_positions[0]
    completed_add_on = next(
        event
        for event in result.execution_audit
        if event.event_type == "completed" and event.reason_code == "DATE_ADD_ON"
    )

    assert add_on_intent.signal_values["sizing"]["requested_quantity"] == 100
    assert open_position.entry_date == date(2024, 1, 1)
    assert open_position.size == 200
    assert open_position.add_on_count == 1
    assert open_position.entry_price == pytest.approx(11.0)
    assert completed_add_on.executed_quantity == pytest.approx(100.0)
    assert completed_add_on.executed_price == pytest.approx(12.0)
    assert result.final_cash == pytest.approx(7800.0)
    assert result.final_value == pytest.approx(10400.0)


def _bars(symbol: str, *, closes: tuple[float, ...]) -> tuple[DailyBar, ...]:
    start_date = date(2024, 1, 1)
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000,
        )
        for index, close in enumerate(closes)
    )
