"""Run catalog helpers for AI-first backtest workbench navigation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


RUN_CATALOG_SCHEMA = "attbacktrader.run_catalog.v1"

_ARTIFACT_SPECS: tuple[dict[str, Any], ...] = (
    {"artifact": "run_plan", "filename": "run_plan.json", "required": True},
    {"artifact": "report", "filename": "report.json", "required": True},
    {"artifact": "evidence_validation", "filename": "evidence_validation.json", "required": True},
    {"artifact": "trades", "filename": "trades.json", "required": True},
    {"artifact": "signal_audit", "filename": "signal_audit.json", "required": True},
    {"artifact": "sizing_audit", "filename": "sizing_audit.json", "required": False},
    {"artifact": "execution_audit", "filename": "execution_audit.json", "required": True},
    {"artifact": "trade_lifecycle", "filename": "trade_lifecycle.json", "required": True},
    {"artifact": "trade_review", "filename": "trade_review.json", "required": True},
    {"artifact": "post_exit_analysis", "filename": "post_exit_analysis.json", "required": True},
    {"artifact": "run_data_dictionary", "filename": "run_data_dictionary.json", "required": False},
    {"artifact": "run_data_overview", "filename": "run_data_overview.json", "required": False},
    {"artifact": "run_data_attribution_index", "filename": "run_data_attribution_index.json", "required": False},
    {"artifact": "run_data_attribution_summary", "filename": "run_data_attribution_summary.json", "required": False},
    {"artifact": "review_packet_all", "filename": "review_packet.all.json", "required": False},
    {"artifact": "review_brief_all", "filename": "review_brief.all.json", "required": False},
    {"artifact": "ai_review_result_all", "filename": "ai_review_result.all.json", "required": False},
)

_ROLE_LABELS_ZH = {
    "market_segment_baseline": "市场段基线 run",
    "strategy_variant_segment": "策略变体市场段 run",
    "experiment_run": "实验 run",
    "smoke_run": "冒烟 run",
    "single_run": "普通 run",
    "manifest_only": "manifest 已知但 artifact 缺失",
}


def build_run_catalog(
    *,
    report_root: str | Path = "reports",
    manifests: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Build a catalog of persisted run artifacts and manifest-known runs."""

    report_root_path = Path(report_root)
    manifest_context = _load_manifest_context(manifests)
    discovered_run_ids = _discover_report_run_ids(report_root_path)
    known_run_ids = sorted(discovered_run_ids | set(manifest_context["run_refs"]))

    runs = [
        _run_catalog_row(
            run_id,
            report_root=report_root_path,
            manifest_ref=_as_mapping(manifest_context["run_refs"].get(run_id)),
        )
        for run_id in known_run_ids
    ]
    status_counts = Counter(str(_as_mapping(row.get("evidence_validation")).get("status")) for row in runs)
    role_counts = Counter(str(row.get("role")) for row in runs)
    missing_required_count = sum(1 for row in runs if _as_sequence(row.get("missing_required_artifacts")))
    missing_run_dir_count = sum(1 for row in runs if not row.get("source_dir_exists"))
    return {
        "schema": RUN_CATALOG_SCHEMA,
        "report_root": str(report_root_path),
        "source_manifests": manifest_context["source_manifests"],
        "run_count": len(runs),
        "group_count": len(manifest_context["comparison_groups"]),
        "role_counts": _count_rows(role_counts),
        "evidence_status_counts": _count_rows(status_counts),
        "missing_required_artifact_run_count": missing_required_count,
        "missing_run_dir_count": missing_run_dir_count,
        "runs": runs,
        "comparison_groups": manifest_context["comparison_groups"],
        "ai_entrypoints": _ai_entrypoints(),
        "rules": [
            "Run Catalog 只索引已落盘 artifacts 和 manifest 已知 run，不重跑回测。",
            "evidence_validation.status != ok 的 run 只能先修证据链，不能直接复盘结论。",
            "manifest 中存在但 report 目录缺失的 run 保留为 manifest_only 或缺失 artifact 记录。",
            "comparability 来自 manifest 或显式分组，不由收益表现自动推断。",
            "Catalog 是 AI 的第一入口；详细样本仍通过 run_data_overview、dictionary、drilldown 和 review_packet 下钻。",
        ],
    }


