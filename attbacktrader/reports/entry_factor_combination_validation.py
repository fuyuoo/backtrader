"""Build and assess stepwise Stage 2 entry-factor combination validation."""

from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from attbacktrader.config import RunPlan


ENTRY_FACTOR_COMBINATION_MANIFEST_SCHEMA = "attbacktrader.entry_factor_combination_manifest.v1"
ENTRY_FACTOR_COMBINATION_VALIDATION_SCHEMA = "attbacktrader.entry_factor_combination_validation.v1"

_SURVIVOR_CLASSIFICATIONS = {"stable_favorable", "stable_unfavorable"}


def build_entry_factor_combination_manifest(
    classification_or_path: Mapping[str, Any] | str | Path,
    baseline_run_plan_or_path: Mapping[str, Any] | str | Path,
    *,
    max_steps: int | None = None,
    reuse_snapshots: bool = True,
    missing_policy: str = "block",
) -> dict[str, Any]:
    """Generate non-exhaustive stepwise combination RunPlans from Stage 1 survivors."""

    if max_steps is not None and max_steps <= 0:
        raise ValueError("max_steps must be greater than 0")
    if missing_policy not in {"block", "pass"}:
        raise ValueError("missing_policy must be block or pass")

    classification, classification_path = _load_json_mapping(classification_or_path)
    baseline, baseline_path = _load_run_plan_mapping(baseline_run_plan_or_path)
    base_plan = RunPlan.from_mapping(baseline)
    survivors = _stable_survivors(classification)
    if max_steps is not None:
        survivors = survivors[:max_steps]

    candidates: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []
    source_survivors: list[dict[str, Any]] = []
    for index, survivor in enumerate(survivors, start=1):
        condition = _condition_from_survivor(survivor)
        conditions.append(condition)
        source_survivors.append(_survivor_summary(survivor))
        run_id = _combination_run_id(
            base_plan.run.id,
            step=index,
            latest_condition=condition,
        )
        run_plan = _variant_run_plan(
            baseline,
            run_id=run_id,
            conditions=conditions,
            reuse_snapshots=reuse_snapshots,
            missing_policy=missing_policy,
        )
        RunPlan.from_mapping(run_plan)
        candidates.append(
            {
                "candidate_index": index,
                "candidate_rank": index,
                "combination_step": index,
                "direction": "combination",
                "action": "entry_filter_combo",
                "run_id": run_id,
                "filter_conditions": copy.deepcopy(conditions),
                "source_survivors": copy.deepcopy(source_survivors),
                "latest_source_survivor": _survivor_summary(survivor),
                "run_plan": run_plan,
                "run_plan_path": None,
            }
        )

    skipped_rows = [
        _skipped_row(row)
        for row in _as_sequence(classification.get("rows"))
        if _as_mapping(row).get("classification") not in _SURVIVOR_CLASSIFICATIONS
    ]
    return {
        "schema": ENTRY_FACTOR_COMBINATION_MANIFEST_SCHEMA,
        "source_classification": str(classification_path) if classification_path is not None else None,
        "source_matrix": classification.get("source_matrix"),
        "source_manifest": classification.get("source_manifest"),
        "source_baseline_run_plan": str(baseline_path) if baseline_path is not None else None,
        "base_run_id": base_plan.run.id,
        "reuse_snapshots": reuse_snapshots,
        "missing_policy": missing_policy,
        "survivor_count": len(_stable_survivors(classification)),
        "generated_count": len(candidates),
        "skipped_count": len(skipped_rows),
        "candidates": candidates,
        "skipped_rows": skipped_rows,
        "rules": [
            "Stage 2 只接收 Stage 1 stable_favorable/stable_unfavorable survivor。",
            "每一步只新增一个过滤条件，并运行一个真实 RunPlan。",
            "组合流程是前缀式 stepwise validation，不做穷举组合搜索。",
            "stable_favorable 继续使用 keep 条件；stable_unfavorable 继续使用 exclude 条件。",
            "组合验证只产出研究证据，不自动修改默认策略。",
        ],
    }


