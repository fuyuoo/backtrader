"""Persist run-plan execution artifacts."""

from __future__ import annotations

import json
import re
from collections import Counter
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
from attbacktrader.reports.trade_attribution import (
    build_trade_attribution_report,
    render_trade_attribution_markdown_zh,
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
    trade_attribution_path: Path
    trade_attribution_chinese_markdown_path: Path
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
    data_preflight_path: Path
    stock_pool_filter_path: Path
    attribution_factor_selection_path: Path


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
        trade_attribution_path=output_dir / "trade_attribution.json",
        trade_attribution_chinese_markdown_path=output_dir / "trade_attribution.zh.md",
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
        data_preflight_path=output_dir / "data_preflight.json",
        stock_pool_filter_path=output_dir / "stock_pool_filter.json",
        attribution_factor_selection_path=output_dir / "attribution_factor_selection.json",
    )

    artifact_detail = getattr(run_plan.output, "artifact_detail", "compact")
    signal_audit_sample_limit = int(getattr(run_plan.output, "signal_audit_sample_limit", 200))
    run_config = _run_config_trace(run_plan)
    trade_lifecycle = _trade_lifecycle(result)

    _write_json(artifact_paths.run_plan_path, run_plan)
    _write_json(artifact_paths.result_path, _result_payload(result, artifact_detail=artifact_detail, run_config=run_config))
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
            "schema": "attbacktrader.trades.v2",
            "run_id": result.run_id,
            "run_config": run_config,
            "closed_trades": _closed_trades_with_lifecycle_indexes(result.closed_trades, trade_lifecycle),
            "open_positions": result.open_positions,
        },
    )
    _write_json(
        artifact_paths.signal_audit_path,
        _signal_audit_payload(
            result,
            artifact_detail=artifact_detail,
            sample_limit=signal_audit_sample_limit,
        ),
    )
    _write_json(artifact_paths.sizing_audit_path, _sizing_audit(result))
    _write_json(artifact_paths.result_diagnostics_path, _result_diagnostics(result))
    _write_json(artifact_paths.trade_lifecycle_path, trade_lifecycle)
    artifact_paths.trade_lifecycle_chinese_markdown_path.write_text(
        render_trade_lifecycle_markdown_zh(trade_lifecycle),
        encoding="utf-8",
    )
    trade_attribution = _trade_attribution(result, trade_lifecycle)
    _write_json(artifact_paths.trade_attribution_path, trade_attribution)
    artifact_paths.trade_attribution_chinese_markdown_path.write_text(
        render_trade_attribution_markdown_zh(trade_attribution),
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
    _write_json(artifact_paths.data_preflight_path, result.data_preflight_report)
    _write_json(artifact_paths.stock_pool_filter_path, result.stock_pool_filter)
    _write_json(artifact_paths.attribution_factor_selection_path, result.attribution_factor_selection)

    return artifact_paths


def _snapshot_index(result: RunPlanExecutionResult) -> dict[str, Any]:
    return {
        "stock_pool_filter": result.stock_pool_filter,
        "attribution_factor_selection": result.attribution_factor_selection,
        "data_windows": _data_windows(result),
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


def _run_config_trace(run_plan: RunPlan) -> dict[str, Any]:
    sizing_params = dict(run_plan.strategy.sizing_params or {})
    max_holding_count = sizing_params.get("max_holding_count")
    per_symbol_max_value = None
    target_buy_value = None
    if max_holding_count:
        per_symbol_max_value = run_plan.broker.initial_cash / int(max_holding_count)
        target_buy_value = per_symbol_max_value * run_plan.execution.baoma.buy_slice_fraction

    return {
        "schema": "attbacktrader.run_config_trace.v1",
        "run": {
            "id": run_plan.run.id,
            "from_date": run_plan.run.from_date,
            "to_date": run_plan.run.to_date,
        },
        "data": {
            "provider": run_plan.data.provider,
            "price_adjustment": run_plan.data.price_adjustment,
            "stock_pool_file": run_plan.data.stock_pool_file,
            "symbol_count": len(run_plan.data.resolved_tradable_series),
        },
        "strategy": {
            "template": run_plan.strategy.template,
            "entry_method": run_plan.strategy.entry_method,
            "entry_params": run_plan.strategy.entry_params,
            "profit_taking_method": run_plan.strategy.profit_taking_method,
            "profit_taking_params": run_plan.strategy.profit_taking_params,
            "stop_loss_method": run_plan.strategy.stop_loss_method,
            "stop_loss_params": run_plan.strategy.stop_loss_params,
            "add_on_method": run_plan.strategy.add_on_method,
            "add_on_params": run_plan.strategy.add_on_params,
            "sizing_rule": run_plan.strategy.sizing_rule,
            "sizing_params": run_plan.strategy.sizing_params,
        },
        "sizing": {
            "max_holding_count": max_holding_count,
            "per_symbol_max_value": per_symbol_max_value,
            "buy_slice_fraction": run_plan.execution.baoma.buy_slice_fraction,
            "target_buy_value": target_buy_value,
            "min_order_quantity": sizing_params.get("min_order_quantity"),
        },
        "execution": {
            "engine": run_plan.execution.engine,
            "stake": run_plan.execution.stake,
            "baoma": run_plan.execution.baoma,
        },
        "constraints": {
            "ashare": run_plan.constraints.ashare,
        },
        "broker": {
            "initial_cash": run_plan.broker.initial_cash,
            "commission_rate": run_plan.broker.commission_rate,
            "stamp_tax_rate": run_plan.broker.stamp_tax_rate,
            "transfer_fee_rate": run_plan.broker.transfer_fee_rate,
            "slippage": run_plan.broker.slippage,
        },
    }


def _result_payload(result: RunPlanExecutionResult, *, artifact_detail: str, run_config: Mapping[str, Any]) -> Any:
    if artifact_detail == "full":
        return {
            "schema": "attbacktrader.full_result.v2",
            "run_config": run_config,
            "result": result,
        }
    return {
        "schema": "attbacktrader.compact_result.v1",
        "artifact_detail": "compact",
        "raw_result_persisted": False,
        "run_id": result.run_id,
        "engine": result.engine,
        "adjustment": result.adjustment,
        "run_config": run_config,
        "symbols": result.symbols,
        "counts": {
            "symbol_count": len(result.symbols),
            "closed_trade_count": len(result.closed_trades),
            "open_position_count": len(result.open_positions),
            "signal_intent_count": len(result.signal_audit),
            "execution_event_count": len(result.execution_audit),
            "lifecycle_event_count": len(result.lifecycle_events),
            "lifecycle_snapshot_count": len(result.lifecycle_snapshots),
            "equity_point_count": len(result.equity_curve),
            "position_snapshot_count": len(result.position_snapshots),
        },
        "final_cash": result.final_cash,
        "final_value": result.final_value,
        "report": result.report,
        "post_exit_analysis_summary": {
            "trade_count": result.post_exit_analysis.trade_count,
            "window_days": result.post_exit_analysis.window_days,
            "configured_window_days": result.post_exit_analysis.configured_window_days,
            "sold_too_early_threshold": result.post_exit_analysis.sold_too_early_threshold,
            "rebound_thresholds": result.post_exit_analysis.rebound_thresholds,
        },
        "attribution_factor_selection": result.attribution_factor_selection,
        "raw_detail_note": (
            "Full result persistence is disabled by output.artifact_detail=compact. "
            "Use report/trades/snapshots/evidence_validation and derived review artifacts for AI review, "
            "or set output.artifact_detail=full for debugging."
        ),
    }


def _signal_audit_payload(
    result: RunPlanExecutionResult,
    *,
    artifact_detail: str,
    sample_limit: int,
) -> Any:
    if artifact_detail == "full":
        return result.signal_audit

    intents = tuple(result.signal_audit)
    return {
        "schema": "attbacktrader.compact_signal_audit.v1",
        "artifact_detail": "compact",
        "raw_signal_audit_persisted": False,
        "total_count": len(intents),
        "sample_limit": sample_limit,
        "intent_type_counts": _counter_rows(getattr(intent.intent_type, "value", str(intent.intent_type)) for intent in intents),
        "reason_code_counts": _counter_rows(intent.reason_code for intent in intents),
        "blocked_by_counts": _counter_rows(intent.blocked_by for intent in intents if intent.blocked_by),
        "method_counts": _counter_rows(intent.method_name for intent in intents),
        "date_range": _date_range_for_intents(intents),
        "samples": tuple(intents[:sample_limit]),
        "raw_detail_note": (
            "Full signal audit persistence is disabled by output.artifact_detail=compact. "
            "Use sizing_audit/execution_audit/trade_lifecycle/trade_review for drill-down, "
            "or set output.artifact_detail=full for debugging."
        ),
    }


def _counter_rows(values) -> tuple[dict[str, Any], ...]:
    counts = Counter(str(value) for value in values)
    return tuple(
        {"key": key, "count": count}
        for key, count in counts.most_common()
    )


def _date_range_for_intents(intents) -> dict[str, str | None]:
    dates = sorted(intent.trade_date for intent in intents)
    if not dates:
        return {"start": None, "end": None}
    return {"start": dates[0].isoformat(), "end": dates[-1].isoformat()}


def _data_windows(result: RunPlanExecutionResult) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for symbol_result in result.symbol_results:
        items.append(
            _data_window_item(
                kind="symbol",
                symbol=symbol_result.symbol,
                provenance=symbol_result.snapshot_provenance,
                bar_count=symbol_result.bar_count,
                calculation_bar_count=None,
            )
        )
    for benchmark in result.benchmark_results:
        items.append(
            _data_window_item(
                kind="benchmark",
                symbol=benchmark.symbol,
                provenance=benchmark.snapshot_provenance,
                bar_count=benchmark.bar_count,
                calculation_bar_count=benchmark.calculation_bar_count,
            )
        )
    for industry_index in result.industry_index_results:
        items.append(
            _data_window_item(
                kind="industry_index",
                symbol=industry_index.symbol,
                provenance=industry_index.snapshot_provenance,
                bar_count=industry_index.bar_count,
                calculation_bar_count=industry_index.calculation_bar_count,
            )
        )

    requested_starts = [
        item["requested_start_date"]
        for item in items
        if item.get("requested_start_date")
    ]
    return {
        "items": tuple(items),
        "earliest_requested_start_date": min(requested_starts) if requested_starts else None,
        "warmup_incomplete_count": sum(1 for item in items if item.get("warmup_incomplete")),
    }


def _data_window_item(
    *,
    kind: str,
    symbol: str,
    provenance,
    bar_count: int,
    calculation_bar_count: int | None,
) -> dict[str, Any]:
    details = dict(getattr(provenance, "details", {}) or {})
    return {
        "kind": kind,
        "symbol": symbol,
        "bar_count": bar_count,
        "calculation_bar_count": calculation_bar_count,
        "snapshot_start_date": getattr(provenance, "start_date", None),
        "snapshot_end_date": getattr(provenance, "end_date", None),
        "requested_start_date": details.get("requested_start_date"),
        "requested_end_date": details.get("requested_end_date"),
        "minimum_start_date": details.get("minimum_start_date"),
        "warmup_incomplete": bool(details.get("warmup_incomplete")),
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


def _closed_trades_with_lifecycle_indexes(closed_trades, trade_lifecycle) -> list[dict[str, Any]]:
    indexes_by_identity: dict[tuple[Any, ...], list[int]] = {}
    for lifecycle in getattr(trade_lifecycle, "lifecycles", ()):
        indexes_by_identity.setdefault(_trade_identity(lifecycle), []).append(lifecycle.trade_index)

    records: list[dict[str, Any]] = []
    for fallback_index, trade in enumerate(closed_trades, start=1):
        payload = to_jsonable(trade)
        identity = _trade_identity(trade)
        trade_indexes = indexes_by_identity.get(identity)
        trade_index = trade_indexes.pop(0) if trade_indexes else fallback_index
        records.append({"trade_index": trade_index, **payload})
    return records


def _trade_identity(trade: Any) -> tuple[Any, ...]:
    return (
        _trade_field(trade, "symbol"),
        _date_key(_trade_field(trade, "entry_date")),
        _date_key(_trade_field(trade, "exit_date")),
        _trade_field(trade, "exit_reason"),
        _number_key(_trade_field(trade, "entry_price")),
        _number_key(_trade_field(trade, "exit_price")),
        _trade_field(trade, "quantity"),
        _number_key(_trade_field(trade, "net_pnl")),
    )


def _trade_field(trade: Any, field_name: str) -> Any:
    if isinstance(trade, Mapping):
        return trade.get(field_name)
    return getattr(trade, field_name, None)


def _date_key(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _number_key(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 8)


def _trade_lifecycle(result: RunPlanExecutionResult):
    return build_trade_lifecycle_report(
        closed_trades=result.closed_trades,
        signal_audit=result.signal_audit,
        execution_audit=result.execution_audit,
    )


def _trade_attribution(result: RunPlanExecutionResult, trade_lifecycle):
    selection = result.attribution_factor_selection
    include = ()
    if isinstance(selection, Mapping):
        include = tuple(str(key) for key in selection.get("include", ()) if key)
    return build_trade_attribution_report(
        trade_lifecycle,
        selected_factor_keys=include,
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
