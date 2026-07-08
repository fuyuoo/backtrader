import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

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
    assert artifacts.trade_attribution_path.exists()
    assert artifacts.trade_attribution_chinese_markdown_path.exists()
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
    assert artifacts.data_preflight_path.exists()
    assert artifacts.stock_pool_filter_path.exists()
    assert artifacts.attribution_factor_selection_path.exists()
    assert not artifacts.entry_score_contract_path.exists()

    run_plan_payload = _read_json(artifacts.run_plan_path)
    result_payload = _read_json(artifacts.result_path)
    report_payload = _read_json(artifacts.report_path)
    trades_payload = pd.read_parquet(artifacts.trades_path)
    signal_audit_payload = pd.read_parquet(artifacts.signal_audit_path)
    sizing_audit_payload = pd.read_parquet(artifacts.sizing_audit_path)
    result_diagnostics_payload = _read_json(artifacts.result_diagnostics_path)
    trade_lifecycle_payload = _read_json(artifacts.trade_lifecycle_path)
    trade_attribution_payload = _read_json(artifacts.trade_attribution_path)
    trade_review_payload = _read_json(artifacts.trade_review_path)
    environment_fit_payload = _read_json(artifacts.environment_fit_path)
    strategy_environment_profile_payload = _read_json(artifacts.strategy_environment_profile_path)
    post_exit_analysis_payload = _read_json(artifacts.post_exit_analysis_path)
    evidence_validation_payload = _read_json(artifacts.evidence_validation_path)
    equity_curve_payload = pd.read_parquet(artifacts.equity_curve_path)
    positions_payload = pd.read_parquet(artifacts.positions_path)
    execution_audit_payload = pd.read_parquet(artifacts.execution_audit_path)
    snapshots_payload = _read_json(artifacts.snapshots_path)
    data_preflight_payload = json.loads(artifacts.data_preflight_path.read_text(encoding="utf-8"))
    stock_pool_filter_payload = json.loads(artifacts.stock_pool_filter_path.read_text(encoding="utf-8"))
    attribution_factor_selection_payload = _read_json(artifacts.attribution_factor_selection_path)
    report_markdown = artifacts.report_markdown_path.read_text(encoding="utf-8")
    report_chinese_markdown = artifacts.report_chinese_markdown_path.read_text(encoding="utf-8")
    trade_lifecycle_markdown = artifacts.trade_lifecycle_chinese_markdown_path.read_text(encoding="utf-8")
    trade_attribution_markdown = artifacts.trade_attribution_chinese_markdown_path.read_text(encoding="utf-8")
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
    assert artifacts.trades_path.name == "trades.parquet"
    assert artifacts.signal_audit_path.name == "signal_audit.parquet"
    assert artifacts.sizing_audit_path.name == "sizing_audit.parquet"
    assert artifacts.equity_curve_path.name == "equity_curve.parquet"
    assert artifacts.positions_path.name == "positions.parquet"
    assert artifacts.execution_audit_path.name == "execution_audit.parquet"
    assert artifacts.entry_score_contract_path.name == "entry_score_contract.json"
    assert artifacts.entry_score_selected_entries_path.name == "entry_score_selected_entries.parquet"
    closed_trades = trades_payload[trades_payload["record_type"] == "closed_trade"]
    assert set(trades_payload["run_id"]) == {"writer-test"}
    assert len(closed_trades) == 2
    assert {int(trade_index) for trade_index in closed_trades["trade_index"]} == {1, 2}
    assert result_payload["run_config"]["sizing"]["max_holding_count"] == 5
    assert result_payload["run_config"]["sizing"]["per_symbol_max_value"] == 200000
    assert result_payload["run_config"]["sizing"]["target_buy_value"] == 66000
    assert run_plan_payload["output"]["artifact_detail"] == "compact"
    assert len(signal_audit_payload) == len(result.signal_audit)
    first_signal = signal_audit_payload.iloc[0].to_dict()
    first_signal_values = json.loads(first_signal["signal_values"])
    assert first_signal["method_name"] == "kdj_oversold_entry"
    assert "reason_code" in first_signal
    assert "checks" in first_signal_values
    assert "attribution" in first_signal_values
    assert not sizing_audit_payload.empty
    assert json.loads(sizing_audit_payload.iloc[0]["sizing"])["method_name"] == "equal_weight"
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
    closed_trades_by_index = {
        int(trade["trade_index"]): trade
        for trade in closed_trades.to_dict(orient="records")
    }
    for lifecycle in trade_lifecycle_payload["lifecycles"]:
        closed_trade = closed_trades_by_index[lifecycle["trade_index"]]
        assert closed_trade["symbol"] == lifecycle["symbol"]
        assert closed_trade["entry_date"] == lifecycle["entry_date"]
        assert closed_trade["exit_date"] == lifecycle["exit_date"]
    assert trade_lifecycle_payload["indexes"]["by_outcome"]
    assert trade_lifecycle_payload["indexes"]["by_symbol"][0]["key"] == "000001.SZ"
    assert trade_lifecycle_payload["lifecycles"][0]["events"][0]["event_type"] == "entry"
    assert trade_lifecycle_payload["lifecycles"][0]["events"][-1]["event_type"] == "exit"
    assert trade_lifecycle_payload["lifecycles"][0]["events"][0]["executions"]
    assert "# 交易生命周期审阅" in trade_lifecycle_markdown
    assert trade_attribution_payload["schema"] == "attbacktrader.trade_attribution.v1"
    assert trade_attribution_payload["trade_count"] == 2
    assert trade_attribution_payload["entry_event_count"] == 2
    assert "attributions" in trade_attribution_payload
    assert "factor_summaries" in trade_attribution_payload
    assert "# 交易后验归因" in trade_attribution_markdown
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
    assert equity_curve_payload.iloc[-1]["total_value"] == result.final_value
    assert len(positions_payload) == len(result.position_snapshots)
    assert any(execution_audit_payload["event_type"] == "completed")
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
    assert "stock_pool_filter" in snapshots_payload
    assert "attribution_factor_selection" in snapshots_payload
    assert attribution_factor_selection_payload["schema"] == "attbacktrader.attribution_factor_selection.v1"
    assert attribution_factor_selection_payload["configured_source"] == "default:all_applicable"
    assert "symbol.ma.price_above_ma25" in attribution_factor_selection_payload["include"]
    assert attribution_factor_selection_payload["not_include"] == []
    assert snapshots_payload["attribution_factor_selection"]["include"] == attribution_factor_selection_payload["include"]
    assert data_preflight_payload is None
    assert stock_pool_filter_payload is None


