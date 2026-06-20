"""AI Skill entry contract helpers for ATTbacktrader review workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


AI_SKILL_ENTRY_CONTRACT_SCHEMA = "attbacktrader.ai_skill_entry_contract.v1"

DEFAULT_AI_SKILL_CONTRACT_PATH = Path("examples/attbacktrader-ai-skill-entry-contract.json")
DEFAULT_AI_SKILL_CONTRACT_DOC_PATH = Path("docs/attbacktrader-ai-skill-entry-contract.md")


def build_ai_skill_entry_contract(
    *,
    generated_on: str,
    source_workbench_closure: str | Path = "examples/backtest-workbench-v1-baseline.json",
    skill_name: str = "attbacktrader-ai-review",
    skill_doc_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a versioned entry contract for ATTbacktrader AI review skills."""

    closure_payload = _as_mapping(_load_json_if_exists(Path(source_workbench_closure)))
    return {
        "schema": AI_SKILL_ENTRY_CONTRACT_SCHEMA,
        "generated_on": generated_on,
        "skill_name": skill_name,
        "skill_doc_path": str(skill_doc_path) if skill_doc_path is not None else None,
        "source_workbench_closure": _source_ref(source_workbench_closure, payload=closure_payload),
        "workbench_summary": _workbench_summary(closure_payload),
        "objective_zh": "让 AI 复盘从固定入口开始，按证据顺序读取，不重跑策略、不跳过证据门禁、不无限扩展分析方向。",
        "entry_read_order": _entry_read_order(),
        "interaction_modes": _interaction_modes(),
        "preflight_gates": _preflight_gates(),
        "allowed_actions": _allowed_actions(),
        "forbidden_actions": _forbidden_actions(),
        "evidence_citation_rules": _evidence_citation_rules(),
        "output_contract": _output_contract(),
        "next_recommendation_contract": _next_recommendation_contract(),
        "skill_update_notes": _skill_update_notes(skill_name),
        "rules": [
            "AI Skill Entry Contract 是 Skill 的读取和输出边界，不是新的策略分析结果。",
            "除非用户明确要求跑回测，AI review 默认只读取 persisted artifacts。",
            "任何结论必须经过 evidence_validation、sample refs、run_id/trade_index 或 comparison source 引用。",
            "当 Experiment Lifecycle 显示缺少 decision 时，下一步应先记录 accepted/rejected/parked，而不是继续调参。",
            "每次完成一个功能后的推荐必须给出三个下一步，并标明方向、作用、最推荐项和原因。",
        ],
    }


