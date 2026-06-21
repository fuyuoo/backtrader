from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from attbacktrader.config import RunPlan
from attbacktrader.data import (
    DailyBar,
    IndexBar,
    ShenwanIndustryClassification,
    StockIndustryMembership,
    TradabilityStatus,
)
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.engines.business import BaomaBusinessRunResult, LifecycleClosedTrade, LifecycleExecutionEvent
from attbacktrader.reports.renderer import render_backtest_report_markdown_zh
import attbacktrader.runners.run_plan as run_plan_module
from attbacktrader.runners import execute_run_plan
from attbacktrader.strategies import TradeIntent, TradeIntentType


class FakeRunDataProvider:
    def __init__(
        self,
        bars_by_symbol: dict[str, tuple[DailyBar, ...]],
        index_bars_by_symbol: dict[str, tuple[IndexBar, ...]] | None = None,
    ) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.index_bars_by_symbol = index_bars_by_symbol or {}
        self.calls: list[tuple[str, str]] = []
        self.index_calls: list[str] = []
        self.industry_index_calls: list[tuple[str, str]] = []
        self.industry_classification_calls: list[str] = []
        self.industry_membership_calls: list[tuple[str, str]] = []
        self.tradability_calls: list[str] = []

    def fetch_daily_bars(self, *, symbol, start_date, end_date, adjustment):
        self.calls.append((symbol, adjustment))
        return self.bars_by_symbol[symbol]

    def fetch_index_daily_bars(self, *, symbol, start_date, end_date):
        self.index_calls.append(symbol)
        if symbol in self.index_bars_by_symbol:
            return self.index_bars_by_symbol[symbol]
        return (
            IndexBar(symbol, start_date, 100.0, 101.0, 99.0, 100.0),
            IndexBar(symbol, end_date, 110.0, 111.0, 109.0, 110.0),
        )

    def fetch_industry_index_daily_bars(self, *, symbol, start_date, end_date, source="SW2021"):
        self.industry_index_calls.append((symbol, source))
        return (
            IndexBar(symbol, start_date, 200.0, 201.0, 199.0, 200.0),
            IndexBar(symbol, end_date, 210.0, 211.0, 209.0, 210.0),
        )

    def fetch_shenwan_industry_classifications(self, *, source="SW2021"):
        self.industry_classification_calls.append(source)
        return (
            ShenwanIndustryClassification("801780.SI", "银行", 1, "480000", "0", source),
            ShenwanIndustryClassification("801783.SI", "股份制银行Ⅱ", 2, "480200", "801780.SI", source),
            ShenwanIndustryClassification("857831.SI", "股份制银行Ⅲ", 3, "480201", "801783.SI", source),
        )

    def fetch_stock_industry_memberships(self, *, symbol, source="SW2021"):
        self.industry_membership_calls.append((symbol, source))
        return (
            StockIndustryMembership(
                symbol=symbol,
                stock_name=symbol,
                level1_code="801780.SI",
                level1_name="银行",
                level2_code="801783.SI",
                level2_name="股份制银行Ⅱ",
                level3_code="857831.SI",
                level3_name="股份制银行Ⅲ",
                in_date=date(1990, 1, 1),
                out_date=None,
                is_new=True,
                source=source,
            ),
        )

    def fetch_tradability_statuses(self, *, symbol, start_date, end_date):
        self.tradability_calls.append(symbol)
        return (
            TradabilityStatus(symbol=symbol, trade_date=start_date),
            TradabilityStatus(symbol=symbol, trade_date=end_date),
        )


