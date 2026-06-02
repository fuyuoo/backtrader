import json
from pathlib import Path

from attbacktrader.config import RunPlan
from attbacktrader.data import DailyBar
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.reports import write_run_artifacts
from attbacktrader.runners import execute_run_plan


class FakeDailyProvider:
    def __init__(self, bars: tuple[DailyBar, ...]) -> None:
        self.bars = bars

    def fetch_daily_bars(self, *, symbol, start_date, end_date, adjustment):
        return self.bars


def test_write_run_artifacts_persists_report_plan_trades_and_snapshots(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    run_plan = _run_plan(tmp_path / "snapshots")
    result = execute_run_plan(run_plan, provider=FakeDailyProvider(bars))

    artifacts = write_run_artifacts(run_plan, result, output_root=tmp_path / "reports")

    assert artifacts.output_dir == tmp_path / "reports" / "writer-test"
    assert artifacts.run_plan_path.exists()
    assert artifacts.result_path.exists()
    assert artifacts.report_path.exists()
    assert artifacts.report_markdown_path.exists()
    assert artifacts.trades_path.exists()
    assert artifacts.equity_curve_path.exists()
    assert artifacts.positions_path.exists()
    assert artifacts.execution_audit_path.exists()
    assert artifacts.snapshots_path.exists()

    run_plan_payload = _read_json(artifacts.run_plan_path)
    report_payload = _read_json(artifacts.report_path)
    trades_payload = _read_json(artifacts.trades_path)
    equity_curve_payload = _read_json(artifacts.equity_curve_path)
    positions_payload = _read_json(artifacts.positions_path)
    execution_audit_payload = _read_json(artifacts.execution_audit_path)
    snapshots_payload = _read_json(artifacts.snapshots_path)
    report_markdown = artifacts.report_markdown_path.read_text(encoding="utf-8")

    assert run_plan_payload["run"]["id"] == "writer-test"
    assert report_payload["report_id"] == "writer-test"
    assert report_payload["execution_costs"]["completed_count"] > 0
    assert "# Backtest Report: writer-test" in report_markdown
    assert "## Returns" in report_markdown
    assert "## Trade Quality" in report_markdown
    assert "## Execution Costs" in report_markdown
    assert len(trades_payload["closed_trades"]) == 2
    assert equity_curve_payload[-1]["total_value"] == result.final_value
    assert len(positions_payload) == len(result.position_snapshots)
    assert any(event["event_type"] == "completed" for event in execution_audit_payload)
    assert snapshots_payload["symbols"][0]["symbol"] == "000001.SZ"
    assert snapshots_payload["symbols"][0]["snapshot_path"].endswith(".parquet")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "writer-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-11",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "refresh_snapshots": True,
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
            "execution": {
                "engine": "backtrader",
                "stake": 1,
            },
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )
