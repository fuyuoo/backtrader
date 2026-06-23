"""Generate A-anchored pairwise entry-factor combination manifests."""

from __future__ import annotations

import copy
import csv
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

import yaml

from attbacktrader.config import RunPlan


ENTRY_FACTOR_PAIRWISE_COMBINATION_MANIFEST_SCHEMA = "attbacktrader.entry_factor_pairwise_combination_manifest.v1"


def build_entry_factor_pairwise_combination_manifest(
    screening_layers_or_path: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | Path,
    baseline_run_plan_or_path: Mapping[str, Any] | str | Path,
    *,
    anchor_layer: str = "A",
    layers: Sequence[str] = ("A", "B", "C"),
    require_strict_pre_entry: bool = True,
    reuse_snapshots: bool = True,
    missing_policy: str = "block",
) -> dict[str, Any]:
    """Build independent two-factor entry-filter RunPlans anchored by an A-layer factor."""

    if missing_policy not in {"block", "pass"}:
        raise ValueError("missing_policy must be block or pass")

    anchor = _layer_code(anchor_layer)
    layer_codes = tuple(dict.fromkeys(_layer_code(layer) for layer in layers if _layer_code(layer)))
    if not anchor:
        raise ValueError("anchor_layer must not be empty")
    if anchor not in layer_codes:
        raise ValueError("anchor_layer must be included in layers")

    rows, screening_path = _load_screening_rows(screening_layers_or_path)
    baseline, baseline_path = _load_run_plan_mapping(baseline_run_plan_or_path)
    base_plan = RunPlan.from_mapping(baseline)
    selected, skipped = _select_screening_rows(
        rows,
        layers=layer_codes,
        require_strict_pre_entry=require_strict_pre_entry,
    )
    pairs = [
        _anchor_ordered_pair(left, right, anchor_layer=anchor)
        for left, right in combinations(selected, 2)
        if anchor in {_screening_layer_code(left), _screening_layer_code(right)}
    ]
    candidates = [
        _pairwise_candidate(
            left,
            right,
            baseline=baseline,
            base_run_id=base_plan.run.id,
            sequence=index,
            anchor_layer=anchor,
            reuse_snapshots=reuse_snapshots,
            missing_policy=missing_policy,
        )
        for index, (left, right) in enumerate(pairs, start=1)
    ]

    return {
        "schema": ENTRY_FACTOR_PAIRWISE_COMBINATION_MANIFEST_SCHEMA,
        "source_mode": "a_anchored_pairwise_entry_factor_combination",
        "source_screening_layers": str(screening_path) if screening_path is not None else None,
        "source_baseline_run_plan": str(baseline_path) if baseline_path is not None else None,
        "base_run_id": base_plan.run.id,
        "anchor_layer": anchor,
        "layers": list(layer_codes),
        "require_strict_pre_entry": require_strict_pre_entry,
        "reuse_snapshots": reuse_snapshots,
        "missing_policy": missing_policy,
        "source_layer_counts": dict(Counter(_screening_layer_code(row) for row in selected)),
        "pair_kind_counts": dict(Counter(candidate.get("combo_kind") for candidate in candidates)),
        "generated_count": len(candidates),
        "skipped_count": len(skipped),
        "candidates": candidates,
        "skipped_rows": skipped,
        "rules": [
            "只读取最终筛选分层中的 A/B/C 层候选。",
            "每个组合必须是独立二因子 entry_filter，且至少包含一个 A 层核心因子。",
            "每个组合只改变 entry_filter.conditions，不改变入场、止盈、止损、加仓、仓位或数据范围。",
            "A/B/C 候选必须是严格事前可用时才进入默认组合池。",
            "组合验证只产出研究证据，不自动修改默认策略。",
        ],
    }


