"""Persist run-plan execution artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from attbacktrader.config import RunPlan
    from attbacktrader.runners import RunPlanExecutionResult


@dataclass(frozen=True)
class RunArtifactPaths:
    output_dir: Path
    run_plan_path: Path
    result_path: Path
    report_path: Path
    report_markdown_path: Path
    trades_path: Path
    equity_curve_path: Path
    positions_path: Path
    execution_audit_path: Path
    snapshots_path: Path


def write_run_artifacts(
    run_plan: "RunPlan",
    result: "RunPlanExecutionResult",
    *,
    output_root: str | Path = "reports",
) -> RunArtifactPaths:
    output_dir = Path(output_root) / _safe_path_name(result.run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact_paths = RunArtifactPaths(
        output_dir=output_dir,
        run_plan_path=output_dir / "run_plan.json",
        result_path=output_dir / "result.json",
        report_path=output_dir / "report.json",
        report_markdown_path=output_dir / "report.md",
        trades_path=output_dir / "trades.json",
        equity_curve_path=output_dir / "equity_curve.json",
        positions_path=output_dir / "positions.json",
        execution_audit_path=output_dir / "execution_audit.json",
        snapshots_path=output_dir / "snapshots.json",
    )

    _write_json(artifact_paths.run_plan_path, run_plan)
    _write_json(artifact_paths.result_path, result)
    _write_json(artifact_paths.report_path, result.report)
    artifact_paths.report_markdown_path.write_text(
        render_backtest_report_markdown(run_plan, result),
        encoding="utf-8",
    )
    _write_json(
        artifact_paths.trades_path,
        {
            "closed_trades": result.closed_trades,
            "open_positions": result.open_positions,
        },
    )
    _write_json(artifact_paths.equity_curve_path, result.equity_curve)
    _write_json(artifact_paths.positions_path, result.position_snapshots)
    _write_json(artifact_paths.execution_audit_path, result.execution_audit)
    _write_json(artifact_paths.snapshots_path, _snapshot_index(result))

    return artifact_paths


def render_backtest_report_markdown(run_plan: "RunPlan", result: "RunPlanExecutionResult") -> str:
    report = result.report
    lines = [
        f"# Backtest Report: {report.report_id}",
        "",
        "## Run",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Window | {run_plan.run.from_date} to {run_plan.run.to_date} |",
        f"| Engine | {result.engine} |",
        f"| Adjustment | {result.adjustment} |",
        f"| Symbols | {', '.join(result.symbols)} |",
        f"| Final cash | {_format_optional_number(result.final_cash)} |",
        f"| Final value | {_format_optional_number(result.final_value)} |",
        "",
        "## Returns",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Starting equity | {_format_number(report.returns.starting_equity)} |",
        f"| Final equity | {_format_number(report.returns.final_equity)} |",
        f"| Cumulative return | {_format_percent(report.returns.cumulative_return)} |",
        f"| Max drawdown | {_format_percent(report.risk.max_drawdown)} |",
        "",
        "## Trade Quality",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Trades | {report.trade_quality.trade_count} |",
        f"| Wins | {report.trade_quality.win_count} |",
        f"| Losses | {report.trade_quality.loss_count} |",
        f"| Win rate | {_format_optional_percent(report.trade_quality.win_rate)} |",
        f"| Average win | {_format_optional_percent(report.trade_quality.average_win)} |",
        f"| Average loss | {_format_optional_percent(report.trade_quality.average_loss)} |",
        f"| Profit/loss ratio | {_format_optional_number(report.trade_quality.profit_loss_ratio)} |",
        "",
    ]

    if report.portfolio_behavior is not None:
        portfolio = report.portfolio_behavior
        lines.extend(
            [
                "## Portfolio Behavior",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Open positions | {portfolio.open_position_count} |",
                f"| Open symbols | {', '.join(portfolio.open_symbols) if portfolio.open_symbols else '-'} |",
                f"| Closed symbols | {portfolio.closed_symbol_count} |",
                f"| Max symbol trade share | {_format_optional_percent(portfolio.max_symbol_trade_share)} |",
                f"| Cash ratio | {_format_optional_percent(portfolio.cash_ratio)} |",
                "",
            ]
        )
        if portfolio.symbol_contributions:
            lines.extend(
                [
                    "| Symbol | Trades | Cumulative return | Average return |",
                    "|---|---:|---:|---:|",
                ]
            )
            for contribution in portfolio.symbol_contributions:
                lines.append(
                    "| "
                    f"{contribution.symbol} | "
                    f"{contribution.trade_count} | "
                    f"{_format_percent(contribution.cumulative_return)} | "
                    f"{_format_percent(contribution.average_return)} |"
                )
            lines.append("")

    if report.execution_costs is not None:
        execution = report.execution_costs
        lines.extend(
            [
                "## Execution Costs",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Orders | {execution.order_count} |",
                f"| Submitted | {execution.submitted_count} |",
                f"| Accepted | {execution.accepted_count} |",
                f"| Completed | {execution.completed_count} |",
                f"| Failed | {execution.failed_count} |",
                f"| Rejected | {execution.rejected_count} |",
                f"| Fill rate | {_format_optional_percent(execution.fill_rate)} |",
                f"| Rejection rate | {_format_optional_percent(execution.rejection_rate)} |",
                f"| Total commission | {_format_number(execution.total_commission)} |",
                f"| Average commission | {_format_optional_number(execution.average_commission)} |",
                f"| Total slippage cost | {_format_number(execution.total_slippage_cost)} |",
                f"| Average slippage cost | {_format_optional_number(execution.average_slippage_cost)} |",
                "",
            ]
        )
        if execution.rejections:
            lines.extend(["| Rejection reason | Count |", "|---|---:|"])
            for rejection in execution.rejections:
                lines.append(f"| {rejection.blocked_by} | {rejection.count} |")
            lines.append("")

    if report.benchmark_comparison:
        lines.extend(
            [
                "## Benchmark Comparison",
                "",
                "| Benchmark | Strategy return | Benchmark return | Excess return |",
                "|---|---:|---:|---:|",
            ]
        )
        for comparison in report.benchmark_comparison:
            lines.append(
                "| "
                f"{comparison.benchmark_symbol} | "
                f"{_format_percent(comparison.strategy_return)} | "
                f"{_format_percent(comparison.benchmark_return)} | "
                f"{_format_percent(comparison.excess_return)} |"
            )
        lines.append("")

    if report.industry_attribution:
        lines.extend(
            [
                "## Industry Attribution",
                "",
                "| Level | Code | Name | Trades | Average return | Contribution |",
                "|---:|---|---|---:|---:|---:|",
            ]
        )
        for attribution in report.industry_attribution:
            lines.append(
                "| "
                f"{attribution.level} | "
                f"{attribution.industry_code} | "
                f"{attribution.industry_name} | "
                f"{attribution.trade_count} | "
                f"{_format_percent(attribution.average_return)} | "
                f"{_format_percent(attribution.contribution_return)} |"
            )
        lines.append("")

    if report.market_regime is not None:
        regime = report.market_regime
        lines.extend(
            [
                "## Market Regime",
                "",
                f"Primary label: `{regime.primary_label}`",
                "",
                "| Timeframe | Label | Benchmark return | Drawdown | Volatility | Industry positive ratio |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for window in regime.windows:
            lines.append(
                "| "
                f"{window.timeframe} | "
                f"{window.label} | "
                f"{_format_optional_percent(window.benchmark_return)} | "
                f"{_format_optional_percent(window.benchmark_max_drawdown)} | "
                f"{_format_optional_percent(window.benchmark_volatility)} | "
                f"{_format_optional_percent(window.industry_positive_ratio)} |"
            )
        lines.append("")

    if report.scenario_fit is not None:
        scenario = report.scenario_fit
        lines.extend(
            [
                "## Scenario Fit",
                "",
                f"- Label: `{scenario.label}`",
                f"- Score: {scenario.score}",
            ]
        )
        if scenario.reasons:
            lines.append(f"- Reasons: {'; '.join(scenario.reasons)}")
        if scenario.warnings:
            lines.append(f"- Warnings: {'; '.join(scenario.warnings)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _snapshot_index(result: RunPlanExecutionResult) -> dict[str, Any]:
    return {
        "symbols": [
            {
                "symbol": symbol_result.symbol,
                "asset_type": symbol_result.asset_type,
                "adjustment": symbol_result.adjustment,
                "snapshot_path": symbol_result.snapshot_path,
                "indicator_snapshot_path": symbol_result.indicator_snapshot_path,
                "tradability_snapshot_path": symbol_result.tradability_snapshot_path,
            }
            for symbol_result in result.symbol_results
        ],
        "benchmarks": result.benchmark_results,
        "decision_series": result.decision_series_results,
        "industry_indexes": result.industry_index_results,
        "industry_classification": result.industry_classification_result,
        "industry_memberships": result.industry_membership_results,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, (tuple, list)):
        return [_to_jsonable(item) for item in value]

    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}

    return value


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_number(value)


def _format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_percent(value)


def _safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe or "run"