def render_run_catalog_markdown_zh(catalog: Mapping[str, Any]) -> str:
    """Render run catalog as Chinese Markdown."""

    lines = [
        "# 回测 Run Catalog",
        "",
        f"- schema: `{catalog.get('schema')}`",
        f"- report_root: `{catalog.get('report_root')}`",
        f"- run_count: `{catalog.get('run_count')}`",
        f"- group_count: `{catalog.get('group_count')}`",
        f"- missing_required_artifact_run_count: `{catalog.get('missing_required_artifact_run_count')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(catalog.get("rules")):
        lines.append(f"- {rule}")

    lines.extend(["", "## 角色分布", "", "| role | label | count |", "|---|---|---:|"])
    for row in _as_sequence(catalog.get("role_counts")):
        row_map = _as_mapping(row)
        role = str(row_map.get("key"))
        lines.append(f"| `{role}` | {_ROLE_LABELS_ZH.get(role, role)} | {row_map.get('count')} |")

    lines.extend(["", "## 证据状态", "", "| status | count |", "|---|---:|"])
    for row in _as_sequence(catalog.get("evidence_status_counts")):
        row_map = _as_mapping(row)
        lines.append(f"| `{row_map.get('key')}` | {row_map.get('count')} |")

    lines.extend(
        [
            "",
            "## Runs",
            "",
            "| role | run_id | validation | return | max_drawdown | trades | artifacts missing | group |",
            "|---|---|---|---:|---:|---:|---|---|",
        ]
    )
    for row in _as_sequence(catalog.get("runs")):
        row_map = _as_mapping(row)
        metrics = _as_mapping(row_map.get("metrics"))
        validation = _as_mapping(row_map.get("evidence_validation"))
        missing = _as_sequence(row_map.get("missing_required_artifacts"))
        lines.append(
            "| "
            f"{_ROLE_LABELS_ZH.get(str(row_map.get('role')), row_map.get('role'))} | "
            f"`{row_map.get('run_id')}` | "
            f"`{validation.get('status')}` | "
            f"{_format_optional_percent(metrics.get('cumulative_return'))} | "
            f"{_format_optional_percent(metrics.get('max_drawdown'))} | "
            f"{_markdown_value(metrics.get('trade_count'))} | "
            f"{_markdown_value(', '.join(str(item) for item in missing) if missing else 'ok')} | "
            f"`{row_map.get('comparison_group_id')}` |"
        )

    lines.extend(["", "## 可比较分组", "", "| group_id | type | market_type | segment | baseline | variants |", "|---|---|---|---|---|---|"])
    for group in _as_sequence(catalog.get("comparison_groups")):
        group_map = _as_mapping(group)
        lines.append(
            "| "
            f"`{group_map.get('group_id')}` | "
            f"`{group_map.get('group_type')}` | "
            f"`{group_map.get('market_type_id')}` | "
            f"`{group_map.get('segment_id')}` | "
            f"`{group_map.get('baseline_run_id')}` | "
            f"{_markdown_value(', '.join(str(item) for item in _as_sequence(group_map.get('variant_run_ids'))))} |"
        )

    lines.extend(["", "## AI 入口", ""])
    for entry in _as_sequence(catalog.get("ai_entrypoints")):
        entry_map = _as_mapping(entry)
        lines.append(f"- {entry_map.get('purpose_zh')}: `{entry_map.get('command')}`")
    lines.append("")
    return "\n".join(lines)


def write_run_catalog(
    catalog: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write run catalog JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "run_catalog.json"
    markdown_path = output_path / "run_catalog.zh.md"
    json_path.write_text(_to_pretty_json(catalog), encoding="utf-8")
    markdown_path.write_text(render_run_catalog_markdown_zh(catalog), encoding="utf-8")
    return json_path, markdown_path


def safe_run_catalog_dir_name() -> str:
    return "run-catalog"


def _run_catalog_row(
    run_id: str,
    *,
    report_root: Path,
    manifest_ref: Mapping[str, Any],
) -> dict[str, Any]:
    run_dir = report_root / run_id
    artifacts = [_artifact_status(run_dir, spec) for spec in _ARTIFACT_SPECS]
    payloads = {
        "run_plan": _load_json_if_exists(run_dir / "run_plan.json"),
        "report": _load_json_if_exists(run_dir / "report.json"),
        "evidence_validation": _load_json_if_exists(run_dir / "evidence_validation.json"),
        "trades": _load_json_if_exists(run_dir / "trades.json"),
    }
    run_plan = _as_mapping(payloads.get("run_plan"))
    report = _as_mapping(payloads.get("report"))
    validation = _as_mapping(payloads.get("evidence_validation"))
    trades = _as_mapping(payloads.get("trades"))
    role = str(manifest_ref.get("role") or _infer_role(run_id, run_plan, run_dir.exists()))
    missing_required = [
        str(item["artifact"])
        for item in artifacts
        if item.get("required") and not item.get("exists")
    ]
    return {
        "run_id": _run_id(run_id, run_plan),
        "role": role,
        "role_label_zh": _ROLE_LABELS_ZH.get(role, role),
        "source_dir": str(run_dir),
        "source_dir_exists": run_dir.exists(),
        "manifest_ref": dict(manifest_ref),
        "comparison_group_id": manifest_ref.get("comparison_group_id"),
        "comparable_run_ids": sorted(str(item) for item in _as_sequence(manifest_ref.get("comparable_run_ids"))),
        "run": _run_summary(run_plan),
        "data": _data_summary(run_plan),
        "strategy": _strategy_summary(run_plan),
        "metrics": _metrics_summary(report, trades),
        "evidence_validation": {
            "status": validation.get("status") if validation else "missing",
            "error_count": validation.get("error_count") if validation else None,
            "warning_count": validation.get("warning_count") if validation else None,
        },
        "artifacts": artifacts,
        "present_artifact_count": sum(1 for item in artifacts if item.get("exists")),
        "missing_required_artifacts": missing_required,
        "ai_next_reads": _ai_next_reads(run_id),
    }


def _load_manifest_context(manifests: Sequence[str | Path]) -> dict[str, Any]:
    run_refs: dict[str, dict[str, Any]] = {}
    source_manifests = []
    comparison_groups: list[dict[str, Any]] = []
    seen_groups: set[str] = set()
    for manifest_path in manifests:
        path = Path(manifest_path)
        if not path.exists():
            source_manifests.append({"path": str(path), "exists": False, "schema": None})
            continue
        manifest = _as_mapping(_load_json_if_exists(path))
        schema = manifest.get("schema")
        source_manifests.append({"path": str(path), "exists": True, "schema": schema})
        segments = [_as_mapping(item) for item in _as_sequence(manifest.get("segments"))]
        is_variant_manifest = "strategy_variant_run_manifest" in str(schema) or any(
            segment.get("baseline_run_id") and segment.get("draft_id") for segment in segments
        )
        for segment in segments:
            segment_id = str(segment.get("segment_id") or "")
            market_type_id = str(segment.get("market_type_id") or "")
            group_id = f"{market_type_id}:{segment_id}" if market_type_id and segment_id else None
            if is_variant_manifest:
                variant_run_id = str(segment.get("run_id") or "")
                baseline_run_id = str(segment.get("baseline_run_id") or "")
                if baseline_run_id:
                    _merge_run_ref(
                        run_refs,
                        baseline_run_id,
                        {
                            "role": "market_segment_baseline",
                            "source_manifest": str(path),
                            "segment_id": segment_id,
                            "market_type_id": market_type_id,
                            "market_type_label_zh": segment.get("market_type_label_zh"),
                            "segment_label_zh": segment.get("segment_label_zh"),
                            "comparison_group_id": group_id,
                            "comparable_run_ids": [variant_run_id] if variant_run_id else [],
                        },
                    )
                if variant_run_id:
                    _merge_run_ref(
                        run_refs,
                        variant_run_id,
                        {
                            "role": "strategy_variant_segment",
                            "source_manifest": str(path),
                            "segment_id": segment_id,
                            "market_type_id": market_type_id,
                            "market_type_label_zh": segment.get("market_type_label_zh"),
                            "segment_label_zh": segment.get("segment_label_zh"),
                            "variant_draft_id": segment.get("draft_id"),
                            "baseline_run_id": baseline_run_id or None,
                            "comparison_group_id": group_id,
                            "comparable_run_ids": [baseline_run_id] if baseline_run_id else [],
                        },
                    )
                if group_id and group_id not in seen_groups:
                    seen_groups.add(group_id)
                    comparison_groups.append(
                        {
                            "group_id": group_id,
                            "group_type": "baseline_vs_strategy_variant",
                            "market_type_id": market_type_id,
                            "market_type_label_zh": segment.get("market_type_label_zh"),
                            "segment_id": segment_id,
                            "segment_label_zh": segment.get("segment_label_zh"),
                            "baseline_run_id": baseline_run_id or None,
                            "variant_run_ids": [variant_run_id] if variant_run_id else [],
                        }
                    )
            else:
                run_id = str(segment.get("run_id") or "")
                if run_id:
                    _merge_run_ref(
                        run_refs,
                        run_id,
                        {
                            "role": "market_segment_baseline",
                            "source_manifest": str(path),
                            "segment_id": segment_id,
                            "market_type_id": market_type_id,
                            "market_type_label_zh": segment.get("market_type_label_zh"),
                            "segment_label_zh": segment.get("segment_label_zh"),
                            "comparison_group_id": group_id,
                        },
                    )
    return {
        "source_manifests": source_manifests,
        "run_refs": run_refs,
        "comparison_groups": comparison_groups,
    }


def _merge_run_ref(target: dict[str, dict[str, Any]], run_id: str, ref: Mapping[str, Any]) -> None:
    if not run_id:
        return
    current = target.setdefault(run_id, {})
    for key, value in ref.items():
        if value in (None, "", []):
            continue
        if key == "comparable_run_ids":
            existing = set(str(item) for item in _as_sequence(current.get(key)))
            existing.update(str(item) for item in _as_sequence(value) if item)
            current[key] = sorted(existing)
        elif key not in current:
            current[key] = value


def _discover_report_run_ids(report_root: Path) -> set[str]:
    if not report_root.exists():
        return set()
    run_ids = set()
    for child in report_root.iterdir():
        if not child.is_dir():
            continue
        if (child / "run_plan.json").exists() or (child / "report.json").exists():
            run_ids.add(child.name)
    return run_ids


def _artifact_status(run_dir: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    path = run_dir / str(spec["filename"])
    return {
        "artifact": spec["artifact"],
        "filename": spec["filename"],
        "required": spec["required"],
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _infer_role(run_id: str, run_plan: Mapping[str, Any], source_dir_exists: bool) -> str:
    if not source_dir_exists:
        return "manifest_only"
    lowered = run_id.lower()
    if "__variant__" in lowered:
        return "strategy_variant_segment"
    if "market-segment" in lowered:
        return "market_segment_baseline"
    if "smoke" in lowered:
        return "smoke_run"
    strategy = _as_mapping(run_plan.get("strategy"))
    if any(token in lowered for token in ("expanded", "sized", "filter", "add-on")):
        return "experiment_run"
    if strategy.get("add_on_method") not in (None, "", "none"):
        return "experiment_run"
    return "single_run"


def _run_summary(run_plan: Mapping[str, Any]) -> dict[str, Any]:
    run = _as_mapping(run_plan.get("run"))
    return {
        "id": run.get("id"),
        "from_date": run.get("from_date"),
        "to_date": run.get("to_date"),
    }


def _data_summary(run_plan: Mapping[str, Any]) -> dict[str, Any]:
    data = _as_mapping(run_plan.get("data"))
    tradable_series = _as_sequence(data.get("tradable_series"))
    symbols = _as_sequence(data.get("symbols"))
    return {
        "provider": data.get("provider"),
        "price_adjustment": data.get("price_adjustment"),
        "symbol_count": len(symbols) if symbols else len(tradable_series),
        "symbols": list(symbols) if symbols else [item.get("symbol") for item in tradable_series if isinstance(item, Mapping)],
    }


def _strategy_summary(run_plan: Mapping[str, Any]) -> dict[str, Any]:
    strategy = _as_mapping(run_plan.get("strategy"))
    return {
        "template": strategy.get("template"),
        "entry_method": strategy.get("entry_method"),
        "profit_taking_method": strategy.get("profit_taking_method"),
        "stop_loss_method": strategy.get("stop_loss_method"),
        "add_on_method": strategy.get("add_on_method"),
        "sizing_rule": strategy.get("sizing_rule"),
    }


def _metrics_summary(report: Mapping[str, Any], trades: Mapping[str, Any]) -> dict[str, Any]:
    returns = _as_mapping(report.get("returns"))
    risk = _as_mapping(report.get("risk"))
    trade_quality = _as_mapping(report.get("trade_quality"))
    closed_trades = _as_sequence(trades.get("closed_trades"))
    return {
        "final_equity": returns.get("final_equity"),
        "cumulative_return": returns.get("cumulative_return"),
        "max_drawdown": risk.get("max_drawdown"),
        "trade_count": trade_quality.get("trade_count", len(closed_trades) if trades else None),
        "win_rate": trade_quality.get("win_rate"),
        "average_win": trade_quality.get("average_win"),
        "average_loss": trade_quality.get("average_loss"),
    }


def _ai_next_reads(run_id: str) -> list[dict[str, str]]:
    return [
        {
            "artifact": "run_data_overview",
            "command": f"att-run-data-overview --run-id {run_id}",
            "purpose_zh": "先看 run 是否可复盘、核心指标和证据状态。",
        },
        {
            "artifact": "run_data_dictionary",
            "command": f"att-run-data-dictionary --run-id {run_id}",
            "purpose_zh": "确认 artifact 和字段含义。",
        },
        {
            "artifact": "review_packet",
            "command": f"att-review-packet --run-dir reports/{run_id} --focus all",
            "purpose_zh": "生成 AI 复盘包。",
        },
    ]


def _ai_entrypoints() -> list[dict[str, str]]:
    return [
        {
            "purpose_zh": "查看单个 run 总览",
            "command": "att-run-data-overview --run-id <run_id>",
        },
        {
            "purpose_zh": "查看单个 run 数据字典",
            "command": "att-run-data-dictionary --run-id <run_id>",
        },
        {
            "purpose_zh": "生成 AI 复盘包",
            "command": "att-review-packet --run-dir reports/<run_id> --focus all",
        },
        {
            "purpose_zh": "比较多个 run",
            "command": "att-compare-runs --run-id <baseline> --run-id <experiment>",
        },
    ]


def _run_id(fallback: str, run_plan: Mapping[str, Any]) -> str:
    return str(_as_mapping(run_plan.get("run")).get("id") or fallback)


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _count_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"key": key, "count": count} for key, count in sorted(counter.items())]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return ()


def _format_optional_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value * 100:.2f}%"


def _markdown_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|")


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
