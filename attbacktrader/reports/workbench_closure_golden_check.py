"""Deterministic golden checks for Backtest Workbench V1 closure docs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .workbench_closure import DEFAULT_BASELINE_PATH, DEFAULT_CLOSURE_DOC_PATH, WORKBENCH_CLOSURE_SCHEMA


WORKBENCH_CLOSURE_GOLDEN_CHECK_SCHEMA = "attbacktrader.workbench_closure_golden_check.v1"

DEFAULT_WORKBENCH_CLOSURE_GOLDEN_CHECK_OUTPUT_DIR = Path("reports/workbench-closure-golden-check")


def build_workbench_closure_golden_check(
    *,
    baseline: Mapping[str, Any] | str | Path = DEFAULT_BASELINE_PATH,
    closure_doc: str | Path = DEFAULT_CLOSURE_DOC_PATH,
) -> dict[str, Any]:
    """Check that the closure Markdown still reflects the baseline contract."""

    baseline_payload, baseline_path = _load_baseline(baseline)
    doc_path = Path(closure_doc)
    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
    checks: list[dict[str, Any]] = []

    _add_check(
        checks,
        check_id="baseline.schema",
        category="baseline",
        ok=baseline_payload.get("schema") == WORKBENCH_CLOSURE_SCHEMA,
        expected_zh=f"baseline schema 必须是 {WORKBENCH_CLOSURE_SCHEMA}",
        actual_zh=f"actual={baseline_payload.get('schema')}",
        expected_value=WORKBENCH_CLOSURE_SCHEMA,
        actual_value=baseline_payload.get("schema"),
    )
    _add_check(
        checks,
        check_id="closure_doc.exists",
        category="source",
        ok=doc_path.exists(),
        expected_zh="closure Markdown 必须存在。",
        actual_zh=str(doc_path),
        expected_value=True,
        actual_value=doc_path.exists(),
    )
    _check_verification(checks, baseline_payload, doc_text)
    _check_navigation_state(checks, baseline_payload, doc_text)
    _check_commands(checks, baseline_payload, doc_text)
    _check_artifact_groups(checks, baseline_payload, doc_text)
    _check_non_goals(checks, baseline_payload, doc_text)
    _check_ai_read_order(checks, baseline_payload, doc_text)
    _check_next_allowed_slices(checks, baseline_payload, doc_text)
    _check_rules(checks, baseline_payload, doc_text)

    failed = [check for check in checks if check["status"] == "failed"]
    return {
        "schema": WORKBENCH_CLOSURE_GOLDEN_CHECK_SCHEMA,
        "status": "ok" if not failed else "failed",
        "golden_for": "Backtest Workbench V1 closure",
        "source_baseline": _source_ref(baseline_path, payload=baseline_payload),
        "source_closure_doc": _text_source_ref(doc_path, doc_text),
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "checks": checks,
        "rules": [
            "Workbench Closure Golden Check 只校验 closure 文档是否忠实投影 baseline，不评价策略收益。",
            "baseline 中的 accepted commands、artifact groups、non-goals、verification 和 AI read order 必须在 Markdown 中出现。",
            "AI first read order 必须保持顺序，不能只检查存在性。",
            "失败时先重新生成 closure snapshot 或修正文档，再继续下一阶段。",
        ],
    }


def render_workbench_closure_golden_check_markdown_zh(check: Mapping[str, Any]) -> str:
    """Render the Workbench closure golden check as Chinese Markdown."""

    lines = [
        "# Workbench Closure Golden Check",
        "",
        f"- schema: `{check.get('schema')}`",
        f"- status: `{check.get('status')}`",
        f"- golden_for: {check.get('golden_for')}",
        f"- check_count: `{check.get('check_count')}`",
        f"- failed_count: `{check.get('failed_count')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(check.get("rules")):
        lines.append(f"- {rule}")

    failures = [row for row in _as_sequence(check.get("checks")) if _as_mapping(row).get("status") == "failed"]
    lines.extend(["", "## 失败项", "", "| check_id | category | expected | actual |", "|---|---|---|---|"])
    if failures:
        for row in failures:
            row_map = _as_mapping(row)
            lines.append(
                "| "
                f"`{_markdown_value(row_map.get('check_id'))}` | "
                f"{_markdown_value(row_map.get('category'))} | "
                f"{_markdown_value(row_map.get('expected_zh'))} | "
                f"{_markdown_value(row_map.get('actual_zh'))} |"
            )
    else:
        lines.append("| - | - | - | 无失败项 |")

    lines.extend(["", "## 全部检查", "", "| status | check_id | category | expected | actual |", "|---|---|---|---|---|"])
    for row in _as_sequence(check.get("checks")):
        row_map = _as_mapping(row)
        lines.append(
            "| "
            f"`{_markdown_value(row_map.get('status'))}` | "
            f"`{_markdown_value(row_map.get('check_id'))}` | "
            f"{_markdown_value(row_map.get('category'))} | "
            f"{_markdown_value(row_map.get('expected_zh'))} | "
            f"{_markdown_value(row_map.get('actual_zh'))} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_workbench_closure_golden_check(
    check: Mapping[str, Any],
    *,
    output_dir: str | Path = DEFAULT_WORKBENCH_CLOSURE_GOLDEN_CHECK_OUTPUT_DIR,
) -> tuple[Path, Path]:
    """Write Workbench closure golden check JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "workbench_closure_golden_check.json"
    markdown_path = output_path / "workbench_closure_golden_check.zh.md"
    json_path.write_text(_to_pretty_json(check), encoding="utf-8")
    markdown_path.write_text(render_workbench_closure_golden_check_markdown_zh(check), encoding="utf-8")
    return json_path, markdown_path