def render_entry_factor_combination_manifest_markdown_zh(manifest: Mapping[str, Any]) -> str:
    """Render the Stage 2 combination manifest in Chinese Markdown."""

    lines = [
        "# 入场因子组合验证 Manifest",
        "",
        f"- schema: `{manifest.get('schema')}`",
        f"- base_run_id: `{manifest.get('base_run_id')}`",
        f"- survivor_count: `{manifest.get('survivor_count')}`",
        f"- generated_count: `{manifest.get('generated_count')}`",
        "",
        "## 规则",
    ]
    for rule in _as_sequence(manifest.get("rules")):
        lines.append(f"- {rule}")
    lines.extend(
        [
            "",
            "## 组合步骤",
            "",
            "| 步骤 | 新增因子 | 新增值 | 条件数 | run_id |",
            "|---:|---|---|---:|---|",
        ]
    )
    for candidate in _as_sequence(manifest.get("candidates")):
        item = _as_mapping(candidate)
        latest = _as_mapping(item.get("latest_source_survivor"))
        lines.append(
            "| "
            f"{item.get('combination_step')} | "
            f"`{_escape_cell(latest.get('field_key'))}` | "
            f"{_escape_cell(latest.get('value_label_zh') or latest.get('value'))} | "
            f"{len(_as_sequence(item.get('filter_conditions')))} | "
            f"`{_escape_cell(item.get('run_id'))}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_entry_factor_combination_manifest(
    manifest: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, tuple[Path, ...], dict[str, Any]]:
    """Write combination manifest JSON, Markdown, and generated RunPlan YAML files."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    run_plan_dir = output_path / "run-plans"
    run_plan_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[dict[str, Any]] = []
    yaml_paths: list[Path] = []
    for candidate in _as_sequence(manifest.get("candidates")):
        item = dict(_as_mapping(candidate))
        run_plan = _as_mapping(item.pop("run_plan"))
        path = run_plan_dir / f"{item.get('run_id')}.run.yaml"
        path.write_text(yaml.safe_dump(run_plan, allow_unicode=True, sort_keys=False), encoding="utf-8")
        item["run_plan_path"] = str(path)
        yaml_paths.append(path)
        candidates.append(item)

    payload = dict(manifest)
    payload["candidates"] = candidates
    payload["artifacts"] = {
        "combination_manifest_json": str(output_path / "entry_factor_combination_manifest.json"),
        "combination_manifest_markdown_zh": str(output_path / "entry_factor_combination_manifest.zh.md"),
        "combination_run_plan_paths": [str(path) for path in yaml_paths],
    }
    json_path = output_path / "entry_factor_combination_manifest.json"
    markdown_path = output_path / "entry_factor_combination_manifest.zh.md"
    json_path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_factor_combination_manifest_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, tuple(yaml_paths), _jsonable(payload)


def build_entry_factor_combination_validation_report(
    validation_records_or_paths: Sequence[Mapping[str, Any] | str | Path],
    *,
    baseline_metrics: Mapping[str, Any] | None = None,
    baseline_run_id: str | None = None,
    source_manifest: str | Path | None = None,
) -> dict[str, Any]:
    """Compare each stepwise combination run against baseline and previous step."""

    records = sorted(
        (_load_record(record) for record in validation_records_or_paths),
        key=lambda record: _combination_step(record),
    )
    baseline = dict(baseline_metrics or {})
    rows: list[dict[str, Any]] = []
    previous_metrics = baseline
    for record in records:
        row = _combination_row(
            record,
            baseline_metrics=baseline,
            previous_metrics=previous_metrics,
        )
        rows.append(row)
        previous_metrics = _as_mapping(row.get("metrics"))

    return {
        "schema": ENTRY_FACTOR_COMBINATION_VALIDATION_SCHEMA,
        "source_manifest": str(source_manifest) if source_manifest is not None else None,
        "baseline": {
            "run_id": baseline_run_id,
            "metrics": baseline,
        },
        "record_count": len(rows),
        "status_counts": dict(Counter(str(row.get("combination_status")) for row in rows)),
        "rows": rows,
        "rankings": {
            "additive": [row for row in rows if row.get("combination_status") == "additive"],
            "non_additive": [row for row in rows if row.get("combination_status") == "non_additive"],
            "unstable": [row for row in rows if row.get("combination_status") == "unstable"],
            "invalid": [row for row in rows if row.get("combination_status") == "invalid"],
        },
        "rules": [
            "additive 要求相对 baseline 和上一步组合的收益指标均改善。",
            "non_additive 表示仍优于 baseline，但相对上一步没有新增改善。",
            "unstable 表示组合后不再优于 baseline。",
            "invalid 表示无交易或 evidence_validation 非 ok。",
        ],
    }


def render_entry_factor_combination_validation_markdown_zh(report: Mapping[str, Any]) -> str:
    """Render the Stage 2 combination validation report in Chinese Markdown."""

    baseline = _as_mapping(report.get("baseline"))
    lines = [
        "# 入场因子组合验证报告",
        "",
        f"- schema: `{report.get('schema')}`",
        f"- source_manifest: `{report.get('source_manifest')}`",
        f"- baseline_run_id: `{baseline.get('run_id')}`",
        f"- record_count: `{report.get('record_count')}`",
        "",
        "## 组合步骤",
        "",
        "| 步骤 | 状态 | 条件数 | 收益 | 相对基线 | 相对上一步 | 回撤 | 胜率 | 交易数 | run_id |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_sequence(report.get("rows")):
        item = _as_mapping(row)
        metrics = _as_mapping(item.get("metrics"))
        baseline_delta = _as_mapping(item.get("baseline_deltas"))
        previous_delta = _as_mapping(item.get("previous_step_deltas"))
        lines.append(
            "| "
            f"{item.get('combination_step')} | "
            f"{_escape_cell(item.get('combination_status'))} | "
            f"{len(_as_sequence(item.get('filter_conditions')))} | "
            f"{_format_percent(_primary_return(metrics))} | "
            f"{_format_signed_percent(_primary_return(baseline_delta))} | "
            f"{_format_signed_percent(_primary_return(previous_delta))} | "
            f"{_format_percent(metrics.get('max_drawdown'))} | "
            f"{_format_percent(metrics.get('win_rate'))} | "
            f"{_format_int(metrics.get('trade_count'))} | "
            f"`{_escape_cell(item.get('run_id'))}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_entry_factor_combination_validation_report(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, dict[str, Any]]:
    """Write Stage 2 combination validation JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "entry_factor_combination_validation.json"
    markdown_path = output_path / "entry_factor_combination_validation.zh.md"
    payload = _jsonable(report)
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["combination_validation_json"] = str(json_path)
    artifacts["combination_validation_markdown_zh"] = str(markdown_path)
    payload["artifacts"] = artifacts
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_factor_combination_validation_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def safe_entry_factor_combination_validation_dir_name(classification_path: str | Path) -> str:
    stem = Path(classification_path).parent.name or Path(classification_path).stem
    return f"entry-factor-combination-validation-{_safe_path_name(stem)}"


