"""Generate single-factor entry validation RunPlan manifests."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from attbacktrader.config import RunPlan
from attbacktrader.strategies import entry_attribution_declaration_by_key


ENTRY_FACTOR_VALIDATION_MANIFEST_SCHEMA = "attbacktrader.entry_factor_validation_manifest.v1"


def build_entry_factor_validation_manifest(
    discovery_or_path: Mapping[str, Any] | str | Path,
    baseline_run_plan_or_path: Mapping[str, Any] | str | Path,
    *,
    positive_limit: int = 10,
    negative_limit: int = 10,
    reuse_snapshots: bool = True,
    missing_policy: str = "block",
) -> dict[str, Any]:
    """Build legal RunPlan variants for Stage 1 single-factor validation."""

    if positive_limit < 0:
        raise ValueError("positive_limit must be greater than or equal to 0")
    if negative_limit < 0:
        raise ValueError("negative_limit must be greater than or equal to 0")
    if missing_policy not in {"block", "pass"}:
        raise ValueError("missing_policy must be block or pass")

    discovery, discovery_path = _load_json_mapping(discovery_or_path)
    baseline, baseline_path = _load_run_plan_mapping(baseline_run_plan_or_path)
    base_plan = RunPlan.from_mapping(baseline)
    selected = _selected_candidates(discovery, positive_limit=positive_limit, negative_limit=negative_limit)
    candidates = [
        _manifest_candidate(
            candidate,
            baseline=baseline,
            base_run_id=base_plan.run.id,
            sequence=index,
            reuse_snapshots=reuse_snapshots,
            missing_policy=missing_policy,
        )
        for index, candidate in enumerate(selected, start=1)
    ]

    return {
        "schema": ENTRY_FACTOR_VALIDATION_MANIFEST_SCHEMA,
        "source_bayesian_factor_discovery": str(discovery_path) if discovery_path is not None else None,
        "source_discovery_run_id": discovery.get("run_id"),
        "source_baseline_run_plan": str(baseline_path) if baseline_path is not None else None,
        "base_run_id": base_plan.run.id,
        "positive_limit": positive_limit,
        "negative_limit": negative_limit,
        "reuse_snapshots": reuse_snapshots,
        "missing_policy": missing_policy,
        "generated_count": len(candidates),
        "candidates": candidates,
        "rules": [
            "只读取 Bayesian Factor Discovery 的 tradable_pre_entry positive/negative 排名。",
            "positive 候选生成 keep 条件；negative 候选生成 exclude 条件。",
        "每个候选只生成一个单因子 RunPlan，不能在 Stage 1 叠加多因子。",
        "每个候选必须是运行时 EntryAttribution 已声明的可执行字段；仅存在于 wide sample/environment_fit 的诊断字段不进入真实验证。",
        "lifecycle_diagnostic、trade.path、exit、post_exit、entry_to_exit、sizing 等字段不得进入入场验证 manifest。",
        "生成的 RunPlan 已通过 RunPlan.from_mapping 校验；执行前仍需人工确认数据范围和运行成本。",
        ],
    }


def render_entry_factor_validation_manifest_markdown_zh(manifest: Mapping[str, Any]) -> str:
    """Render the entry factor validation manifest in Chinese Markdown."""

    lines = [
        "# 入场单因子验证 Manifest",
        "",
        f"- schema: `{manifest.get('schema')}`",
        f"- base_run_id: `{manifest.get('base_run_id')}`",
        f"- source_discovery_run_id: `{manifest.get('source_discovery_run_id')}`",
        f"- generated_count: `{manifest.get('generated_count')}`",
        f"- reuse_snapshots: `{manifest.get('reuse_snapshots')}`",
        "",
        "## 规则",
    ]
    for rule in _as_sequence(manifest.get("rules")):
        lines.append(f"- {rule}")
    lines.extend(
        [
            "",
            "## 候选 RunPlan",
            "",
            "| 序号 | 方向 | 动作 | 因子 | 值 | 样本 | 分数 | run_id | YAML |",
            "|---:|---|---|---|---|---:|---:|---|---|",
        ]
    )
    for candidate in _as_sequence(manifest.get("candidates")):
        item = _as_mapping(candidate)
        lines.append(
            "| "
            f"{item.get('candidate_index')} | "
            f"{_escape_cell(item.get('direction'))} | "
            f"{_escape_cell(item.get('action'))} | "
            f"`{_escape_cell(item.get('field_key'))}` | "
            f"{_escape_cell(item.get('value_label_zh') or item.get('value'))} | "
            f"{item.get('sample_count')} | "
            f"{_format_number(item.get('factor_quality_score'))} | "
            f"`{_escape_cell(item.get('run_id'))}` | "
            f"`{_escape_cell(item.get('run_plan_path'))}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_entry_factor_validation_manifest(
    manifest: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, tuple[Path, ...]]:
    """Write manifest JSON, Chinese Markdown, and generated RunPlan YAML files."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    yaml_paths: list[Path] = []
    candidates: list[dict[str, Any]] = []
    for candidate in _as_sequence(manifest.get("candidates")):
        item = dict(_as_mapping(candidate))
        run_plan = _as_mapping(item.pop("run_plan"))
        path = output_path / f"{item.get('run_id')}.run.yaml"
        item["run_plan_path"] = str(path)
        path.write_text(yaml.safe_dump(run_plan, allow_unicode=True, sort_keys=False), encoding="utf-8")
        yaml_paths.append(path)
        candidates.append(item)

    payload = dict(manifest)
    payload["candidates"] = candidates
    json_path = output_path / "entry_factor_validation_manifest.json"
    markdown_path = output_path / "entry_factor_validation_manifest.zh.md"
    json_path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_factor_validation_manifest_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, tuple(yaml_paths)