def test_execute_run_plan_fetches_snapshots_indicators_and_runs_portfolio(tmp_path: Path) -> None:
    first_symbol_bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    second_symbol_bars = tuple(replace(bar, symbol="000002.SZ") for bar in first_symbol_bars)
    provider = FakeRunDataProvider(
        {
            "000001.SZ": first_symbol_bars,
            "000002.SZ": second_symbol_bars,
        }
    )
    run_plan = _run_plan(tmp_path, refresh_snapshots=True)

    result = execute_run_plan(run_plan, provider=provider)

    assert provider.calls == [("000001.SZ", "qfq"), ("000002.SZ", "qfq")]
    assert provider.index_calls == ["000001.SH"]
    assert provider.industry_index_calls == [("801780.SI", "SW2021")]
    assert provider.industry_classification_calls == ["SW2021"]
    assert provider.industry_membership_calls == [("000001.SZ", "SW2021"), ("000002.SZ", "SW2021")]
    assert provider.tradability_calls == ["000001.SZ", "000002.SZ"]
    assert result.engine == "business"
    assert result.adjustment == "qfq"
    assert result.symbols == ("000001.SZ", "000002.SZ")
    assert len(result.symbol_results) == 2
    assert [symbol_result.asset_type for symbol_result in result.symbol_results] == ["stock", "stock"]
    assert len(result.closed_trades) == 4
    assert result.signal_audit
    assert result.symbol_results[0].intents
    assert result.signal_audit[0].signal_values
    assert result.attribution_factor_selection is not None
    assert result.attribution_factor_selection["schema"] == "attbacktrader.attribution_factor_selection.v1"
    assert result.attribution_factor_selection["configured_source"] == "default:all_applicable"
    assert "symbol.ma.price_above_ma25" in result.attribution_factor_selection["include"]
    assert result.attribution_factor_selection["not_include"] == ()
    assert result.report.trade_quality.trade_count == 4
    assert result.post_exit_analysis.trade_count == 4
    assert result.post_exit_analysis.window_days == 5
    assert len(result.report.benchmark_comparison) == 1
    assert result.report.benchmark_comparison[0].benchmark_symbol == "000001.SH"
    assert result.report.benchmark_comparison[0].benchmark_return == pytest.approx(0.1)
    assert len(result.report.industry_attribution) == 3
    assert {summary.level for summary in result.report.industry_attribution} == {1, 2, 3}
    assert result.report.market_regime is not None
    assert result.report.market_regime.primary_label == "input_only"
    assert result.report.market_regime.windows == ()
    assert result.report.market_regime.benchmark_symbols == ("000001.SH",)
    assert result.report.market_regime.industry_index_symbols == ("801780.SI",)
    assert result.report.market_regime.timeframes == ("D", "W", "M")
    assert result.report.scenario_fit is not None
    assert result.report.scenario_fit.label == "conditional_fit"
    assert result.report.scenario_fit.score == 4
    assert result.report.portfolio_behavior is not None
    assert result.report.portfolio_behavior.open_position_count == 0
    assert result.report.portfolio_behavior.closed_symbol_count == 2
    assert result.final_cash is not None
    assert result.final_value is not None
    assert result.equity_curve
    assert result.report.portfolio_behavior.cash_ratio == pytest.approx(1.0)
    assert result.report.portfolio_behavior.max_symbol_trade_share == pytest.approx(0.5)
    assert result.benchmark_results[0].snapshot_path.exists()
    assert result.industry_index_results[0].snapshot_path.exists()
    assert result.industry_classification_result is not None
    assert result.industry_classification_result.snapshot_path.exists()
    assert result.industry_membership_results[0].snapshot_path.exists()
    assert result.symbol_results[0].bar_count == len(first_symbol_bars)
    assert result.symbol_results[0].snapshot_path.exists()
    assert result.symbol_results[0].indicator_snapshot_path.exists()
    assert result.symbol_results[0].tradability_snapshot_path is not None
    assert result.symbol_results[0].tradability_snapshot_path.exists()
    assert result.symbol_results[0].snapshot_path.parent.name == "qfq"
    assert result.symbol_results[0].indicator_snapshot_path.parent.name == "qfq"


