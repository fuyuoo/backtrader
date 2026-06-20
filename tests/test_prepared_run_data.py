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
from attbacktrader.data.snapshots import (
    attribution_reference_snapshot_dir,
    read_daily_bars_csv,
    read_daily_bars_parquet,
    tradable_bars_snapshot_path,
    write_attribution_reference_snapshot,
    write_daily_bars_parquet,
)
from attbacktrader.features import (
    IndicatorRequirement,
    IndicatorSnapshotMetadata,
    build_indicator_snapshots,
    build_indicator_update_plans,
    indicator_snapshot_path,
    indicator_states_from_bars,
    read_indicator_snapshot_metadata,
    read_indicator_snapshots_parquet,
    write_indicator_snapshot_metadata,
    write_indicator_snapshots_parquet,
)
from attbacktrader.runners.prepared_data import prepare_run_data


class FakePreparedDataProvider:
    def __init__(self, bars: tuple[DailyBar, ...]) -> None:
        self.bars = bars
        self.calls: list[tuple[str, str]] = []
        self.daily_bar_ranges: list[tuple[str, date, date, str]] = []
        self.index_calls: list[str] = []
        self.index_ranges: list[tuple[str, date, date]] = []
        self.industry_index_calls: list[tuple[str, str]] = []
        self.industry_index_ranges: list[tuple[str, date, date, str]] = []
        self.classification_calls: list[str] = []
        self.membership_calls: list[tuple[str, str]] = []
        self.tradability_calls: list[str] = []

    def fetch_daily_bars(self, *, symbol, start_date, end_date, adjustment):
        self.calls.append((symbol, adjustment))
        self.daily_bar_ranges.append((symbol, start_date, end_date, adjustment))
        return tuple(
            replace(bar, symbol=symbol)
            for bar in self.bars
            if start_date <= bar.trade_date <= end_date
        )

    def fetch_index_daily_bars(self, *, symbol, start_date, end_date):
        self.index_calls.append(symbol)
        self.index_ranges.append((symbol, start_date, end_date))
        return _index_bars(symbol, start_date, end_date)

    def fetch_industry_index_daily_bars(self, *, symbol, start_date, end_date, source="SW2021"):
        self.industry_index_calls.append((symbol, source))
        self.industry_index_ranges.append((symbol, start_date, end_date, source))
        return _index_bars(symbol, start_date, end_date)

    def fetch_shenwan_industry_classifications(self, *, source="SW2021"):
        self.classification_calls.append(source)
        return (
            ShenwanIndustryClassification("801780.SI", "银行", 1, "480000", "0", source),
        )

    def fetch_stock_industry_memberships(self, *, symbol, source="SW2021"):
        self.membership_calls.append((symbol, source))
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


class FullCalendarPreparedDataProvider(FakePreparedDataProvider):
    def __init__(self, bars: tuple[DailyBar, ...], calendar_bars: tuple[IndexBar, ...]) -> None:
        super().__init__(bars)
        self.calendar_bars = calendar_bars

    def fetch_index_daily_bars(self, *, symbol, start_date, end_date):
        self.index_calls.append(symbol)
        self.index_ranges.append((symbol, start_date, end_date))
        return tuple(
            replace(bar, symbol=symbol)
            for bar in self.calendar_bars
            if start_date <= bar.trade_date <= end_date
        )


