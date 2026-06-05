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
    assert artifacts.report_chinese_markdown_path.exists()
    assert artifacts.trades_path.exists()
    assert artifacts.signal_audit_path.exists()
    assert artifacts.sizing_audit_path.exists()
    assert artifacts.result_diagnostics_path.exists()
    assert artifacts.trade_lifecycle_path.exists()
    assert artifacts.trade_lifecycle_chinese_markdown_path.exists()
    assert artifacts.trade_review_path.exists()
    assert artifacts.trade_review_chinese_markdown_path.exists()
    assert artifacts.environment_fit_path.exists()
    assert artifacts.environment_fit_chinese_markdown_path.exists()
    assert artifacts.strategy_environment_profile_path.exists()
    assert artifacts.strategy_environment_profile_chinese_markdown_path.exists()
    assert artifacts.post_exit_analysis_path.exists()
    assert artifacts.post_exit_analysis_chinese_markdown_path.exists()
    assert artifacts.evidence_validation_path.exists()
    assert artifacts.equity_curve_path.exists()
    assert artifacts.positions_path.exists()
    assert artifacts.execution_audit_path.exists()
    assert artifacts.snapshots_path.exists()

    run_plan_payload = _read_json(artifacts.run_plan_path)
    report_payload = _read_json(artifacts.report_path)
    trades_payload = _read_json(artifacts.trades_path)
    signal_audit_payload = _read_json(artifacts.signal_audit_path)
    sizing_audit_payload = _read_json(artifacts.sizing_audit_path)
    result_diagnostics_payload = _read_json(artifacts.result_diagnostics_path)
    trade_lifecycle_payload = _read_json(artifacts.trade_lifecycle_path)
    trade_review_payload = _read_json(artifacts.trade_review_path)
    environment_fit_payload = _read_json(artifacts.environment_fit_path)
    strategy_environment_profile_payload = _read_json(artifacts.strategy_environment_profile_path)
    post_exit_analysis_payload = _read_json(artifacts.post_exit_analysis_path)
    evidence_validation_payload = _read_json(artifacts.evidence_validation_path)
    equity_curve_payload = _read_json(artifacts.equity_curve_path)
    positions_payload = _read_json(artifacts.positions_path)
    execution_audit_payload = _read_json(artifacts.execution_audit_path)
    snapshots_payload = _read_json(artifacts.snapshots_path)
    report_markdown = artifacts.report_markdown_path.read_text(encoding="utf-8")
    report_chinese_markdown = artifacts.report_chinese_markdown_path.read_text(encoding="utf-8")
    trade_lifecycle_markdown = artifacts.trade_lifecycle_chinese_markdown_path.read_text(encoding="utf-8")
    trade_review_markdown = artifacts.trade_review_chinese_markdown_path.read_text(encoding="utf-8")
    environment_fit_markdown = artifacts.environment_fit_chinese_markdown_path.read_text(encoding="utf-8")
    strategy_environment_profile_markdown = artifacts.strategy_environment_profile_chinese_markdown_path.read_text(
        encoding="utf-8"
    )
    post_exit_analysis_markdown = artifacts.post_exit_analysis_chinese_markdown_path.read_text(encoding="utf-8")

    assert run_plan_payload["run"]["id"] == "writer-test"
    assert report_payload["report_id"] == "writer-test"
    assert report_payload["execution_costs"]["completed_count"] > 0
    assert "# Backtest Report: writer-test" in report_markdown
    assert "## Returns" in report_markdown
    assert "## Trade Quality" in report_markdown
    assert "## Execution Costs" in report_markdown
    assert "# 回测报告：writer-test" in report_chinese_markdown
    assert "## 收益与风险" in report_chinese_markdown
    assert "## 交易质量" in report_chinese_markdown
    assert "## 执行成本" in report_chinese_markdown
    assert len(trades_payload["closed_trades"]) == 2
    assert signal_audit_payload[0]["method_name"] == "kdj_oversold_entry"
    assert "reason_code" in signal_audit_payload[0]
    assert "signal_values" in signal_audit_payload[0]
    assert "checks" in signal_audit_payload[0]["signal_values"]
    assert "attribution" in signal_audit_payload[0]["signal_values"]
    assert sizing_audit_payload
    assert sizing_audit_payload[0]["sizing"]["method_name"] == "equal_weight"
    assert result_diagnostics_payload["symbols"][0]["symbol"] == "000001.SZ"
    assert result_diagnostics_payload["symbols"][0]["closed_trade_count"] == 2
    assert "portfolio_entry_contrasts" in result_diagnostics_payload
    assert "portfolio_winning_entry_summary" in result_diagnostics_payload
    assert "portfolio_exit_contrasts" in result_diagnostics_payload
    assert "portfolio_winning_exit_summary" in result_diagnostics_payload
    assert "portfolio_add_on_signal_count" in result_diagnostics_payload
    assert "portfolio_winning_add_on_summary" in result_diagnostics_payload
    assert "portfolio_losing_add_on_summary" in result_diagnostics_payload
    assert "portfolio_add_on_contrasts" in result_diagnostics_payload
    assert "winning_trade_attributions" in result_diagnostics_payload["symbols"][0]
    assert "losing_trade_attributions" in result_diagnostics_payload["symbols"][0]
    assert "winning_trade_exit_attributions" in result_diagnostics_payload["symbols"][0]
    assert "losing_trade_exit_attributions" in result_diagnostics_payload["symbols"][0]
    assert "winning_trade_add_on_attributions" in result_diagnostics_payload["symbols"][0]
    assert "losing_trade_add_on_attributions" in result_diagnostics_payload["symbols"][0]
    assert "add_on_signal_count" in result_diagnostics_payload["symbols"][0]
    assert trade_lifecycle_payload["trade_count"] == 2
    assert trade_lifecycle_payload["indexes"]["by_outcome"]
    assert trade_lifecycle_payload["indexes"]["by_symbol"][0]["key"] == "000001.SZ"
    assert trade_lifecycle_payload["lifecycles"][0]["events"][0]["event_type"] == "entry"
    assert trade_lifecycle_payload["lifecycles"][0]["events"][-1]["event_type"] == "exit"
    assert trade_lifecycle_payload["lifecycles"][0]["events"][0]["executions"]
    assert "# 交易生命周期审阅" in trade_lifecycle_markdown
    assert trade_review_payload["trade_count"] == 2
    assert "sold_too_early_profiles" in trade_review_payload
    assert "stop_loss_rebound_profiles" in trade_review_payload
    assert "opportunity_summaries" in trade_review_payload
    assert "opportunity_cost_summaries" in trade_review_payload
    assert "add_on_entry_summaries" in trade_review_payload
    assert "add_on_entry_points" in trade_review_payload
    assert trade_review_payload["add_on_entry_count"] == 0
    assert "# 交易复盘" in trade_review_markdown
    assert "## 交易复盘明细" in trade_review_markdown
    assert environment_fit_payload["schema"] == "attbacktrader.environment_fit.v1"
    assert environment_fit_payload["trade_count"] == 2
    assert "single_factor_summaries" in environment_fit_payload
    assert "combination_summaries" in environment_fit_payload
    assert "trade_contributions" in environment_fit_payload
    assert "# 策略环境适配与利润贡献" in environment_fit_markdown
    assert "## 交易利润贡献明细" in environment_fit_markdown
    assert strategy_environment_profile_payload["schema"] == "attbacktrader.strategy_environment_profile.v1"
    assert strategy_environment_profile_payload["trade_count"] == 2
    assert "preferred_environments" in strategy_environment_profile_payload
    assert "avoid_environments" in strategy_environment_profile_payload
    assert "uncertain_environments" in strategy_environment_profile_payload
    assert "# 策略环境画像" in strategy_environment_profile_markdown
    assert "## 适合环境候选" in strategy_environment_profile_markdown
    assert post_exit_analysis_payload["window_days"] == 5
    assert post_exit_analysis_payload["configured_window_days"] == [5]
    assert post_exit_analysis_payload["rebound_thresholds"] == [0.0, 0.02, 0.05, 0.1]
    assert post_exit_analysis_payload["threshold_summaries"]
    assert post_exit_analysis_payload["window_summaries"]
    assert "factor_group_summaries" in post_exit_analysis_payload
    assert post_exit_analysis_payload["trade_count"] == 2
    assert post_exit_analysis_payload["observations"][0]["observed_day_count"] > 0
    assert "# 卖出后观察" in post_exit_analysis_markdown
    assert "## 反弹阈值分层" in post_exit_analysis_markdown
    assert evidence_validation_payload["status"] == "ok"
    assert evidence_validation_payload["error_count"] == 0
    assert evidence_validation_payload["counts"]["closed_trade_count"] == 2
    assert evidence_validation_payload["counts"]["sizing_decision_count"] == len(sizing_audit_payload)
    assert evidence_validation_payload["counts"]["post_exit_threshold_summary_count"] > 0
    assert evidence_validation_payload["counts"]["trade_review_trade_count"] == 2
    assert "trade_review_add_on_entry_count" in evidence_validation_payload["counts"]
    assert equity_curve_payload[-1]["total_value"] == result.final_value
    assert len(positions_payload) == len(result.position_snapshots)
    assert any(event["event_type"] == "completed" for event in execution_audit_payload)
    assert snapshots_payload["data_windows"]["items"]
    assert snapshots_payload["data_windows"]["warmup_incomplete_count"] >= 0
    assert snapshots_payload["symbols"][0]["symbol"] == "000001.SZ"
    assert snapshots_payload["symbols"][0]["snapshot_path"].endswith(".parquet")
    assert snapshots_payload["symbols"][0]["indicator_snapshot_paths"] == [
        snapshots_payload["symbols"][0]["indicator_snapshot_path"]
    ]
    assert snapshots_payload["symbols"][0]["snapshot_provenance"]["action"] == "created"
    assert snapshots_payload["symbols"][0]["indicator_snapshot_provenance"][0]["action"] == "created"
    assert snapshots_payload["symbols"][0]["data_quality_issues"] == []


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