def test_execute_run_plan_auto_filters_stock_pool_before_backtest(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.csv"
    pool_path.write_text(
        "\n".join(
            [
                "ts_code,name,source_index,freeze_date",
                "000001.SZ,平安银行,HS300,2026-06-07",
                "000002.SZ,万科A,HS300,2026-06-07",
            ]
        ),
        encoding="utf-8",
    )
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakeRunDataProvider({"000001.SZ": bars})

    run_plan = _stock_pool_run_plan(tmp_path, pool_path)
    result = execute_run_plan(run_plan, provider=provider)

    assert result.symbols == ("000001.SZ",)
    assert result.stock_pool_filter is not None
    assert result.stock_pool_filter.original_count == 2
    assert result.stock_pool_filter.kept_count == 1
    assert result.stock_pool_filter.excluded_count == 1
    assert result.stock_pool_filter.excluded_symbols[0].symbol == "000002.SZ"
    assert result.stock_pool_filter.excluded_symbols[0].status == "error"
    assert result.data_preflight_report is not None
    assert result.data_preflight_report.checked_symbol_count == 2
    report_markdown = render_backtest_report_markdown_zh(run_plan, result)
    assert "## 股票池过滤" in report_markdown
    assert "| 原始股票数 | 2 |" in report_markdown
    assert "| 回测保留 | 1 |" in report_markdown
    assert "| 自动剔除 | 1 |" in report_markdown


def test_execute_run_plan_auto_filter_reuses_existing_snapshots(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.csv"
    pool_path.write_text(
        "\n".join(
            [
                "ts_code,name,source_index,freeze_date",
                "000001.SZ,平安银行,HS300,2026-06-07",
                "000002.SZ,万科A,HS300,2026-06-07",
            ]
        ),
        encoding="utf-8",
    )
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    run_plan = _stock_pool_run_plan(tmp_path, pool_path)

    execute_run_plan(run_plan, provider=FakeRunDataProvider({"000001.SZ": bars}))
    offline_result = execute_run_plan(run_plan, provider=None)

    assert offline_result.symbols == ("000001.SZ",)
    assert offline_result.stock_pool_filter is not None
    assert offline_result.stock_pool_filter.original_count == 2
    assert offline_result.stock_pool_filter.kept_count == 1
    assert offline_result.stock_pool_filter.excluded_count == 1
    assert offline_result.data_preflight_report is not None
    assert offline_result.data_preflight_report.checked_symbol_count == 2


def test_execute_run_plan_can_reuse_existing_snapshots_without_provider(tmp_path: Path) -> None:
    first_symbol_bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    second_symbol_bars = tuple(replace(bar, symbol="000002.SZ") for bar in first_symbol_bars)
    provider = FakeRunDataProvider(
        {
            "000001.SZ": first_symbol_bars,
            "000002.SZ": second_symbol_bars,
        }
    )

    execute_run_plan(_run_plan(tmp_path, refresh_snapshots=True), provider=provider)
    offline_result = execute_run_plan(_run_plan(tmp_path, refresh_snapshots=False), provider=None)

    assert len(offline_result.closed_trades) == 4
    assert offline_result.report.trade_quality.trade_count == 4


def test_execute_run_plan_backtrader_returns_equity_curve_and_account_value_report(tmp_path: Path) -> None:
    first_symbol_bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    second_symbol_bars = tuple(replace(bar, symbol="000002.SZ") for bar in first_symbol_bars)
    provider = FakeRunDataProvider(
        {
            "000001.SZ": first_symbol_bars,
            "000002.SZ": second_symbol_bars,
        }
    )
    run_plan = _run_plan(tmp_path, refresh_snapshots=True)
    run_plan = run_plan.model_copy(
        update={
            "execution": run_plan.execution.model_copy(
                update={
                    "engine": "backtrader",
                    "stake": 100,
                }
            )
        }
    )

    result = execute_run_plan(run_plan, provider=provider)

    assert result.engine == "backtrader"
    assert result.final_cash is not None
    assert result.final_value is not None
    assert len(result.equity_curve) == len(first_symbol_bars)
    assert result.equity_curve[-1].cash == pytest.approx(result.final_cash)
    assert result.equity_curve[-1].total_value == pytest.approx(result.final_value)
    assert len(result.position_snapshots) == 8
    assert any(event.event_type == "completed" for event in result.execution_audit)
    assert all(event.order_ref is not None for event in result.execution_audit if event.event_type == "completed")
    assert any("sizing" in intent.signal_values for intent in result.signal_audit)
    assert result.report.returns.starting_equity == pytest.approx(run_plan.broker.initial_cash)
    assert result.report.returns.final_equity == pytest.approx(result.final_value)
    assert result.report.returns.cumulative_return == pytest.approx(
        result.final_value / run_plan.broker.initial_cash - 1.0
    )
    assert result.report.portfolio_behavior is not None
    assert result.report.portfolio_behavior.cash_ratio is not None
    assert result.report.execution_costs is not None
    assert result.report.execution_costs.completed_count > 0
    assert result.report.execution_costs.total_commission > 0
    assert result.report.execution_costs.total_slippage_cost > 0


def test_execute_run_plan_backtrader_applies_max_holding_count_sizing(tmp_path: Path) -> None:
    first_symbol_bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    second_symbol_bars = tuple(replace(bar, symbol="000002.SZ") for bar in first_symbol_bars)
    provider = FakeRunDataProvider(
        {
            "000001.SZ": first_symbol_bars,
            "000002.SZ": second_symbol_bars,
        }
    )
    run_plan = _run_plan(tmp_path, refresh_snapshots=True)
    run_plan = run_plan.model_copy(
        update={
            "strategy": run_plan.strategy.model_copy(
                update={"sizing_params": {"max_holding_count": 1}}
            ),
            "execution": run_plan.execution.model_copy(
                update={
                    "engine": "backtrader",
                    "stake": 100,
                }
            ),
        }
    )

    result = execute_run_plan(run_plan, provider=provider)
    blocked_intents = tuple(intent for intent in result.signal_audit if intent.blocked_by == "MAX_HOLDING_COUNT")

    assert blocked_intents
    assert all(intent.signal_values["sizing"]["max_holding_count"] == 1 for intent in blocked_intents)


def test_execute_run_plan_backtrader_can_use_macd_strategy_methods(tmp_path: Path) -> None:
    bars = _macd_fixture_bars("000001.SZ")
    provider = FakeRunDataProvider({"000001.SZ": bars})
    run_plan = _macd_run_plan(tmp_path)

    result = execute_run_plan(run_plan, provider=provider)
    audit_reason_codes = {event.reason_code for event in result.execution_audit}

    assert result.engine == "backtrader"
    assert result.symbol_results[0].indicator_snapshot_path.parts[-3:-1] == ("macd", "qfq")
    assert "MACD_BULLISH_CROSSOVER" in audit_reason_codes
    assert any(trade.exit_reason == "MACD_BEARISH_CROSSOVER" for trade in result.closed_trades)
    assert result.report.trade_quality.trade_count >= 1


def test_execute_run_plan_backtrader_can_use_weekly_macd_strategy_methods(tmp_path: Path) -> None:
    bars = _macd_fixture_bars("000001.SZ")
    provider = FakeRunDataProvider({"000001.SZ": bars})
    run_plan = _macd_run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={
            "strategy": run_plan.strategy.model_copy(
                update={
                    "entry_method": "macd_weekly_bullish_crossover_entry",
                    "profit_taking_method": "macd_weekly_bearish_crossover_exit",
                }
            )
        }
    )

    result = execute_run_plan(run_plan, provider=provider)

    assert result.engine == "backtrader"
    assert result.symbol_results[0].indicator_snapshot_path.parts[-4:-1] == ("macd", "W", "qfq")
    assert result.symbol_results[0].indicator_snapshot_paths == (result.symbol_results[0].indicator_snapshot_path,)
    assert result.symbol_results[0].indicator_snapshot_path.exists()
    assert len(result.equity_curve) == len(bars)


def test_execute_run_plan_signal_audit_records_combo_method_checks(tmp_path: Path) -> None:
    bars = _combo_fixture_bars("000001.SZ")
    provider = FakeRunDataProvider({"000001.SZ": bars})
    run_plan = _combo_run_plan(tmp_path)

    result = execute_run_plan(run_plan, provider=provider)
    combo_intents = tuple(
        intent
        for intent in result.signal_audit
        if intent.method_name == "ma_macd_bullish_confirmation_entry"
    )

    assert combo_intents
    assert any(intent.signal_values["checks"]["required_values_available"] for intent in combo_intents)
    assert any(
        intent.reason_code == "MA_MACD_BULLISH_CONFIRMATION"
        for intent in combo_intents
    )
    assert result.symbol_results[0].indicator_snapshot_path.parts[-3:-1] == ("ma20_ma60_macd", "qfq")


def test_execute_run_plan_can_trade_index_series_without_stock_coupling(tmp_path: Path) -> None:
    fixture_bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    index_bars = _index_bars_from_daily_bars(fixture_bars, symbol="000001.SH")
    provider = FakeRunDataProvider({}, {"000001.SH": index_bars})
    run_plan = _index_run_plan(tmp_path)

    result = execute_run_plan(run_plan, provider=provider)

    assert provider.calls == []
    assert provider.index_calls == ["000001.SH"]
    assert provider.tradability_calls == []
    assert provider.industry_classification_calls == []
    assert provider.industry_membership_calls == []
    assert result.symbols == ("000001.SH",)
    assert result.adjustment == "none"
    assert result.symbol_results[0].asset_type == "index"
    assert result.symbol_results[0].adjustment == "none"
    assert result.symbol_results[0].bar_count == len(index_bars)
    assert result.symbol_results[0].snapshot_path.parts[-4:-1] == ("tradable_bars", "index", "none")
    assert result.symbol_results[0].indicator_snapshot_path.parts[-5:-1] == ("indicators", "kdj", "index", "none")
    assert len(result.closed_trades) == 2
    assert result.industry_classification_result is None
    assert result.industry_membership_results == ()


def test_execute_run_plan_can_route_to_baoma_dedicated_business_runner(tmp_path: Path, monkeypatch) -> None:
    bars = _route_fixture_bars("000001.SZ")
    provider = FakeRunDataProvider({"000001.SZ": bars})
    captured = {}
    entry_intent = TradeIntent(
        intent_type=TradeIntentType.ENTER,
        symbol="000001.SZ",
        trade_date=date(2024, 1, 5),
        method_name="baoma_entry",
        reason_code="BAOMA_ENTRY_TRIGGERED",
    )
    exit_intent = TradeIntent(
        intent_type=TradeIntentType.EXIT_LOSS,
        symbol="000001.SZ",
        trade_date=date(2024, 1, 8),
        method_name="baoma_ma60_stop",
        reason_code="BAOMA_MA60_STOP_TRIGGERED",
    )
    lifecycle_events = (
        LifecycleExecutionEvent(
            trade_date=date(2024, 1, 5),
            symbol="000001.SZ",
            side="buy",
            status="accepted",
            reason_code="BAOMA_ENTRY_TRIGGERED",
            requested_quantity=300,
            executed_quantity=300,
            price=10.0,
        ),
        LifecycleExecutionEvent(
            trade_date=date(2024, 1, 7),
            symbol="000001.SZ",
            side="sell",
            status="accepted",
            reason_code="BAOMA_SCALE_OUT_5_PERCENT_TRIGGERED",
            requested_quantity=100,
            executed_quantity=100,
            price=11.0,
            position_quantity_after=200,
            remaining_cost_basis_after=9.5,
        ),
        LifecycleExecutionEvent(
            trade_date=date(2024, 1, 8),
            symbol="000001.SZ",
            side="sell",
            status="accepted",
            reason_code="BAOMA_MA60_STOP_TRIGGERED",
            requested_quantity=200,
            executed_quantity=200,
            price=9.0,
        ),
    )

    def fake_baoma_runner(*args, **kwargs):
        captured["bars_by_symbol"] = args[0]
        captured.update(kwargs)
        return BaomaBusinessRunResult(
            intents=(entry_intent, exit_intent),
            lifecycle_events=lifecycle_events,
            lifecycle_snapshots=(),
            closed_trades=(
                LifecycleClosedTrade(
                    symbol="000001.SZ",
                    entry_date=date(2024, 1, 5),
                    exit_date=date(2024, 1, 8),
                    entry_price=10.0,
                    exit_price=9.0,
                    quantity=200,
                    exit_reason="BAOMA_MA60_STOP_TRIGGERED",
                    original_entry_price=10.0,
                    remaining_cost_basis_at_exit=9.5,
                    entry_quantity=300,
                ),
            ),
            open_positions=(),
        )

    def fail_unused_entry_context(*args, **kwargs):
        raise AssertionError("baoma_v1_business must not build the unused generic entry attribution context")

    monkeypatch.setattr(run_plan_module, "run_baoma_v1_business", fake_baoma_runner)
    monkeypatch.setattr(run_plan_module, "_entry_attribution_context", fail_unused_entry_context)

    result = run_plan_module.execute_run_plan(_baoma_route_run_plan(tmp_path), provider=provider)

    assert result.engine == "baoma_v1_business"
    assert result.closed_trades[0].exit_reason == "BAOMA_MA60_STOP_TRIGGERED"
    assert result.lifecycle_events == lifecycle_events
    assert [event.reason_code for event in result.execution_audit] == [
        "BAOMA_ENTRY_TRIGGERED",
        "BAOMA_SCALE_OUT_5_PERCENT_TRIGGERED",
        "BAOMA_MA60_STOP_TRIGGERED",
    ]
    scale_out_audit = result.execution_audit[1]
    assert scale_out_audit.position_quantity_after == 200
    assert scale_out_audit.remaining_cost_basis_after == pytest.approx(9.5)
    assert captured["config"].total_asset_value == pytest.approx(1_200_000.0)
    assert captured["config"].max_holding_count == 12
    assert captured["config"].buy_slice_fraction == pytest.approx(0.25)
    assert captured["config"].board_lot_size == 100
    assert captured["config"].first_scale_out_return == pytest.approx(0.04)
    assert captured["config"].second_scale_out_return == pytest.approx(0.12)
    assert captured["config"].force_exit_at_end is True
    assert captured["entry_method"].method_name == "baoma_entry"
    assert captured["profit_exit_method"].method_name == "baoma_ma25_profit_exit"
    assert captured["stop_loss_method"].method_name == "baoma_ma60_stop"
    assert captured["add_on_method"].method_name == "baoma_add_on"
    entry_context = captured["entry_attribution_context"]
    assert entry_context.entry_filter.conditions[0].field == "entry.volatility.atr_20d_bucket"
    assert "entry.volatility.atr_20d_bucket" in entry_context.enabled_factor_keys


def _run_plan(snapshot_root: Path, *, refresh_snapshots: bool) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "executor-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-11",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "provider": "tushare",
                "price_adjustment": "qfq",
                "refresh_snapshots": refresh_snapshots,
                "symbols": ["000001.SZ", "000002.SZ"],
                "benchmark_series": {"indexes": ["000001.SH"]},
                "industry_series": {"source": "SW2021", "indexes": ["801780.SI"]},
            },
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
            "execution": {
                "engine": "business",
                "stake": 100,
            },
            "analysis": {
                "industry_attribution": {
                    "enabled": True,
                    "source": "SW2021",
                    "levels": [1, 2, 3],
                },
                "market_regime": {
                    "enabled": True,
                    "timeframes": ["D", "W", "M"],
                },
                "scenario_fit": {
                    "enabled": True,
                    "min_trades": 3,
                },
            },
        }
    )