def render_ai_skill_entry_contract_markdown_zh(contract: Mapping[str, Any]) -> str:
    """Render the AI Skill entry contract as Chinese Markdown."""

    lines = [
        "# ATTbacktrader AI Skill Entry Contract",
        "",
        f"- schema: `{contract.get('schema')}`",
        f"- generated_on: `{contract.get('generated_on')}`",
        f"- skill_name: `{contract.get('skill_name')}`",
        f"- objective: {contract.get('objective_zh')}",
        "",
        "## First Read Order",
        "",
        "| order | artifact | required | when | command | stop rule |",
        "|---:|---|---:|---|---|---|",
    ]
    for row in _as_sequence(contract.get("entry_read_order")):
        row_map = _as_mapping(row)
        lines.append(
            "| "
            f"{row_map.get('order')} | "
            f"`{_markdown_value(row_map.get('artifact'))}` | "
            f"{_markdown_value(row_map.get('required'))} | "
            f"{_markdown_value(row_map.get('when_zh'))} | "
            f"`{_markdown_value(row_map.get('command'))}` | "
            f"{_markdown_value(row_map.get('stop_rule_zh'))} |"
        )

    lines.extend(["", "## Interaction Modes", "", "| mode | direction | first reads | output |", "|---|---|---|---|"])
    for mode in _as_sequence(contract.get("interaction_modes")):
        mode_map = _as_mapping(mode)
        first_reads = ", ".join(str(item) for item in _as_sequence(mode_map.get("first_reads")))
        lines.append(
            "| "
            f"`{_markdown_value(mode_map.get('mode'))}` | "
            f"{_markdown_value(mode_map.get('direction_zh'))} | "
            f"{_markdown_value(first_reads)} | "
            f"{_markdown_value(mode_map.get('expected_output_zh'))} |"
        )

    lines.extend(["", "## Preflight Gates", ""])
    for gate in _as_sequence(contract.get("preflight_gates")):
        gate_map = _as_mapping(gate)
        lines.append(f"- `{gate_map.get('gate_id')}`: {gate_map.get('rule_zh')}")

    lines.extend(["", "## Allowed Actions", ""])
    for item in _as_sequence(contract.get("allowed_actions")):
        item_map = _as_mapping(item)
        lines.append(f"- {item_map.get('action_zh')}: `{item_map.get('command')}`")

    lines.extend(["", "## Forbidden Actions", ""])
    for item in _as_sequence(contract.get("forbidden_actions")):
        lines.append(f"- {item}")

    lines.extend(["", "## Evidence Citation Rules", ""])
    for rule in _as_sequence(contract.get("evidence_citation_rules")):
        rule_map = _as_mapping(rule)
        lines.append(f"- {rule_map.get('claim_type_zh')}: {rule_map.get('required_refs_zh')}")

    lines.extend(["", "## Output Contract", ""])
    output_contract = _as_mapping(contract.get("output_contract"))
    lines.append(f"- language: {output_contract.get('language')}")
    lines.append(f"- max_next_actions: {output_contract.get('max_next_actions')}")
    lines.append(f"- must_include: {', '.join(str(item) for item in _as_sequence(output_contract.get('must_include')))}")

    lines.extend(["", "## Next Recommendation Contract", ""])
    next_contract = _as_mapping(contract.get("next_recommendation_contract"))
    for rule in _as_sequence(next_contract.get("rules")):
        lines.append(f"- {rule}")

    lines.extend(["", "## Rules", ""])
    for rule in _as_sequence(contract.get("rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_ai_skill_entry_contract(
    contract: Mapping[str, Any],
    *,
    output_path: str | Path = DEFAULT_AI_SKILL_CONTRACT_PATH,
    doc_output_path: str | Path = DEFAULT_AI_SKILL_CONTRACT_DOC_PATH,
) -> tuple[Path, Path]:
    """Write the AI Skill entry contract JSON and Markdown document."""

    json_path = Path(output_path)
    doc_path = Path(doc_output_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(_to_pretty_json(contract), encoding="utf-8")
    doc_path.write_text(render_ai_skill_entry_contract_markdown_zh(contract), encoding="utf-8")
    return json_path, doc_path


def _entry_read_order() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "artifact": "reports/run-catalog/run_catalog.json",
            "required": True,
            "when_zh": "任何工作台复盘或 run 选择前。",
            "command": "att-run-catalog",
            "stop_rule_zh": "如果目标 run 不存在，先报告缺失，不猜路径。",
        },
        {
            "order": 2,
            "artifact": "reports/experiment-lifecycle/experiment_lifecycle.json",
            "required": True,
            "when_zh": "涉及实验、变体、下一步建议或封板状态时。",
            "command": "att-experiment-lifecycle",
            "stop_rule_zh": "如果链路缺少执行或比较，先说明当前阶段，不直接评价策略。",
        },
        {
            "order": 3,
            "artifact": "reports/experiment-decisions/experiment_decisions.json",
            "required": False,
            "when_zh": "涉及 compared/attributed experiment 的最终处理时。",
            "command": "att-experiment-decisions",
            "stop_rule_zh": "如果 lifecycle 仍缺 decision，先生成或要求显式 decision input。",
        },
        {
            "order": 4,
            "artifact": "reports/<run_id>/run_data_overview.json",
            "required": True,
            "when_zh": "进入单个 run 复盘时。",
            "command": "att-run-data-overview --run-id <run_id>",
            "stop_rule_zh": "如果 evidence_validation.status != ok，先报告证据问题。",
        },
        {
            "order": 5,
            "artifact": "reports/<run_id>/run_data_dictionary.json",
            "required": True,
            "when_zh": "需要解释字段或下钻 artifact 时。",
            "command": "att-run-data-dictionary --run-id <run_id>",
            "stop_rule_zh": "如果字段含义不明，不自行推断。",
        },
        {
            "order": 6,
            "artifact": "reports/<run_id>/review_packet.all.json",
            "required": False,
            "when_zh": "需要 AI 复盘样本、finding 或候选实验时。",
            "command": "att-review-packet --run-dir reports/<run_id> --focus all",
            "stop_rule_zh": "如果 packet 不存在，可生成；生成后再写 finding。",
        },
        {
            "order": 7,
            "artifact": "comparison / market_type_summary / strategy_variant_validation",
            "required": False,
            "when_zh": "需要跨 run、跨市场类型或策略变体比较时。",
            "command": "att-compare-runs / att-market-type-summary / att-strategy-variant-validation",
            "stop_rule_zh": "没有比较 artifact 时，不从单 run 推出环境适配或策略优劣。",
        },
    ]


