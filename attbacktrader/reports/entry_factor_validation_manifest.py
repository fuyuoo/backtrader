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
_KEEP_CANDIDATES = "keep_candidates"
_EXCLUDE_CANDIDATES = "exclude_candidates"
_KEEP_WATCHLIST = "keep_watchlist"
_EXCLUDE_WATCHLIST = "exclude_watchlist"
_EXPOSURE_WATCHLIST = "exposure_watchlist"
_SCREENING_CATEGORY_ORDER = (
    _KEEP_CANDIDATES,
    _EXCLUDE_CANDIDATES,
    _KEEP_WATCHLIST,
    _EXCLUDE_WATCHLIST,
    _EXPOSURE_WATCHLIST,
)


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
        "source_mode": "bayesian_factor_discovery",
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
        "skipped_candidates": [],
        "skipped_count": 0,
        "rules": [
            "只读取 Bayesian Factor Discovery 的 tradable_pre_entry positive/negative 排名。",
            "positive 候选生成 keep 条件；negative 候选生成 exclude 条件。",
            "每个候选只生成一个单因子 RunPlan，不能在 Stage 1 叠加多因子。",
            "每个候选必须是运行时 EntryAttribution 已声明的可执行字段；仅存在于 wide sample/environment_fit 的诊断字段不进入真实验证。",
            "lifecycle_diagnostic、trade.path、exit、post_exit、entry_to_exit、sizing 等字段不得进入入场验证 manifest。",
            "生成的 RunPlan 已通过 RunPlan.from_mapping 校验；执行前仍需人工确认数据范围和运行成本。",
        ],
    }


def build_entry_factor_validation_manifest_from_screening(
    screening_or_path: Mapping[str, Any] | str | Path,
    baseline_run_plan_or_path: Mapping[str, Any] | str | Path,
    *,
    positive_limit: int | None = None,
    negative_limit: int | None = None,
    include_watchlist: bool = False,
    include_exposure_watchlist: bool = False,
    reuse_snapshots: bool = True,
    missing_policy: str = "block",
) -> dict[str, Any]:
    """Build legal RunPlan variants from entry single-factor candidate screening."""

    _validate_optional_limit("positive_limit", positive_limit)
    _validate_optional_limit("negative_limit", negative_limit)
    if missing_policy not in {"block", "pass"}:
        raise ValueError("missing_policy must be block or pass")

    screening, screening_path = _load_json_mapping(screening_or_path)
    baseline, baseline_path = _load_run_plan_mapping(baseline_run_plan_or_path)
    base_plan = RunPlan.from_mapping(baseline)
    selected, skipped = _selected_screening_candidates(
        screening,
        positive_limit=positive_limit,
        negative_limit=negative_limit,
        include_watchlist=include_watchlist,
        include_exposure_watchlist=include_exposure_watchlist,
    )
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
        "source_mode": "entry_single_factor_candidate_screening",
        "source_entry_single_factor_candidate_screening": str(screening_path) if screening_path is not None else None,
        "source_screening_run_id": screening.get("run_id"),
        "source_baseline_run_plan": str(baseline_path) if baseline_path is not None else None,
        "base_run_id": base_plan.run.id,
        "positive_limit": positive_limit,
        "negative_limit": negative_limit,
        "include_watchlist": include_watchlist,
        "include_exposure_watchlist": include_exposure_watchlist,
        "reuse_snapshots": reuse_snapshots,
        "missing_policy": missing_policy,
        "category_counts": dict(_as_mapping(screening.get("category_counts"))),
        "generated_count": len(candidates),
        "skipped_count": len(skipped),
        "candidates": candidates,
        "skipped_candidates": skipped,
        "rules": [
            "默认只读取 entry_single_factor_candidate_screening 的 keep_candidates/exclude_candidates。",
            "keep_candidates 生成 keep 条件；exclude_candidates 生成 exclude 条件。",
            "keep_watchlist/exclude_watchlist 默认不生成 RunPlan，必须显式 include_watchlist。",
            "exposure_watchlist 默认不生成 RunPlan，必须显式 include_exposure_watchlist。",
            "entry.execution 入场执行因子只要是正式 keep/exclude 候选且已声明为 entry 可执行字段，就可以进入验证。",
            "future/lifecycle/exit/post_exit/entry_to_exit/sizing/metadata 字段在回测前被拒绝。",
            "生成的 RunPlan 已通过 RunPlan.from_mapping 校验；执行前仍需人工确认数据范围和运行成本。",
        ],
    }


