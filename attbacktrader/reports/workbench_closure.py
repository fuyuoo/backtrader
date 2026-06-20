"""Backtest Workbench V1 closure snapshot helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


WORKBENCH_CLOSURE_SCHEMA = "attbacktrader.backtest_workbench_v1_baseline.v1"

DEFAULT_BASELINE_PATH = Path("examples/backtest-workbench-v1-baseline.json")
DEFAULT_CLOSURE_DOC_PATH = Path("docs/backtest-workbench-v1-closure.md")


def build_workbench_closure_snapshot(
    *,
    sealed_on: str,
    source_branch: str = "autoBacktrader",
    mvp_base_commit: str = "d339bfc",
    strategy_adaptation_v1_commit: str = "8c63fdf",
    run_catalog: str | Path | None = "reports/run-catalog/run_catalog.json",
    experiment_lifecycle: str | Path | None = "reports/experiment-lifecycle/experiment_lifecycle.json",
    strategy_adaptation_golden_check: str | Path | None = "reports/strategy-adaptation-v1-ai-review-golden-check/ai_review_golden_check.json",
    accepted_verification: Mapping[str, Any] | None = None,
    sealed_docs: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Build a machine-readable Backtest Workbench V1 closure snapshot."""

    run_catalog_payload = _load_json_if_exists(Path(run_catalog)) if run_catalog is not None else None
    lifecycle_payload = _load_json_if_exists(Path(experiment_lifecycle)) if experiment_lifecycle is not None else None
    golden_payload = (
        _load_json_if_exists(Path(strategy_adaptation_golden_check))
        if strategy_adaptation_golden_check is not None
        else None
    )
    source_refs = {
        "run_catalog": _source_ref(run_catalog, payload=_as_mapping(run_catalog_payload)),
        "experiment_lifecycle": _source_ref(experiment_lifecycle, payload=_as_mapping(lifecycle_payload)),
        "strategy_adaptation_golden_check": _source_ref(
            strategy_adaptation_golden_check,
            payload=_as_mapping(golden_payload),
        ),
    }
    verification = dict(accepted_verification or _default_verification())
    sealed_doc_refs = [_file_ref(path) for path in (sealed_docs or _default_sealed_docs())]
    snapshot = {
        "schema": WORKBENCH_CLOSURE_SCHEMA,
        "sealed_on": sealed_on,
        "objective": (
            "Seal Backtest Workbench V1 as an AI-friendly evidence workbench: "
            "run, validate, index, review, compare, and close bounded experiment cycles "
            "from persisted artifacts."
        ),
        "source_branch": source_branch,
        "mvp_base_commit": mvp_base_commit,
        "strategy_adaptation_v1_commit": strategy_adaptation_v1_commit,
        "verification": verification,
        "source_artifacts": source_refs,
        "run_catalog_summary": _run_catalog_summary(_as_mapping(run_catalog_payload)),
        "experiment_lifecycle_summary": _experiment_lifecycle_summary(_as_mapping(lifecycle_payload)),
        "strategy_adaptation_golden_summary": _golden_check_summary(_as_mapping(golden_payload)),
        "accepted_commands": _accepted_commands(),
        "accepted_artifact_groups": _accepted_artifact_groups(),
        "sealed_docs": sealed_doc_refs,
        "active_non_goals": _active_non_goals(),
        "closure_criteria": _closure_criteria(source_refs, _as_mapping(lifecycle_payload), _as_mapping(golden_payload)),
        "ai_first_read_order": _ai_first_read_order(),
        "next_allowed_slices": _next_allowed_slices(),
        "rules": [
            "Workbench Closure Snapshot 是边界合同，不是策略收益评分。",
            "Snapshot 只记录已接受命令、artifact、测试、文档和非目标；不重跑回测。",
            "reports/ 下的本地 artifacts 可缺失；缺失时先生成 Run Catalog 和 Experiment Lifecycle。",
            "新的深度分析必须先进入独立 stage 文档，不能在 Workbench V1 内无限扩展。",
            "accepted/rejected/parked 决策应作为实验生命周期的下一层闭环，不应由收益表现自动推断。",
        ],
    }
    return snapshot