def _interaction_modes() -> list[dict[str, Any]]:
    return [
        {
            "mode": "workspace_status",
            "direction_zh": "工作台状态",
            "first_reads": ["run_catalog", "experiment_lifecycle", "experiment_decisions", "workbench_closure"],
            "expected_output_zh": "当前可用 run、证据缺口、实验缺口、最推荐下一步。",
        },
        {
            "mode": "single_run_review",
            "direction_zh": "单 run 复盘",
            "first_reads": ["run_catalog", "run_data_overview", "run_data_dictionary", "review_packet"],
            "expected_output_zh": "证据状态、关键 findings、引用样本、三个下一步。",
        },
        {
            "mode": "experiment_followup",
            "direction_zh": "实验治理",
            "first_reads": ["experiment_lifecycle", "experiment_decisions", "review_findings", "review_experiment_drafts"],
            "expected_output_zh": "当前阶段、缺失阶段、是否需要人工确认或决策记录。",
        },
        {
            "mode": "strategy_variant_review",
            "direction_zh": "策略变体验证",
            "first_reads": [
                "strategy_variant_validation",
                "strategy_variant_attribution",
                "experiment_lifecycle",
                "experiment_decisions",
            ],
            "expected_output_zh": "变体相对基线变化、证据引用、是否 parked/accepted/rejected 的建议。",
        },
        {
            "mode": "sealed_stage_check",
            "direction_zh": "封板校验",
            "first_reads": [
                "workbench_closure",
                "workbench_closure_golden_check",
                "strategy_adaptation_v1_baseline",
                "golden_check",
            ],
            "expected_output_zh": "是否越界、是否漏掉 non-goals、是否需要 golden check。",
        },
    ]


def _preflight_gates() -> list[dict[str, str]]:
    return [
        {
            "gate_id": "catalog_exists",
            "rule_zh": "开始复盘前必须有 Run Catalog；没有就运行 att-run-catalog。",
        },
        {
            "gate_id": "run_exists",
            "rule_zh": "用户给 run_id 时必须在 catalog 中找到；找不到先报告缺失。",
        },
        {
            "gate_id": "evidence_ok",
            "rule_zh": "单 run 复盘必须先看 evidence_validation.status；非 ok 时停止策略结论。",
        },
        {
            "gate_id": "lifecycle_stage",
            "rule_zh": "涉及实验时必须先读 Experiment Lifecycle；缺 execution/comparison/decision 时先说明缺口。",
        },
        {
            "gate_id": "comparison_required",
            "rule_zh": "涉及适合什么环境、哪个策略更好时必须有 comparison 或 market_type_summary。",
        },
        {
            "gate_id": "manual_confirmation",
            "rule_zh": "确认 RunPlan、执行变体、记录决策前必须有用户确认或已有 confirmation artifact。",
        },
    ]


def _allowed_actions() -> list[dict[str, str]]:
    return [
        {"action_zh": "生成 run catalog", "command": "att-run-catalog"},
        {"action_zh": "生成 experiment lifecycle", "command": "att-experiment-lifecycle"},
        {"action_zh": "生成 experiment decision records", "command": "att-experiment-decisions"},
        {"action_zh": "生成单 run overview", "command": "att-run-data-overview --run-id <run_id>"},
        {"action_zh": "生成单 run dictionary", "command": "att-run-data-dictionary --run-id <run_id>"},
        {"action_zh": "生成 AI review packet", "command": "att-review-packet --run-dir reports/<run_id> --focus all"},
        {"action_zh": "生成 findings 和 samples", "command": "att-review-findings / att-review-expand-samples"},
        {"action_zh": "生成 bounded experiment candidates/drafts", "command": "att-review-experiment-candidates / att-review-experiment-drafts"},
        {"action_zh": "读取比较 artifact", "command": "att-compare-runs / att-compare-environment-fit / att-strategy-variant-validation"},
        {"action_zh": "运行 sealed golden check", "command": "att-review-golden-check"},
        {"action_zh": "运行 Workbench closure golden check", "command": "att-workbench-closure-golden-check"},
    ]