def test_write_run_artifacts_persists_entry_score_replay_outputs(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    run_plan = _run_plan(tmp_path / "snapshots")
    result = execute_run_plan(run_plan, provider=FakeDailyProvider(bars))
    result = replace(
        result,
        entry_score_replay={
            "source": {
                "scope": "backtest_only",
                "artifact_path": "reports/scores.parquet",
                "source_score_field": "ew_score",
                "decision_event_count": 2,
            },
            "precomputed_score_contract": {
                "schema": "attbacktrader.precomputed_score_portfolio_run.v1",
                "scope": "backtest_only",
                "score_id": "ew_seed_only_v2",
                "score_field": "entry.score.ew_seed_only_v2",
                "missing_score_policy": "skip",
                "enter_event_count": 2,
                "matched_enter_score_count": 1,
                "missing_enter_score_count": 1,
                "score_keys_not_in_enter_events_count": 0,
            },
            "executed_entries": [
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-05",
                    "score": 0.9,
                    "quantity": 100,
                    "cost": 1000.0,
                }
            ],
            "blocked_entries": [
                {
                    "symbol": "000002.SZ",
                    "trade_date": "2024-01-05",
                    "blocked_by": "SCORE_GATE",
                    "score_status": "missing",
                }
            ],
            "equity_curve": [
                {
                    "trade_date": "2024-01-05",
                    "cash": 99000.0,
                    "total_value": 100000.0,
                    "drawdown": 0.0,
                }
            ],
            "metrics": {"trade_count": 1},
            "funnel": {"raw_entry_candidates": 2, "executed_entries": 1},
        },
    )

    artifacts = write_run_artifacts(run_plan, result, output_root=tmp_path / "reports")
    result_payload = _read_json(artifacts.result_path)
    contract_payload = _read_json(artifacts.entry_score_contract_path)
    selected_entries = pd.read_parquet(artifacts.entry_score_selected_entries_path)
    blocked_entries = pd.read_parquet(artifacts.entry_score_blocked_entries_path)
    equity_curve = pd.read_parquet(artifacts.entry_score_equity_curve_path)

    assert contract_payload["score_id"] == "ew_seed_only_v2"
    assert contract_payload["matched_enter_score_count"] == 1
    assert result_payload["entry_score_replay"]["precomputed_score_contract"] == contract_payload
    assert selected_entries.iloc[0]["symbol"] == "000001.SZ"
    assert blocked_entries.iloc[0]["blocked_by"] == "SCORE_GATE"
    assert equity_curve.iloc[0]["total_value"] == 100000.0


def test_write_run_artifacts_can_persist_full_raw_audit_for_debugging(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    run_plan = _run_plan(tmp_path / "snapshots")
    run_plan = run_plan.model_copy(
        update={"output": run_plan.output.model_copy(update={"artifact_detail": "full"})}
    )
    result = execute_run_plan(run_plan, provider=FakeDailyProvider(bars))

    progress_events = []
    artifacts = write_run_artifacts(
        run_plan,
        result,
        output_root=tmp_path / "reports",
        progress_callback=progress_events.append,
    )

    result_payload = _read_json(artifacts.result_path)
    signal_audit_payload = pd.read_parquet(artifacts.signal_audit_path)
    stage_statuses = [
        (event["artifact"], event["status"])
        for event in progress_events
        if event["stage"] == "write_artifact"
    ]

    assert result_payload["schema"] == "attbacktrader.full_artifact_manifest_result.v1"
    assert result_payload["run_config"]["run"]["id"] == "writer-test"
    assert result_payload["run_id"] == "writer-test"
    assert result_payload["counts"]["signal_intent_count"] == len(result.signal_audit)
    assert "signal_audit" not in result_payload
    assert len(signal_audit_payload) == len(result.signal_audit)
    assert signal_audit_payload.iloc[0]["method_name"] == "kdj_oversold_entry"
    assert ("result", "started") in stage_statuses
    assert ("result", "completed") in stage_statuses
    assert ("signal_audit", "started") in stage_statuses
    assert ("signal_audit", "completed") in stage_statuses


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
                "sizing_params": {
                    "max_holding_count": 5,
                    "min_order_quantity": 100,
                },
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