def test_prepare_run_data_returns_one_interface_for_snapshots_features_and_analysis_evidence(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)

    prepared = prepare_run_data(run_plan, provider=provider)

    assert prepared.symbols == ("000001.SZ",)
    assert prepared.adjustment_label == "qfq"
    assert tuple(prepared.bars_by_symbol) == ("000001.SZ",)
    assert tuple(prepared.indicators_by_symbol) == ("000001.SZ",)
    assert provider.calls == [("000001.SZ", "qfq")]
    assert provider.index_calls == ["000001.SH"]
    assert provider.industry_index_calls == [("801780.SI", "SW2021")]
    assert provider.classification_calls == ["SW2021"]
    assert provider.membership_calls == [("000001.SZ", "SW2021")]
    assert provider.tradability_calls == ["000001.SZ"]
    assert prepared.benchmark_results(run_plan)[0].bar_count == 2
    assert prepared.industry_index_results(run_plan)[0].calculation_bar_count == 2
    assert prepared.industry_index_results(run_plan)[0].snapshot_provenance.details["requested_start_date"] == "2023-12-14"
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_path.exists()
    assert prepared.symbol_data_by_symbol["000001.SZ"].indicator_snapshot_path.exists()
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_provenance.action == "created"
    assert prepared.symbol_data_by_symbol["000001.SZ"].indicator_snapshot_provenance[0].action == "created"
    assert prepared.symbol_data_by_symbol["000001.SZ"].data_quality_issues == ()
    assert prepared.symbol_data_by_symbol["000001.SZ"].tradability_snapshot_path is not None
    assert prepared.symbol_data_by_symbol["000001.SZ"].tradability_snapshot_path.exists()
    assert prepared.symbol_data_by_symbol["000001.SZ"].tradability_snapshot_provenance is not None
    assert prepared.symbol_data_by_symbol["000001.SZ"].tradability_snapshot_provenance.action == "created"
    assert prepared.tradability_by_symbol["000001.SZ"][0].trade_date == date(2024, 1, 2)
    assert prepared.industry_classification_result is not None
    assert prepared.industry_classification_result.snapshot_path.exists()
    assert prepared.industry_membership_results[0].snapshot_path.exists()
    assert prepared.risk_group_by_symbol(level=1) == {"000001.SZ": "801780.SI"}


def test_prepare_run_data_loads_attribution_reference_snapshot_evidence(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)
    reference_dir = attribution_reference_snapshot_dir(
        tmp_path,
        reference_universe="full_a_main_chinext_star",
        start_date=date(2023, 1, 1),
        end_date=date(2024, 12, 31),
    )
    write_attribution_reference_snapshot(
        {
            "metadata": {
                "reference_universe": "full_a_main_chinext_star",
                "start_date": "2023-01-01",
                "end_date": "2024-12-31",
            },
            "rows": [
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-02",
                    "field_key": "entry.market_cap.total_mv_abs_bucket",
                    "value": 80.0,
                    "bucket": "0_100yi",
                    "asof_date": "2024-01-02",
                    "staleness_trading_days": 0,
                    "exception_codes": [],
                }
            ],
        },
        reference_dir,
    )

    prepared = prepare_run_data(run_plan, provider=provider)

    evidence = prepared.attribution_reference_evidence_by_symbol_date["000001.SZ"][date(2024, 1, 2)]
    assert evidence.categories["entry.market_cap.total_mv_abs_bucket"] == "0_100yi"


def test_prepare_run_data_fetches_warmup_windows_for_entry_attribution_indexes(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={
            "data": run_plan.data.model_copy(
                update={
                    "benchmark_series": run_plan.data.benchmark_series.model_copy(
                        update={"indexes": ("000300.SH",)}
                    )
                }
            )
        }
    )

    prepared = prepare_run_data(run_plan, provider=provider)

    assert provider.index_ranges == [("000300.SH", date(2023, 10, 4), run_plan.run.to_date)]
    assert provider.industry_index_ranges == [
        ("801780.SI", date(2023, 12, 14), run_plan.run.to_date, "SW2021")
    ]
    assert prepared.benchmark_calculation_bars_by_symbol(run_plan)["000300.SH"][0].trade_date == date(2023, 10, 4)
    assert prepared.industry_index_calculation_bars_by_symbol(run_plan)["801780.SI"][0].trade_date == date(2023, 12, 14)
    assert prepared.benchmark_bars_by_symbol(run_plan)["000300.SH"][0].trade_date >= run_plan.run.from_date


