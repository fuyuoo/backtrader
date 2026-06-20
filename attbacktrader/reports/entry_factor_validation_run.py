"""Persist one real entry-factor validation execution."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


ENTRY_FACTOR_VALIDATION_RUN_SCHEMA = "attbacktrader.entry_factor_validation_run.v1"


def build_entry_factor_validation_run_record(
    *,
    manifest: Mapping[str, Any],
    candidate: Mapping[str, Any],
    run_plan: Any,
    run_plan_path: str | Path | None,
    run_summary: Mapping[str, Any],
    artifact_paths: Any | None,
    validation_output_dir: str | Path,
) -> dict[str, Any]:
    """Build the compact trace for one executed validation candidate."""

    run_plan_payload = _jsonable(run_plan)
    entry_filter = _entry_filter_from_run_plan(run_plan_payload)
    compact_summary = _compact_run_summary(run_summary)
    run = _as_mapping(compact_summary.get("run"))
    return {
        "schema": ENTRY_FACTOR_VALIDATION_RUN_SCHEMA,
        "manifest": {
            "base_run_id": manifest.get("base_run_id"),
            "source_discovery_run_id": manifest.get("source_discovery_run_id"),
            "source_bayesian_factor_discovery": manifest.get("source_bayesian_factor_discovery"),
            "source_baseline_run_plan": manifest.get("source_baseline_run_plan"),
        },
        "candidate": _candidate_summary(candidate),
        "run": {
            "id": run.get("id") or _run_plan_id(run_plan_payload) or candidate.get("run_id"),
            "from_date": run.get("from_date") or _nested_get(run_plan_payload, ("run", "from_date")),
            "to_date": run.get("to_date") or _nested_get(run_plan_payload, ("run", "to_date")),
        },
        "run_plan_path": str(run_plan_path) if run_plan_path is not None else None,
        "entry_filter": entry_filter,
        "run_summary": compact_summary,
        "artifacts": _artifact_summary(artifact_paths),
        "validation_output_dir": str(validation_output_dir),
        "rules": [
            "该记录只代表一个入场候选因子的真实 RunPlan 验证，不代表多因子组合优化结果。",
            "候选来自 manifest 的 tradable_pre_entry 排名；positive 使用 keep，negative 使用 exclude。",
            "执行层复用普通 RunPlan artifact，验证记录只保存候选、过滤条件、摘要指标和路径索引。",
        ],
    }


def render_entry_factor_validation_run_markdown_zh(record: Mapping[str, Any]) -> str:
    """Render one entry factor validation run in Chinese Markdown."""

    candidate = _as_mapping(record.get("candidate"))
    run = _as_mapping(record.get("run"))
    metrics = _as_mapping(_as_mapping(record.get("run_summary")).get("metrics"))
    artifacts = _as_mapping(record.get("artifacts"))
    entry_filter = _as_mapping(record.get("entry_filter"))
    conditions = _as_sequence(entry_filter.get("conditions"))
    first_condition = _as_mapping(conditions[0]) if conditions else {}

    lines = [
        "# 入场单因子真实验证",
        "",
        f"- schema: `{record.get('schema')}`",
        f"- run_id: `{run.get('id')}`",
        f"- candidate_index: `{candidate.get('candidate_index')}`",
        f"- 方向/动作: `{candidate.get('direction')}` / `{candidate.get('action')}`",
        f"- 因子: `{candidate.get('field_key')}`",
        f"- 值: `{candidate.get('value_label_zh') or candidate.get('value')}`",
        f"- 原始样本数: `{candidate.get('sample_count')}`",
        f"- 发现分数: `{_format_number(candidate.get('factor_quality_score'))}`",
        "",
        "## 入场过滤条件",
        "",
        "| field | operator | value | action | missing_policy |",
        "|---|---|---|---|---|",
        (
            "| "
            f"`{_escape_cell(first_condition.get('field'))}` | "
            f"`{_escape_cell(first_condition.get('operator'))}` | "
            f"{_escape_cell(first_condition.get('value'))} | "
            f"`{_escape_cell(first_condition.get('action'))}` | "
            f"`{_escape_cell(entry_filter.get('missing_policy'))}` |"
        ),
        "",
        "## 结果摘要",
        "",
        f"- 累计收益: {_format_percent(metrics.get('cumulative_return'))}",
        f"- 最大回撤: {_format_percent(metrics.get('max_drawdown'))}",
        f"- 交易数: {_format_int(metrics.get('trade_count'))}",
        f"- 胜率: {_format_percent(metrics.get('win_rate'))}",
        f"- 盈亏比: {_format_number(metrics.get('profit_loss_ratio'))}",
        "",
        "## 路径",
        "",
        f"- run_plan: `{record.get('run_plan_path')}`",
    ]
    for label in (
        "output_dir",
        "report_zh",
        "environment_fit",
        "trade_review",
        "evidence_validation",
        "validation_json",
        "validation_markdown_zh",
    ):
        if artifacts.get(label):
            lines.append(f"- {label}: `{artifacts[label]}`")
    lines.append("")
    return "\n".join(lines)


def write_entry_factor_validation_run_record(
    record: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, dict[str, Any]]:
    """Write one validation execution record as JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "entry_factor_validation_run.json"
    markdown_path = output_path / "entry_factor_validation_run.zh.md"

    payload = dict(record)
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["validation_json"] = str(json_path)
    artifacts["validation_markdown_zh"] = str(markdown_path)
    payload["artifacts"] = artifacts

    json_path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_factor_validation_run_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, _jsonable(payload)


