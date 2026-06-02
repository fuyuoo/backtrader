from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from attbacktrader.config import RunPlan
from attbacktrader.data import (
    DailyBar,
    IndexBar,
    ShenwanIndustryClassification,
    StockIndustryMembership,
    TradabilityStatus,
)
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.runners.prepared_data import prepare_run_data


class FakePreparedDataProvider:
    def __init__(self, bars: tuple[DailyBar, ...]) -> None:
        self.bars = bars
        self.calls: list[tuple[str, str]] = []
        self.index_calls: list[str] = []
        self.industry_index_calls: list[tuple[str, str]] = []
        self.classification_calls: list[str] = []
        self.membership_calls: list[tuple[str, str]] = []
        self.tradability_calls: list[str] = []

    def fetch_daily_bars(self, *, symbol, start_date, end_date, adjustment):
        self.calls.append((symbol, adjustment))
        return tuple(replace(bar, symbol=symbol) for bar in self.bars)

    def fetch_index_daily_bars(self, *, symbol, start_date, end_date):
        self.index_calls.append(symbol)
        return _index_bars(symbol, start_date, end_date)

    def fetch_industry_index_daily_bars(self, *, symbol, start_date, end_date, source="SW2021"):
        self.industry_index_calls.append((symbol, source))
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
    assert prepared.industry_index_results(run_plan)[0].bar_count == 2
    assert prepared.symbol_data_by_symbol["000001.SZ"].snapshot_path.exists()
    assert prepared.symbol_data_by_symbol["000001.SZ"].indicator_snapshot_path.exists()
    assert prepared.symbol_data_by_symbol["000001.SZ"].tradability_snapshot_path is not None
    assert prepared.symbol_data_by_symbol["000001.SZ"].tradability_snapshot_path.exists()
    assert prepared.tradability_by_symbol["000001.SZ"][0].trade_date == date(2024, 1, 2)
    assert prepared.industry_classification_result is not None
    assert prepared.industry_classification_result.snapshot_path.exists()
    assert prepared.industry_membership_results[0].snapshot_path.exists()


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


def _index_bars(symbol: str, start_date: date, end_date: date) -> tuple[IndexBar, ...]:
    return (
        IndexBar(symbol, start_date, 100.0, 101.0, 99.0, 100.0),
        IndexBar(symbol, end_date, 110.0, 111.0, 109.0, 110.0),
    )