def test_prepare_run_data_fetches_objective_market_component_warmup_windows(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={
            "data": run_plan.data.model_copy(
                update={
                    "benchmark_series": run_plan.data.benchmark_series.model_copy(
                        update={"indexes": ("000300.SH", "000905.SH")}
                    )
                }
            ),
            "analysis": run_plan.analysis.model_copy(
                update={
                    "entry_attribution": run_plan.analysis.entry_attribution.model_copy(
                        update={
                            "factors": (
                                "market.objective.entry_index_drawdown_250d_bucket",
                                "market.objective.entry_index_ma60_slope_20d_bucket",
                            )
                        }
                    )
                }
            ),
        }
    )

    prepared = prepare_run_data(run_plan, provider=provider)

    assert provider.index_ranges == [
        ("000300.SH", date(2023, 1, 11), run_plan.run.to_date),
        ("000905.SH", date(2023, 1, 11), run_plan.run.to_date),
    ]
    assert prepared.benchmark_calculation_bars_by_symbol(run_plan)["000300.SH"][0].trade_date == date(2023, 1, 11)
    assert prepared.benchmark_calculation_bars_by_symbol(run_plan)["000905.SH"][0].trade_date == date(2023, 1, 11)
    assert prepared.benchmark_bars_by_symbol(run_plan)["000300.SH"][0].trade_date >= run_plan.run.from_date
    assert prepared.benchmark_bars_by_symbol(run_plan)["000905.SH"][0].trade_date >= run_plan.run.from_date


def test_prepare_run_data_fetches_warmup_windows_for_selected_industry_relative_attribution(
    tmp_path: Path,
) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={
            "data": run_plan.data.model_copy(
                update={
                    "benchmark_series": run_plan.data.benchmark_series.model_copy(
                        update={"indexes": ("000300.SH",)}
                    )
                }
            ),
            "analysis": run_plan.analysis.model_copy(
                update={
                    "attribution": run_plan.analysis.attribution.model_copy(
                        update={
                            "include": (
                                "industry.ma.trend_state",
                                "industry.relative.hs300.strength_state",
                            )
                        }
                    )
                }
            ),
        }
    )

    prepared = prepare_run_data(run_plan, provider=provider)

    assert provider.index_ranges == [("000300.SH", date(2023, 10, 4), run_plan.run.to_date)]
    assert provider.industry_index_ranges == [
        ("801780.SI", date(2023, 10, 4), run_plan.run.to_date, "SW2021")
    ]
    assert prepared.benchmark_calculation_bars_by_symbol(run_plan)["000300.SH"][0].trade_date == date(2023, 10, 4)
    assert prepared.industry_index_calculation_bars_by_symbol(run_plan)["801780.SI"][0].trade_date == date(2023, 10, 4)


def test_prepare_run_data_fetches_warmup_window_for_selected_industry_weekly_kdj_attribution(
    tmp_path: Path,
) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={
            "analysis": run_plan.analysis.model_copy(
                update={
                    "attribution": run_plan.analysis.attribution.model_copy(
                        update={"include": ("industry.kdj.week.j",)}
                    )
                }
            ),
        }
    )

    prepared = prepare_run_data(run_plan, provider=provider)

    assert provider.industry_index_ranges == [
        ("801780.SI", date(2023, 10, 24), run_plan.run.to_date, "SW2021")
    ]
    assert prepared.industry_index_calculation_bars_by_symbol(run_plan)["801780.SI"][0].trade_date == date(2023, 10, 24)


def test_prepare_run_data_fetches_warmup_window_for_selected_industry_weekly_macd_attribution(
    tmp_path: Path,
) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={
            "analysis": run_plan.analysis.model_copy(
                update={
                    "attribution": run_plan.analysis.attribution.model_copy(
                        update={"include": ("industry.macd.week.energy_zone",)}
                    )
                }
            ),
        }
    )

    prepared = prepare_run_data(run_plan, provider=provider)

    assert provider.industry_index_ranges == [
        ("801780.SI", date(2023, 5, 2), run_plan.run.to_date, "SW2021")
    ]
    assert prepared.industry_index_calculation_bars_by_symbol(run_plan)["801780.SI"][0].trade_date == date(2023, 5, 2)