def _stock_pool_run_plan(tmp_path: Path, pool_path: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "stock-pool-filter-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-11",
            },
            "data": {
                "snapshot_root": tmp_path / "snapshots",
                "provider": "tushare",
                "price_adjustment": "qfq",
                "refresh_snapshots": True,
                "stock_pool_file": pool_path,
            },
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
            "constraints": {
                "ashare": {
                    "enabled": False,
                },
            },
            "execution": {
                "engine": "business",
                "stake": 100,
            },
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )


def _baoma_route_run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "baoma-route-test",
                "from_date": "2024-01-02",
                "to_date": "2024-02-15",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "provider": "tushare",
                "price_adjustment": "qfq",
                "refresh_snapshots": True,
                "symbols": ["000001.SZ"],
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "baoma_entry",
                "profit_taking_method": "baoma_ma25_profit_exit",
                "stop_loss_method": "baoma_ma60_stop",
                "add_on_method": "baoma_add_on",
                "sizing_rule": "equal_weight",
                "sizing_params": {
                    "max_holding_count": 12,
                    "min_order_quantity": 100,
                },
            },
            "constraints": {
                "ashare": {
                    "enabled": True,
                    "board_lot_size": 100,
                },
            },
            "broker": {
                "initial_cash": 1_200_000,
                "commission_rate": 0.0003,
                "stamp_tax_rate": 0.001,
                "transfer_fee_rate": 0.00001,
                "slippage": {"type": "percent", "value": 0.0005},
            },
            "execution": {
                "engine": "baoma_v1_business",
                "stake": 100,
                "baoma": {
                    "buy_slice_fraction": 0.25,
                    "first_scale_out_return": 0.04,
                    "second_scale_out_return": 0.12,
                    "force_exit_at_end": True,
                },
            },
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
                "entry_attribution": {
                    "entry_filter": {
                        "enabled": True,
                        "conditions": [
                            {
                                "field": "entry.volatility.atr_20d_bucket",
                                "value": "2_3pct",
                                "action": "keep",
                            }
                        ],
                    },
                },
            },
        }
    )


