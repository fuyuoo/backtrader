from datetime import date
from types import SimpleNamespace
import json

from attbacktrader.data.snapshots import SnapshotProvenance
from attbacktrader.cli import run_plan as run_plan_cli
from attbacktrader.reports import (
    BacktestReport,
    BenchmarkComparisonSummary,
    ExecutionCostSummary,
    ExecutionRejectionSummary,
    PortfolioBehaviorSummary,
    ReturnSummary,
    RiskSummary,
    ScenarioFitSummary,
    SymbolContributionSummary,
    TradeQualitySummary,
    build_run_execution_summary,
    render_run_execution_summary_text_zh,
)


def test_build_run_execution_summary_keeps_terminal_output_compact(tmp_path) -> None:
    result = _result()
    artifacts = _artifacts(tmp_path)
    artifacts.evidence_validation_path.write_text(
        json.dumps({"status": "ok", "error_count": 0, "warning_count": 0}),
        encoding="utf-8",
    )

    summary = build_run_execution_summary(_run_plan(), result, artifact_paths=artifacts)

    assert summary["schema"] == "attbacktrader.run_execution_summary.v1"
    assert summary["run"]["id"] == "summary-test"
    assert summary["metrics"]["cumulative_return"] == 0.05
    assert summary["execution"]["rejections"] == [
        {"code": "BOARD_LOT_TOO_SMALL", "label_zh": "不足一手，无法下单", "count": 2}
    ]
    assert summary["data_windows"]["earliest_requested_start_date"] == "2023-10-03"
    assert summary["data_windows"]["warmup_incomplete_count"] == 1
    assert summary["evidence"] == {"status": "ok", "error_count": 0, "warning_count": 0}
    assert summary["artifacts"]["report_zh"].endswith("report.zh.md")

    text = render_run_execution_summary_text_zh(summary)

    assert "回测完成" in text
    assert "累计收益: 5.00%" in text
    assert "不足一手，无法下单 (BOARD_LOT_TOO_SMALL): 2" in text
    assert "warmup 不完整 1" in text
    assert "report.zh.md" in text
    assert "signal_audit" not in text


def test_run_plan_cli_defaults_to_concise_text(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_plan_cli, "load_run_plan", lambda _path: _run_plan())
    monkeypatch.setattr(run_plan_cli, "execute_run_plan", lambda _run_plan, provider=None: _result())

    assert run_plan_cli.main(["--config", "dummy.yaml", "--no-persist"]) == 0

    stdout = capsys.readouterr().out
    assert "回测完成" in stdout
    assert "Run ID: summary-test" in stdout
    assert "signal_audit" not in stdout
    assert "closed_trades" not in stdout


def test_run_plan_cli_can_print_summary_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_plan_cli, "load_run_plan", lambda _path: _run_plan())
    monkeypatch.setattr(run_plan_cli, "execute_run_plan", lambda _run_plan, provider=None: _result())

    assert run_plan_cli.main(["--config", "dummy.yaml", "--no-persist", "--summary-json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "attbacktrader.run_execution_summary.v1"
    assert payload["metrics"]["trade_count"] == 4
    assert "signal_audit" not in payload


def _run_plan():
    return SimpleNamespace(
        run=SimpleNamespace(id="summary-test", from_date=date(2024, 1, 1), to_date=date(2024, 3, 31)),
        data=SimpleNamespace(refresh_snapshots=False, provider="fake"),
        execution=SimpleNamespace(engine="backtrader"),
        output=SimpleNamespace(persist=True, report_root="reports"),
    )


def _result():
    return SimpleNamespace(
        run_id="summary-test",
        engine="backtrader",
        adjustment="qfq",
        symbols=("000001.SZ", "600519.SH"),
        symbol_results=(
            SimpleNamespace(
                symbol="000001.SZ",
                bar_count=40,
                snapshot_provenance=SnapshotProvenance(
                    snapshot_type="tradable_bars",
                    action="created",
                    path="snapshots/000001.parquet",
                    start_date=date(2023, 10, 3),
                    end_date=date(2024, 3, 31),
                    details={
                        "requested_start_date": "2023-10-03",
                        "requested_end_date": "2024-03-31",
                        "minimum_start_date": "2024-01-01",
                        "warmup_incomplete": True,
                    },
                ),
            ),
        ),
        benchmark_results=(
            SimpleNamespace(
                symbol="000300.SH",
                bar_count=40,
                calculation_bar_count=100,
                snapshot_provenance=SnapshotProvenance(
                    snapshot_type="index_bars",
                    action="created",
                    path="snapshots/000300.parquet",
                    start_date=date(2023, 10, 3),
                    end_date=date(2024, 3, 31),
                    details={
                        "requested_start_date": "2023-10-03",
                        "requested_end_date": "2024-03-31",
                        "minimum_start_date": "2024-01-01",
                    },
                ),
            ),
        ),
        industry_index_results=(),
        open_positions=(SimpleNamespace(symbol="000001.SZ"),),
        final_cash=250000.0,
        final_value=1050000.0,
        post_exit_analysis=SimpleNamespace(
            window_days=5,
            sold_too_early_threshold=0.0,
            trade_count=4,
            summaries=(
                SimpleNamespace(
                    group="all",
                    sold_too_early_count=3,
                    sold_too_early_rate=0.75,
                ),
            ),
        ),
        report=BacktestReport(
            report_id="summary-test",
            returns=ReturnSummary(
                starting_equity=1000000.0,
                final_equity=1050000.0,
                cumulative_return=0.05,
            ),
            risk=RiskSummary(max_drawdown=0.08),
            trade_quality=TradeQualitySummary(
                trade_count=4,
                win_count=3,
                loss_count=1,
                win_rate=0.75,
                average_win=0.06,
                average_loss=-0.03,
                profit_loss_ratio=2.0,
            ),
            benchmark_comparison=(
                BenchmarkComparisonSummary(
                    benchmark_symbol="000300.SH",
                    strategy_return=0.05,
                    benchmark_return=0.02,
                    excess_return=0.03,
                ),
            ),
            scenario_fit=ScenarioFitSummary(
                label="conditional_fit",
                score=4,
                reasons=("positive cumulative return",),
                warnings=("sample needs review",),
            ),
            portfolio_behavior=PortfolioBehaviorSummary(
                open_position_count=1,
                open_symbols=("000001.SZ",),
                closed_symbol_count=2,
                max_symbol_trade_share=0.5,
                cash_ratio=0.23809523809523808,
                symbol_contributions=(
                    SymbolContributionSummary(
                        symbol="000001.SZ",
                        trade_count=2,
                        cumulative_return=0.04,
                        average_return=0.02,
                    ),
                ),
            ),
            execution_costs=ExecutionCostSummary(
                order_count=6,
                submitted_count=6,
                accepted_count=4,
                completed_count=4,
                failed_count=0,
                rejected_count=2,
                fill_rate=2 / 3,
                rejection_rate=1 / 3,
                total_commission=120.0,
                average_commission=30.0,
                total_slippage_cost=45.0,
                average_slippage_cost=11.25,
                rejections=(ExecutionRejectionSummary(blocked_by="BOARD_LOT_TOO_SMALL", count=2),),
            ),
        ),
    )


def _artifacts(root):
    return SimpleNamespace(
        output_dir=root,
        report_chinese_markdown_path=root / "report.zh.md",
        report_path=root / "report.json",
        trades_path=root / "trades.json",
        environment_fit_path=root / "environment_fit.json",
        trade_review_path=root / "trade_review.json",
        post_exit_analysis_path=root / "post_exit_analysis.json",
        evidence_validation_path=root / "evidence_validation.json",
    )