def test_prepare_run_data_uses_benchmark_index_as_trading_calendar(tmp_path: Path) -> None:
    bars = (
        DailyBar("000001.SZ", date(2024, 1, 2), 10.0, 11.0, 9.0, 10.0, 1000.0),
        DailyBar("000001.SZ", date(2024, 1, 4), 10.0, 11.0, 9.0, 10.0, 1000.0),
    )
    calendar_bars = (
        IndexBar("000001.SH", date(2024, 1, 2), 100.0, 101.0, 99.0, 100.0),
        IndexBar("000001.SH", date(2024, 1, 3), 101.0, 102.0, 100.0, 101.0),
        IndexBar("000001.SH", date(2024, 1, 4), 102.0, 103.0, 101.0, 102.0),
    )
    provider = FullCalendarPreparedDataProvider(bars, calendar_bars)
    run_plan = _calendar_quality_run_plan(tmp_path)

    prepared = prepare_run_data(run_plan, provider=provider)
    issue_codes = {issue.code for issue in prepared.symbol_data_by_symbol["000001.SZ"].data_quality_issues}

    assert prepared.trading_calendar is not None
    assert prepared.trading_calendar.name == "000001.SH"
    assert "MISSING_TRADING_SESSIONS" in issue_codes


def test_prepare_run_data_builds_indicators_required_by_selected_methods(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={
            "strategy": run_plan.strategy.model_copy(
                update={
                    "entry_method": "macd_bullish_crossover_entry",
                    "profit_taking_method": "macd_bearish_crossover_exit",
                }
            )
        }
    )

    prepared = prepare_run_data(run_plan, provider=provider)
    symbol_data = prepared.symbol_data_by_symbol["000001.SZ"]

    assert symbol_data.indicator_snapshot_path.parts[-3:-1] == ("macd", "qfq")
    assert symbol_data.indicator_snapshots[0].has_indicator("macd")
    assert not symbol_data.indicator_snapshots[0].has_indicator("kdj")
    assert symbol_data.indicator_frame.macd_at(date(2024, 1, 3)).line != 0.0


def test_prepare_run_data_builds_weekly_indicators_required_by_selected_methods(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    provider = FakePreparedDataProvider(bars)
    run_plan = _run_plan(tmp_path)
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

    prepared = prepare_run_data(run_plan, provider=provider)
    symbol_data = prepared.symbol_data_by_symbol["000001.SZ"]

    assert symbol_data.indicator_snapshot_path.parts[-4:-1] == ("macd", "W", "qfq")
    assert symbol_data.indicator_snapshot_paths == (symbol_data.indicator_snapshot_path,)
    assert {snapshot.timeframe for snapshot in symbol_data.indicator_snapshots} == {"W"}
    assert symbol_data.indicator_frame.macd_at(date(2024, 1, 5), timeframe="W").line is not None
    with pytest.raises(KeyError, match="MACD D is missing"):
        symbol_data.indicator_frame.macd_at(date(2024, 1, 5))


def test_prepare_run_data_fetches_warmup_window_for_required_indicators(tmp_path: Path) -> None:
    run_plan = _ma_run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={"data": run_plan.data.model_copy(update={"refresh_snapshots": True})}
    )
    warmup_start = date(2023, 10, 3)
    bars = _trend_bars_from(
        "000001.SZ",
        start_date=warmup_start,
        count=(run_plan.run.to_date - warmup_start).days + 1,
    )
    provider = FakePreparedDataProvider(bars)

    prepared = prepare_run_data(run_plan, provider=provider)
    symbol_data = prepared.symbol_data_by_symbol["000001.SZ"]

    assert provider.daily_bar_ranges == [
        ("000001.SZ", warmup_start, run_plan.run.to_date, "qfq"),
    ]
    assert symbol_data.bars[0].trade_date == run_plan.run.from_date
    assert symbol_data.bars[-1].trade_date == run_plan.run.to_date
    assert symbol_data.snapshot_provenance.start_date == warmup_start
    assert symbol_data.snapshot_provenance.details["requested_start_date"] == warmup_start.isoformat()
    assert symbol_data.indicator_snapshots[0].trade_date == warmup_start
    assert symbol_data.indicator_frame.ma_at(run_plan.run.from_date, period=60).value is not None