def _index_run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "index-executor-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-11",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "provider": "tushare",
                "refresh_snapshots": True,
                "tradable_series": [
                    {
                        "symbol": "000001.SH",
                        "asset_type": "index",
                    }
                ],
            },
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
            "execution": {
                "engine": "business",
                "stake": 100,
            },
            "analysis": {
                "industry_attribution": {
                    "enabled": False,
                },
                "market_regime": {
                    "enabled": False,
                },
            },
        }
    )


def _macd_run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "macd-executor-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-31",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "provider": "tushare",
                "price_adjustment": "qfq",
                "refresh_snapshots": True,
                "symbols": ["000001.SZ"],
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "macd_bullish_crossover_entry",
                "profit_taking_method": "macd_bearish_crossover_exit",
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
            "constraints": {
                "ashare": {
                    "enabled": False,
                },
            },
            "execution": {
                "engine": "backtrader",
                "stake": 100,
            },
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )


def _combo_run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "combo-executor-test",
                "from_date": "2024-01-01",
                "to_date": "2024-03-30",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "provider": "tushare",
                "price_adjustment": "qfq",
                "refresh_snapshots": True,
                "symbols": ["000001.SZ"],
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "ma_macd_bullish_confirmation_entry",
                "profit_taking_method": "ma_macd_weakening_exit",
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
            "constraints": {
                "ashare": {
                    "enabled": False,
                },
            },
            "execution": {
                "engine": "business",
                "stake": 100,
            },
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )


def _macd_fixture_bars(symbol: str) -> tuple[DailyBar, ...]:
    closes = (
        [10.0] * 10
        + [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0]
        + [17.0, 16.0, 15.0, 14.0, 13.0, 12.0, 11.0, 10.0]
        + [11.0, 12.0, 13.0, 14.0]
    )
    start_date = date(2024, 1, 2)
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1000,
        )
        for index, close in enumerate(closes)
    )


def _combo_fixture_bars(symbol: str) -> tuple[DailyBar, ...]:
    start_date = date(2024, 1, 1)
    closes = [10.0 + index * 0.4 for index in range(90)]
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1000,
        )
        for index, close in enumerate(closes)
    )


def _route_fixture_bars(symbol: str) -> tuple[DailyBar, ...]:
    start_date = date(2023, 12, 1)
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=10.0 + index * 0.01,
            high=10.5 + index * 0.01,
            low=9.5 + index * 0.01,
            close=10.0 + index * 0.01,
            volume=1000,
        )
        for index in range(90)
    )


def _index_bars_from_daily_bars(bars: tuple[DailyBar, ...], *, symbol: str) -> tuple[IndexBar, ...]:
    return tuple(
        IndexBar(
            symbol=symbol,
            trade_date=bar.trade_date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            amount=bar.volume * bar.close,
        )
        for bar in bars
    )