def _stable_survivors(classification: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [
        dict(_as_mapping(row))
        for row in _as_sequence(classification.get("rows"))
        if _as_mapping(row).get("classification") in _SURVIVOR_CLASSIFICATIONS
    ]
    rows.sort(
        key=lambda row: (
            -(_number_or_none(row.get("validation_score")) or 0.0),
            int(row.get("candidate_index") or 0),
            str(row.get("field_key")),
            str(row.get("value_label_zh") or row.get("value")),
        )
    )
    return rows


def _condition_from_survivor(row: Mapping[str, Any]) -> dict[str, Any]:
    action = str(row.get("action") or "")
    if action not in {"keep", "exclude"}:
        action = "keep" if row.get("classification") == "stable_favorable" else "exclude"
    return {
        "field": row.get("field_key"),
        "operator": "eq",
        "value": row.get("value"),
        "action": action,
    }


def _survivor_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "candidate_index",
        "candidate_rank",
        "classification",
        "classification_label_zh",
        "direction",
        "action",
        "field_key",
        "field_label_zh",
        "value",
        "value_label_zh",
        "run_id",
        "validation_score",
    )
    return {key: _jsonable(row.get(key)) for key in keys if key in row}


def _skipped_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_index": row.get("candidate_index"),
        "classification": row.get("classification"),
        "field_key": row.get("field_key"),
        "value": row.get("value"),
        "value_label_zh": row.get("value_label_zh"),
        "skip_reason": "not_stage1_stable_survivor",
    }