def render_entry_factor_pairwise_combination_manifest_markdown_zh(manifest: Mapping[str, Any]) -> str:
    """Render an A-anchored pairwise combination manifest in Chinese Markdown."""

    lines = [
        "# A 锚定二因子入场组合验证 Manifest",
        "",
        f"- schema: `{manifest.get('schema')}`",
        f"- base_run_id: `{manifest.get('base_run_id')}`",
        f"- anchor_layer: `{manifest.get('anchor_layer')}`",
        f"- layers: `{', '.join(str(layer) for layer in _as_sequence(manifest.get('layers')))}`",
        f"- generated_count: `{manifest.get('generated_count')}`",
        f"- skipped_count: `{manifest.get('skipped_count', 0)}`",
        f"- reuse_snapshots: `{manifest.get('reuse_snapshots')}`",
        "",
        "## 规则",
    ]
    for rule in _as_sequence(manifest.get("rules")):
        lines.append(f"- {rule}")
    lines.extend(
        [
            "",
            "## 组合 RunPlan",
            "",
            "| 序号 | 类型 | 条件1 | 条件2 | 弱侧分数 | 最小交易数 | run_id | YAML |",
            "|---:|---|---|---|---:|---:|---|---|",
        ]
    )
    for candidate in _as_sequence(manifest.get("candidates")):
        item = _as_mapping(candidate)
        factors = [_as_mapping(factor) for factor in _as_sequence(item.get("source_factors"))]
        first = factors[0] if factors else {}
        second = factors[1] if len(factors) > 1 else {}
        lines.append(
            "| "
            f"{item.get('candidate_index')} | "
            f"{_escape_cell(item.get('combo_kind'))} | "
            f"{_escape_cell(_factor_label(first))} | "
            f"{_escape_cell(_factor_label(second))} | "
            f"{_format_number(item.get('factor_quality_score'))} | "
            f"{_format_int(item.get('sample_count'))} | "
            f"`{_escape_cell(item.get('run_id'))}` | "
            f"`{_escape_cell(item.get('run_plan_path'))}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_entry_factor_pairwise_combination_manifest(
    manifest: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, tuple[Path, ...], dict[str, Any]]:
    """Write manifest JSON, Markdown, and generated RunPlan YAML files."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    run_plan_dir = output_path / "run-plans"
    run_plan_dir.mkdir(parents=True, exist_ok=True)

    yaml_paths: list[Path] = []
    candidates: list[dict[str, Any]] = []
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
        "pairwise_manifest_json": str(output_path / "entry_factor_pairwise_combination_manifest.json"),
        "pairwise_manifest_markdown_zh": str(output_path / "entry_factor_pairwise_combination_manifest.zh.md"),
        "pairwise_run_plan_paths": [str(path) for path in yaml_paths],
    }
    json_path = output_path / "entry_factor_pairwise_combination_manifest.json"
    markdown_path = output_path / "entry_factor_pairwise_combination_manifest.zh.md"
    json_path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_factor_pairwise_combination_manifest_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, tuple(yaml_paths), _jsonable(payload)


def safe_entry_factor_pairwise_combination_manifest_dir_name(screening_layers_path: str | Path) -> str:
    stem = Path(screening_layers_path).parent.name or Path(screening_layers_path).stem
    return f"entry-factor-pairwise-combination-manifest-{_safe_path_name(stem)}"


def _select_screening_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    layers: Sequence[str],
    require_strict_pre_entry: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    layer_set = set(layers)
    for position, row in enumerate(rows, start=1):
        item = dict(row)
        layer = _screening_layer_code(item)
        reasons: list[str] = []
        if layer not in layer_set:
            reasons.append("layer_not_selected")
        if require_strict_pre_entry and not _is_strict_pre_entry(item):
            reasons.append("not_strict_pre_entry")
        if not item.get("field_key"):
            reasons.append("missing_field_key")
        if item.get("action") not in {"keep", "exclude"}:
            reasons.append("unsupported_action")
        if reasons:
            skipped.append(_skipped_row(item, position=position, reasons=reasons))
            continue
        selected.append(item)
    return selected, skipped


def _pairwise_candidate(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
    base_run_id: str,
    sequence: int,
    anchor_layer: str,
    reuse_snapshots: bool,
    missing_policy: str,
) -> dict[str, Any]:
    rows = (left, right)
    conditions = [_condition_from_row(row) for row in rows]
    source_factors = [_source_factor(row) for row in rows]
    combo_kind = "".join(_screening_layer_code(row) for row in rows)
    run_id = _pairwise_run_id(base_run_id, sequence=sequence, combo_kind=combo_kind, rows=rows)
    run_plan = _variant_run_plan(
        baseline,
        run_id=run_id,
        conditions=conditions,
        reuse_snapshots=reuse_snapshots,
        missing_policy=missing_policy,
    )
    RunPlan.from_mapping(run_plan)
    scores = [_number_or_none(row.get("validation_score")) for row in rows]
    trade_counts = [_number_or_none(row.get("trade_count")) for row in rows]
    return {
        "candidate_index": sequence,
        "candidate_rank": sequence,
        "view": "a_anchored_pairwise_entry_factor_combination",
        "combo_kind": combo_kind,
        "anchor_layer": anchor_layer,
        "screening_layers": [_screening_layer_code(row) for row in rows],
        "direction": "combination",
        "action": "entry_filter_pair",
        "field_key": "combo.a_anchored_pairwise",
        "field_label_zh": "A锚定二因子入场组合",
        "value": f"combo_{sequence:03d}",
        "value_label_zh": "；".join(_factor_label(factor) for factor in source_factors),
        "sample_count": _min_number(trade_counts),
        "factor_quality_score": _min_number(scores),
        "single_factor_score_sum": sum(score for score in scores if score is not None),
        "conditions": conditions,
        "filter_conditions": conditions,
        "source_factors": source_factors,
        "positive_conditions": [factor for factor in source_factors if factor.get("action") == "keep"],
        "negative_conditions": [factor for factor in source_factors if factor.get("action") == "exclude"],
        "run_id": run_id,
        "run_plan": run_plan,
        "run_plan_path": None,
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


def _anchor_ordered_pair(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    anchor_layer: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    left_is_anchor = _screening_layer_code(left) == anchor_layer
    right_is_anchor = _screening_layer_code(right) == anchor_layer
    if right_is_anchor and not left_is_anchor:
        return right, left
    return left, right


def _condition_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "field": row.get("field_key"),
        "operator": "eq",
        "value": row.get("value"),
        "action": row.get("action"),
    }


def _source_factor(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "candidate_index",
        "screening_layer",
        "status",
        "validation_score",
        "direction",
        "action",
        "field_key",
        "field_label_zh",
        "value",
        "value_label_zh",
        "cumulative_return",
        "return_delta",
        "max_drawdown",
        "drawdown_delta",
        "win_rate",
        "win_rate_delta",
        "profit_loss_ratio",
        "profit_loss_ratio_delta",
        "trade_count",
        "usability",
        "scope",
    )
    return {key: _jsonable(row.get(key)) for key in keys if key in row}


def _skipped_row(row: Mapping[str, Any], *, position: int, reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "source_position": position,
        "candidate_index": row.get("candidate_index"),
        "screening_layer": row.get("screening_layer"),
        "usability": row.get("usability"),
        "action": row.get("action"),
        "field_key": row.get("field_key"),
        "value": row.get("value"),
        "value_label_zh": row.get("value_label_zh"),
        "skip_reasons": list(reasons),
    }


def _pairwise_run_id(
    base_run_id: str,
    *,
    sequence: int,
    combo_kind: str,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    parts = ["efp", f"{sequence:03d}", combo_kind.lower()]
    for row in rows:
        parts.extend(
            [
                f"c{int(row.get('candidate_index') or 0):03d}",
                _slug(row.get("field_key"), max_len=28),
                _slug(row.get("value"), max_len=18),
            ]
        )
    return _trim_run_id(f"{base_run_id}-{'-'.join(part for part in parts if part)}")


def _load_screening_rows(
    value: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | Path,
) -> tuple[list[dict[str, Any]], Path | None]:
    if isinstance(value, Mapping):
        return _rows_from_payload(value), None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [dict(_as_mapping(item)) for item in value], None
    path = Path(value)
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)], path
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _rows_from_payload(payload), path


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [dict(_as_mapping(item)) for item in payload]
    if isinstance(payload, Mapping):
        for key in ("rows", "items", "layers"):
            rows = payload.get(key)
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray)):
                return [dict(_as_mapping(item)) for item in rows]
    raise ValueError("screening layers must be a JSON array, CSV, or object with rows/items/layers")


def _load_run_plan_mapping(value: Mapping[str, Any] | str | Path) -> tuple[dict[str, Any], Path | None]:
    if isinstance(value, Mapping):
        return _jsonable(value), None
    path = Path(value)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload, path


def _screening_layer_code(row: Mapping[str, Any]) -> str:
    return _layer_code(row.get("screening_layer"))


def _layer_code(value: object) -> str:
    return str(value or "").strip().split(" ", 1)[0].upper()


def _is_strict_pre_entry(row: Mapping[str, Any]) -> bool:
    return str(row.get("usability") or "").startswith("U0")


def _factor_label(row: Mapping[str, Any]) -> str:
    action = "保留" if row.get("action") == "keep" else "排除"
    label = row.get("field_label_zh") or row.get("field_key")
    value = row.get("value_label_zh") or row.get("value")
    return f"{action}:{label}={value}"


def _safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe or "run"


def _trim_run_id(run_id: str, *, max_len: int = 160) -> str:
    if len(run_id) <= max_len:
        return run_id
    return run_id[:max_len].rstrip("-_.")


def _slug(value: Any, *, max_len: int) -> str:
    raw = str(value).strip().lower()
    safe = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return (safe or "value")[:max_len].strip("-")


def _min_number(values: Sequence[float | None]) -> float | int | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    number = min(numbers)
    return int(number) if number.is_integer() else number


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: object) -> Sequence[Any]:
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
        return str(int(float(value)))
    except (TypeError, ValueError):
        return "-"