def safe_entry_factor_validation_manifest_dir_name(discovery_path: str | Path) -> str:
    path = Path(discovery_path)
    stem = path.parent.name if path.name == "bayesian_factor_discovery.json" and path.parent.name else path.stem
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem.strip())
    return f"entry-factor-validation-manifest-{safe or 'discovery'}"


def _selected_candidates(
    discovery: Mapping[str, Any],
    *,
    positive_limit: int,
    negative_limit: int,
) -> list[dict[str, Any]]:
    rankings = _as_mapping(_as_mapping(discovery.get("rankings")).get("tradable_pre_entry"))
    selected: list[dict[str, Any]] = []
    selected.extend(
        _candidate_row(candidate, direction="positive", action="keep", candidate_rank=rank)
        for rank, candidate in _safe_ranked_candidates(rankings.get("positive"), limit=positive_limit)
    )
    selected.extend(
        _candidate_row(candidate, direction="negative", action="exclude", candidate_rank=rank)
        for rank, candidate in _safe_ranked_candidates(rankings.get("negative"), limit=negative_limit)
    )
    return selected


def _safe_ranked_candidates(candidates: object, *, limit: int) -> list[tuple[int, object]]:
    if limit <= 0:
        return []
    safe: list[tuple[int, object]] = []
    for rank, candidate in enumerate(_as_sequence(candidates), start=1):
        if not _candidate_is_safe(candidate):
            continue
        safe.append((rank, candidate))
        if len(safe) >= limit:
            break
    return safe


def _candidate_row(candidate: object, *, direction: str, action: str, candidate_rank: int) -> dict[str, Any]:
    row = dict(_as_mapping(candidate))
    row["direction"] = direction
    row["action"] = action
    row["candidate_rank"] = candidate_rank
    row["view"] = "tradable_pre_entry"
    return row