def _forbidden_actions() -> list[str]:
    return [
        "不在 review 中重跑策略，除非用户明确要求执行某个 RunPlan。",
        "不抓取新行情数据来补 review 证据。",
        "不从单个 run 直接推导策略适合的市场环境。",
        "不把 post-exit rebound、卖飞、机会成本直接变成交易规则。",
        "不默认填充缺失 warmup、缺失 evidence、缺失 future bars。",
        "不自动确认 review draft 或 strategy variant draft。",
        "不运行 planning draft YAML；只运行合法 RunPlan YAML。",
        "不宣称策略可上线、可自动切换、可自动调参。",
    ]


def _evidence_citation_rules() -> list[dict[str, str]]:
    return [
        {
            "claim_type_zh": "单 run 复盘 finding",
            "required_refs_zh": "finding_id + artifact path + 至少一个 trade_index 或 sample_index。",
        },
        {
            "claim_type_zh": "环境适配结论",
            "required_refs_zh": "environment_fit / environment_fit_comparison source + sample warning + representative trade refs。",
        },
        {
            "claim_type_zh": "市场类型或策略变体结论",
            "required_refs_zh": "market_type_id + baseline/variant summary paths + segment_id 或 run_id。",
        },
        {
            "claim_type_zh": "策略变体行为解释",
            "required_refs_zh": "strategy_variant_attribution source + segment_id + variant_run_id + sample run_id/trade_index。",
        },
        {
            "claim_type_zh": "实验下一步或决策",
            "required_refs_zh": "experiment_lifecycle chain_id + missing_stages + next_action_zh；已有决策时引用 experiment_decisions decision_id。",
        },
    ]


def _output_contract() -> dict[str, Any]:
    return {
        "language": "zh-CN",
        "max_next_actions": 3,
        "must_include": [
            "current_direction_zh",
            "evidence_status_zh",
            "bounded_findings",
            "risk_or_caveat_zh",
            "next_actions_with_direction_and_purpose",
            "most_recommended_next_action_with_why",
        ],
        "finding_shape": {
            "finding_id": "string",
            "claim_zh": "string",
            "evidence_refs": [],
            "sample_refs": [],
            "risk_zh": "string",
            "next_check_zh": "string",
        },
    }


def _next_recommendation_contract() -> dict[str, Any]:
    return {
        "count": 3,
        "rules": [
            "每个推荐必须标明 direction_zh。",
            "每个推荐必须说明 purpose_zh。",
            "必须明确一个 most_recommended，并说明 why_zh。",
            "推荐必须来自 lifecycle 缺口、closure allowed slices 或用户当前目标，不要无限深化单一分析点。",
        ],
    }


def _skill_update_notes(skill_name: str) -> list[dict[str, str]]:
    return [
        {
            "target": skill_name,
            "change_zh": "Quick Start 先运行 att-run-catalog、att-experiment-lifecycle 和 att-experiment-decisions，再进入单 run review。",
        },
        {
            "target": skill_name,
            "change_zh": "Workflow 第一条改为读取本 contract 或 Workbench closure，然后执行 preflight gates。",
        },
        {
            "target": skill_name,
            "change_zh": "Strategy Adaptation V1 的 next-stage 说明改成 parked；当前主线是 Workbench V1 closure。",
        },
    ]


def _workbench_summary(closure: Mapping[str, Any]) -> dict[str, Any]:
    lifecycle = _as_mapping(closure.get("experiment_lifecycle_summary"))
    catalog = _as_mapping(closure.get("run_catalog_summary"))
    return {
        "closure_schema": closure.get("schema"),
        "sealed_on": closure.get("sealed_on"),
        "run_count": catalog.get("run_count"),
        "chain_count": lifecycle.get("chain_count"),
        "decision_gap_count": lifecycle.get("decision_gap_count"),
        "active_non_goals": list(_as_sequence(closure.get("active_non_goals"))),
        "next_allowed_slices": list(_as_sequence(closure.get("next_allowed_slices"))),
    }


def _source_ref(path: str | Path, *, payload: Mapping[str, Any]) -> dict[str, Any]:
    source_path = Path(path)
    return {
        "path": str(source_path),
        "exists": source_path.exists(),
        "schema": payload.get("schema") if payload else None,
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
