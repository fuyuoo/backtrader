from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pytest

from attbacktrader.config import RunPlan
from attbacktrader.data import DailyBar
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.engines.backtrader import BacktraderAShareSettings, run_trend_template_v1_portfolio_backtrader
from attbacktrader.features import IndicatorRequirement, build_indicator_snapshots_for_requirements, indicator_frame_from_snapshots, join_bars_with_indicators
from attbacktrader.reports import build_evidence_validation, build_result_diagnostics, build_trade_lifecycle_report
from attbacktrader.runners import execute_run_plan
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies.templates import ClosedTrade


class FakeDailyProvider:
    def __init__(self, bars: tuple[DailyBar, ...]) -> None:
        self.bars = bars

    def fetch_daily_bars(self, *, symbol, start_date, end_date, adjustment):
        return self.bars


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
                TradeIntentType.ADD_ON,
                symbol,
                trade_date,
                self.method_name,
                "DATE_ADD_ON",
                signal_values={
                    "position_action": "add_on",
                    "attribution": entry_attribution_payload(
                        checks={"position.add_on_count_available": True},
                        values={"position.unrealized_return": current_price / entry_price - 1.0},
                    ),
                },
            )
        return TradeIntent(TradeIntentType.HOLD, symbol, trade_date, self.method_name, "NO_ADD_ON")


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


def test_correctness_golden_indicator_warmup_and_higher_timeframe_alignment() -> None:
    bars = _bars("000001.SZ", count=70)
    requirements = (
        IndicatorRequirement("ma60", "D"),
        IndicatorRequirement("macd", "W"),
        IndicatorRequirement("macd", "M"),
    )

    snapshots = build_indicator_snapshots_for_requirements(bars, indicator_requirements=requirements)
    rows = join_bars_with_indicators(bars, snapshots, indicator_requirements=requirements)
    frame = indicator_frame_from_snapshots(snapshots)

    with pytest.raises(KeyError, match="MA60 D is missing"):
        rows[58].indicators.ma_at(60)
    assert rows[59].indicators.ma_at(60).value == pytest.approx(sum(range(1, 61)) / 60)
    with pytest.raises(KeyError, match="indicator is missing"):
        rows[0].indicators.macd_at("W")
    first_weekly_date = min(snapshot.trade_date for snapshot in snapshots if snapshot.timeframe == "W")
    first_weekly_row = next(row for row in rows if row.trade_date > first_weekly_date)
    assert first_weekly_row.indicators.indicator_date("macd", "W") == first_weekly_date
    assert first_weekly_row.indicators.macd_at("W") == frame.macd_at(first_weekly_date, timeframe="W")
    assert rows[-1].indicators.indicator_date("macd", "M") <= rows[-1].trade_date


def test_correctness_golden_lifecycle_buy_add_on_and_sell_are_grouped() -> None:
    bars = _bars("000001.SZ", closes=(10.0, 12.0, 13.0, 14.0))

    result = run_trend_template_v1_portfolio_backtrader(
        {"000001.SZ": bars},
        initial_cash=10000.0,
        stake=100,
        entry_method=_DateEntry(date(2024, 1, 1)),
        add_on_method=_DateAddOn(date(2024, 1, 2)),
        profit_taking_method=_DateExit(date(2024, 1, 3)),
        stop_loss_method=_NeverStop(),
        ashare_settings=BacktraderAShareSettings(enabled=False),
    )
    diagnostics = build_result_diagnostics(
        symbols=("000001.SZ",),
        closed_trades=result.strategy_result.closed_trades,
        signal_audit=result.strategy_result.intents,
        execution_audit=result.execution_audit,
    )
    lifecycle_report = build_trade_lifecycle_report(
        closed_trades=result.strategy_result.closed_trades,
        signal_audit=result.strategy_result.intents,
        execution_audit=result.execution_audit,
    )

    completed = tuple(event for event in result.execution_audit if event.event_type == "completed")
    diagnostic = diagnostics.symbols[0]
    lifecycle = lifecycle_report.lifecycles[0]

    assert [event.reason_code for event in completed] == ["DATE_ENTRY", "DATE_ADD_ON", "DATE_EXIT"]
    assert result.strategy_result.open_positions == ()
    assert result.strategy_result.closed_trades[0].entry_price == pytest.approx(11.0)
    assert result.strategy_result.closed_trades[0].exit_price == pytest.approx(13.0)
    assert [event.event_type for event in lifecycle.events] == ["entry", "add_on", "exit"]
    assert [event.reason_code for event in lifecycle.events] == ["DATE_ENTRY", "DATE_ADD_ON", "DATE_EXIT"]
    assert lifecycle.events[1].values["position.unrealized_return"] == pytest.approx(0.2)
    assert any(event.event_type == "completed" for event in lifecycle.events[1].executions)
    assert lifecycle_report.indexes.by_outcome[0].key == "win"
    assert lifecycle_report.indexes.by_add_on_count[0].key == "1"
    assert diagnostic.winning_trade_add_on_attributions[0].entry_date == date(2024, 1, 1)
    assert diagnostic.winning_trade_add_on_attributions[0].add_on_date == date(2024, 1, 2)
    assert diagnostic.winning_trade_add_on_attributions[0].exit_date == date(2024, 1, 3)
    assert diagnostics.portfolio_winning_add_on_summary.sample_count == 1