def _candidate_is_safe(candidate: object) -> bool:
    row = _as_mapping(candidate)
    field_key = str(row.get("field_key") or "")
    guard = _as_mapping(row.get("future_function_guard"))
    if guard and guard.get("eligible_for_entry_rule_review") is not True:
        return False
    if _is_future_field(field_key):
        return False
    if field_key not in entry_attribution_declaration_by_key():
        return False
    return bool(field_key)


def _manifest_candidate(
    candidate: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
    base_run_id: str,
    sequence: int,
    reuse_snapshots: bool,
    missing_policy: str,
) -> dict[str, Any]:
    field_key = str(candidate.get("field_key") or "")
    value = candidate.get("value")
    action = str(candidate.get("action") or "")
    direction = str(candidate.get("direction") or "")
    rank = int(candidate.get("candidate_rank") or sequence)
    run_id = _variant_run_id(
        base_run_id,
        direction=direction,
        rank=rank,
        field_key=field_key,
        value=value,
    )
    run_plan = _variant_run_plan(
        baseline,
        run_id=run_id,
        field_key=field_key,
        value=value,
        action=action,
        reuse_snapshots=reuse_snapshots,
        missing_policy=missing_policy,
    )
    RunPlan.from_mapping(run_plan)
    return {
        "candidate_index": sequence,
        "candidate_rank": rank,
        "view": candidate.get("view"),
        "direction": direction,
        "action": action,
        "field_key": field_key,
        "field_label_zh": candidate.get("field_label_zh"),
        "value": value,
        "value_label_zh": candidate.get("value_label_zh") or str(value),
        "factor_quality_score": candidate.get("factor_quality_score"),
        "sample_count": candidate.get("sample_count"),
        "flags": list(_as_sequence(candidate.get("flags"))),
        "source_candidate": _jsonable(candidate),
        "filter_condition": {
            "field": field_key,
            "operator": "eq",
            "value": value,
            "action": action,
        },
        "run_id": run_id,
        "run_plan": run_plan,
        "run_plan_path": None,
    }


def _variant_run_plan(
    baseline: Mapping[str, Any],
    *,
    run_id: str,
    field_key: str,
    value: Any,
    action: str,
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
        "conditions": [
            {
                "field": field_key,
                "operator": "eq",
                "value": value,
                "action": action,
            }
        ],
        "missing_policy": missing_policy,
    }
    _ensure_factor_selected(run_plan, field_key)
    return _jsonable(run_plan)


def _ensure_factor_selected(run_plan: dict[str, Any], field_key: str) -> None:
    analysis = _as_mapping(run_plan.get("analysis"))
    attribution = analysis.get("attribution")
    if isinstance(attribution, dict) and attribution.get("include"):
        attribution["include"] = _append_unique(attribution.get("include"), field_key)
        return
    entry_attribution = analysis.get("entry_attribution")
    if isinstance(entry_attribution, dict) and entry_attribution.get("factors"):
        entry_attribution["factors"] = _append_unique(entry_attribution.get("factors"), field_key)


def _append_unique(values: object, value: str) -> list[Any]:
    result = list(_as_sequence(values))
    if value not in result:
        result.append(value)
    return result


def _variant_run_id(base_run_id: str, *, direction: str, rank: int, field_key: str, value: Any) -> str:
    direction_code = "pos" if direction == "positive" else "neg"
    suffix = "-".join(
        part
        for part in (
            "efv",
            f"{direction_code}{rank:03d}",
            _slug(field_key, max_len=42),
            _slug(value, max_len=24),
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


def _is_future_field(field_key: str) -> bool:
    key = field_key.lower()
    if key.startswith(("trade.", "exit.", "post_exit.", "entry_to_exit.", "sizing.", "execution.", "portfolio.")):
        return True
    return any(
        token in key
        for token in (
            ".exit_",
            ".exit.",
            "exit_stage",
            "entry_to_exit",
            "post_exit",
            "sold_too_early",
            "stop_loss_rebound",
        )
    )


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _escape_cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _format_number(value: object) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return ""
