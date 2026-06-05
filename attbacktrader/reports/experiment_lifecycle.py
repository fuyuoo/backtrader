"""Experiment lifecycle helpers for AI-first backtest workbench closure."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPERIMENT_LIFECYCLE_SCHEMA = "attbacktrader.experiment_lifecycle.v1"

_STAGE_ORDER = {
    "candidate": 10,
    "draft": 20,
    "confirmed_run_plan": 30,
    "generated_run": 40,
    "executed_run": 50,
    "comparison": 60,
    "attribution": 70,
    "decision": 80,
}

_STAGE_LABELS_ZH = {
    "candidate": "候选",
    "draft": "草稿",
    "confirmed_run_plan": "确认 RunPlan",
    "generated_run": "生成 run",
    "executed_run": "已执行 run",
    "comparison": "比较/验证",
    "attribution": "归因下钻",
    "decision": "结论决策",
}

_LINEAGE_LABELS_ZH = {
    "review_experiment": "复盘实验",
    "strategy_variant": "策略变体",
    "generic_validation": "通用验证",
}


def build_experiment_lifecycle(
    *,
    candidates: Sequence[str | Path] = (),
    drafts: Sequence[str | Path] = (),
    confirmations: Sequence[str | Path] = (),
    variant_manifests: Sequence[str | Path] = (),
    validations: Sequence[str | Path] = (),
    attributions: Sequence[str | Path] = (),
    decisions: Sequence[str | Path] = (),
    run_catalog: str | Path | None = None,
) -> dict[str, Any]:
    """Build a lifecycle view over persisted experiment artifacts."""

    run_catalog_ref = _source_ref(run_catalog) if run_catalog is not None else None
    run_catalog_payload = _load_json_if_exists(Path(run_catalog)) if run_catalog is not None else None
    collector = _LifecycleCollector(_run_catalog_index(_as_mapping(run_catalog_payload)))
    source_artifacts: list[dict[str, Any]] = []

    for path in candidates:
        payload, ref = _load_source(path)
        source_artifacts.append(ref)
        collector.add_review_candidates(payload, ref)
    for path in drafts:
        payload, ref = _load_source(path)
        source_artifacts.append(ref)
        collector.add_drafts(payload, ref)
    for path in confirmations:
        payload, ref = _load_source(path)
        source_artifacts.append(ref)
        collector.add_review_confirmation(payload, ref)
    for path in variant_manifests:
        payload, ref = _load_source(path)
        source_artifacts.append(ref)
        collector.add_strategy_variant_manifest(payload, ref)
    for path in validations:
        payload, ref = _load_source(path)
        source_artifacts.append(ref)
        collector.add_validation(payload, ref)
    for path in attributions:
        payload, ref = _load_source(path)
        source_artifacts.append(ref)
        collector.add_attribution(payload, ref)
    for path in decisions:
        payload, ref = _load_source(path)
        source_artifacts.append(ref)
        collector.add_decisions(payload, ref)

    items = sorted(collector.items, key=_item_sort_key)
    chains = _build_chains(items)
    return {
        "schema": EXPERIMENT_LIFECYCLE_SCHEMA,
        "source_run_catalog": run_catalog_ref,
        "source_artifacts": source_artifacts,
        "item_count": len(items),
        "chain_count": len(chains),
        "lineage_counts": _count_rows(Counter(str(item.get("lineage_type")) for item in items)),
        "stage_counts": _count_rows(Counter(str(item.get("stage")) for item in items)),
        "status_counts": _count_rows(Counter(str(item.get("status")) for item in items)),
        "items": items,
        "chains": chains,
        "ai_entrypoints": _ai_entrypoints(),
        "rules": [
            "Experiment Lifecycle 只读取已落盘 artifact，不重跑回测、不重算指标。",
            "candidate/draft/confirmed/generated/executed/comparison/decision 是状态链，不是收益排序。",
            "executed_run 是否可复盘以 Run Catalog 的 evidence_validation 和缺失 artifact 为准。",
            "comparison 或 attribution 只能说明相对变化，不能自动确认 accepted/rejected。",
            "缺少 decision 时，下一步是记录 accepted / rejected / parked，而不是继续无边界调参。",
        ],
    }


def render_experiment_lifecycle_markdown_zh(lifecycle: Mapping[str, Any]) -> str:
    """Render experiment lifecycle as Chinese Markdown."""

    lines = [
        "# 实验 Lifecycle",
        "",
        f"- schema: `{lifecycle.get('schema')}`",
        f"- item_count: `{lifecycle.get('item_count')}`",
        f"- chain_count: `{lifecycle.get('chain_count')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(lifecycle.get("rules")):
        lines.append(f"- {rule}")

    lines.extend(["", "## 来源", "", "| artifact | exists | schema |", "|---|---:|---|"])
    source_run_catalog = _as_mapping(lifecycle.get("source_run_catalog"))
    if source_run_catalog:
        lines.append(
            "| "
            f"`{_markdown_value(source_run_catalog.get('path'))}` | "
            f"{_markdown_value(source_run_catalog.get('exists'))} | "
            f"`{_markdown_value(source_run_catalog.get('schema'))}` |"
        )
    for source in _as_sequence(lifecycle.get("source_artifacts")):
        source_map = _as_mapping(source)
        lines.append(
            "| "
            f"`{_markdown_value(source_map.get('path'))}` | "
            f"{_markdown_value(source_map.get('exists'))} | "
            f"`{_markdown_value(source_map.get('schema'))}` |"
        )

    lines.extend(["", "## 阶段分布", "", "| stage | label | count |", "|---|---|---:|"])
    for row in _as_sequence(lifecycle.get("stage_counts")):
        row_map = _as_mapping(row)
        stage = str(row_map.get("key"))
        lines.append(f"| `{stage}` | {_STAGE_LABELS_ZH.get(stage, stage)} | {row_map.get('count')} |")

    lines.extend(["", "## 状态分布", "", "| status | count |", "|---|---:|"])
    for row in _as_sequence(lifecycle.get("status_counts")):
        row_map = _as_mapping(row)
        lines.append(f"| `{row_map.get('key')}` | {row_map.get('count')} |")

    lines.extend(
        [
            "",
            "## 生命周期链",
            "",
            "| lineage | chain_id | current_stage | status | executed_runs | missing | next_action |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for chain in _as_sequence(lifecycle.get("chains")):
        chain_map = _as_mapping(chain)
        lineage_type = str(chain_map.get("lineage_type"))
        run_ids = ", ".join(str(item) for item in _as_sequence(chain_map.get("executed_run_ids")))
        missing = ", ".join(str(item) for item in _as_sequence(chain_map.get("missing_stages")))
        lines.append(
            "| "
            f"{_LINEAGE_LABELS_ZH.get(lineage_type, lineage_type)} | "
            f"`{_markdown_value(chain_map.get('chain_id'))}` | "
            f"{_STAGE_LABELS_ZH.get(str(chain_map.get('current_stage')), str(chain_map.get('current_stage')))} | "
            f"`{_markdown_value(chain_map.get('status'))}` | "
            f"{_markdown_value(run_ids)} | "
            f"{_markdown_value(missing or 'ok')} | "
            f"{_markdown_value(chain_map.get('next_action_zh'))} |"
        )

    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| stage | status | chain_id | title | run_id | source |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in _as_sequence(lifecycle.get("items")):
        item_map = _as_mapping(item)
        source = _as_mapping(item_map.get("source_artifact"))
        stage = str(item_map.get("stage"))
        lines.append(
            "| "
            f"{_STAGE_LABELS_ZH.get(stage, stage)} | "
            f"`{_markdown_value(item_map.get('status'))}` | "
            f"`{_markdown_value(item_map.get('chain_id'))}` | "
            f"{_markdown_value(item_map.get('title_zh'))} | "
            f"`{_markdown_value(item_map.get('run_id'))}` | "
            f"`{_markdown_value(source.get('path'))}` |"
        )

    lines.extend(["", "## AI 入口", ""])
    for entry in _as_sequence(lifecycle.get("ai_entrypoints")):
        entry_map = _as_mapping(entry)
        lines.append(f"- {entry_map.get('purpose_zh')}: `{entry_map.get('command')}`")
    lines.append("")
    return "\n".join(lines)


def write_experiment_lifecycle(
    lifecycle: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write experiment lifecycle JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "experiment_lifecycle.json"
    markdown_path = output_path / "experiment_lifecycle.zh.md"
    json_path.write_text(_to_pretty_json(lifecycle), encoding="utf-8")
    markdown_path.write_text(render_experiment_lifecycle_markdown_zh(lifecycle), encoding="utf-8")
    return json_path, markdown_path


def safe_experiment_lifecycle_dir_name() -> str:
    return "experiment-lifecycle"


class _LifecycleCollector:
    def __init__(self, run_catalog_index: Mapping[str, Mapping[str, Any]]) -> None:
        self.run_catalog_index = run_catalog_index
        self.items: list[dict[str, Any]] = []
        self.market_type_to_draft_id: dict[str, str] = {}
        self.market_type_to_title: dict[str, str] = {}

    def add_review_candidates(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        if not payload:
            return
        for candidate in _as_sequence(payload.get("candidates")):
            candidate_map = _as_mapping(candidate)
            candidate_id = str(candidate_map.get("candidate_id") or "")
            if not candidate_id:
                continue
            self.items.append(
                _base_item(
                    lineage_type="review_experiment",
                    chain_id=_review_chain_id(candidate_id),
                    stage="candidate",
                    status=str(candidate_map.get("status") or "candidate"),
                    source_ref=source_ref,
                    candidate_id=candidate_id,
                    title_zh=candidate_map.get("title_zh"),
                    purpose_zh=candidate_map.get("purpose_zh"),
                    validation_plan_zh=candidate_map.get("validation_plan_zh"),
                    evidence_refs=candidate_map.get("evidence_refs"),
                    sample_refs=candidate_map.get("sample_refs"),
                    linked_ids={"source_finding_id": candidate_map.get("source_finding_id")},
                    metrics=candidate_map.get("metrics"),
                )
            )

    def add_drafts(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        if not payload:
            return
        schema = str(payload.get("schema") or "")
        if "strategy_variant_drafts" in schema:
            self._add_strategy_variant_drafts(payload, source_ref)
        else:
            self._add_review_drafts(payload, source_ref)

    def add_review_confirmation(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        if not payload:
            return
        source_candidate_id = str(payload.get("source_candidate_id") or "")
        draft_id = str(payload.get("draft_id") or "")
        run_id = str(payload.get("run_id") or "")
        self.items.append(
            _base_item(
                lineage_type="review_experiment",
                chain_id=_review_chain_id(source_candidate_id or draft_id),
                stage="confirmed_run_plan",
                status=str(payload.get("status") or "confirmed_run_plan_generated"),
                source_ref=source_ref,
                candidate_id=source_candidate_id or None,
                draft_id=draft_id or None,
                run_id=run_id or None,
                title_zh=payload.get("title_zh") or draft_id,
                purpose_zh=payload.get("confirmation_note"),
                validation_plan_zh=_as_mapping(payload.get("legal_run_plan"))
                .get("analysis", {})
                .get("review_candidate", {}),
                linked_ids={"source_draft": payload.get("source_draft")},
            )
        )
        self._append_execution_item(
            lineage_type="review_experiment",
            chain_id=_review_chain_id(source_candidate_id or draft_id),
            source_ref=source_ref,
            run_id=run_id,
            title_zh=payload.get("title_zh") or draft_id,
            linked_ids={"source_candidate_id": source_candidate_id or None, "draft_id": draft_id or None},
        )

    def add_strategy_variant_manifest(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        if not payload:
            return
        for segment in _as_sequence(payload.get("segments")):
            segment_map = _as_mapping(segment)
            draft_id = str(segment_map.get("draft_id") or "")
            run_id = str(segment_map.get("run_id") or "")
            if not draft_id and not run_id:
                continue
            chain_id = _strategy_variant_chain_id(draft_id or run_id)
            title = _strategy_variant_title(segment_map)
            self.items.append(
                _base_item(
                    lineage_type="strategy_variant",
                    chain_id=chain_id,
                    stage="generated_run",
                    status="generated_run_plan",
                    source_ref=source_ref,
                    draft_id=draft_id or None,
                    run_id=run_id or None,
                    baseline_run_id=segment_map.get("baseline_run_id"),
                    market_type_id=segment_map.get("market_type_id"),
                    segment_id=segment_map.get("segment_id"),
                    title_zh=title,
                    purpose_zh=segment_map.get("adaptation_label_zh"),
                    linked_ids={
                        "run_plan_path": segment_map.get("run_plan_path"),
                        "baseline_run_plan_path": segment_map.get("baseline_run_plan_path"),
                    },
                    metrics={
                        "from_date": segment_map.get("from_date"),
                        "to_date": segment_map.get("to_date"),
                    },
                )
            )
            self._append_execution_item(
                lineage_type="strategy_variant",
                chain_id=chain_id,
                source_ref=source_ref,
                run_id=run_id,
                title_zh=title,
                baseline_run_id=segment_map.get("baseline_run_id"),
                market_type_id=segment_map.get("market_type_id"),
                segment_id=segment_map.get("segment_id"),
                linked_ids={"draft_id": draft_id or None},
            )

    def add_validation(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        if not payload:
            return
        schema = str(payload.get("schema") or "")
        if "strategy_variant_validation" in schema:
            for row in _as_sequence(payload.get("rows")):
                row_map = _as_mapping(row)
                market_type_id = str(row_map.get("market_type_id") or "")
                draft_id = self.market_type_to_draft_id.get(market_type_id, market_type_id)
                self.items.append(
                    _base_item(
                        lineage_type="strategy_variant",
                        chain_id=_strategy_variant_chain_id(draft_id),
                        stage="comparison",
                        status="compared",
                        source_ref=source_ref,
                        draft_id=draft_id or None,
                        market_type_id=market_type_id or None,
                        title_zh=self.market_type_to_title.get(market_type_id)
                        or f"{row_map.get('market_type_label_zh') or market_type_id} 变体验证",
                        purpose_zh=row_map.get("direction_zh"),
                        linked_ids={
                            "baseline_summary_path": payload.get("baseline_summary_path"),
                            "variant_summary_path": payload.get("variant_summary_path"),
                        },
                        metrics={"delta": row_map.get("delta")},
                    )
                )
        else:
            chain_id = f"generic_validation:{Path(str(source_ref.get('path') or 'validation')).stem}"
            self.items.append(
                _base_item(
                    lineage_type="generic_validation",
                    chain_id=chain_id,
                    stage="comparison",
                    status="compared",
                    source_ref=source_ref,
                    title_zh=str(payload.get("title_zh") or payload.get("schema") or "通用验证"),
                    metrics=_generic_validation_metrics(payload),
                )
            )

    def add_attribution(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        if not payload:
            return
        schema = str(payload.get("schema") or "")
        if "strategy_variant_attribution" not in schema:
            return
        market_type_id = str(payload.get("market_type_id") or "")
        draft_id = self.market_type_to_draft_id.get(market_type_id, market_type_id)
        self.items.append(
            _base_item(
                lineage_type="strategy_variant",
                chain_id=_strategy_variant_chain_id(draft_id),
                stage="attribution",
                status="attributed",
                source_ref=source_ref,
                draft_id=draft_id or None,
                market_type_id=market_type_id or None,
                title_zh=f"{payload.get('market_type_label_zh') or market_type_id} 变体归因",
                purpose_zh="解释 baseline 与 variant 的行为差异，不自动调参。",
                linked_ids={
                    "baseline_manifest_path": payload.get("baseline_manifest_path"),
                    "variant_manifest_path": payload.get("variant_manifest_path"),
                },
                metrics={
                    "segment_count": payload.get("segment_count"),
                    "overall_delta": _as_mapping(payload.get("overall")).get("delta"),
                },
            )
        )

    def add_decisions(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        if not payload:
            return
        for record in _as_sequence(payload.get("records")):
            record_map = _as_mapping(record)
            if record_map.get("status") != "recorded":
                continue
            chain_id = str(record_map.get("chain_id") or "")
            if not chain_id:
                continue
            chain_snapshot = _as_mapping(record_map.get("chain_snapshot"))
            self.items.append(
                _base_item(
                    lineage_type=str(chain_snapshot.get("lineage_type") or _infer_lineage_type_from_chain_id(chain_id)),
                    chain_id=chain_id,
                    stage="decision",
                    status=str(record_map.get("decision") or "decided"),
                    source_ref=source_ref,
                    title_zh=chain_snapshot.get("title_zh") or chain_id,
                    purpose_zh=record_map.get("reason_zh"),
                    evidence_refs=record_map.get("evidence_refs"),
                    linked_ids={
                        "decision_id": record_map.get("decision_id"),
                        "decided_on": record_map.get("decided_on"),
                        "decided_by": record_map.get("decided_by"),
                    },
                    metrics={"next_allowed_action_zh": record_map.get("next_allowed_action_zh")},
                )
            )

    def _add_review_drafts(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        for draft in _as_sequence(payload.get("drafts")):
            draft_map = _as_mapping(draft)
            source_candidate_id = str(draft_map.get("source_candidate_id") or "")
            draft_id = str(draft_map.get("draft_id") or "")
            if not source_candidate_id and not draft_id:
                continue
            self.items.append(
                _base_item(
                    lineage_type="review_experiment",
                    chain_id=_review_chain_id(source_candidate_id or draft_id),
                    stage="draft",
                    status=str(draft_map.get("status") or "draft_requires_manual_confirmation"),
                    source_ref=source_ref,
                    candidate_id=source_candidate_id or None,
                    draft_id=draft_id or None,
                    run_id=draft_map.get("suggested_run_id"),
                    title_zh=draft_map.get("title_zh"),
                    purpose_zh=draft_map.get("purpose_zh"),
                    validation_plan_zh=draft_map.get("validation_plan_zh"),
                    evidence_refs=draft_map.get("evidence_refs"),
                    sample_refs=draft_map.get("sample_refs"),
                    linked_ids={"base_config_path": draft_map.get("base_config_path")},
                    metrics={"candidate_type": draft_map.get("candidate_type")},
                )
            )

    def _add_strategy_variant_drafts(self, payload: Mapping[str, Any], source_ref: Mapping[str, Any]) -> None:
        for draft in _as_sequence(payload.get("drafts")):
            draft_map = _as_mapping(draft)
            draft_id = str(draft_map.get("draft_id") or "")
            market_type_id = str(draft_map.get("market_type_id") or "")
            if not draft_id:
                continue
            self.market_type_to_draft_id[market_type_id] = draft_id
            self.market_type_to_title[market_type_id] = str(draft_map.get("title_zh") or draft_id)
            self.items.append(
                _base_item(
                    lineage_type="strategy_variant",
                    chain_id=_strategy_variant_chain_id(draft_id),
                    stage="draft",
                    status=str(draft_map.get("status") or "draft_requires_manual_confirmation"),
                    source_ref=source_ref,
                    draft_id=draft_id,
                    run_id=draft_map.get("suggested_run_id"),
                    market_type_id=market_type_id or None,
                    title_zh=draft_map.get("title_zh"),
                    purpose_zh=draft_map.get("purpose_zh"),
                    validation_plan_zh=draft_map.get("validation_plan_zh"),
                    evidence_refs=_strategy_variant_evidence_refs(draft_map.get("evidence_factors")),
                    sample_refs=draft_map.get("sample_refs"),
                    linked_ids={"base_config_path": draft_map.get("base_config_path")},
                    metrics=draft_map.get("metrics"),
                )
            )

    def _append_execution_item(
        self,
        *,
        lineage_type: str,
        chain_id: str,
        source_ref: Mapping[str, Any],
        run_id: str,
        title_zh: Any,
        baseline_run_id: Any = None,
        market_type_id: Any = None,
        segment_id: Any = None,
        linked_ids: Mapping[str, Any] | None = None,
    ) -> None:
        if not run_id:
            return
        catalog_row = _as_mapping(self.run_catalog_index.get(str(run_id)))
        if not catalog_row or not catalog_row.get("source_dir_exists"):
            return
        validation = _as_mapping(catalog_row.get("evidence_validation"))
        missing_required = _as_sequence(catalog_row.get("missing_required_artifacts"))
        status = "executed_ok" if validation.get("status") == "ok" and not missing_required else "executed_with_evidence_issues"
        self.items.append(
            _base_item(
                lineage_type=lineage_type,
                chain_id=chain_id,
                stage="executed_run",
                status=status,
                source_ref=source_ref,
                run_id=run_id,
                baseline_run_id=baseline_run_id,
                market_type_id=market_type_id,
                segment_id=segment_id,
                title_zh=title_zh,
                linked_ids=linked_ids,
                run_catalog_ref=_run_catalog_ref(catalog_row),
                metrics=catalog_row.get("metrics"),
            )
        )


def _base_item(
    *,
    lineage_type: str,
    chain_id: str,
    stage: str,
    status: str,
    source_ref: Mapping[str, Any],
    candidate_id: Any = None,
    draft_id: Any = None,
    run_id: Any = None,
    baseline_run_id: Any = None,
    market_type_id: Any = None,
    segment_id: Any = None,
    title_zh: Any = None,
    purpose_zh: Any = None,
    validation_plan_zh: Any = None,
    evidence_refs: Any = None,
    sample_refs: Any = None,
    linked_ids: Mapping[str, Any] | None = None,
    run_catalog_ref: Mapping[str, Any] | None = None,
    metrics: Any = None,
) -> dict[str, Any]:
    return {
        "lineage_type": lineage_type,
        "chain_id": chain_id,
        "stage": stage,
        "status": status,
        "source_artifact": dict(source_ref),
        "candidate_id": candidate_id,
        "draft_id": draft_id,
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "market_type_id": market_type_id,
        "segment_id": segment_id,
        "title_zh": title_zh,
        "purpose_zh": purpose_zh,
        "validation_plan_zh": validation_plan_zh,
        "evidence_refs": list(_as_sequence(evidence_refs)),
        "sample_refs": list(_as_sequence(sample_refs)),
        "linked_ids": _compact_mapping(linked_ids or {}),
        "run_catalog_ref": dict(run_catalog_ref or {}),
        "metrics": metrics if metrics is not None else {},
    }


def _build_chains(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("chain_id") or ""), []).append(item)

    chains = []
    for chain_id, chain_items in grouped.items():
        sorted_items = sorted(chain_items, key=_item_sort_key)
        stages_present = []
        for item in sorted_items:
            stage = str(item.get("stage"))
            if stage not in stages_present:
                stages_present.append(stage)
        lineage_type = str(sorted_items[0].get("lineage_type") or "")
        current_stage = max(stages_present, key=lambda stage: _STAGE_ORDER.get(stage, 999), default="")
        status = _chain_status(stages_present)
        run_ids = sorted({str(item.get("run_id")) for item in sorted_items if item.get("run_id")})
        planned_run_ids = sorted(
            {
                str(item.get("run_id"))
                for item in sorted_items
                if item.get("run_id") and str(item.get("stage")) in {"draft", "confirmed_run_plan", "generated_run"}
            }
        )
        executed_run_ids = sorted(
            {str(item.get("run_id")) for item in sorted_items if item.get("run_id") and item.get("stage") == "executed_run"}
        )
        missing_stages = _missing_stages(lineage_type, stages_present)
        chains.append(
            {
                "chain_id": chain_id,
                "lineage_type": lineage_type,
                "lineage_label_zh": _LINEAGE_LABELS_ZH.get(lineage_type, lineage_type),
                "title_zh": _first_present(item.get("title_zh") for item in sorted_items),
                "current_stage": current_stage,
                "status": status,
                "stages_present": stages_present,
                "missing_stages": missing_stages,
                "run_ids": run_ids,
                "planned_run_ids": planned_run_ids,
                "executed_run_ids": executed_run_ids,
                "candidate_id": _first_present(item.get("candidate_id") for item in sorted_items),
                "draft_id": _first_present(item.get("draft_id") for item in sorted_items),
                "market_type_id": _first_present(item.get("market_type_id") for item in sorted_items),
                "next_action_zh": _next_action(lineage_type, stages_present, missing_stages),
            }
        )
    return sorted(chains, key=lambda chain: (str(chain.get("lineage_type")), str(chain.get("chain_id"))))


def _missing_stages(lineage_type: str, stages_present: Sequence[str]) -> list[str]:
    stage_set = set(stages_present)
    if lineage_type == "review_experiment":
        expected = ("candidate", "draft", "confirmed_run_plan", "executed_run", "comparison")
    elif lineage_type == "strategy_variant":
        expected = ("draft", "generated_run", "executed_run", "comparison")
    else:
        expected = ("comparison",)
    missing = [stage for stage in expected if stage not in stage_set]
    if ("comparison" in stage_set or "attribution" in stage_set) and "decision" not in stage_set:
        missing.append("decision")
    return missing


def _chain_status(stages_present: Sequence[str]) -> str:
    stage_set = set(stages_present)
    if "decision" in stage_set:
        return "decided"
    if "attribution" in stage_set:
        return "attributed"
    if "comparison" in stage_set:
        return "compared"
    if "executed_run" in stage_set:
        return "executed"
    if "generated_run" in stage_set:
        return "generated"
    if "confirmed_run_plan" in stage_set:
        return "confirmed"
    if "draft" in stage_set:
        return "drafted"
    return "candidate"


def _next_action(lineage_type: str, stages_present: Sequence[str], missing_stages: Sequence[str]) -> str:
    stage_set = set(stages_present)
    if "candidate" in missing_stages and lineage_type == "review_experiment":
        return "先从 findings 生成 candidate。"
    if "draft" in missing_stages:
        return "把 candidate 或矩阵结论整理成需要人工确认的 draft。"
    if "confirmed_run_plan" in missing_stages and lineage_type == "review_experiment":
        return "人工确认一个 draft，再生成合法 RunPlan。"
    if "generated_run" in missing_stages and lineage_type == "strategy_variant":
        return "把已确认的变体 draft 生成市场段 RunPlan。"
    if "executed_run" in missing_stages:
        return "执行对应 RunPlan，并先通过 evidence_validation。"
    if "comparison" in missing_stages:
        return "读取已执行 run，生成 comparison 或 market_type_summary validation。"
    if "decision" in missing_stages and ("comparison" in stage_set or "attribution" in stage_set):
        return "记录 accepted / rejected / parked 决策，防止继续无边界优化。"
    return "当前链路完整；只在新证据出现时继续。"


def _load_source(path: str | Path) -> tuple[Mapping[str, Any], dict[str, Any]]:
    source_path = Path(path)
    payload = _as_mapping(_load_json_if_exists(source_path))
    ref = _source_ref(source_path, payload=payload)
    return payload, ref


def _source_ref(path: str | Path | None, *, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "schema": None}
    source_path = Path(path)
    if payload is None:
        payload = _as_mapping(_load_json_if_exists(source_path))
    return {
        "path": str(source_path),
        "exists": source_path.exists(),
        "schema": payload.get("schema") if payload else None,
    }


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run_catalog_index(catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(row.get("run_id")): _as_mapping(row) for row in _as_sequence(catalog.get("runs")) if row}


def _run_catalog_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row.get("run_id"),
        "role": row.get("role"),
        "source_dir": row.get("source_dir"),
        "evidence_validation": row.get("evidence_validation"),
        "missing_required_artifacts": list(_as_sequence(row.get("missing_required_artifacts"))),
    }


def _review_chain_id(value: str) -> str:
    safe_value = value or "unknown"
    return f"review:{safe_value}"


def _strategy_variant_chain_id(value: str) -> str:
    safe_value = value or "unknown"
    return f"strategy_variant:{safe_value}"


def _infer_lineage_type_from_chain_id(chain_id: str) -> str:
    if chain_id.startswith("strategy_variant:"):
        return "strategy_variant"
    if chain_id.startswith("review:"):
        return "review_experiment"
    return "generic_validation"


def _strategy_variant_title(segment: Mapping[str, Any]) -> str:
    market_type = segment.get("market_type_label_zh") or segment.get("market_type_id")
    segment_label = segment.get("segment_label_zh") or segment.get("segment_id")
    draft_id = segment.get("draft_id")
    return f"{market_type} / {segment_label} / {draft_id}"


def _generic_validation_metrics(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_count": payload.get("run_count"),
        "row_count": len(_as_sequence(payload.get("rows"))),
        "status": payload.get("status"),
    }


def _strategy_variant_evidence_refs(evidence_factors: Any) -> list[dict[str, Any]]:
    refs = []
    for factor in _as_sequence(evidence_factors)[:5]:
        factor_map = _as_mapping(factor)
        refs.append(
            {
                "factor_key": factor_map.get("factor_key"),
                "factor_label_zh": factor_map.get("factor_label_zh"),
                "sample_count": factor_map.get("sample_count"),
                "win_rate": factor_map.get("win_rate"),
            }
        )
    return refs


def _ai_entrypoints() -> list[dict[str, str]]:
    return [
        {
            "purpose_zh": "查看生命周期总览",
            "command": "att-experiment-lifecycle",
        },
        {
            "purpose_zh": "查看 run 索引和证据状态",
            "command": "att-run-catalog",
        },
        {
            "purpose_zh": "记录 accepted/rejected/parked 实验决策",
            "command": "att-experiment-decisions",
        },
        {
            "purpose_zh": "从单个 run 下钻复盘包",
            "command": "att-review-packet --run-dir reports/<run_id> --focus all",
        },
        {
            "purpose_zh": "比较两个或多个已执行 run",
            "command": "att-compare-runs --run-id <baseline> --run-id <experiment>",
        },
    ]


def _item_sort_key(item: Mapping[str, Any]) -> tuple[str, str, int, str, str]:
    return (
        str(item.get("lineage_type") or ""),
        str(item.get("chain_id") or ""),
        _STAGE_ORDER.get(str(item.get("stage")), 999),
        str(item.get("segment_id") or ""),
        str(item.get("run_id") or ""),
    )


def _count_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"key": key, "count": count} for key, count in sorted(counter.items())]


def _compact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in mapping.items() if value not in (None, "", [], {})}


def _first_present(values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


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