def render_workbench_closure_markdown_zh(snapshot: Mapping[str, Any]) -> str:
    """Render the closure snapshot as a Chinese Markdown document."""

    run_catalog = _as_mapping(snapshot.get("run_catalog_summary"))
    lifecycle = _as_mapping(snapshot.get("experiment_lifecycle_summary"))
    golden = _as_mapping(snapshot.get("strategy_adaptation_golden_summary"))
    lines = [
        "# Backtest Workbench V1 Closure",
        "",
        "本文档封板当前 Backtest Workbench V1。封板对象是回测证据工作台，",
        "不是某个策略参数、策略收益结果或自动调参流程。",
        "",
        "## Closure Statement",
        "",
        str(snapshot.get("objective")),
        "",
        "## Accepted Verification",
        "",
        "| check | command | expected |",
        "|---|---|---|",
    ]
    for key, value in _as_mapping(snapshot.get("verification")).items():
        value_map = _as_mapping(value)
        lines.append(
            "| "
            f"`{key}` | "
            f"`{_markdown_value(value_map.get('command'))}` | "
            f"{_markdown_value(value_map.get('expected'))} |"
        )

    lines.extend(
        [
            "",
            "## Accepted Navigation State",
            "",
            "| source | exists | schema | summary |",
            "|---|---:|---|---|",
        ]
    )
    source_artifacts = _as_mapping(snapshot.get("source_artifacts"))
    for key, ref in source_artifacts.items():
        ref_map = _as_mapping(ref)
        summary = "-"
        if key == "run_catalog":
            summary = f"run_count={run_catalog.get('run_count')}, group_count={run_catalog.get('group_count')}"
        elif key == "experiment_lifecycle":
            summary = f"chain_count={lifecycle.get('chain_count')}, decision_gap={lifecycle.get('decision_gap_count')}"
        elif key == "strategy_adaptation_golden_check":
            summary = f"status={golden.get('status')}, failed={golden.get('failed_count')}"
        lines.append(
            "| "
            f"`{key}` | "
            f"{_markdown_value(ref_map.get('exists'))} | "
            f"`{_markdown_value(ref_map.get('schema'))}` | "
            f"{_markdown_value(summary)} |"
        )

    lines.extend(["", "## Closure Criteria", "", "| criterion | status | evidence |", "|---|---|---|"])
    for criterion in _as_sequence(snapshot.get("closure_criteria")):
        criterion_map = _as_mapping(criterion)
        lines.append(
            "| "
            f"{_markdown_value(criterion_map.get('criterion_zh'))} | "
            f"`{_markdown_value(criterion_map.get('status'))}` | "
            f"{_markdown_value(criterion_map.get('evidence'))} |"
        )

    lines.extend(["", "## Accepted Commands", "", "| command | direction | purpose |", "|---|---|---|"])
    for command in _as_sequence(snapshot.get("accepted_commands")):
        command_map = _as_mapping(command)
        lines.append(
            "| "
            f"`{_markdown_value(command_map.get('command'))}` | "
            f"{_markdown_value(command_map.get('direction_zh'))} | "
            f"{_markdown_value(command_map.get('purpose_zh'))} |"
        )

    lines.extend(["", "## Accepted Artifact Groups", ""])
    for group in _as_sequence(snapshot.get("accepted_artifact_groups")):
        group_map = _as_mapping(group)
        lines.append(f"### {group_map.get('group_label_zh')}")
        lines.append("")
        lines.append(f"- direction: {group_map.get('direction_zh')}")
        lines.append(f"- purpose: {group_map.get('purpose_zh')}")
        for artifact in _as_sequence(group_map.get("artifacts")):
            lines.append(f"- `{artifact}`")
        lines.append("")

    lines.extend(["## Active Non-Goals", ""])
    for non_goal in _as_sequence(snapshot.get("active_non_goals")):
        lines.append(f"- {non_goal}")

    lines.extend(["", "## AI First Read Order", "", "| order | artifact | purpose |", "|---:|---|---|"])
    for entry in _as_sequence(snapshot.get("ai_first_read_order")):
        entry_map = _as_mapping(entry)
        lines.append(
            "| "
            f"{entry_map.get('order')} | "
            f"`{_markdown_value(entry_map.get('artifact'))}` | "
            f"{_markdown_value(entry_map.get('purpose_zh'))} |"
        )

    lines.extend(["", "## Next Allowed Slices", "", "| slice | direction | purpose |", "|---|---|---|"])
    for item in _as_sequence(snapshot.get("next_allowed_slices")):
        item_map = _as_mapping(item)
        lines.append(
            "| "
            f"{_markdown_value(item_map.get('name_zh'))} | "
            f"{_markdown_value(item_map.get('direction_zh'))} | "
            f"{_markdown_value(item_map.get('purpose_zh'))} |"
        )

    lines.extend(["", "## Rules", ""])
    for rule in _as_sequence(snapshot.get("rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_workbench_closure_snapshot(
    snapshot: Mapping[str, Any],
    *,
    baseline_path: str | Path = DEFAULT_BASELINE_PATH,
    closure_doc_path: str | Path = DEFAULT_CLOSURE_DOC_PATH,
) -> tuple[Path, Path]:
    """Write the versioned baseline JSON and closure Markdown document."""

    baseline_output = Path(baseline_path)
    closure_output = Path(closure_doc_path)
    baseline_output.parent.mkdir(parents=True, exist_ok=True)
    closure_output.parent.mkdir(parents=True, exist_ok=True)
    baseline_output.write_text(_to_pretty_json(snapshot), encoding="utf-8")
    closure_output.write_text(render_workbench_closure_markdown_zh(snapshot), encoding="utf-8")
    return baseline_output, closure_output


def _default_verification() -> dict[str, dict[str, str]]:
    return {
        "acceptance_smoke": {
            "command": "python scripts\\acceptance_smoke.py",
            "expected": (
                "231 passed; Strategy Adaptation V1 golden check status ok, "
                "check_count 72, failed_count 0; Workbench Closure golden check status ok, "
                "failed_count 0"
            ),
        },
        "full_pytest": {
            "command": "python -m pytest -q",
            "expected": "315 passed",
        },
        "diff_check": {
            "command": "git diff --check",
            "expected": "no whitespace errors; CRLF warnings are acceptable on Windows",
        },
    }


def _accepted_commands() -> list[dict[str, str]]:
    return [
        {
            "command": "att-run-plan",
            "direction_zh": "回测执行",
            "purpose_zh": "从一个已验证 YAML RunPlan 执行可重复回测并落盘证据链。",
        },
        {
            "command": "att-run-catalog",
            "direction_zh": "工作台导航",
            "purpose_zh": "索引已落盘 runs、角色、artifact 完整性、证据状态和可比较分组。",
        },
        {
            "command": "att-experiment-lifecycle",
            "direction_zh": "实验治理",
            "purpose_zh": "查看候选、草稿、确认、生成、执行、比较、归因和缺失决策阶段。",
        },
        {
            "command": "att-experiment-decisions",
            "direction_zh": "实验治理",
            "purpose_zh": "从显式 decision input 写出 accepted/rejected/parked 实验决策记录。",
        },
        {
            "command": "att-run-data-overview",
            "direction_zh": "AI 下钻",
            "purpose_zh": "读取单个 run 的第一屏总览和证据状态。",
        },
        {
            "command": "att-run-data-dictionary",
            "direction_zh": "AI 下钻",
            "purpose_zh": "解释单个 run 的 artifact 和字段含义。",
        },
        {
            "command": "att-review-packet",
            "direction_zh": "AI 复盘",
            "purpose_zh": "从已落盘 run 生成 Skill 可读复盘包。",
        },
        {
            "command": "att-review-findings",
            "direction_zh": "AI 复盘",
            "purpose_zh": "把复盘包整理成引用明确的 finding。",
        },
        {
            "command": "att-review-experiment-candidates",
            "direction_zh": "实验治理",
            "purpose_zh": "把 finding 转成候选验证方向，不修改策略。",
        },
        {
            "command": "att-review-experiment-drafts",
            "direction_zh": "实验治理",
            "purpose_zh": "生成需要人工确认的实验草稿。",
        },
        {
            "command": "att-review-experiment-confirm",
            "direction_zh": "实验治理",
            "purpose_zh": "把一个人工确认草稿转成合法 RunPlan。",
        },
        {
            "command": "att-compare-runs",
            "direction_zh": "比较验证",
            "purpose_zh": "比较多个已落盘 run 的收益、风险、交易和阻断差异。",
        },
        {
            "command": "att-compare-environment-fit",
            "direction_zh": "比较验证",
            "purpose_zh": "比较多个 run 的环境适配证据稳定性。",
        },
        {
            "command": "att-generate-market-segment-runs",
            "direction_zh": "市场段验证",
            "purpose_zh": "从人工行情段 catalog 生成合法市场段 RunPlans。",
        },
        {
            "command": "att-market-type-summary",
            "direction_zh": "市场段验证",
            "purpose_zh": "汇总已知牛市、震荡市、熊市段表现。",
        },
        {
            "command": "att-strategy-adaptation-matrix",
            "direction_zh": "策略适配 V1",
            "purpose_zh": "从已知市场类型的交易证据生成适配矩阵。",
        },
        {
            "command": "att-strategy-variant-validation",
            "direction_zh": "策略适配 V1",
            "purpose_zh": "比较基线和策略变体在已知市场类型下的表现。",
        },
        {
            "command": "att-review-golden-check",
            "direction_zh": "封板校验",
            "purpose_zh": "校验 sealed-stage AI review 是否越界或漏证据。",
        },
        {
            "command": "att-workbench-closure-snapshot",
            "direction_zh": "封板/验收",
            "purpose_zh": "写出 Backtest Workbench V1 baseline JSON 和 closure 文档。",
        },
        {
            "command": "att-workbench-closure-golden-check",
            "direction_zh": "封板校验",
            "purpose_zh": "校验 Workbench V1 closure 文档是否忠实保留 baseline 的命令、非目标、测试计数和 AI 读取顺序。",
        },
        {
            "command": "att-ai-skill-entry-contract",
            "direction_zh": "AI 易用",
            "purpose_zh": "写出 ATTbacktrader AI review Skill 的固定入口、证据门禁和输出合同。",
        },
        {
            "command": "scripts\\acceptance_smoke.py",
            "direction_zh": "封板校验",
            "purpose_zh": "运行 curated regression suite、sealed V1 golden check 和 Workbench closure golden check。",
        },
    ]


def _accepted_artifact_groups() -> list[dict[str, Any]]:
    return [
        {
            "group": "per_run_core",
            "group_label_zh": "单次回测核心证据",
            "direction_zh": "回测执行",
            "purpose_zh": "证明一次 run 可复盘、可校验、可下钻。",
            "artifacts": [
                "run_plan.json",
                "report.json",
                "report.zh.md",
                "trades.json",
                "signal_audit.json",
                "sizing_audit.json",
                "execution_audit.json",
                "trade_lifecycle.json",
                "trade_lifecycle.zh.md",
                "trade_review.json",
                "trade_review.zh.md",
                "post_exit_analysis.json",
                "post_exit_analysis.zh.md",
                "evidence_validation.json",
                "equity_curve.json",
                "positions.json",
                "snapshots.json",
            ],
        },
        {
            "group": "ai_review_workbench",
            "group_label_zh": "AI 复盘工作台",
            "direction_zh": "AI 复盘",
            "purpose_zh": "让 AI 从总览、字典、样本和 brief 开始复盘。",
            "artifacts": [
                "run_data_overview.json",
                "run_data_dictionary.json",
                "run_data_drilldown.json",
                "run_data_drilldown_batch.json",
                "run_data_attribution_index.json",
                "review_packet.<focus>.json",
                "review_findings.<focus>.json",
                "review_sample.<kind>.<id>.json",
                "review_sample_batch.<focus>.json",
                "review_brief.<focus>.json",
                "ai_review_result.<focus>.json",
            ],
        },
        {
            "group": "experiment_governance",
            "group_label_zh": "实验治理",
            "direction_zh": "实验闭环",
            "purpose_zh": "把复盘发现转成有限候选、草稿、确认和生命周期状态。",
            "artifacts": [
                "review_experiment_candidates.<focus>.json",
                "review_experiment_drafts.<focus>.json",
                "review_experiment_confirmed.<draft>.json",
                "run_catalog.json",
                "run_catalog.zh.md",
                "experiment_lifecycle.json",
                "experiment_lifecycle.zh.md",
                "experiment_decisions.json",
                "experiment_decisions.zh.md",
                "examples/experiment-decisions/workbench-v1-strategy-variant-decisions.json",
            ],
        },
        {
            "group": "comparison_and_market_type",
            "group_label_zh": "比较与市场类型",
            "direction_zh": "比较验证",
            "purpose_zh": "比较 run、环境适配、市场段和策略变体表现。",
            "artifacts": [
                "comparison.json",
                "environment_fit_comparison.json",
                "market_segment_run_manifest.json",
                "market_type_summary.json",
                "strategy_adaptation_matrix.json",
                "strategy_adaptation_drilldown.json",
                "strategy_variant_drafts.json",
                "strategy_variant_run_manifest.json",
                "strategy_variant_validation.json",
                "strategy_variant_attribution.json",
            ],
        },
        {
            "group": "closure",
            "group_label_zh": "封板合同",
            "direction_zh": "封板/验收",
            "purpose_zh": "固定当前 V1 边界、测试计数、非目标和 AI 入口。",
            "artifacts": [
                "examples/backtest-workbench-v1-baseline.json",
                "docs/backtest-workbench-v1-closure.md",
                "workbench_closure_golden_check.json",
                "workbench_closure_golden_check.zh.md",
                "examples/attbacktrader-ai-skill-entry-contract.json",
                "docs/attbacktrader-ai-skill-entry-contract.md",
                "examples/strategy-adaptation-v1-baseline.json",
                "docs/strategy-adaptation-v1-closure.md",
                "examples/strategy-adaptation-v1-ai-review-golden.json",
                "ai_review_golden_check.json",
            ],
        },
    ]


def _default_sealed_docs() -> tuple[str, ...]:
    return (
        "docs/mvp-checklist.md",
        "docs/backtest-workbench-system-map.md",
        "docs/backtest-workbench-v1-closure.md",
        "docs/attbacktrader-ai-skill-entry-contract.md",
        "docs/run-review-workbench-closure.md",
        "docs/strategy-adaptation-v1-closure.md",
        "docs/strategy-adaptation-v1-ai-review.md",
        "docs/architecture/project-structure.md",
        "docs/architecture/evidence-chain.md",
        "docs/next-stage-exit-method-attribution.md",
        "docs/exit-method-attribution-missing-evidence-check.md",
    )


def _active_non_goals() -> list[str]:
    return [
        "不做自动参数调优或贝叶斯优化。",
        "不做自动策略搜索。",
        "不做自动牛市/震荡市/熊市识别。",
        "不做自动策略切换。",
        "不把报告层后验观察直接变成交易规则。",
        "不在指标层计算多头趋势、突破、卖飞原因等决策语义。",
        "不默认填充缺失 warmup、缺失证据或缺失未来窗口。",
        "不继续在当前主线深挖 Exit Method Attribution；该方向已 parked 为未来 stage。",
        "不宣称当前策略已经可上线或适合生产交易。",
    ]


def _closure_criteria(
    source_refs: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    golden_check: Mapping[str, Any],
) -> list[dict[str, str]]:
    run_catalog_ref = _as_mapping(source_refs.get("run_catalog"))
    lifecycle_ref = _as_mapping(source_refs.get("experiment_lifecycle"))
    golden_ref = _as_mapping(source_refs.get("strategy_adaptation_golden_check"))
    decision_gap_count = _experiment_lifecycle_summary(lifecycle).get("decision_gap_count")
    return [
        {
            "criterion_zh": "curated acceptance smoke 通过",
            "status": "accepted",
            "evidence": "python scripts\\acceptance_smoke.py -> 231 passed; Strategy golden 72/72 ok; Workbench closure golden ok",
        },
        {
            "criterion_zh": "完整仓库测试通过",
            "status": "accepted",
            "evidence": "python -m pytest -q -> 315 passed",
        },
        {
            "criterion_zh": "Run Catalog 可作为第一入口",
            "status": "accepted" if run_catalog_ref.get("exists") else "missing_local_artifact",
            "evidence": str(run_catalog_ref.get("path")),
        },
        {
            "criterion_zh": "Experiment Lifecycle 可显示实验阶段",
            "status": "accepted" if lifecycle_ref.get("exists") else "missing_local_artifact",
            "evidence": f"{lifecycle_ref.get('path')} decision_gap_count={decision_gap_count}",
        },
        {
            "criterion_zh": "Strategy Adaptation V1 受 golden check 保护",
            "status": "accepted"
            if golden_ref.get("exists") and golden_check.get("status") == "ok"
            else "missing_or_failed",
            "evidence": str(golden_ref.get("path")),
        },
        {
            "criterion_zh": "Exit Method Attribution 等深度分析已 parked",
            "status": "accepted",
            "evidence": "docs/next-stage-exit-method-attribution.md; docs/exit-method-attribution-missing-evidence-check.md",
        },
    ]


def _ai_first_read_order() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "artifact": "reports/run-catalog/run_catalog.json",
            "purpose_zh": "先确定 run 是否存在、证据是否完整、可比较分组是什么。",
        },
        {
            "order": 2,
            "artifact": "reports/experiment-lifecycle/experiment_lifecycle.json",
            "purpose_zh": "再确定实验链路卡在 draft、execution、comparison、attribution 还是 decision。",
        },
        {
            "order": 3,
            "artifact": "reports/experiment-decisions/experiment_decisions.json",
            "purpose_zh": "涉及 compared/attributed experiment 时先看 explicit accepted/rejected/parked 决策。",
        },
        {
            "order": 4,
            "artifact": "reports/<run_id>/run_data_overview.json",
            "purpose_zh": "读取单个 run 的复盘总览和 evidence_validation 状态。",
        },
        {
            "order": 5,
            "artifact": "reports/<run_id>/run_data_dictionary.json",
            "purpose_zh": "确认字段含义和 artifact 下钻入口。",
        },
        {
            "order": 6,
            "artifact": "reports/<run_id>/review_packet.all.json",
            "purpose_zh": "进入 AI review，引用样本和证据，不重跑策略。",
        },
        {
            "order": 7,
            "artifact": "comparison / market_type_summary / strategy_variant_validation",
            "purpose_zh": "只有需要比较时才读取，不从单 run 直接推出策略结论。",
        },
    ]