def test_prepare_run_data_fetches_one_year_symbol_warmup_for_baoma_engine(tmp_path: Path) -> None:
    run_plan = _ma_run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={"execution": run_plan.execution.model_copy(update={"engine": "baoma_v1_business"})}
    )
    warmup_start = date(2023, 1, 1)
    bars = _trend_bars_from(
        "000001.SZ",
        start_date=warmup_start,
        count=(run_plan.run.to_date - warmup_start).days + 1,
    )
    provider = FakePreparedDataProvider(bars)

    prepared = prepare_run_data(run_plan, provider=provider)
    symbol_data = prepared.symbol_data_by_symbol["000001.SZ"]

    assert provider.daily_bar_ranges == [
        ("000001.SZ", warmup_start, run_plan.run.to_date, "qfq"),
    ]
    assert symbol_data.bars[0].trade_date == run_plan.run.from_date
    assert symbol_data.snapshot_provenance.start_date == warmup_start
    assert symbol_data.snapshot_provenance.details["requested_start_date"] == warmup_start.isoformat()
    assert symbol_data.indicator_snapshots[0].trade_date == warmup_start


def test_prepare_run_data_includes_symbol_indicators_required_by_selected_attribution(
    tmp_path: Path,
) -> None:
    bars = _trend_bars("000001.SZ", count=70)
    run_plan = RunPlan.from_mapping(
        {
            "run": {
                "id": "prepared-data-attribution-indicator-test",
                "from_date": "2024-01-01",
                "to_date": "2024-03-10",
            },
            "data": {
                "snapshot_root": tmp_path,
                "refresh_snapshots": False,
                "symbols": ["000001.SZ"],
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "ma_bullish_trend_entry",
                "profit_taking_method": "rsi_overbought_exit",
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
            "analysis": {
                "attribution": {
                    "enabled": True,
                    "include": [
                        "symbol.kdj.j",
                        "symbol.kdj.j_below_threshold",
                        "symbol.kdj.week.j",
                        "symbol.kdj.week.j_bucket",
                        "symbol.macd.energy_zone",
                        "symbol.macd.week.energy_zone",
                    ],
                },
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )
    bar_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type="stock",
        adjustment="qfq",
    )
    write_daily_bars_parquet(bars, bar_path)

    prepared = prepare_run_data(run_plan, provider=None)
    symbol_data = prepared.symbol_data_by_symbol["000001.SZ"]

    assert symbol_data.indicator_frame.kdj_at(run_plan.run.to_date).j is not None
    assert symbol_data.indicator_frame.kdj_at(run_plan.run.to_date, timeframe="W").j is not None
    assert symbol_data.indicator_frame.macd_at(run_plan.run.to_date).line is not None
    assert symbol_data.indicator_frame.macd_at(run_plan.run.to_date, timeframe="W").line is not None
    assert {snapshot.timeframe for snapshot in symbol_data.indicator_snapshots} == {"D", "W"}


def test_prepare_run_data_allows_trailing_gap_when_run_window_has_bars(tmp_path: Path) -> None:
    run_plan = _ma_run_plan(tmp_path)
    run_plan = run_plan.model_copy(
        update={"data": run_plan.data.model_copy(update={"refresh_snapshots": True})}
    )
    warmup_start = date(2023, 10, 3)
    available_end = run_plan.run.to_date - timedelta(days=5)
    bars = _trend_bars_from(
        "000001.SZ",
        start_date=warmup_start,
        count=(available_end - warmup_start).days + 1,
    )
    provider = FakePreparedDataProvider(bars)

    prepared = prepare_run_data(run_plan, provider=provider)
    symbol_data = prepared.symbol_data_by_symbol["000001.SZ"]
    issue_codes = {issue.code for issue in symbol_data.data_quality_issues}

    assert symbol_data.bars[0].trade_date == run_plan.run.from_date
    assert symbol_data.bars[-1].trade_date == available_end
    assert "MISSING_TRAILING_RANGE" in issue_codes
    assert symbol_data.snapshot_provenance.details["warmup_incomplete"] is True


def test_index_bars_cover_date_range_allows_short_leading_calendar_gap() -> None:
    from attbacktrader.runners.prepared_data import _index_bars_cover_date_range

    bars = _index_bars("000300.SH", date(2023, 1, 3), date(2023, 1, 5))

    assert _index_bars_cover_date_range(
        bars,
        start_date=date(2023, 1, 1),
        end_date=date(2023, 1, 5),
    )


def test_prepare_run_data_incrementally_overwrites_indicator_tail(tmp_path: Path) -> None:
    bars = _trend_bars("000001.SZ", count=70)
    run_plan = _ma_run_plan(tmp_path)
    bar_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type="stock",
        adjustment="qfq",
    )
    indicator_path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        adjustment="qfq",
        indicator_names=("kdj", "ma20", "ma60"),
    )
    write_daily_bars_parquet(bars, bar_path)
    write_indicator_snapshots_parquet(
        build_indicator_snapshots(bars[:65], indicator_names=("kdj", "ma20", "ma60")),
        indicator_path,
    )

    prepared = prepare_run_data(run_plan, provider=None)
    loaded_snapshots = read_indicator_snapshots_parquet(indicator_path)

    assert len(loaded_snapshots) == len(bars)
    assert loaded_snapshots[-1].trade_date == bars[-1].trade_date
    assert loaded_snapshots[-1].ma60 is not None
    assert prepared.symbol_data_by_symbol["000001.SZ"].indicator_snapshot_path == indicator_path


