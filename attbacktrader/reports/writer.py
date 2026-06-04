"""Persist run-plan execution artifacts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from attbacktrader.data.snapshots import read_daily_bars_parquet
from attbacktrader.reports.diagnostics import build_result_diagnostics
from attbacktrader.reports.environment_fit import (
    build_environment_fit_report_from_artifacts,
    render_environment_fit_markdown_zh,
)
from attbacktrader.reports.evidence_validation import build_evidence_validation
from attbacktrader.reports.lifecycle import build_trade_lifecycle_report, render_trade_lifecycle_markdown_zh
from attbacktrader.reports.post_exit import render_post_exit_analysis_markdown_zh
from attbacktrader.reports.renderer import render_backtest_report_markdown, render_backtest_report_markdown_zh
from attbacktrader.reports.strategy_environment_profile import (
    build_strategy_environment_profile_from_artifacts,
    render_strategy_environment_profile_markdown_zh,
)
from attbacktrader.reports.trade_review import build_trade_review_report, render_trade_review_markdown_zh

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
    report_chinese_markdown_path: Path
    trades_path: Path
    signal_audit_path: Path
    sizing_audit_path: Path
    result_diagnostics_path: Path
    trade_lifecycle_path: Path
    trade_lifecycle_chinese_markdown_path: Path
    trade_review_path: Path
    trade_review_chinese_markdown_path: Path
    environment_fit_path: Path
    environment_fit_chinese_markdown_path: Path
    strategy_environment_profile_path: Path
    strategy_environment_profile_chinese_markdown_path: Path
    post_exit_analysis_path: Path
    post_exit_analysis_chinese_markdown_path: Path
    evidence_validation_path: Path
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
        report_chinese_markdown_path=output_dir / "report.zh.md",
        trades_path=output_dir / "trades.json",
        signal_audit_path=output_dir / "signal_audit.json",
        sizing_audit_path=output_dir / "sizing_audit.json",
        result_diagnostics_path=output_dir / "result_diagnostics.json",
        trade_lifecycle_path=output_dir / "trade_lifecycle.json",
        trade_lifecycle_chinese_markdown_path=output_dir / "trade_lifecycle.zh.md",
        trade_review_path=output_dir / "trade_review.json",
        trade_review_chinese_markdown_path=output_dir / "trade_review.zh.md",
        environment_fit_path=output_dir / "environment_fit.json",
        environment_fit_chinese_markdown_path=output_dir / "environment_fit.zh.md",
        strategy_environment_profile_path=output_dir / "strategy_environment_profile.json",
        strategy_environment_profile_chinese_markdown_path=output_dir / "strategy_environment_profile.zh.md",
        post_exit_analysis_path=output_dir / "post_exit_analysis.json",
        post_exit_analysis_chinese_markdown_path=output_dir / "post_exit_analysis.zh.md",
        evidence_validation_path=output_dir / "evidence_validation.json",
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
    artifact_paths.report_chinese_markdown_path.write_text(
        render_backtest_report_markdown_zh(run_plan, result),
        encoding="utf-8",
    )
    _write_json(
        artifact_paths.trades_path,
        {
            "closed_trades": result.closed_trades,
            "open_positions": result.open_positions,
        },
    )
    _write_json(artifact_paths.signal_audit_path, result.signal_audit)
    _write_json(artifact_paths.sizing_audit_path, _sizing_audit(result))
    _write_json(artifact_paths.result_diagnostics_path, _result_diagnostics(result))
    trade_lifecycle = _trade_lifecycle(result)
    _write_json(artifact_paths.trade_lifecycle_path, trade_lifecycle)
    artifact_paths.trade_lifecycle_chinese_markdown_path.write_text(
        render_trade_lifecycle_markdown_zh(trade_lifecycle),
        encoding="utf-8",
    )
    trade_review = _trade_review(result, trade_lifecycle)
    _write_json(artifact_paths.trade_review_path, trade_review)
    artifact_paths.trade_review_chinese_markdown_path.write_text(
        render_trade_review_markdown_zh(trade_review),
        encoding="utf-8",
    )
    environment_fit = _environment_fit(
        result.run_id,
        output_dir=output_dir,
        trade_lifecycle=trade_lifecycle,
        trade_review=trade_review,
    )
    _write_json(artifact_paths.environment_fit_path, environment_fit)
    artifact_paths.environment_fit_chinese_markdown_path.write_text(
        render_environment_fit_markdown_zh(environment_fit),
        encoding="utf-8",
    )
    strategy_environment_profile = _strategy_environment_profile(
        output_dir=output_dir,
        environment_fit=environment_fit,
    )
    _write_json(artifact_paths.strategy_environment_profile_path, strategy_environment_profile)
    artifact_paths.strategy_environment_profile_chinese_markdown_path.write_text(
        render_strategy_environment_profile_markdown_zh(strategy_environment_profile),
        encoding="utf-8",
    )
    _write_json(artifact_paths.post_exit_analysis_path, result.post_exit_analysis)
    artifact_paths.post_exit_analysis_chinese_markdown_path.write_text(
        render_post_exit_analysis_markdown_zh(result.post_exit_analysis),
        encoding="utf-8",
    )
    _write_json(artifact_paths.evidence_validation_path, _evidence_validation(result))
    _write_json(artifact_paths.equity_curve_path, result.equity_curve)
    _write_json(artifact_paths.positions_path, result.position_snapshots)
    _write_json(artifact_paths.execution_audit_path, result.execution_audit)
    _write_json(artifact_paths.snapshots_path, _snapshot_index(result))

    return artifact_paths


def _snapshot_index(result: RunPlanExecutionResult) -> dict[str, Any]:
    return {
        "symbols": [
            {
                "symbol": symbol_result.symbol,
                "asset_type": symbol_result.asset_type,
                "adjustment": symbol_result.adjustment,
                "snapshot_path": symbol_result.snapshot_path,
                "indicator_snapshot_path": symbol_result.indicator_snapshot_path,
                "indicator_snapshot_paths": symbol_result.indicator_snapshot_paths,
                "snapshot_provenance": symbol_result.snapshot_provenance,
                "indicator_snapshot_provenance": symbol_result.indicator_snapshot_provenance,
                "tradability_snapshot_path": symbol_result.tradability_snapshot_path,
                "tradability_snapshot_provenance": symbol_result.tradability_snapshot_provenance,
                "data_quality_issues": symbol_result.data_quality_issues,
            }
            for symbol_result in result.symbol_results
        ],
        "benchmarks": result.benchmark_results,
        "decision_series": result.decision_series_results,
        "industry_indexes": result.industry_index_results,
        "industry_classification": result.industry_classification_result,
        "industry_memberships": result.industry_membership_results,
    }


def _sizing_audit(result: RunPlanExecutionResult) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for intent in result.signal_audit:
        sizing_values = intent.signal_values.get("sizing")
        if not isinstance(sizing_values, Mapping):
            continue
        records.append(
            {
                "symbol": intent.symbol,
                "trade_date": intent.trade_date,
                "intent_method_name": intent.method_name,
                "intent_reason_code": intent.reason_code,
                "intent_type": intent.intent_type.value,
                "blocked_by": intent.blocked_by,
                "sizing": dict(sizing_values),
            }
        )
    return tuple(records)


def _result_diagnostics(result: RunPlanExecutionResult):
    return build_result_diagnostics(
        symbols=result.symbols,
        closed_trades=result.closed_trades,
        signal_audit=result.signal_audit,
        execution_audit=result.execution_audit,
        open_positions=result.open_positions,
    )


def _trade_lifecycle(result: RunPlanExecutionResult):
    return build_trade_lifecycle_report(
        closed_trades=result.closed_trades,
        signal_audit=result.signal_audit,
        execution_audit=result.execution_audit,
    )


def _trade_review(result: RunPlanExecutionResult, trade_lifecycle):
    return build_trade_review_report(
        closed_trades=result.closed_trades,
        signal_audit=result.signal_audit,
        execution_audit=result.execution_audit,
        post_exit_analysis=result.post_exit_analysis,
        trade_lifecycle=trade_lifecycle,
        bars_by_symbol=_bars_by_symbol(result),
    )


def _environment_fit(run_id: str, *, output_dir: Path, trade_lifecycle, trade_review):
    return build_environment_fit_report_from_artifacts(
        run_id=run_id,
        source_dir=str(output_dir),
        trade_review=to_jsonable(trade_review),
        trade_lifecycle=to_jsonable(trade_lifecycle),
    )


def _strategy_environment_profile(*, output_dir: Path, environment_fit):
    return build_strategy_environment_profile_from_artifacts(
        environment_fit=to_jsonable(environment_fit),
        source_dir=str(output_dir),
        environment_fit_path=str(output_dir / "environment_fit.json"),
    )


def _evidence_validation(result: RunPlanExecutionResult):
    return build_evidence_validation(result)


def _bars_by_symbol(result: RunPlanExecutionResult):
    bars_by_symbol = {}
    for symbol_result in result.symbol_results:
        if not symbol_result.snapshot_path.exists():
            continue
        bars_by_symbol[symbol_result.symbol] = read_daily_bars_parquet(symbol_result.snapshot_path)
    return bars_by_symbol


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, (tuple, list)):
        return [to_jsonable(item) for item in value]

    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}

    return value


def _safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe or "run"