def _variant_run_plan(
    baseline: Mapping[str, Any],
    *,
    run_id: str,
    conditions: Sequence[Mapping[str, Any]],
    reuse_snapshots: bool,
    missing_policy: str,
) -> dict[str, Any]:
    run_plan = copy.deepcopy(dict(baseline))
    run_plan.setdefault("run", {})["id"] = run_id
    run_plan.setdefault("data", {})["refresh_snapshots"] = not reuse_snapshots
    analysis = run_plan.setdefault("analysis", {})
    entry_attribution = analysis.setdefault("entry_attribution", {})
    entry_attribution["enabled"] = True
    entry_attribution["entry_filter"] = {
        "enabled": True,
        "conditions": [dict(condition) for condition in conditions],
        "missing_policy": missing_policy,
    }
    for condition in conditions:
        _ensure_factor_selected(run_plan, str(condition.get("field") or ""))
    return _jsonable(run_plan)


def _ensure_factor_selected(run_plan: dict[str, Any], field_key: str) -> None:
    if not field_key:
        return
    analysis = _as_mapping(run_plan.get("analysis"))
    attribution = analysis.get("attribution")
    if isinstance(attribution, dict) and attribution.get("include"):
        attribution["include"] = _append_unique(attribution.get("include"), field_key)
        return
    entry_attribution = analysis.get("entry_attribution")
    if isinstance(entry_attribution, dict):
        entry_attribution["factors"] = _append_unique(entry_attribution.get("factors"), field_key)


def _append_unique(values: object, value: str) -> list[Any]:
    result = list(_as_sequence(values))
    if value not in result:
        result.append(value)
    return result


def _combination_row(
    record: Mapping[str, Any],
    *,
    baseline_metrics: Mapping[str, Any],
    previous_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = _as_mapping(record.get("candidate"))
    run = _as_mapping(record.get("run"))
    metrics = _core_metrics(_as_mapping(_as_mapping(record.get("run_summary")).get("metrics")))
    baseline_deltas = _metric_deltas(metrics, baseline_metrics)
    previous_deltas = _metric_deltas(metrics, previous_metrics)
    evidence = _as_mapping(_as_mapping(record.get("run_summary")).get("evidence"))
    status, reasons = _combination_status(
        metrics,
        baseline_deltas=baseline_deltas,
        previous_deltas=previous_deltas,
        evidence=evidence,
    )
    return {
        "candidate_index": candidate.get("candidate_index"),
        "candidate_rank": candidate.get("candidate_rank"),
        "combination_step": candidate.get("combination_step") or candidate.get("candidate_index"),
        "run_id": run.get("id") or candidate.get("run_id"),
        "filter_conditions": list(_as_sequence(candidate.get("filter_conditions"))),
        "source_survivors": list(_as_sequence(candidate.get("source_survivors"))),
        "metrics": metrics,
        "baseline_deltas": baseline_deltas,
        "previous_step_deltas": previous_deltas,
        "combination_status": status,
        "combination_reasons": reasons,
        "slice_comparisons": _slice_comparisons(record),
        "artifacts": _as_mapping(record.get("artifacts")),
    }


def _core_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "cumulative_return",
        "return_on_entry_value",
        "max_drawdown",
        "trade_count",
        "win_rate",
        "profit_loss_ratio",
        "average_return_pct",
    )
    return {key: metrics.get(key) for key in keys if key in metrics}