def test_correctness_golden_costs_and_evidence_validation_match_audit(tmp_path: Path) -> None:
    result = _execute_fixture_run(tmp_path)
    completed = tuple(event for event in result.execution_audit if event.event_type == "completed")
    validation = build_evidence_validation(result)

    assert validation.status == "ok"
    assert result.report.execution_costs is not None
    assert result.report.execution_costs.completed_count == len(completed)
    assert result.report.execution_costs.total_commission == pytest.approx(
        sum(event.commission or 0.0 for event in completed)
    )
    assert result.report.trade_quality.trade_count == len(result.closed_trades)


def test_correctness_golden_missing_attribution_is_missing_not_false() -> None:
    diagnostics = build_result_diagnostics(
        symbols=("000001.SZ",),
        closed_trades=(
            ClosedTrade("000001.SZ", date(2024, 1, 1), date(2024, 1, 2), 10.0, 11.0, "WIN_EXIT"),
            ClosedTrade("000001.SZ", date(2024, 1, 3), date(2024, 1, 4), 10.0, 9.0, "LOSS_EXIT"),
        ),
        signal_audit=(
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                date(2024, 1, 1),
                "entry",
                "ENTRY",
                signal_values={
                    "attribution": entry_attribution_payload(
                        checks={"symbol.ma.price_above_ma25": True},
                    ),
                    "sizing": {"requested_quantity": 100},
                },
            ),
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                date(2024, 1, 3),
                "entry",
                "ENTRY",
                signal_values={"sizing": {"requested_quantity": 100}},
            ),
        ),
    )

    check_summary = next(
        summary
        for summary in diagnostics.portfolio_entry_contrasts
        if summary.key == "symbol.ma.price_above_ma25"
    )

    assert check_summary.loss_present_count == 0
    assert check_summary.loss_missing_rate == pytest.approx(1.0)
    assert diagnostics.portfolio_losing_entry_summary.checks == ()


def _execute_fixture_run(tmp_path: Path):
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    return execute_run_plan(_run_plan(tmp_path / "snapshots"), provider=FakeDailyProvider(bars))


def _run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {"id": "correctness-golden", "from_date": "2024-01-02", "to_date": "2024-01-11"},
            "data": {"snapshot_root": snapshot_root, "refresh_snapshots": True, "symbols": ["000001.SZ"]},
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "kdj_oversold_entry",
                "profit_taking_method": "kdj_overheated_exit",
                "stop_loss_method": "fixed_percent_stop",
                "sizing_rule": "equal_weight",
            },
            "broker": {
                "initial_cash": 1000000,
                "commission_rate": 0.0003,
                "stamp_tax_rate": 0.001,
                "transfer_fee_rate": 0.00001,
                "slippage": {"type": "percent", "value": 0.0005},
            },
            "constraints": {"ashare": {"enabled": False}},
            "execution": {"engine": "backtrader", "stake": 1},
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )


def _bars(symbol: str, *, count: int | None = None, closes: tuple[float, ...] | None = None) -> tuple[DailyBar, ...]:
    start_date = date(2024, 1, 1)
    if closes is None:
        if count is None:
            raise ValueError("count or closes is required")
        closes = tuple(float(index + 1) for index in range(count))
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=close,
            high=close + 0.5,
            low=max(0.1, close - 0.5),
            close=close,
            volume=1000,
        )
        for index, close in enumerate(closes)
    )