def test_prepare_run_data_incrementally_fills_existing_bar_snapshot(tmp_path: Path) -> None:
    bars = _trend_bars("000001.SZ", count=70)
    provider = FakePreparedDataProvider(bars)
    run_plan = _ma_run_plan(tmp_path)
    warmup_start = date(2023, 10, 3)
    bar_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type="stock",
        adjustment="qfq",
    )
    write_daily_bars_parquet(bars[:60], bar_path)

    prepared = prepare_run_data(run_plan, provider=provider)
    snapshot_path = prepared.symbol_data_by_symbol["000001.SZ"].snapshot_path

    assert provider.daily_bar_ranges == [
        ("000001.SZ", warmup_start, run_plan.run.from_date - timedelta(days=1), "qfq"),
        ("000001.SZ", bars[60].trade_date, run_plan.run.to_date, "qfq"),
    ]
    assert read_daily_bars_parquet(snapshot_path) == bars
    assert len(prepared.bars_by_symbol["000001.SZ"]) == len(bars)
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_provenance.action == "incremental_filled"
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_provenance.details["warmup_incomplete"] is True


def test_prepare_run_data_discovers_broader_bar_snapshot_without_provider(tmp_path: Path) -> None:
    run_plan = _ma_run_plan(tmp_path)
    warmup_start = date(2023, 10, 3)
    broad_bars = _trend_bars_from(
        "000001.SZ",
        start_date=warmup_start,
        count=(date(2024, 3, 19) - warmup_start).days + 1,
    )
    broad_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=warmup_start,
        end_date=date(2024, 3, 19),
        asset_type="stock",
        adjustment="qfq",
    )
    target_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=warmup_start,
        end_date=run_plan.run.to_date,
        asset_type="stock",
        adjustment="qfq",
    )
    write_daily_bars_parquet(broad_bars, broad_path)

    prepared = prepare_run_data(run_plan, provider=None)
    expected_bars = tuple(
        bar
        for bar in broad_bars
        if run_plan.run.from_date <= bar.trade_date <= run_plan.run.to_date
    )
    expected_snapshot_bars = tuple(
        bar
        for bar in broad_bars
        if warmup_start <= bar.trade_date <= run_plan.run.to_date
    )

    assert prepared.bars_by_symbol["000001.SZ"] == expected_bars
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_path == target_path
    assert target_path.exists()
    assert read_daily_bars_parquet(target_path) == expected_snapshot_bars
    assert (
        prepared.symbol_data_by_symbol["000001.SZ"]
        .indicator_frame.ma_at(run_plan.run.from_date, period=60)
        .value
        is not None
    )
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_provenance.action == "range_reused"
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_provenance.source_paths == (broad_path,)