def _metric_deltas(metrics: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not baseline:
        return result
    for key in ("cumulative_return", "return_on_entry_value", "max_drawdown", "trade_count", "win_rate", "profit_loss_ratio", "average_return_pct"):
        value = _number_or_none(metrics.get(key))
        base = _number_or_none(baseline.get(key))
        if value is not None and base is not None:
            result[key] = value - base
    return result


def _combination_status(
    metrics: Mapping[str, Any],
    *,
    baseline_deltas: Mapping[str, Any],
    previous_deltas: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[str, list[str]]:
    if (_number_or_none(metrics.get("trade_count")) or 0.0) <= 0:
        return "invalid", ["组合运行没有交易"]
    if evidence.get("status") not in {None, "ok"}:
        return "invalid", [f"evidence_validation status={evidence.get('status')}"]

    baseline_return = _primary_return(baseline_deltas)
    previous_return = _primary_return(previous_deltas)
    if baseline_return is None:
        return "mixed", ["缺少 baseline 收益对比"]
    if baseline_return <= 0:
        return "unstable", ["组合后不再优于 baseline"]
    if previous_return is not None and previous_return <= 0:
        return "non_additive", ["优于 baseline，但相对上一步没有新增改善"]
    return "additive", ["相对 baseline 和上一步均有新增改善"]


def _slice_comparisons(record: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for key in ("overall_comparison", "year_slices", "market_stage_slices"):
        if key in record:
            result[key] = _jsonable(record.get(key))
    return result


def _primary_return(metrics: Mapping[str, Any]) -> float | None:
    for key in ("return_on_entry_value", "cumulative_return", "average_return_pct"):
        value = _number_or_none(metrics.get(key))
        if value is not None:
            return value
    return None


def _combination_step(record: Mapping[str, Any]) -> int:
    candidate = _as_mapping(record.get("candidate"))
    return int(candidate.get("combination_step") or candidate.get("candidate_index") or 0)


def _combination_run_id(base_run_id: str, *, step: int, latest_condition: Mapping[str, Any]) -> str:
    suffix = "-".join(
        part
        for part in (
            "efc",
            f"step{step:03d}",
            _slug(latest_condition.get("field"), max_len=42),
            _slug(latest_condition.get("value"), max_len=24),
        )
        if part
    )
    return _trim_run_id(f"{base_run_id}-{suffix}")


def _trim_run_id(run_id: str, *, max_len: int = 160) -> str:
    if len(run_id) <= max_len:
        return run_id
    return run_id[:max_len].rstrip("-_.")


def _slug(value: Any, *, max_len: int) -> str:
    raw = str(value).strip().lower()
    safe = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return (safe or "value")[:max_len].strip("-")


def _load_record(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _load_json_mapping(value: Mapping[str, Any] | str | Path) -> tuple[dict[str, Any], Path | None]:
    if isinstance(value, Mapping):
        return dict(value), None
    path = Path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload, path


def _load_run_plan_mapping(value: Mapping[str, Any] | str | Path) -> tuple[dict[str, Any], Path | None]:
    if isinstance(value, Mapping):
        return _jsonable(value), None
    path = Path(value)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload, path


def _safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe or "run"


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    return number if math.isfinite(number) else None


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _escape_cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _format_int(value: object) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "-"


def _format_percent(value: object) -> str:
    number = _number_or_none(value)
    return "-" if number is None else f"{number * 100:.2f}%"


def _format_signed_percent(value: object) -> str:
    number = _number_or_none(value)
    if number is None:
        return "-"
    prefix = "+" if number > 0 else ""
    return f"{prefix}{number * 100:.2f}%"