def safe_workbench_closure_golden_check_dir_name() -> str:
    return "workbench-closure-golden-check"


def _check_verification(checks: list[dict[str, Any]], baseline: Mapping[str, Any], doc_text: str) -> None:
    for key, value in _as_mapping(baseline.get("verification")).items():
        value_map = _as_mapping(value)
        _add_contains_check(
            checks,
            check_id=f"verification.{key}.command",
            category="verification",
            doc_text=doc_text,
            expected_value=value_map.get("command"),
            expected_zh=f"closure doc 必须包含 verification command: {key}",
        )
        _add_contains_check(
            checks,
            check_id=f"verification.{key}.expected",
            category="verification",
            doc_text=doc_text,
            expected_value=value_map.get("expected"),
            expected_zh=f"closure doc 必须包含 verification expected: {key}",
        )


def _check_navigation_state(checks: list[dict[str, Any]], baseline: Mapping[str, Any], doc_text: str) -> None:
    run_catalog = _as_mapping(baseline.get("run_catalog_summary"))
    lifecycle = _as_mapping(baseline.get("experiment_lifecycle_summary"))
    golden = _as_mapping(baseline.get("strategy_adaptation_golden_summary"))
    expected_fragments = [
        f"run_count={run_catalog.get('run_count')}",
        f"group_count={run_catalog.get('group_count')}",
        f"chain_count={lifecycle.get('chain_count')}",
        f"decision_gap={lifecycle.get('decision_gap_count')}",
        f"status={golden.get('status')}",
        f"failed={golden.get('failed_count')}",
    ]
    for index, fragment in enumerate(expected_fragments, start=1):
        _add_contains_check(
            checks,
            check_id=f"navigation.summary.{index}",
            category="navigation",
            doc_text=doc_text,
            expected_value=fragment,
            expected_zh="closure doc 必须包含 navigation summary 片段。",
        )


def _check_commands(checks: list[dict[str, Any]], baseline: Mapping[str, Any], doc_text: str) -> None:
    for command in _as_sequence(baseline.get("accepted_commands")):
        command_map = _as_mapping(command)
        command_text = command_map.get("command")
        _add_contains_check(
            checks,
            check_id=f"accepted_command.{_safe_id(command_text)}",
            category="accepted_commands",
            doc_text=doc_text,
            expected_value=command_text,
            expected_zh="closure doc 必须列出 accepted command。",
        )


def _check_artifact_groups(checks: list[dict[str, Any]], baseline: Mapping[str, Any], doc_text: str) -> None:
    for group in _as_sequence(baseline.get("accepted_artifact_groups")):
        group_map = _as_mapping(group)
        group_key = _safe_id(group_map.get("group") or group_map.get("group_label_zh"))
        _add_contains_check(
            checks,
            check_id=f"artifact_group.{group_key}.label",
            category="artifact_groups",
            doc_text=doc_text,
            expected_value=group_map.get("group_label_zh"),
            expected_zh="closure doc 必须包含 artifact group label。",
        )
        for artifact in _as_sequence(group_map.get("artifacts")):
            _add_contains_check(
                checks,
                check_id=f"artifact_group.{group_key}.{_safe_id(artifact)}",
                category="artifact_groups",
                doc_text=doc_text,
                expected_value=artifact,
                expected_zh="closure doc 必须包含 accepted artifact。",
            )