def test_prepare_run_data_extends_discovered_bar_snapshot_edges(tmp_path: Path) -> None:
    bars = _trend_bars("000001.SZ", count=70)
    provider = FakePreparedDataProvider(bars)
    run_plan = _ma_run_plan(tmp_path)
    warmup_start = date(2023, 10, 3)
    central_bars = tuple(
        bar
        for bar in bars
        if date(2024, 1, 10) <= bar.trade_date <= date(2024, 2, 20)
    )
    central_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 10),
        end_date=date(2024, 2, 20),
        asset_type="stock",
        adjustment="qfq",
    )
    target_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=warmup_start,
        end_date=run_plan.run.to_date,
        asset_type="stock",
        adjustment="qfq",
    )
    write_daily_bars_parquet(central_bars, central_path)

    prepared = prepare_run_data(run_plan, provider=provider)

    assert provider.daily_bar_ranges == [
        ("000001.SZ", warmup_start, date(2024, 1, 9), "qfq"),
        ("000001.SZ", date(2024, 2, 21), date(2024, 3, 10), "qfq"),
    ]
    assert prepared.bars_by_symbol["000001.SZ"] == bars
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_path == target_path
    assert read_daily_bars_parquet(target_path) == bars
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_provenance.action == "incremental_filled"
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_provenance.details["warmup_incomplete"] is True


def test_prepare_run_data_uses_indicator_state_to_append_stateful_snapshots(tmp_path: Path) -> None:
    bars = _trend_bars("000001.SZ", count=40)
    run_plan = _macd_run_plan(tmp_path)
    bar_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type="stock",
        adjustment="qfq",
    )
    indicator_path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        adjustment="qfq",
        indicator_names=("macd",),
    )
    initial_bars = bars[:30]
    plan = build_indicator_update_plans(
        symbol="000001.SZ",
        indicator_requirements=(IndicatorRequirement("macd"),),
    )[0]
    write_daily_bars_parquet(bars, bar_path)
    write_indicator_snapshots_parquet(
        build_indicator_snapshots(initial_bars, indicator_names=("macd",)),
        indicator_path,
    )
    write_indicator_snapshot_metadata(
        indicator_path,
        IndicatorSnapshotMetadata(
            symbol="000001.SZ",
            timeframe="D",
            indicator_names=("macd",),
            version_fingerprint=plan.version_fingerprint,
            start_date=initial_bars[0].trade_date,
            end_date=initial_bars[-1].trade_date,
            warmup_bars=plan.warmup_bars,
            recompute_lookback_bars=plan.recompute_lookback_bars,
            requires_state=plan.requires_state,
            states=indicator_states_from_bars(("macd",), initial_bars),
        ),
    )

    prepared = prepare_run_data(run_plan, provider=None)
    loaded_snapshots = read_indicator_snapshots_parquet(indicator_path)
    metadata = read_indicator_snapshot_metadata(indicator_path)

    assert loaded_snapshots == build_indicator_snapshots(bars, indicator_names=("macd",))
    assert metadata is not None
    assert metadata.end_date == bars[-1].trade_date
    assert "fast_ema" in metadata.states["macd"]
    assert prepared.symbol_data_by_symbol["000001.SZ"].indicator_snapshot_path == indicator_path
    assert prepared.symbol_data_by_symbol["000001.SZ"].indicator_snapshot_provenance[0].action == "incremental_filled"


