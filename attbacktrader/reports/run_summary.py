"""Concise run-plan execution summaries for CLI output."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from attbacktrader.reports.run_data import REASON_CODE_LABELS

if TYPE_CHECKING:
    from attbacktrader.config import RunPlan
    from attbacktrader.reports.writer import RunArtifactPaths
    from attbacktrader.runners import RunPlanExecutionResult

RUN_EXECUTION_SUMMARY_SCHEMA = "attbacktrader.run_execution_summary.v1"


def build_run_execution_summary(
    run_plan: "RunPlan",
    result: "RunPlanExecutionResult",
    *,
    artifact_paths: "RunArtifactPaths | None" = None,
) -> dict[str, Any]:
    """Build the compact result users need after one backtest run."""
    report = result.report
    trade_quality = report.trade_quality
    portfolio = report.portfolio_behavior
    execution_costs = report.execution_costs
    evidence_validation = _read_evidence_validation(artifact_paths)

    return {
        "schema": RUN_EXECUTION_SUMMARY_SCHEMA,
        "run": {
            "id": result.run_id,
            "engine": result.engine,
            "adjustment": result.adjustment,
            "from_date": _iso(getattr(run_plan.run, "from_date", None)),
            "to_date": _iso(getattr(run_plan.run, "to_date", None)),
            "symbol_count": len(result.symbols),
            "symbols": list(result.symbols),
        },
        "metrics": {
            "starting_equity": report.returns.starting_equity,
            "final_equity": report.returns.final_equity,
            "final_cash": result.final_cash,
            "final_value": result.final_value,
            "cumulative_return": report.returns.cumulative_return,
            "max_drawdown": report.risk.max_drawdown,
            "trade_count": trade_quality.trade_count,
            "win_count": trade_quality.win_count,
            "loss_count": trade_quality.loss_count,
            "win_rate": trade_quality.win_rate,
            "average_win": trade_quality.average_win,
            "average_loss": trade_quality.average_loss,
            "profit_loss_ratio": trade_quality.profit_loss_ratio,
        },
        "portfolio": {
            "open_position_count": portfolio.open_position_count if portfolio else len(result.open_positions),
            "open_symbols": list(portfolio.open_symbols if portfolio else _open_symbols(result.open_positions)),
            "cash_ratio": portfolio.cash_ratio if portfolio else _cash_ratio(result.final_cash, result.final_value),
        },
        "execution": _execution_summary(execution_costs),
        "post_exit": _post_exit_summary(result.post_exit_analysis),
        "benchmarks": [
            {
                "symbol": benchmark.benchmark_symbol,
                "strategy_return": benchmark.strategy_return,
                "benchmark_return": benchmark.benchmark_return,
                "excess_return": benchmark.excess_return,
            }
            for benchmark in report.benchmark_comparison
        ],
        "scenario_fit": _scenario_fit_summary(report.scenario_fit),
        "stock_pool_filter": _stock_pool_filter_summary(result),
        "attribution_factor_selection": _attribution_factor_selection_summary(result),
        "data_windows": _data_window_summary(result),
        "evidence": evidence_validation,
        "artifacts": _artifact_summary(artifact_paths),
    }


def render_run_execution_summary_text_zh(summary: Mapping[str, Any]) -> str:
    run = _mapping(summary.get("run"))
    metrics = _mapping(summary.get("metrics"))
    portfolio = _mapping(summary.get("portfolio"))
    execution = _mapping(summary.get("execution"))
    post_exit = _mapping(summary.get("post_exit"))
    scenario_fit = _mapping(summary.get("scenario_fit"))
    data_windows = _mapping(summary.get("data_windows"))
    evidence = _mapping(summary.get("evidence"))
    artifacts = _mapping(summary.get("artifacts"))

    lines = [
        "回测完成",
        f"- Run ID: {run.get('id')}",
        f"- 引擎/复权: {run.get('engine')} / {run.get('adjustment')}",
        f"- 区间: {run.get('from_date')} 至 {run.get('to_date')}",
        f"- 标的: {run.get('symbol_count')} 个",
        "",
        "结果摘要",
        f"- 最终权益: {_format_number(metrics.get('final_equity'))}",
        f"- 累计收益: {_format_percent(metrics.get('cumulative_return'))}",
        f"- 最大回撤: {_format_percent(metrics.get('max_drawdown'))}",
        f"- 交易: {metrics.get('trade_count')} 笔，胜率 {_format_percent(metrics.get('win_rate'))}",
        (
            "- 盈亏比: "
            f"{_format_optional_number(metrics.get('profit_loss_ratio'))}，"
            f"平均盈利 {_format_percent(metrics.get('average_win'))}，"
            f"平均亏损 {_format_percent(metrics.get('average_loss'))}"
        ),
        (
            "- 持仓: "
            f"{portfolio.get('open_position_count')} 个，"
            f"现金占比 {_format_percent(portfolio.get('cash_ratio'))}"
        ),
        "",
        "执行摘要",
        (
            "- 订单: "
            f"{execution.get('order_count')}，完成 {execution.get('completed_count')}，"
            f"拒单 {execution.get('rejected_count')}，拒单率 {_format_percent(execution.get('rejection_rate'))}"
        ),
        (
            "- 成本: "
            f"佣金 {_format_number(execution.get('total_commission'))}，"
            f"滑点成本 {_format_number(execution.get('total_slippage_cost'))}"
        ),
    ]

    rejections = _sequence(execution.get("rejections"))
    if rejections:
        lines.append("- 拒单原因: " + _format_rejections(rejections))

    if post_exit:
        lines.extend(
            [
                "",
                "卖出后观察",
                (
                    "- 主窗口: "
                    f"{post_exit.get('window_days')} 个交易日，"
                    f"卖飞阈值 {_format_percent(post_exit.get('sold_too_early_threshold'))}"
                ),
                (
                    "- 卖飞/反弹: "
                    f"{post_exit.get('sold_too_early_count')} / {post_exit.get('trade_count')}，"
                    f"比例 {_format_percent(post_exit.get('sold_too_early_rate'))}"
                ),
            ]
        )

    if summary.get("benchmarks"):
        lines.extend(["", "基准对比"])
        for benchmark in _sequence(summary.get("benchmarks")):
            benchmark_map = _mapping(benchmark)
            lines.append(
                "- "
                f"{benchmark_map.get('symbol')}: "
                f"基准 {_format_percent(benchmark_map.get('benchmark_return'))}，"
                f"超额 {_format_percent(benchmark_map.get('excess_return'))}"
            )

    if scenario_fit:
        lines.extend(
            [
                "",
                "场景适配",
                f"- 标签: {scenario_fit.get('label')}，评分 {scenario_fit.get('score')}",
            ]
        )
        warnings = _sequence(scenario_fit.get("warnings"))
        if warnings:
            lines.append("- 警告: " + "；".join(str(warning) for warning in warnings[:3]))

    if data_windows:
        lines.extend(
            [
                "",
                "数据窗口",
                (
                    "- "
                    f"最早请求 {data_windows.get('earliest_requested_start_date')}，"
                    f"warmup 不完整 {data_windows.get('warmup_incomplete_count')}"
                ),
            ]
        )

    stock_pool_filter = _mapping(summary.get("stock_pool_filter"))
    if stock_pool_filter:
        lines.extend(
            [
                "",
                "股票池过滤",
                (
                    "- "
                    f"原始 {stock_pool_filter.get('original_count')}，"
                    f"保留 {stock_pool_filter.get('kept_count')}，"
                    f"warning {stock_pool_filter.get('warning_count')}，"
                    f"剔除 {stock_pool_filter.get('excluded_count')}"
                ),
            ]
        )

    attribution_selection = _mapping(summary.get("attribution_factor_selection"))
    if attribution_selection:
        lines.extend(
            [
                "",
                "归因因子",
                (
                    "- "
                    f"来源 {attribution_selection.get('configured_source')}，"
                    f"已选择 {attribution_selection.get('include_count')}，"
                    f"未选择 {attribution_selection.get('not_include_count')}"
                ),
            ]
        )

    if evidence:
        lines.extend(
            [
                "",
                "证据状态",
                (
                    "- "
                    f"{evidence.get('status')}，错误 {evidence.get('error_count')}，"
                    f"警告 {evidence.get('warning_count')}"
                ),
            ]
        )

    if artifacts:
        lines.extend(["", "报告路径"])
        for label in ("output_dir", "report_zh", "evidence_validation", "environment_fit", "trade_review"):
            if artifacts.get(label):
                lines.append(f"- {label}: {artifacts[label]}")

    return "\n".join(lines)


def _execution_summary(execution_costs: Any) -> dict[str, Any]:
    if execution_costs is None:
        return {
            "order_count": None,
            "completed_count": None,
            "rejected_count": None,
            "rejection_rate": None,
            "total_commission": None,
            "total_slippage_cost": None,
            "rejections": [],
        }
    return {
        "order_count": execution_costs.order_count,
        "completed_count": execution_costs.completed_count,
        "rejected_count": execution_costs.rejected_count,
        "rejection_rate": execution_costs.rejection_rate,
        "total_commission": execution_costs.total_commission,
        "total_slippage_cost": execution_costs.total_slippage_cost,
        "rejections": [
            {
                "code": rejection.blocked_by,
                "label_zh": REASON_CODE_LABELS.get(rejection.blocked_by),
                "count": rejection.count,
            }
            for rejection in execution_costs.rejections
        ],
    }


def _post_exit_summary(post_exit_analysis: Any) -> dict[str, Any] | None:
    if post_exit_analysis is None:
        return None
    primary_summary = next(
        (summary for summary in post_exit_analysis.summaries if summary.group == "all"),
        post_exit_analysis.summaries[0] if post_exit_analysis.summaries else None,
    )
    return {
        "window_days": post_exit_analysis.window_days,
        "sold_too_early_threshold": post_exit_analysis.sold_too_early_threshold,
        "trade_count": post_exit_analysis.trade_count,
        "sold_too_early_count": primary_summary.sold_too_early_count if primary_summary else None,
        "sold_too_early_rate": primary_summary.sold_too_early_rate if primary_summary else None,
    }


def _scenario_fit_summary(scenario_fit: Any) -> dict[str, Any] | None:
    if scenario_fit is None:
        return None
    return {
        "label": scenario_fit.label,
        "score": scenario_fit.score,
        "reasons": list(scenario_fit.reasons),
        "warnings": list(scenario_fit.warnings),
    }


def _data_window_summary(result: "RunPlanExecutionResult") -> dict[str, Any] | None:
    items = tuple(_data_window_items(result))
    if not items:
        return None
    requested_starts = [
        item["requested_start_date"]
        for item in items
        if item.get("requested_start_date")
    ]
    return {
        "earliest_requested_start_date": min(requested_starts) if requested_starts else None,
        "warmup_incomplete_count": sum(1 for item in items if item.get("warmup_incomplete")),
        "items": list(items),
    }


def _data_window_items(result: "RunPlanExecutionResult") -> tuple[dict[str, Any], ...]:
    items: list[dict[str, Any]] = []
    for symbol_result in _sequence(getattr(result, "symbol_results", ())):
        items.append(
            _data_window_item(
                kind="symbol",
                symbol=getattr(symbol_result, "symbol", None),
                provenance=getattr(symbol_result, "snapshot_provenance", None),
                bar_count=getattr(symbol_result, "bar_count", None),
                calculation_bar_count=None,
            )
        )
    for benchmark in _sequence(getattr(result, "benchmark_results", ())):
        items.append(
            _data_window_item(
                kind="benchmark",
                symbol=getattr(benchmark, "symbol", None),
                provenance=getattr(benchmark, "snapshot_provenance", None),
                bar_count=getattr(benchmark, "bar_count", None),
                calculation_bar_count=getattr(benchmark, "calculation_bar_count", None),
            )
        )
    for industry_index in _sequence(getattr(result, "industry_index_results", ())):
        items.append(
            _data_window_item(
                kind="industry_index",
                symbol=getattr(industry_index, "symbol", None),
                provenance=getattr(industry_index, "snapshot_provenance", None),
                bar_count=getattr(industry_index, "bar_count", None),
                calculation_bar_count=getattr(industry_index, "calculation_bar_count", None),
            )
        )
    return tuple(item for item in items if item["symbol"])


def _stock_pool_filter_summary(result: "RunPlanExecutionResult") -> dict[str, Any] | None:
    stock_pool_filter = getattr(result, "stock_pool_filter", None)
    if stock_pool_filter is None:
        return None
    return {
        "source_pool_file": str(getattr(stock_pool_filter, "source_pool_file", "")),
        "original_count": getattr(stock_pool_filter, "original_count", None),
        "kept_count": getattr(stock_pool_filter, "kept_count", None),
        "warning_count": getattr(stock_pool_filter, "warning_count", None),
        "excluded_count": getattr(stock_pool_filter, "excluded_count", None),
        "excluded_symbols": [
            getattr(item, "symbol", None)
            for item in _sequence(getattr(stock_pool_filter, "excluded_symbols", ()))
        ],
    }


def _attribution_factor_selection_summary(result: "RunPlanExecutionResult") -> dict[str, Any] | None:
    selection = getattr(result, "attribution_factor_selection", None)
    selection_map = _mapping(selection)
    if not selection_map:
        return None
    include = _sequence(selection_map.get("include"))
    not_include = _sequence(selection_map.get("not_include"))
    return {
        "schema": selection_map.get("schema"),
        "enabled": selection_map.get("enabled"),
        "configured_source": selection_map.get("configured_source"),
        "include_count": selection_map.get("include_count", len(include)),
        "not_include_count": selection_map.get("not_include_count", len(not_include)),
        "include": [str(key) for key in include],
        "not_include": [str(key) for key in not_include],
        "entry_attribution": selection_map.get("entry_attribution"),
    }


def _data_window_item(
    *,
    kind: str,
    symbol: Any,
    provenance: Any,
    bar_count: Any,
    calculation_bar_count: Any,
) -> dict[str, Any]:
    details = _mapping(getattr(provenance, "details", {}))
    return {
        "kind": kind,
        "symbol": str(symbol) if symbol is not None else None,
        "bar_count": bar_count,
        "calculation_bar_count": calculation_bar_count,
        "snapshot_start_date": _iso(getattr(provenance, "start_date", None)),
        "snapshot_end_date": _iso(getattr(provenance, "end_date", None)),
        "requested_start_date": details.get("requested_start_date"),
        "requested_end_date": details.get("requested_end_date"),
        "minimum_start_date": details.get("minimum_start_date"),
        "warmup_incomplete": bool(details.get("warmup_incomplete")),
    }


def _artifact_summary(artifact_paths: "RunArtifactPaths | None") -> dict[str, str]:
    if artifact_paths is None:
        return {}
    return {
        "output_dir": str(artifact_paths.output_dir),
        "report_zh": str(artifact_paths.report_chinese_markdown_path),
        "report_json": str(artifact_paths.report_path),
        "trades": str(artifact_paths.trades_path),
        "environment_fit": str(artifact_paths.environment_fit_path),
        "trade_review": str(artifact_paths.trade_review_path),
        "trade_attribution": _path_string(getattr(artifact_paths, "trade_attribution_path", None)),
        "post_exit_analysis": str(artifact_paths.post_exit_analysis_path),
        "evidence_validation": str(artifact_paths.evidence_validation_path),
        "data_preflight": _path_string(getattr(artifact_paths, "data_preflight_path", None)),
        "stock_pool_filter": _path_string(getattr(artifact_paths, "stock_pool_filter_path", None)),
        "attribution_factor_selection": _path_string(
            getattr(artifact_paths, "attribution_factor_selection_path", None)
        ),
    }


def _path_string(value: Any) -> str:
    return str(value) if value is not None else ""


def _read_evidence_validation(artifact_paths: "RunArtifactPaths | None") -> dict[str, Any] | None:
    if artifact_paths is None or not artifact_paths.evidence_validation_path.exists():
        return None
    try:
        payload = json.loads(artifact_paths.evidence_validation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {
        "status": payload.get("status"),
        "error_count": payload.get("error_count"),
        "warning_count": payload.get("warning_count"),
    }


def _open_symbols(open_positions: Sequence[Any]) -> tuple[str, ...]:
    return tuple(str(getattr(position, "symbol")) for position in open_positions)


def _cash_ratio(final_cash: float | None, final_value: float | None) -> float | None:
    if final_cash is None or final_value in (None, 0):
        return None
    return final_cash / final_value


def _format_rejections(rejections: Sequence[Any]) -> str:
    labels: list[str] = []
    for rejection in rejections:
        rejection_map = _mapping(rejection)
        code = rejection_map.get("code")
        label = rejection_map.get("label_zh") or code
        labels.append(f"{label} ({code}): {rejection_map.get('count')}")
    return "；".join(labels)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, str):
        return ()
    if isinstance(value, Sequence):
        return value
    return ()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _format_number(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{float(value):,.2f}"


def _format_optional_number(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{float(value):.2f}"


def _format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{float(value) * 100:.2f}%"
