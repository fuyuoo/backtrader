from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from attbacktrader.cli import data_preflight as data_preflight_cli
from attbacktrader.config import RunPlan
from attbacktrader.data import DailyBar, IndexBar, TradabilityStatus
from attbacktrader.runners import run_data_preflight


class FakePreflightProvider:
    def __init__(self, bars_by_symbol: dict[str, tuple[DailyBar, ...]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.daily_calls: list[str] = []
        self.index_calls: list[str] = []
        self.tradability_calls: list[str] = []

    def fetch_daily_bars(self, *, symbol, start_date, end_date, adjustment):
        self.daily_calls.append(symbol)
        return self.bars_by_symbol.get(symbol, ())

    def fetch_index_daily_bars(self, *, symbol, start_date, end_date):
        self.index_calls.append(symbol)
        return tuple(
            IndexBar(symbol, start_date + timedelta(days=index), 100 + index, 101 + index, 99 + index, 100 + index)
            for index in range((end_date - start_date).days + 1)
        )

    def fetch_industry_index_daily_bars(self, *, symbol, start_date, end_date, source="SW2021"):
        return ()

    def fetch_shenwan_industry_classifications(self, *, source="SW2021"):
        return ()

    def fetch_stock_industry_memberships(self, *, symbol, source="SW2021"):
        return ()

    def fetch_tradability_statuses(self, *, symbol, start_date, end_date):
        self.tradability_calls.append(symbol)
        return tuple(
            TradabilityStatus(symbol=symbol, trade_date=bar.trade_date)
            for bar in self.bars_by_symbol.get(symbol, ())
            if start_date <= bar.trade_date <= end_date
        )


def test_data_preflight_reports_successful_symbols(tmp_path: Path) -> None:
    bars = _bars("000001.SZ", date(2022, 1, 1), 1100)
    provider = FakePreflightProvider({"000001.SZ": bars})

    report = run_data_preflight(_run_plan(tmp_path, symbols=("000001.SZ",)), provider=provider)

    assert report.status == "ok"
    assert report.checked_symbol_count == 1
    assert report.ok_symbol_count == 1
    assert report.symbol_results[0].bar_count > 0
    assert {item.name for item in report.symbol_results[0].indicator_coverage} == {"ma25", "ma60", "macd"}
    assert all(item.status == "ok" for item in report.symbol_results[0].indicator_coverage)
    assert report.symbol_results[0].tradability_coverage is not None
    assert report.symbol_results[0].tradability_coverage.status == "ok"


def test_data_preflight_keeps_going_when_one_symbol_fails(tmp_path: Path) -> None:
    bars = _bars("000001.SZ", date(2022, 1, 1), 1100)
    provider = FakePreflightProvider({"000001.SZ": bars})

    report = run_data_preflight(_run_plan(tmp_path, symbols=("000001.SZ", "000002.SZ")), provider=provider)

    assert report.status == "error"
    assert report.checked_symbol_count == 2
    assert report.failed_symbol_count == 1
    failed = report.symbol_results[1]
    assert failed.symbol == "000002.SZ"
    assert failed.status == "error"
    assert failed.error_type == "ValueError"
    assert provider.daily_calls == ["000001.SZ", "000002.SZ"]


def test_data_preflight_flags_indicator_coverage_alarm(tmp_path: Path) -> None:
    bars = _bars("000001.SZ", date(2024, 1, 1), 70)
    provider = FakePreflightProvider({"000001.SZ": bars})

    report = run_data_preflight(_run_plan(tmp_path, symbols=("000001.SZ",)), provider=provider)

    assert report.status == "error"
    assert report.symbol_results[0].status == "error"
    ma60 = next(item for item in report.symbol_results[0].indicator_coverage if item.name == "ma60")
    assert ma60.missing_ratio > 0.05
    assert report.issue_summary["indicator.ma60:D"] == 1


def test_data_preflight_cli_prints_json(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        """
run:
  id: preflight-cli
  from_date: "2024-01-01"
  to_date: "2024-01-10"
data:
  snapshot_root: "{snapshot_root}"
  refresh_snapshots: true
  symbols: ["000001.SZ"]
strategy:
  template: trend_template_v1
  entry_method: baoma_entry
  entry_params:
    dea_max_age_trading_days: 14
  profit_taking_method: baoma_ma25_profit_exit
  stop_loss_method: baoma_ma60_stop
  add_on_method: baoma_add_on
  sizing_rule: equal_weight
broker:
  initial_cash: 1000000
  commission_rate: 0
  stamp_tax_rate: 0
  transfer_fee_rate: 0
  slippage:
    type: percent
    value: 0
execution:
  engine: baoma_v1_business
""".format(snapshot_root=(tmp_path / "snapshots").as_posix()),
        encoding="utf-8",
    )
    bars = _bars("000001.SZ", date(2023, 1, 1), 390)

    class FakeTushareProvider(FakePreflightProvider):
        def __init__(self, token, **kwargs):
            super().__init__({"000001.SZ": bars})

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace())
    monkeypatch.setattr(data_preflight_cli, "read_tushare_token", lambda path: "token")
    monkeypatch.setattr(data_preflight_cli, "TushareProvider", FakeTushareProvider)

    exit_code = data_preflight_cli.main(["--config", str(config_path), "--json"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"schema": "attbacktrader.data_preflight.v1"' in output
    assert '"run_id": "preflight-cli"' in output


def _run_plan(tmp_path: Path, *, symbols: tuple[str, ...]) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {"id": "preflight-test", "from_date": "2024-01-01", "to_date": "2024-12-31"},
            "data": {
                "snapshot_root": tmp_path / "snapshots",
                "refresh_snapshots": True,
                "symbols": list(symbols),
                "benchmark_series": {"indexes": ["000300.SH"]},
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "baoma_entry",
                "entry_params": {"dea_max_age_trading_days": 14},
                "profit_taking_method": "baoma_ma25_profit_exit",
                "stop_loss_method": "baoma_ma60_stop",
                "add_on_method": "baoma_add_on",
                "add_on_params": {"dea_max_age_trading_days": 14},
                "sizing_rule": "equal_weight",
            },
            "broker": {
                "initial_cash": 1000000,
                "commission_rate": 0,
                "stamp_tax_rate": 0,
                "transfer_fee_rate": 0,
                "slippage": {"type": "percent", "value": 0},
            },
            "constraints": {
                "ashare": {
                    "enabled": True,
                    "t_plus_one": True,
                    "limit_up_down": True,
                    "suspension": True,
                    "board_lot_size": 100,
                }
            },
            "execution": {"engine": "baoma_v1_business"},
            "analysis": {"industry_attribution": {"enabled": False}},
        }
    )


def _bars(symbol: str, start_date: date, count: int) -> tuple[DailyBar, ...]:
    bars = []
    for index in range(count):
        close = 10.0 + index * 0.01
        bars.append(
            DailyBar(
                symbol=symbol,
                trade_date=start_date + timedelta(days=index),
                open=close - 0.02,
                high=close + 0.05,
                low=close - 0.05,
                close=close,
                volume=1000,
            )
        )
    return tuple(bars)