def test_prepare_run_data_discovers_longer_indicator_snapshot_without_rebuilding(tmp_path: Path) -> None:
    bars = _trend_bars("000001.SZ", count=70)
    longer_bars = _trend_bars("000001.SZ", count=80)
    run_plan = _ma_run_plan(tmp_path)
    bar_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type="stock",
        adjustment="qfq",
    )
    longer_indicator_path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.from_date + timedelta(days=79),
        adjustment="qfq",
        indicator_names=("kdj", "ma20", "ma60"),
    )
    target_indicator_path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        adjustment="qfq",
        indicator_names=("kdj", "ma20", "ma60"),
    )
    write_daily_bars_parquet(bars, bar_path)
    write_indicator_snapshots_parquet(
        build_indicator_snapshots(longer_bars, indicator_names=("kdj", "ma20", "ma60")),
        longer_indicator_path,
    )

    prepared = prepare_run_data(run_plan, provider=None)
    loaded_snapshots = read_indicator_snapshots_parquet(target_indicator_path)

    assert loaded_snapshots == build_indicator_snapshots(bars, indicator_names=("kdj", "ma20", "ma60"))
    assert target_indicator_path.exists()
    assert target_indicator_path != longer_indicator_path
    assert prepared.symbol_data_by_symbol["000001.SZ"].indicator_snapshot_path == target_indicator_path
    assert prepared.symbol_data_by_symbol["000001.SZ"].indicator_snapshot_provenance[0].action == "range_reused"


def test_prepare_run_data_records_large_bar_gap_quality_issue(tmp_path: Path) -> None:
    run_plan = _quality_run_plan(tmp_path)
    bars = (
        DailyBar("000001.SZ", date(2024, 1, 1), 10.0, 11.0, 9.0, 10.0, 1000.0),
        DailyBar("000001.SZ", date(2024, 1, 20), 10.0, 11.0, 9.0, 10.0, 1000.0),
    )
    bar_path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type="stock",
        adjustment="qfq",
    )
    write_daily_bars_parquet(bars, bar_path)

    prepared = prepare_run_data(run_plan, provider=None)
    issue_codes = {issue.code for issue in prepared.symbol_data_by_symbol["000001.SZ"].data_quality_issues}

    assert "LARGE_CALENDAR_GAP" in issue_codes


def _run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "prepared-data-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-11",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "refresh_snapshots": True,
                "symbols": ["000001.SZ"],
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
        }
    )


def _ma_run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "prepared-data-ma-incremental-test",
                "from_date": "2024-01-01",
                "to_date": "2024-03-10",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "refresh_snapshots": False,
                "symbols": ["000001.SZ"],
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "ma_bullish_trend_entry",
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
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )


def _macd_run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "prepared-data-macd-state-test",
                "from_date": "2024-01-01",
                "to_date": "2024-02-09",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "refresh_snapshots": False,
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
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )


def _quality_run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "prepared-data-quality-test",
                "from_date": "2024-01-01",
                "to_date": "2024-01-20",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "refresh_snapshots": False,
                "symbols": ["000001.SZ"],
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
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )


def _calendar_quality_run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "prepared-data-calendar-quality-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-04",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "refresh_snapshots": True,
                "symbols": ["000001.SZ"],
                "benchmark_series": {"indexes": ["000001.SH"]},
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
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )


def _trend_bars(symbol: str, *, count: int) -> tuple[DailyBar, ...]:
    return _trend_bars_from(symbol, start_date=date(2024, 1, 1), count=count)


def _trend_bars_from(symbol: str, *, start_date: date, count: int) -> tuple[DailyBar, ...]:
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=10.0 + index,
            high=11.0 + index,
            low=9.0 + index,
            close=10.0 + index,
            volume=1000,
        )
        for index in range(count)
    )


def _index_bars(symbol: str, start_date: date, end_date: date) -> tuple[IndexBar, ...]:
    return (
        IndexBar(symbol, start_date, 100.0, 101.0, 99.0, 100.0),
        IndexBar(symbol, end_date, 110.0, 111.0, 109.0, 110.0),
    )