def render_entry_factor_validation_manifest_markdown_zh(manifest: Mapping[str, Any]) -> str:
    """Render the entry factor validation manifest in Chinese Markdown."""

    source_run_id = manifest.get("source_discovery_run_id") or manifest.get("source_screening_run_id")
    lines = [
        "# 入场单因子验证 Manifest",
        "",
        f"- schema: `{manifest.get('schema')}`",
        f"- base_run_id: `{manifest.get('base_run_id')}`",
        f"- source_mode: `{manifest.get('source_mode')}`",
        f"- source_run_id: `{source_run_id}`",
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
    source_names = {"bayesian_factor_discovery.json", "entry_single_factor_candidate_screening.json"}
    stem = path.parent.name if path.name in source_names and path.parent.name else path.stem
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
    return _candidate_safety_issue(candidate) is None


def _candidate_safety_issue(candidate: object) -> str | None:
    row = _as_mapping(candidate)
    field_key = str(row.get("field_key") or "")
    guard = _as_mapping(row.get("future_function_guard"))
    if guard and guard.get("eligible_for_entry_rule_review") is not True:
        return "future_guard_not_entry_eligible"
    if _is_future_field(field_key):
        return "future_or_lifecycle_field"
    if field_key not in entry_attribution_declaration_by_key():
        return "unsafe_or_unknown_entry_factor"
    if not field_key:
        return "missing_field_key"
    return None


def _selected_screening_candidates(
    screening: Mapping[str, Any],
    *,
    positive_limit: int | None,
    negative_limit: int | None,
    include_watchlist: bool,
    include_exposure_watchlist: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    selected_by_direction = {"positive": 0, "negative": 0}
    limits = {"positive": positive_limit, "negative": negative_limit}

    for category in _SCREENING_CATEGORY_ORDER:
        for category_rank, raw_row in enumerate(_as_sequence(screening.get(category)), start=1):
            row = dict(_as_mapping(raw_row))
            direction, action = _screening_manifest_direction_action(category, row)
            skip_reason = _screening_category_skip_reason(
                category,
                include_watchlist=include_watchlist,
                include_exposure_watchlist=include_exposure_watchlist,
            )
            if skip_reason is not None:
                skipped.append(
                    _screening_skip_row(
                        row,
                        category=category,
                        category_rank=category_rank,
                        direction=direction,
                        action=action,
                        reasons=(skip_reason,),
                    )
                )
                continue

            if direction is None or action is None:
                skipped.append(
                    _screening_skip_row(
                        row,
                        category=category,
                        category_rank=category_rank,
                        direction=direction,
                        action=action,
                        reasons=("missing_screening_direction",),
                    )
                )
                continue

            safety_issue = _candidate_safety_issue(row)
            if safety_issue is not None:
                skipped.append(
                    _screening_skip_row(
                        row,
                        category=category,
                        category_rank=category_rank,
                        direction=direction,
                        action=action,
                        reasons=("unsafe_or_unknown_entry_factor", safety_issue),
                    )
                )
                continue

            limit = limits[direction]
            if limit is not None and selected_by_direction[direction] >= limit:
                skipped.append(
                    _screening_skip_row(
                        row,
                        category=category,
                        category_rank=category_rank,
                        direction=direction,
                        action=action,
                        reasons=(f"{direction}_limit_reached",),
                    )
                )
                continue

            selected_by_direction[direction] += 1
            selected.append(
                _screening_candidate_row(
                    row,
                    category=category,
                    category_rank=category_rank,
                    direction=direction,
                    action=action,
                    candidate_rank=selected_by_direction[direction],
                )
            )

    return selected, skipped


def _screening_category_skip_reason(
    category: str,
    *,
    include_watchlist: bool,
    include_exposure_watchlist: bool,
) -> str | None:
    if category in {_KEEP_WATCHLIST, _EXCLUDE_WATCHLIST} and not include_watchlist:
        return "watchlist_excluded_by_default"
    if category == _EXPOSURE_WATCHLIST and not include_exposure_watchlist:
        return "exposure_watchlist_excluded_by_default"
    return None


def _screening_manifest_direction_action(
    category: str,
    row: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    if category in {_KEEP_CANDIDATES, _KEEP_WATCHLIST}:
        return "positive", "keep"
    if category in {_EXCLUDE_CANDIDATES, _EXCLUDE_WATCHLIST}:
        return "negative", "exclude"

    row_direction = str(row.get("direction") or "").lower()
    if row_direction in {"keep", "positive"}:
        return "positive", "keep"
    if row_direction in {"exclude", "negative"}:
        return "negative", "exclude"
    return None, None


def _screening_candidate_row(
    row: Mapping[str, Any],
    *,
    category: str,
    category_rank: int,
    direction: str,
    action: str,
    candidate_rank: int,
) -> dict[str, Any]:
    result = dict(row)
    result["primary_category"] = result.get("primary_category") or category
    result["source_category"] = category
    result["category_rank"] = category_rank
    result["screening_direction"] = result.get("direction")
    result["direction"] = direction
    result["action"] = action
    result["candidate_rank"] = candidate_rank
    result["view"] = "entry_single_factor_candidate_screening"
    return result


def _screening_skip_row(
    row: Mapping[str, Any],
    *,
    category: str,
    category_rank: int,
    direction: str | None,
    action: str | None,
    reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "source_category": category,
        "primary_category": row.get("primary_category") or category,
        "category_rank": category_rank,
        "direction": direction,
        "action": action,
        "screening_direction": row.get("direction"),
        "factor_kind": row.get("factor_kind"),
        "field_key": row.get("field_key"),
        "value": row.get("value"),
        "value_label_zh": row.get("value_label_zh"),
        "sample_count": row.get("sample_count"),
        "skip_reasons": sorted(set(str(reason) for reason in reasons)),
        "source_candidate": _jsonable(row),
    }


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
        "source_category": candidate.get("source_category"),
        "primary_category": candidate.get("primary_category"),
        "direction": direction,
        "action": action,
        "factor_kind": candidate.get("factor_kind"),
        "field_key": field_key,
        "field_label_zh": candidate.get("field_label_zh"),
        "value": value,
        "value_label_zh": candidate.get("value_label_zh") or str(value),
        "factor_quality_score": candidate.get("factor_quality_score"),
        "sample_count": candidate.get("sample_count"),
        "win_rate": candidate.get("win_rate"),
        "average_return_pct": candidate.get("average_return_pct"),
        "median_return_pct": candidate.get("median_return_pct"),
        "return_on_entry_value": candidate.get("return_on_entry_value"),
        "profit_loss_ratio": candidate.get("profit_loss_ratio"),
        "ma60_stop_exit_rate": candidate.get("ma60_stop_exit_rate"),
        "candidate_source": candidate.get("candidate_source"),
        "category_reasons": list(_as_sequence(candidate.get("category_reasons"))),
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


def _validate_optional_limit(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be greater than or equal to 0")


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