def _candidate_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "candidate_index",
        "candidate_rank",
        "view",
        "direction",
        "action",
        "field_key",
        "field_label_zh",
        "value",
        "value_label_zh",
        "factor_quality_score",
        "sample_count",
        "flags",
        "filter_condition",
        "run_id",
        "run_plan_path",
    )
    return {key: _jsonable(candidate.get(key)) for key in keys if key in candidate}


def _artifact_summary(artifact_paths: Any | None) -> dict[str, str]:
    if artifact_paths is None:
        return {}
    return {
        "output_dir": _path_string(getattr(artifact_paths, "output_dir", None)),
        "report_zh": _path_string(getattr(artifact_paths, "report_chinese_markdown_path", None)),
        "report_json": _path_string(getattr(artifact_paths, "report_path", None)),
        "trades": _path_string(getattr(artifact_paths, "trades_path", None)),
        "environment_fit": _path_string(getattr(artifact_paths, "environment_fit_path", None)),
        "trade_review": _path_string(getattr(artifact_paths, "trade_review_path", None)),
        "trade_attribution": _path_string(getattr(artifact_paths, "trade_attribution_path", None)),
        "post_exit_analysis": _path_string(getattr(artifact_paths, "post_exit_analysis_path", None)),
        "evidence_validation": _path_string(getattr(artifact_paths, "evidence_validation_path", None)),
        "attribution_factor_selection": _path_string(
            getattr(artifact_paths, "attribution_factor_selection_path", None)
        ),
    }


def _compact_run_summary(run_summary: Mapping[str, Any]) -> dict[str, Any]:
    summary = _jsonable(run_summary)
    run = dict(_as_mapping(summary.get("run")))
    run.pop("symbols", None)

    data_windows = dict(_as_mapping(summary.get("data_windows")))
    data_window_items = _as_sequence(data_windows.get("items"))
    if data_windows:
        data_windows["item_count"] = len(data_window_items)
        data_windows.pop("items", None)

    compact = {
        "schema": summary.get("schema"),
        "run": run,
        "metrics": _as_mapping(summary.get("metrics")),
        "portfolio": _as_mapping(summary.get("portfolio")),
        "execution": _as_mapping(summary.get("execution")),
        "benchmarks": _as_sequence(summary.get("benchmarks")),
        "scenario_fit": _as_mapping(summary.get("scenario_fit")),
        "stock_pool_filter": _as_mapping(summary.get("stock_pool_filter")),
        "attribution_factor_selection": _as_mapping(summary.get("attribution_factor_selection")),
        "data_windows": data_windows,
        "evidence": _as_mapping(summary.get("evidence")),
    }
    return {key: _jsonable(value) for key, value in compact.items() if value not in ({}, (), [], None)}


def _entry_filter_from_run_plan(run_plan: Mapping[str, Any]) -> dict[str, Any]:
    entry_attribution = _as_mapping(_nested_get(run_plan, ("analysis", "entry_attribution")))
    entry_filter = _as_mapping(entry_attribution.get("entry_filter"))
    return _jsonable(entry_filter)


def _run_plan_id(run_plan: Mapping[str, Any]) -> str | None:
    run_id = _nested_get(run_plan, ("run", "id"))
    return str(run_id) if run_id is not None else None


def _nested_get(value: Mapping[str, Any], keys: Sequence[str]) -> Any:
    current: Any = value
    for key in keys:
        current = _as_mapping(current).get(key)
        if current is None:
            return None
    return current


def _path_string(value: Any) -> str:
    return str(value) if value is not None else ""


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _escape_cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _format_number(value: object) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "-"


def _format_int(value: object) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "-"


def _format_percent(value: object) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"