def _next_allowed_slices() -> list[dict[str, str]]:
    return [
        {
            "name_zh": "AI Skill Contract Golden Check",
            "direction_zh": "AI 易用/封板校验",
            "purpose_zh": "校验 Skill 文档是否保留 contract 的 first-read order、preflight gates 和输出推荐规则。",
        },
        {
            "name_zh": "AI Skill Dry-run Review Smoke",
            "direction_zh": "AI 可用性验证",
            "purpose_zh": "用一个已知 run 按 Skill 入口完整复盘，检查证据引用、边界和三下一步输出是否稳定。",
        },
        {
            "name_zh": "Workbench Artifact Freshness Check",
            "direction_zh": "工作台可用性",
            "purpose_zh": "检查 run catalog、lifecycle、decisions、closure、AI contract 是否由最新命令生成，避免 AI 读到旧 artifact。",
        },
    ]


def _run_catalog_summary(catalog: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": catalog.get("schema"),
        "run_count": catalog.get("run_count"),
        "group_count": catalog.get("group_count"),
        "missing_required_artifact_run_count": catalog.get("missing_required_artifact_run_count"),
        "missing_run_dir_count": catalog.get("missing_run_dir_count"),
        "role_counts": list(_as_sequence(catalog.get("role_counts"))),
        "evidence_status_counts": list(_as_sequence(catalog.get("evidence_status_counts"))),
    }