def _check_non_goals(checks: list[dict[str, Any]], baseline: Mapping[str, Any], doc_text: str) -> None:
    for index, non_goal in enumerate(_as_sequence(baseline.get("active_non_goals")), start=1):
        _add_contains_check(
            checks,
            check_id=f"non_goal.{index}",
            category="non_goals",
            doc_text=doc_text,
            expected_value=non_goal,
            expected_zh="closure doc 必须包含 active non-goal。",
        )


def _check_ai_read_order(checks: list[dict[str, Any]], baseline: Mapping[str, Any], doc_text: str) -> None:
    entries = [_as_mapping(entry) for entry in _as_sequence(baseline.get("ai_first_read_order"))]
    positions = []
    for entry in entries:
        artifact = entry.get("artifact")
        position = _find_markdown_value(doc_text, artifact)
        positions.append(position)
        _add_check(
            checks,
            check_id=f"ai_first_read_order.{entry.get('order')}.{_safe_id(artifact)}",
            category="ai_first_read_order",
            ok=position >= 0,
            expected_zh="closure doc 必须包含 AI first-read artifact。",
            actual_zh=f"position={position}",
            expected_value=artifact,
            actual_value=position,
        )
    present_positions = [position for position in positions if position >= 0]
    ordered = len(present_positions) == len(positions) and present_positions == sorted(present_positions)
    _add_check(
        checks,
        check_id="ai_first_read_order.sequence",
        category="ai_first_read_order",
        ok=ordered,
        expected_zh="AI first-read artifacts 必须按 baseline 顺序出现在 closure doc。",
        actual_zh=f"positions={positions}",
        expected_value=[entry.get("artifact") for entry in entries],
        actual_value=positions,
    )


def _check_next_allowed_slices(checks: list[dict[str, Any]], baseline: Mapping[str, Any], doc_text: str) -> None:
    for item in _as_sequence(baseline.get("next_allowed_slices")):
        item_map = _as_mapping(item)
        _add_contains_check(
            checks,
            check_id=f"next_allowed_slice.{_safe_id(item_map.get('name_zh'))}",
            category="next_allowed_slices",
            doc_text=doc_text,
            expected_value=item_map.get("name_zh"),
            expected_zh="closure doc 必须包含 next allowed slice。",
        )


def _check_rules(checks: list[dict[str, Any]], baseline: Mapping[str, Any], doc_text: str) -> None:
    for index, rule in enumerate(_as_sequence(baseline.get("rules")), start=1):
        _add_contains_check(
            checks,
            check_id=f"rule.{index}",
            category="rules",
            doc_text=doc_text,
            expected_value=rule,
            expected_zh="closure doc 必须包含 closure rule。",
        )


def _add_contains_check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    category: str,
    doc_text: str,
    expected_value: Any,
    expected_zh: str,
) -> None:
    expected_text = str(expected_value) if expected_value is not None else ""
    _add_check(
        checks,
        check_id=check_id,
        category=category,
        ok=bool(expected_text) and expected_text in doc_text,
        expected_zh=expected_zh,
        actual_zh="present" if expected_text and expected_text in doc_text else "missing",
        expected_value=expected_value,
        actual_value=expected_text in doc_text if expected_text else False,
    )


def _add_check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    category: str,
    ok: bool,
    expected_zh: str,
    actual_zh: str,
    expected_value: Any,
    actual_value: Any,
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "category": category,
            "status": "passed" if ok else "failed",
            "expected_zh": expected_zh,
            "actual_zh": actual_zh,
            "expected_value": expected_value,
            "actual_value": actual_value,
        }
    )


def _load_baseline(baseline: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(baseline, Mapping):
        return baseline, None
    path = Path(baseline)
    if not path.exists():
        return {}, path
    return _as_mapping(json.loads(path.read_text(encoding="utf-8"))), path


def _source_ref(path: Path | None, *, payload: Mapping[str, Any]) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": True, "schema": payload.get("schema")}
    return {
        "path": str(path),
        "exists": path.exists(),
        "schema": payload.get("schema") if payload else None,
    }


def _text_source_ref(path: Path, text: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": len(text.encode("utf-8")) if path.exists() else None,
    }


def _find_markdown_value(doc_text: str, value: Any) -> int:
    if value is None:
        return -1
    text = str(value)
    ticked = f"`{text}`"
    position = doc_text.find(ticked)
    if position >= 0:
        return position
    return doc_text.find(text)


def _safe_id(value: Any) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in str(value or "").lower())
    return "_".join(part for part in safe.split("_") if part) or "unknown"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return ()


def _markdown_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|")


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