def _experiment_lifecycle_summary(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    chains = [_as_mapping(chain) for chain in _as_sequence(lifecycle.get("chains"))]
    return {
        "schema": lifecycle.get("schema"),
        "item_count": lifecycle.get("item_count"),
        "chain_count": lifecycle.get("chain_count"),
        "lineage_counts": list(_as_sequence(lifecycle.get("lineage_counts"))),
        "stage_counts": list(_as_sequence(lifecycle.get("stage_counts"))),
        "status_counts": list(_as_sequence(lifecycle.get("status_counts"))),
        "decision_gap_count": sum(1 for chain in chains if "decision" in _as_sequence(chain.get("missing_stages"))),
        "execution_gap_count": sum(1 for chain in chains if "executed_run" in _as_sequence(chain.get("missing_stages"))),
        "chains_waiting_decision": [
            str(chain.get("chain_id")) for chain in chains if "decision" in _as_sequence(chain.get("missing_stages"))
        ],
    }


def _golden_check_summary(golden_check: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": golden_check.get("schema"),
        "status": golden_check.get("status"),
        "check_count": golden_check.get("check_count"),
        "passed_count": golden_check.get("passed_count"),
        "failed_count": golden_check.get("failed_count"),
        "golden_for": golden_check.get("golden_for"),
    }


def _source_ref(path: str | Path | None, *, payload: Mapping[str, Any]) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "schema": None}
    source_path = Path(path)
    return {
        "path": str(source_path),
        "exists": source_path.exists(),
        "schema": payload.get("schema") if payload else None,
    }


def _file_ref(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    return {
        "path": str(source_path),
        "exists": source_path.exists(),
        "size_bytes": source_path.stat().st_size if source_path.exists() else None,
    }


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
