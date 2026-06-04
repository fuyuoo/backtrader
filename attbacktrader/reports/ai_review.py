"""AI-oriented review outputs assembled from persisted run artifacts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from attbacktrader.config import RunPlan


AI_REVIEW_FINDINGS_SCHEMA = "attbacktrader.ai_review_findings.v1"
AI_REVIEW_BRIEF_SCHEMA = "attbacktrader.ai_review_brief.v1"
AI_REVIEW_RESULT_SCHEMA = "attbacktrader.ai_review_result.v1"
REVIEW_SAMPLE_BATCH_SCHEMA = "attbacktrader.review_sample_batch.v1"
REVIEW_SAMPLE_SCHEMA = "attbacktrader.review_sample.v1"
REVIEW_EXPERIMENT_CANDIDATES_SCHEMA = "attbacktrader.review_experiment_candidates.v1"
REVIEW_EXPERIMENT_DRAFTS_SCHEMA = "attbacktrader.review_experiment_drafts.v1"
REVIEW_EXPERIMENT_CONFIRMED_RUN_PLAN_SCHEMA = "attbacktrader.review_experiment_confirmed_run_plan.v1"
REVIEW_SAMPLE_KINDS = ("trade", "opportunity", "add_on")
RUN_PLAN_TOP_LEVEL_KEYS = ("run", "data", "strategy", "constraints", "broker", "execution", "output", "analysis")

_ARTIFACT_FILENAMES = {
    "run_plan": "run_plan.json",
    "report": "report.json",
    "trade_review": "trade_review.json",
    "post_exit_analysis": "post_exit_analysis.json",
    "evidence_validation": "evidence_validation.json",
    "trade_lifecycle": "trade_lifecycle.json",
    "signal_audit": "signal_audit.json",
    "execution_audit": "execution_audit.json",
    "trades": "trades.json",
    "result_diagnostics": "result_diagnostics.json",
}


def build_ai_review_findings(
    packet_or_path: Mapping[str, Any] | str | Path,
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Build structured review findings from a review packet."""

    if top <= 0:
        raise ValueError("top must be greater than 0")
    packet, packet_path = _load_packet(packet_or_path)
    findings = _build_findings(packet, top=top)
    return {
        "schema": AI_REVIEW_FINDINGS_SCHEMA,
        "run_id": packet.get("run_id"),
        "focus": packet.get("focus"),
        "source_packet": str(packet_path) if packet_path is not None else None,
        "source_dir": packet.get("source_dir"),
        "ai_task": _ai_task(packet),
        "overview": packet.get("overview", {}),
        "finding_count": len(findings),
        "findings": findings,
    }


def render_ai_review_findings_markdown_zh(findings: Mapping[str, Any]) -> str:
    """Render AI review findings as Chinese Markdown with JSON evidence blocks."""

    lines = [
        "# AI 复盘 Findings",
        "",
        f"- schema: `{findings.get('schema')}`",
        f"- run_id: `{findings.get('run_id')}`",
        f"- focus: `{findings.get('focus')}`",
        f"- source_packet: `{findings.get('source_packet')}`",
        f"- finding_count: `{findings.get('finding_count')}`",
        "",
        "## AI 任务",
        "```json",
        _to_pretty_json(findings.get("ai_task", {})),
        "```",
        "",
        "## 概览",
        "```json",
        _to_pretty_json(findings.get("overview", {})),
        "```",
    ]
    for finding in _as_sequence(findings.get("findings")):
        finding_map = _as_mapping(finding)
        lines.extend(
            [
                "",
                f"## {finding_map.get('title_zh')}",
                "",
                f"- finding_id: `{finding_map.get('finding_id')}`",
                f"- direction: `{finding_map.get('direction')}`",
                f"- summary: {finding_map.get('summary_zh')}",
                f"- next_action: {finding_map.get('next_action_zh')}",
                f"- caveat: {finding_map.get('caveat_zh')}",
                "",
                "```json",
                _to_pretty_json(
                    {
                        "metrics": finding_map.get("metrics", {}),
                        "evidence_refs": finding_map.get("evidence_refs", []),
                        "sample_refs": finding_map.get("sample_refs", []),
                    }
                ),
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_ai_review_findings(
    findings: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write structured AI findings JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(findings["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    focus = str(findings["focus"])
    json_path = target_dir / f"review_findings.{focus}.json"
    markdown_path = target_dir / f"review_findings.{focus}.zh.md"
    json_path.write_text(_to_pretty_json(findings), encoding="utf-8")
    markdown_path.write_text(render_ai_review_findings_markdown_zh(findings), encoding="utf-8")
    return json_path, markdown_path


def expand_review_samples_from_findings(
    findings_or_path: Mapping[str, Any] | str | Path,
    *,
    run_dir: str | Path | None = None,
    limit_per_finding: int = 3,
    output_dir: str | Path | None = None,
    write_samples: bool = False,
) -> dict[str, Any]:
    """Expand finding sample refs into focused sample packets."""

    if limit_per_finding <= 0:
        raise ValueError("limit_per_finding must be greater than 0")
    findings, findings_path = _load_findings(findings_or_path)
    source_dir = _source_dir_from_findings(findings, run_dir)
    target_dir = Path(output_dir) if output_dir is not None else source_dir
    samples = []
    for ref in _unique_sample_refs(findings, limit_per_finding=limit_per_finding):
        packet = build_review_sample(
            source_dir,
            kind=str(ref["kind"]),
            sample_index=ref.get("sample_index"),
            trade_index=ref.get("trade_index"),
        )
        artifacts = None
        if write_samples:
            json_path, markdown_path = write_review_sample(packet, output_dir=target_dir)
            artifacts = {
                "review_sample_json_path": str(json_path),
                "review_sample_chinese_markdown_path": str(markdown_path),
            }
        samples.append(
            {
                "sample_ref": ref,
                "sample_id": packet["sample_id"],
                "sample_kind": packet["sample_kind"],
                "artifacts": artifacts,
                "sample": packet["sample"],
                "related_summary": _sample_related_summary(packet),
            }
        )
    return {
        "schema": REVIEW_SAMPLE_BATCH_SCHEMA,
        "run_id": findings.get("run_id"),
        "focus": findings.get("focus"),
        "source_findings": str(findings_path) if findings_path is not None else None,
        "source_dir": str(source_dir),
        "limit_per_finding": limit_per_finding,
        "expanded_sample_count": len(samples),
        "samples": samples,
    }


def render_review_sample_batch_markdown_zh(batch: Mapping[str, Any]) -> str:
    """Render expanded sample batch as Chinese Markdown."""

    lines = [
        "# AI 批量样本展开",
        "",
        f"- schema: `{batch.get('schema')}`",
        f"- run_id: `{batch.get('run_id')}`",
        f"- focus: `{batch.get('focus')}`",
        f"- source_findings: `{batch.get('source_findings')}`",
        f"- expanded_sample_count: `{batch.get('expanded_sample_count')}`",
    ]
    for sample in _as_sequence(batch.get("samples")):
        sample_map = _as_mapping(sample)
        lines.extend(
            [
                "",
                f"## {sample_map.get('sample_id')}",
                "",
                f"- kind: `{sample_map.get('sample_kind')}`",
                "",
                "```json",
                _to_pretty_json(
                    {
                        "sample_ref": sample_map.get("sample_ref"),
                        "sample": sample_map.get("sample"),
                        "related_summary": sample_map.get("related_summary"),
                        "artifacts": sample_map.get("artifacts"),
                    }
                ),
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_review_sample_batch(
    batch: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write an expanded sample batch JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(batch["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    focus = str(batch["focus"])
    json_path = target_dir / f"review_sample_batch.{focus}.json"
    markdown_path = target_dir / f"review_sample_batch.{focus}.zh.md"
    json_path.write_text(_to_pretty_json(batch), encoding="utf-8")
    markdown_path.write_text(render_review_sample_batch_markdown_zh(batch), encoding="utf-8")
    return json_path, markdown_path


def build_ai_review_brief(
    findings_or_path: Mapping[str, Any] | str | Path,
    *,
    run_dir: str | Path | None = None,
    sample_batch: Mapping[str, Any] | str | Path | None = None,
    limit_per_finding: int = 3,
) -> dict[str, Any]:
    """Build a compact Skill-ready review brief from findings and samples."""

    findings, findings_path = _load_findings(findings_or_path)
    if sample_batch is None:
        batch = expand_review_samples_from_findings(
            findings,
            run_dir=run_dir,
            limit_per_finding=limit_per_finding,
        )
        batch_path = None
    else:
        batch, batch_path = _load_sample_batch(sample_batch)
    sample_lookup = _expanded_sample_lookup(batch)
    sections = []
    for finding in _as_sequence(findings.get("findings")):
        finding_map = _as_mapping(finding)
        refs = _as_sequence(finding_map.get("sample_refs"))[:limit_per_finding]
        expanded = [sample_lookup[key] for key in (_sample_ref_key(_as_mapping(ref)) for ref in refs) if key in sample_lookup]
        sections.append(
            {
                "finding_id": finding_map.get("finding_id"),
                "direction": finding_map.get("direction"),
                "title_zh": finding_map.get("title_zh"),
                "summary_zh": finding_map.get("summary_zh"),
                "metrics": finding_map.get("metrics", {}),
                "evidence_refs": finding_map.get("evidence_refs", []),
                "sample_refs": refs,
                "expanded_samples": expanded,
                "next_action_zh": finding_map.get("next_action_zh"),
                "caveat_zh": finding_map.get("caveat_zh"),
            }
        )
    overview = _as_mapping(findings.get("overview"))
    return {
        "schema": AI_REVIEW_BRIEF_SCHEMA,
        "run_id": findings.get("run_id"),
        "focus": findings.get("focus"),
        "source_findings": str(findings_path) if findings_path is not None else None,
        "source_sample_batch": str(batch_path) if batch_path is not None else None,
        "source_dir": findings.get("source_dir"),
        "skill_contract": _review_brief_skill_contract(),
        "overview": overview,
        "environment_fit_summary": _environment_fit_brief_summary(overview),
        "section_count": len(sections),
        "sections": sections,
    }


def _environment_fit_brief_summary(overview: Mapping[str, Any]) -> dict[str, Any]:
    environment_fit = _as_mapping(overview.get("environment_fit"))
    if not environment_fit:
        return {}
    best_by_net = _as_mapping(environment_fit.get("best_by_net_pnl"))
    best_by_capital = _as_mapping(environment_fit.get("best_by_return_on_entry_value"))
    return _drop_none(
        {
            "trade_count": environment_fit.get("trade_count"),
            "contribution_available_count": environment_fit.get("contribution_available_count"),
            "overall_net_pnl": environment_fit.get("overall_net_pnl"),
            "overall_return_on_entry_value": environment_fit.get("overall_return_on_entry_value"),
            "best_by_net_pnl_label_zh": best_by_net.get("label_zh"),
            "best_by_net_pnl_sample_count": best_by_net.get("sample_count"),
            "best_by_net_pnl_net_pnl": best_by_net.get("net_pnl"),
            "best_by_net_pnl_return_on_entry_value": best_by_net.get("return_on_entry_value"),
            "best_by_net_pnl_trade_indexes": best_by_net.get("trade_indexes"),
            "best_by_return_on_entry_value_label_zh": best_by_capital.get("label_zh"),
            "best_by_return_on_entry_value_sample_count": best_by_capital.get("sample_count"),
            "best_by_return_on_entry_value_net_pnl": best_by_capital.get("net_pnl"),
            "best_by_return_on_entry_value": best_by_capital.get("return_on_entry_value"),
            "best_by_return_on_entry_value_trade_indexes": best_by_capital.get("trade_indexes"),
            "low_sample_combination_count": environment_fit.get("low_sample_combination_count"),
        }
    )


def _render_environment_fit_summary_markdown_zh(summary: Mapping[str, Any]) -> list[str]:
    if not summary:
        return []
    rows = (
        ("交易数", summary.get("trade_count")),
        ("可计算贡献交易数", summary.get("contribution_available_count")),
        ("整体净 PnL", summary.get("overall_net_pnl")),
        ("整体入场资金收益率", summary.get("overall_return_on_entry_value")),
        ("净利润最高环境", summary.get("best_by_net_pnl_label_zh")),
        ("净利润最高环境样本数", summary.get("best_by_net_pnl_sample_count")),
        ("净利润最高环境净 PnL", summary.get("best_by_net_pnl_net_pnl")),
        ("净利润最高环境交易", summary.get("best_by_net_pnl_trade_indexes")),
        ("资金收益率最高环境", summary.get("best_by_return_on_entry_value_label_zh")),
        ("资金收益率最高环境样本数", summary.get("best_by_return_on_entry_value_sample_count")),
        ("资金收益率最高环境收益率", summary.get("best_by_return_on_entry_value")),
        ("资金收益率最高环境交易", summary.get("best_by_return_on_entry_value_trade_indexes")),
        ("低样本组合数量", summary.get("low_sample_combination_count")),
    )
    lines = [
        "",
        "## 环境适配摘要",
        "",
        "| 指标 | 值 |",
        "|---|---|",
    ]
    for label, value in rows:
        if value is not None:
            lines.append(f"| {label} | {_markdown_table_value(value)} |")
    return lines


def render_ai_review_brief_markdown_zh(brief: Mapping[str, Any]) -> str:
    """Render the Skill-ready review brief as Chinese Markdown."""

    lines = [
        "# AI 自动复盘 Brief",
        "",
        f"- schema: `{brief.get('schema')}`",
        f"- run_id: `{brief.get('run_id')}`",
        f"- focus: `{brief.get('focus')}`",
        f"- section_count: `{brief.get('section_count')}`",
    ]
    lines.extend(_render_environment_fit_summary_markdown_zh(_as_mapping(brief.get("environment_fit_summary"))))
    lines.extend(
        [
            "",
            "## Skill Contract",
            "```json",
            _to_pretty_json(brief.get("skill_contract", {})),
            "```",
            "",
            "## Overview",
            "```json",
            _to_pretty_json(brief.get("overview", {})),
            "```",
        ]
    )
    for section in _as_sequence(brief.get("sections")):
        section_map = _as_mapping(section)
        lines.extend(
            [
                "",
                f"## {section_map.get('title_zh')}",
                "",
                f"- finding_id: `{section_map.get('finding_id')}`",
                f"- direction: `{section_map.get('direction')}`",
                f"- summary: {section_map.get('summary_zh')}",
                f"- next_action: {section_map.get('next_action_zh')}",
                f"- caveat: {section_map.get('caveat_zh')}",
                "",
                "```json",
                _to_pretty_json(
                    {
                        "metrics": section_map.get("metrics", {}),
                        "evidence_refs": section_map.get("evidence_refs", []),
                        "sample_refs": section_map.get("sample_refs", []),
                        "expanded_samples": section_map.get("expanded_samples", []),
                    }
                ),
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_ai_review_brief(
    brief: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write the AI review brief JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(brief["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    focus = str(brief["focus"])
    json_path = target_dir / f"review_brief.{focus}.json"
    markdown_path = target_dir / f"review_brief.{focus}.zh.md"
    json_path.write_text(_to_pretty_json(brief), encoding="utf-8")
    markdown_path.write_text(render_ai_review_brief_markdown_zh(brief), encoding="utf-8")
    return json_path, markdown_path


def build_ai_review_result(
    brief_or_path: Mapping[str, Any] | str | Path,
    *,
    environment_fit_comparison: Mapping[str, Any] | str | Path | None = None,
    reviewer: str = "deterministic_brief_renderer",
) -> dict[str, Any]:
    """Build a persisted review result from a Skill-ready brief."""

    brief, brief_path = _load_brief(brief_or_path)
    comparison = None
    comparison_path = None
    if environment_fit_comparison is not None:
        comparison, comparison_path = _load_environment_fit_comparison(environment_fit_comparison)
    finding_results = []
    for section in _as_sequence(brief.get("sections")):
        section_map = _as_mapping(section)
        finding_results.append(
            {
                "finding_id": section_map.get("finding_id"),
                "claim_zh": section_map.get("summary_zh"),
                "evidence_refs": section_map.get("evidence_refs", []),
                "sample_refs": section_map.get("sample_refs", []),
                "supporting_sample_ids": [
                    _as_mapping(sample).get("sample_id") for sample in _as_sequence(section_map.get("expanded_samples"))
                ],
                "risk_zh": section_map.get("caveat_zh"),
                "next_check_zh": section_map.get("next_action_zh"),
            }
        )
    comparison_result = (
        _environment_fit_comparison_review(comparison, comparison_path=comparison_path)
        if comparison is not None
        else None
    )
    if comparison_result is not None:
        finding_results.append(comparison_result)
    return {
        "schema": AI_REVIEW_RESULT_SCHEMA,
        "run_id": brief.get("run_id"),
        "focus": brief.get("focus"),
        "source_brief": str(brief_path) if brief_path is not None else None,
        "source_environment_fit_comparison": str(comparison_path) if comparison_path is not None else None,
        "source_dir": brief.get("source_dir"),
        "reviewer": reviewer,
        "status": "draft_from_brief",
        "summary_zh": _review_result_summary(brief),
        "finding_result_count": len(finding_results),
        "findings": finding_results,
        "environment_fit_comparison_review": comparison_result,
        "rules": [
            "该结果来自 review_brief 的结构化证据，不是策略调优结论。",
            "环境对比结论来自 environment_fit_comparison；changed 或 low-sample 状态只能作为验证风险。",
            "每条 finding 必须保留 evidence_refs 和 sample_refs。",
            "后续人工或 Skill 修改时，不得删除缺失证据和 caveat。",
        ],
    }


def render_ai_review_result_markdown_zh(result: Mapping[str, Any]) -> str:
    """Render persisted AI review result as Chinese Markdown."""

    lines = [
        "# AI 复盘结果",
        "",
        f"- schema: `{result.get('schema')}`",
        f"- run_id: `{result.get('run_id')}`",
        f"- focus: `{result.get('focus')}`",
        f"- status: `{result.get('status')}`",
        f"- reviewer: `{result.get('reviewer')}`",
        "",
        "## 总结",
        "",
        str(result.get("summary_zh")),
        "",
        "## 规则",
    ]
    for rule in _as_sequence(result.get("rules")):
        lines.append(f"- {rule}")
    for finding in _as_sequence(result.get("findings")):
        finding_map = _as_mapping(finding)
        lines.extend(
            [
                "",
                f"## {finding_map.get('finding_id')}",
                "",
                f"- claim: {finding_map.get('claim_zh')}",
                f"- risk: {finding_map.get('risk_zh')}",
                f"- next_check: {finding_map.get('next_check_zh')}",
                "",
                "```json",
                _to_pretty_json(
                    {
                        "evidence_refs": finding_map.get("evidence_refs", []),
                        "sample_refs": finding_map.get("sample_refs", []),
                        "supporting_sample_ids": finding_map.get("supporting_sample_ids", []),
                        "metrics": finding_map.get("metrics", {}),
                    }
                ),
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_ai_review_result(
    result: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write persisted AI review result JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(result["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    focus = str(result["focus"])
    json_path = target_dir / f"ai_review_result.{focus}.json"
    markdown_path = target_dir / f"ai_review_result.{focus}.zh.md"
    json_path.write_text(_to_pretty_json(result), encoding="utf-8")
    markdown_path.write_text(render_ai_review_result_markdown_zh(result), encoding="utf-8")
    return json_path, markdown_path


def build_review_experiment_candidates(
    findings_or_path: Mapping[str, Any] | str | Path,
    *,
    sample_batch: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """Build validation candidates from review findings without tuning."""

    findings, findings_path = _load_findings(findings_or_path)
    batch = None
    batch_path = None
    if sample_batch is not None:
        batch, batch_path = _load_sample_batch(sample_batch)
    candidates = []
    for finding in _as_sequence(findings.get("findings")):
        candidate = _candidate_from_finding(_as_mapping(finding), batch)
        if candidate is not None:
            candidates.append(candidate)
    return {
        "schema": REVIEW_EXPERIMENT_CANDIDATES_SCHEMA,
        "run_id": findings.get("run_id"),
        "focus": findings.get("focus"),
        "source_findings": str(findings_path) if findings_path is not None else None,
        "source_sample_batch": str(batch_path) if batch_path is not None else None,
        "source_dir": findings.get("source_dir"),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rules": [
            "候选只用于下一轮验证设计，不直接改变当前策略参数。",
            "候选必须引用 finding_id 和 sample_refs。",
            "新增维度应优先进入 decision-time evidence，再由报告和 AI 工具消费。",
            "不要把后验反弹或机会成本样本写成因果结论。",
        ],
    }


def render_review_experiment_candidates_markdown_zh(candidates: Mapping[str, Any]) -> str:
    """Render review-derived experiment candidates as Chinese Markdown."""

    lines = [
        "# 复盘实验候选",
        "",
        f"- schema: `{candidates.get('schema')}`",
        f"- run_id: `{candidates.get('run_id')}`",
        f"- focus: `{candidates.get('focus')}`",
        f"- candidate_count: `{candidates.get('candidate_count')}`",
        "",
        "## 规则",
    ]
    for rule in _as_sequence(candidates.get("rules")):
        lines.append(f"- {rule}")
    for candidate in _as_sequence(candidates.get("candidates")):
        candidate_map = _as_mapping(candidate)
        lines.extend(
            [
                "",
                f"## {candidate_map.get('title_zh')}",
                "",
                f"- candidate_id: `{candidate_map.get('candidate_id')}`",
                f"- direction: `{candidate_map.get('direction')}`",
                f"- type: `{candidate_map.get('candidate_type')}`",
                f"- purpose: {candidate_map.get('purpose_zh')}",
                f"- validation: {candidate_map.get('validation_plan_zh')}",
                "",
                "```json",
                _to_pretty_json(candidate_map),
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_review_experiment_candidates(
    candidates: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write review experiment candidates JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(candidates["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    focus = str(candidates["focus"])
    json_path = target_dir / f"review_experiment_candidates.{focus}.json"
    markdown_path = target_dir / f"review_experiment_candidates.{focus}.zh.md"
    json_path.write_text(_to_pretty_json(candidates), encoding="utf-8")
    markdown_path.write_text(render_review_experiment_candidates_markdown_zh(candidates), encoding="utf-8")
    return json_path, markdown_path


def build_review_experiment_drafts(
    candidates_or_path: Mapping[str, Any] | str | Path,
    *,
    base_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build manually confirmable YAML experiment drafts from candidates."""

    candidates, candidates_path = _load_candidates(candidates_or_path)
    base_config = _load_yaml_mapping(base_config_path) if base_config_path is not None else {}
    base_run_id = _as_mapping(base_config.get("run")).get("id", candidates.get("run_id"))
    drafts = []
    for candidate in _as_sequence(candidates.get("candidates")):
        candidate_map = _as_mapping(candidate)
        draft_id = _draft_id(candidate_map)
        drafts.append(
            {
                "draft_id": draft_id,
                "status": "draft_requires_manual_confirmation",
                "source_candidate_id": candidate_map.get("candidate_id"),
                "title_zh": candidate_map.get("title_zh"),
                "purpose_zh": candidate_map.get("purpose_zh"),
                "base_config_path": str(base_config_path) if base_config_path is not None else None,
                "suggested_run_id": f"{base_run_id}__review__{draft_id}",
                "candidate_direction": candidate_map.get("direction"),
                "candidate_type": candidate_map.get("candidate_type"),
                "suggested_change": candidate_map.get("suggested_change"),
                "validation_plan_zh": candidate_map.get("validation_plan_zh"),
                "evidence_refs": candidate_map.get("evidence_refs", []),
                "sample_refs": candidate_map.get("sample_refs", []),
                "manual_steps": _draft_manual_steps(candidate_map),
                "run_plan_patch": _draft_run_plan_patch(base_run_id, draft_id, candidate_map),
                "not_runnable_until": "人工确认 run_plan_patch 并转成合法 RunPlan YAML",
            }
        )
    return {
        "schema": REVIEW_EXPERIMENT_DRAFTS_SCHEMA,
        "run_id": candidates.get("run_id"),
        "focus": candidates.get("focus"),
        "source_candidates": str(candidates_path) if candidates_path is not None else None,
        "source_dir": candidates.get("source_dir"),
        "base_config_path": str(base_config_path) if base_config_path is not None else None,
        "draft_count": len(drafts),
        "drafts": drafts,
        "rules": [
            "这些 YAML 是实验草案，不是可直接采用的策略配置。",
            "必须人工确认 run_plan_patch 后，才允许生成可执行 RunPlan。",
            "新增归因维度必须先进入 decision-time evidence。",
            "不得把候选中的后验观察直接写成买卖规则。",
        ],
    }


def render_review_experiment_drafts_markdown_zh(drafts: Mapping[str, Any]) -> str:
    """Render review experiment drafts as Chinese Markdown."""

    lines = [
        "# 复盘实验 YAML 草案",
        "",
        f"- schema: `{drafts.get('schema')}`",
        f"- run_id: `{drafts.get('run_id')}`",
        f"- focus: `{drafts.get('focus')}`",
        f"- draft_count: `{drafts.get('draft_count')}`",
        "",
        "## 规则",
    ]
    for rule in _as_sequence(drafts.get("rules")):
        lines.append(f"- {rule}")
    for draft in _as_sequence(drafts.get("drafts")):
        draft_map = _as_mapping(draft)
        lines.extend(
            [
                "",
                f"## {draft_map.get('title_zh')}",
                "",
                f"- draft_id: `{draft_map.get('draft_id')}`",
                f"- source_candidate_id: `{draft_map.get('source_candidate_id')}`",
                f"- suggested_run_id: `{draft_map.get('suggested_run_id')}`",
                f"- validation: {draft_map.get('validation_plan_zh')}",
                "",
                "```yaml",
                yaml.safe_dump(draft_map, allow_unicode=True, sort_keys=False).strip(),
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_review_experiment_drafts(
    drafts: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, tuple[Path, ...]]:
    """Write experiment draft manifest and individual YAML draft files."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    focus = str(drafts["focus"])
    json_path = target_dir / f"review_experiment_drafts.{focus}.json"
    markdown_path = target_dir / f"review_experiment_drafts.{focus}.zh.md"
    json_path.write_text(_to_pretty_json(drafts), encoding="utf-8")
    markdown_path.write_text(render_review_experiment_drafts_markdown_zh(drafts), encoding="utf-8")
    yaml_paths = []
    for draft in _as_sequence(drafts.get("drafts")):
        draft_map = _as_mapping(draft)
        path = target_dir / f"{draft_map.get('draft_id')}.yaml"
        path.write_text(yaml.safe_dump(draft_map, allow_unicode=True, sort_keys=False), encoding="utf-8")
        yaml_paths.append(path)
    return json_path, markdown_path, tuple(yaml_paths)


def build_review_experiment_confirmed_run_plan(
    draft_or_path: Mapping[str, Any] | str | Path,
    *,
    base_config_path: str | Path | None = None,
    confirmed_by: str = "manual",
    confirmation_note: str | None = None,
) -> dict[str, Any]:
    """Convert one manually confirmed draft into a validated legal RunPlan YAML payload."""

    draft, draft_path = _load_draft(draft_or_path)
    resolved_base_config_path = base_config_path or draft.get("base_config_path")
    if resolved_base_config_path is None:
        raise ValueError("base_config_path is required when the draft does not include base_config_path")

    base_config = _load_yaml_mapping(resolved_base_config_path)
    patch = _as_mapping(draft.get("run_plan_patch"))
    legal_patch, omitted_patch_keys = _legal_run_plan_patch(patch)
    if not legal_patch:
        raise ValueError("draft does not contain any legal RunPlan patch keys")

    legal_run_plan = _deep_merge_mapping(base_config, legal_patch)
    RunPlan.from_mapping(legal_run_plan)
    return {
        "schema": REVIEW_EXPERIMENT_CONFIRMED_RUN_PLAN_SCHEMA,
        "status": "confirmed_run_plan_generated",
        "confirmed_by": confirmed_by,
        "confirmation_note": confirmation_note,
        "source_draft": str(draft_path) if draft_path is not None else None,
        "source_candidate_id": draft.get("source_candidate_id"),
        "draft_id": draft.get("draft_id"),
        "candidate_direction": draft.get("candidate_direction"),
        "candidate_type": draft.get("candidate_type"),
        "base_config_path": str(resolved_base_config_path),
        "run_id": _as_mapping(legal_run_plan.get("run")).get("id"),
        "legal_run_plan": legal_run_plan,
        "omitted_patch_keys": omitted_patch_keys,
        "boundary_rules": [
            "只合并合法 RunPlan 顶层字段；review_candidate 等复盘元数据不会写入可执行配置。",
            "该确认器不新增策略参数，不根据复盘结果自动调参。",
            "生成的 RunPlan 已通过 RunPlan.from_mapping 验证，但执行前仍需人工确认样本范围和数据设置。",
        ],
    }


def render_review_experiment_confirmed_run_plan_markdown_zh(confirmation: Mapping[str, Any]) -> str:
    """Render confirmed experiment RunPlan metadata as Chinese Markdown."""

    lines = [
        "# 已确认复盘实验 RunPlan",
        "",
        f"- schema: `{confirmation.get('schema')}`",
        f"- status: `{confirmation.get('status')}`",
        f"- draft_id: `{confirmation.get('draft_id')}`",
        f"- source_candidate_id: `{confirmation.get('source_candidate_id')}`",
        f"- run_id: `{confirmation.get('run_id')}`",
        f"- confirmed_by: `{confirmation.get('confirmed_by')}`",
        "",
        "## 边界",
    ]
    for rule in _as_sequence(confirmation.get("boundary_rules")):
        lines.append(f"- {rule}")
    lines.extend(
        [
            "",
            "## 省略的草稿字段",
            "",
            "```json",
            _to_pretty_json(confirmation.get("omitted_patch_keys", [])),
            "```",
            "",
            "## RunPlan",
            "",
            "```yaml",
            yaml.safe_dump(confirmation.get("legal_run_plan", {}), allow_unicode=True, sort_keys=False).strip(),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_review_experiment_confirmed_run_plan(
    confirmation: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    """Write a confirmed RunPlan YAML plus confirmation manifest."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    draft_id = str(confirmation.get("draft_id") or "review_experiment")
    json_path = target_dir / f"review_experiment_confirmed.{draft_id}.json"
    markdown_path = target_dir / f"review_experiment_confirmed.{draft_id}.zh.md"
    run_plan_path = target_dir / f"{draft_id}.run.yaml"
    json_path.write_text(_to_pretty_json(confirmation), encoding="utf-8")
    markdown_path.write_text(render_review_experiment_confirmed_run_plan_markdown_zh(confirmation), encoding="utf-8")
    run_plan_path.write_text(
        yaml.safe_dump(confirmation.get("legal_run_plan", {}), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return json_path, markdown_path, run_plan_path


def build_review_sample(
    run_dir: str | Path,
    *,
    kind: str,
    sample_index: int | None = None,
    trade_index: int | None = None,
    context_limit: int = 20,
) -> dict[str, Any]:
    """Build a focused evidence packet for one review sample."""

    if kind not in REVIEW_SAMPLE_KINDS:
        raise ValueError(f"Unsupported review sample kind: {kind}")
    if context_limit <= 0:
        raise ValueError("context_limit must be greater than 0")

    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    artifacts, source_artifacts = _load_run_artifacts(run_path)
    trade_review = _as_mapping(artifacts.get("trade_review"))
    sample = _select_sample(trade_review, kind=kind, sample_index=sample_index, trade_index=trade_index)
    sample_map = _as_mapping(sample)
    run_id = _run_id(run_path, _as_mapping(artifacts.get("run_plan")))
    related = _related_evidence(artifacts, sample_map, kind=kind, context_limit=context_limit)
    lookup = {
        "kind": kind,
        "sample_index": sample_index,
        "trade_index": trade_index,
        "context_limit": context_limit,
    }
    return {
        "schema": REVIEW_SAMPLE_SCHEMA,
        "run_id": run_id,
        "source_dir": str(run_path),
        "source_artifacts": source_artifacts,
        "lookup": lookup,
        "sample_kind": kind,
        "sample_id": _sample_id(kind, sample_map),
        "sample": sample_map,
        "related": related,
        "ai_contract": {
            "purpose": "给 AI/Skill 分析单个复盘样本的最小证据包。",
            "rules": [
                "只引用本 sample packet 和 source_artifacts 指向的原始证据。",
                "结论必须引用 trade_index 或 sample_index。",
                "缺失字段保持缺失，不补 0、不补 False。",
                "样本反查只说明当时证据，不证明策略应该买入、卖出或加仓。",
            ],
        },
    }


def render_review_sample_markdown_zh(packet: Mapping[str, Any]) -> str:
    """Render one review sample packet as Chinese Markdown."""

    lines = [
        "# AI 样本反查包",
        "",
        f"- schema: `{packet.get('schema')}`",
        f"- run_id: `{packet.get('run_id')}`",
        f"- sample_kind: `{packet.get('sample_kind')}`",
        f"- sample_id: `{packet.get('sample_id')}`",
        f"- source_dir: `{packet.get('source_dir')}`",
        "",
        "## 样本",
        "```json",
        _to_pretty_json(packet.get("sample", {})),
        "```",
        "",
        "## 关联证据",
        "```json",
        _to_pretty_json(packet.get("related", {})),
        "```",
        "",
        "## AI 使用规则",
    ]
    for rule in _as_sequence(_as_mapping(packet.get("ai_contract")).get("rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_review_sample(
    packet: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write one sample drill-down packet as JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(packet["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    sample_id = str(packet["sample_id"])
    json_path = target_dir / f"review_sample.{sample_id}.json"
    markdown_path = target_dir / f"review_sample.{sample_id}.zh.md"
    json_path.write_text(_to_pretty_json(packet), encoding="utf-8")
    markdown_path.write_text(render_review_sample_markdown_zh(packet), encoding="utf-8")
    return json_path, markdown_path


def _load_findings(findings_or_path: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(findings_or_path, Mapping):
        return findings_or_path, None
    path = Path(findings_or_path)
    return json.loads(path.read_text(encoding="utf-8")), path


def _load_sample_batch(batch_or_path: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(batch_or_path, Mapping):
        return batch_or_path, None
    path = Path(batch_or_path)
    return json.loads(path.read_text(encoding="utf-8")), path


def _load_brief(brief_or_path: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(brief_or_path, Mapping):
        return brief_or_path, None
    path = Path(brief_or_path)
    return json.loads(path.read_text(encoding="utf-8")), path


def _load_environment_fit_comparison(
    comparison_or_path: Mapping[str, Any] | str | Path,
) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(comparison_or_path, Mapping):
        return comparison_or_path, None
    path = Path(comparison_or_path)
    return json.loads(path.read_text(encoding="utf-8")), path


def _load_candidates(candidates_or_path: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(candidates_or_path, Mapping):
        return candidates_or_path, None
    path = Path(candidates_or_path)
    return json.loads(path.read_text(encoding="utf-8")), path


def _load_draft(draft_or_path: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(draft_or_path, Mapping):
        return draft_or_path, None
    path = Path(draft_or_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload, path


def _load_yaml_mapping(path: str | Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, Mapping) else {}


def _legal_run_plan_patch(patch: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    legal = {key: patch[key] for key in RUN_PLAN_TOP_LEVEL_KEYS if key in patch}
    omitted = [str(key) for key in patch if key not in RUN_PLAN_TOP_LEVEL_KEYS]
    return legal, omitted


def _deep_merge_mapping(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge_mapping(_as_mapping(merged.get(key)), value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _source_dir_from_findings(findings: Mapping[str, Any], run_dir: str | Path | None) -> Path:
    if run_dir is not None:
        return Path(run_dir)
    source_dir = findings.get("source_dir")
    if source_dir is None:
        raise ValueError("run_dir is required when findings does not include source_dir")
    return Path(str(source_dir))


def _unique_sample_refs(findings: Mapping[str, Any], *, limit_per_finding: int) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen = set()
    for finding in _as_sequence(findings.get("findings")):
        finding_map = _as_mapping(finding)
        for ref in _as_sequence(finding_map.get("sample_refs"))[:limit_per_finding]:
            ref_map = _as_mapping(ref)
            key = _sample_ref_key(ref_map)
            if key in seen or ref_map.get("kind") not in REVIEW_SAMPLE_KINDS:
                continue
            seen.add(key)
            refs.append(
                _pick_present(
                    ref_map,
                    ("kind", "sample_index", "trade_index", "symbol", "trade_date", "entry_date", "exit_date"),
                )
            )
    return refs


def _sample_ref_key(ref: Mapping[str, Any]) -> tuple[Any, Any]:
    kind = ref.get("kind")
    if kind == "trade":
        return kind, ref.get("trade_index")
    return kind, ref.get("sample_index")


def _expanded_sample_lookup(batch: Mapping[str, Any]) -> dict[tuple[Any, Any], Mapping[str, Any]]:
    lookup = {}
    for sample in _as_sequence(batch.get("samples")):
        sample_map = _as_mapping(sample)
        ref = _as_mapping(sample_map.get("sample_ref"))
        lookup[_sample_ref_key(ref)] = sample_map
    return lookup


def _sample_related_summary(packet: Mapping[str, Any]) -> dict[str, Any]:
    related = _as_mapping(packet.get("related"))
    lifecycle = _as_mapping(related.get("trade_lifecycle"))
    post_exit = _as_mapping(related.get("post_exit_observation"))
    return {
        "trade_lifecycle": _pick_present(
            lifecycle,
            ("trade_index", "symbol", "outcome", "entry_date", "exit_date", "exit_reason", "return_pct"),
        ),
        "post_exit_observation": _pick_present(
            post_exit,
            (
                "trade_index",
                "symbol",
                "exit_date",
                "exit_reason",
                "sold_too_early",
                "max_high_return_pct",
                "primary_window_close_return_pct",
            ),
        ),
        "closed_trade": related.get("closed_trade"),
        "signal_intent_match_count": related.get("signal_intent_match_count"),
        "execution_event_match_count": related.get("execution_event_match_count"),
        "signal_intents": [_signal_summary(row) for row in _as_sequence(related.get("signal_intents"))[:3]],
        "execution_events": [_execution_summary(row) for row in _as_sequence(related.get("execution_events"))[:3]],
        "drill_down_hints": related.get("drill_down_hints", []),
    }


def _signal_summary(row: Any) -> dict[str, Any]:
    row_map = _as_mapping(row)
    signal_values = _as_mapping(row_map.get("signal_values"))
    attribution = _as_mapping(signal_values.get("attribution"))
    return {
        "intent_type": row_map.get("intent_type"),
        "symbol": row_map.get("symbol"),
        "trade_date": row_map.get("trade_date"),
        "method_name": row_map.get("method_name"),
        "reason_code": row_map.get("reason_code"),
        "blocked_by": row_map.get("blocked_by"),
        "checks": _first_present(attribution.get("checks"), signal_values.get("checks")),
        "categories": attribution.get("categories"),
    }


def _execution_summary(row: Any) -> dict[str, Any]:
    return _pick_present(
        _as_mapping(row),
        (
            "event_date",
            "signal_date",
            "symbol",
            "side",
            "event_type",
            "status",
            "reason_code",
            "blocked_by",
            "requested_quantity",
            "executable_quantity",
            "executed_quantity",
            "executed_price",
        ),
    )


def _review_brief_skill_contract() -> dict[str, Any]:
    return {
        "purpose": "给后续 Skill 使用的自动复盘输入，要求复盘结论全部带证据引用。",
        "rules": [
            "只使用 brief、findings、sample batch、sample packet 和 source artifacts 中的证据。",
            "环境适配结论优先读取 environment_fit_summary，再回到 Overview 和 sample refs 查证。",
            "每条结论必须引用 finding_id，并至少引用一个 trade_index 或 sample_index。",
            "缺失字段保持缺失；不要把缺失值补成 0、False 或中性描述。",
            "不要把后验走势写成因果结论，也不要直接给出参数调优建议。",
        ],
        "expected_output_schema": {
            "run_id": "string",
            "summary_zh": "string",
            "findings": [
                {
                    "finding_id": "string",
                    "claim_zh": "string",
                    "evidence_refs": "list",
                    "sample_refs": "list",
                    "risk_zh": "string",
                    "next_check_zh": "string",
                }
            ],
        },
    }


def _review_result_summary(brief: Mapping[str, Any]) -> str:
    overview = _as_mapping(brief.get("overview"))
    validation = _as_mapping(overview.get("evidence_validation"))
    return (
        f"run_id={brief.get('run_id')} focus={brief.get('focus')}，"
        f"evidence_validation={validation.get('status')}，"
        f"共生成 {brief.get('section_count')} 个复盘 finding。"
        "该结果用于记录证据化复盘，不代表策略调优结论。"
    )


def _environment_fit_comparison_review(
    comparison: Mapping[str, Any],
    *,
    comparison_path: Path | None,
) -> dict[str, Any]:
    checks = [_as_mapping(check) for check in _as_sequence(comparison.get("best_environment_stability"))]
    status_parts = [
        f"{check.get('criterion_zh')}={check.get('status_zh')}"
        for check in checks
        if check.get("criterion_zh") is not None and check.get("status_zh") is not None
    ]
    risky = [
        check
        for check in checks
        if check.get("status") not in ("stable",)
    ]
    sample_refs = list(_as_sequence(comparison.get("drill_down_sample_refs")))[:12]
    return {
        "finding_id": "environment-fit-comparison-001",
        "claim_zh": (
            f"环境适配对比覆盖 {comparison.get('source_count')} 个 run，"
            f"共同环境 {comparison.get('common_environment_count')} 个；"
            f"最佳环境状态：{'；'.join(status_parts) if status_parts else '缺失'}。"
        ),
        "evidence_refs": [
            {
                "artifact": "environment_fit_comparison",
                "path": str(comparison_path) if comparison_path is not None else None,
                "section": "best_environment_stability",
            }
        ],
        "sample_refs": sample_refs,
        "supporting_sample_ids": [
            f"{_as_mapping(ref).get('run_id')}:trade.{_as_mapping(ref).get('trade_index')}"
            for ref in sample_refs
        ],
        "metrics": {
            "run_ids": comparison.get("run_ids", []),
            "common_environment_count": comparison.get("common_environment_count"),
            "best_environment_stability": checks,
        },
        "risk_zh": (
            "最佳环境存在变化或样本风险，不能声明稳定适配。"
            if risky
            else "最佳环境在对比 run 中一致；仍需结合样本量和交易下钻确认。"
        ),
        "next_check_zh": "优先反查 sample_refs 中的 trade_index，再判断是否需要扩大样本或补充环境维度。",
    }


def _candidate_from_finding(finding: Mapping[str, Any], batch: Mapping[str, Any] | None) -> dict[str, Any] | None:
    finding_id = str(finding.get("finding_id"))
    direction = finding.get("direction")
    metrics = _as_mapping(finding.get("metrics"))
    refs = list(_as_sequence(finding.get("sample_refs"))[:5])
    batch_sample_ids = _candidate_sample_ids(batch, refs)
    if direction == "post_exit_review" and finding_id.startswith("sold-too-early"):
        return _candidate(
            finding=finding,
            candidate_id="candidate.post_exit.sold_too_early_dimensions",
            direction="post_exit_framework",
            candidate_type="review_dimension",
            title_zh="扩展卖飞复盘维度",
            purpose_zh="围绕最大反弹样本补充退出日证据分组，判断是否缺少可解释维度。",
            suggested_change={
                "artifact_or_config": "analysis.post_exit / exit attribution evidence",
                "change_zh": "优先检查 symbol/industry/market 退出证据覆盖，再决定是否新增退出归因因子。",
                "not_allowed": ["不要直接把卖飞样本变成持仓规则", "不要把反弹幅度作为调参目标"],
            },
            validation_plan_zh="对 top 卖飞 trade_index 生成 sample drill-down，核对 exit_checks、entry_checks 和后续窗口完整性。",
            metrics=metrics,
            batch_sample_ids=batch_sample_ids,
        )
    if direction == "post_exit_review" and finding_id.startswith("stop-loss-rebound"):
        return _candidate(
            finding=finding,
            candidate_id="candidate.post_exit.stop_loss_rebound_groups",
            direction="post_exit_framework",
            candidate_type="grouping_probe",
            title_zh="止损后反弹分组验证",
            purpose_zh="按止损样本的退出证据分组，检查反弹是否集中在特定市场/行业/个股上下文。",
            suggested_change={
                "artifact_or_config": "post_exit_analysis.factor_group_summaries",
                "change_zh": "新增或检查退出证据分组，而不是直接改变止损参数。",
                "not_allowed": ["不要用后验反弹证明止损错误"],
            },
            validation_plan_zh="批量展开 top 止损反弹样本，比较 exit_checks 与 rebound threshold summaries。",
            metrics=metrics,
            batch_sample_ids=batch_sample_ids,
        )
    if direction == "opportunity_review":
        return _candidate(
            finding=finding,
            candidate_id="candidate.execution.opportunity_cost_blocks",
            direction="execution_constraint_review",
            candidate_type="block_reason_probe",
            title_zh="机会成本阻断原因验证",
            purpose_zh="检查机会成本样本是否集中在特定阻断原因、价格区间或一手约束上。",
            suggested_change={
                "artifact_or_config": "sizing/execution review artifacts",
                "change_zh": "把高影响 blocked_by 样本作为 sizing 和执行约束复盘入口。",
                "not_allowed": ["不要把被阻断后的上涨写成当时应该买入"],
            },
            validation_plan_zh="展开 top opportunity sample_index，核对 signal_audit、execution_audit 和 blocked_by 是否一致。",
            metrics=metrics,
            batch_sample_ids=batch_sample_ids,
        )
    if direction == "add_on_review":
        return _candidate(
            finding=finding,
            candidate_id="candidate.add_on.sample_coverage",
            direction="add_on_framework_validation",
            candidate_type="sample_size_probe",
            title_zh="加仓样本覆盖验证",
            purpose_zh="确认真实加仓点的证据链完整性，并判断是否需要扩大样本来验证加仓框架。",
            suggested_change={
                "artifact_or_config": "strategy.add_on_method / trade_review.add_on_entry_points",
                "change_zh": "优先扩大可观测样本和归因维度，暂不调加仓参数。",
                "not_allowed": ["不要用单个加仓样本做策略结论"],
            },
            validation_plan_zh="反查每个 add_on sample_index 的 add_on_date、execution events、trade lifecycle 和 follow_up。",
            metrics=metrics,
            batch_sample_ids=batch_sample_ids,
        )
    if direction == "environment_fit_review":
        return _candidate(
            finding=finding,
            candidate_id="candidate.environment_fit.sample_stability",
            direction="environment_fit_validation",
            candidate_type="sample_stability_probe",
            title_zh="环境适配稳定性验证",
            purpose_zh="验证当前 environment_fit 中表现突出的入场环境是否能在更大股票池或更长年份中保持稳定。",
            suggested_change={
                "artifact_or_config": "environment_fit.json / environment_fit_comparison.json",
                "change_zh": "扩大股票池或年份后重跑同一策略，再用 att-compare-environment-fit 比较最佳环境、资金收益率和低样本组合数量。",
                "not_allowed": ["不要直接把环境统计结论转成买卖规则", "不要基于低样本组合调参"],
            },
            validation_plan_zh="用相同策略在更大样本生成 environment_fit，对比 best_by_net_pnl、best_by_return_on_entry_value、low_sample_combination_count 和代表 trade_index 是否仍集中。",
            metrics=metrics,
            batch_sample_ids=batch_sample_ids,
        )
    if direction == "evidence_validation":
        return _candidate(
            finding=finding,
            candidate_id="candidate.validation.evidence_gate",
            direction="evidence_validation",
            candidate_type="quality_gate",
            title_zh="复盘前证据门禁",
            purpose_zh="保持 evidence_validation 作为 AI 复盘前置门禁。",
            suggested_change={
                "artifact_or_config": "evidence_validation.json",
                "change_zh": "如果 status 不是 ok，先修正证据链，再生成 findings/brief。",
                "not_allowed": ["不要在证据失败时继续输出策略结论"],
            },
            validation_plan_zh="每次真实回测后先检查 validation finding，再进入其它复盘候选。",
            metrics=metrics,
            batch_sample_ids=batch_sample_ids,
        )
    return None


def _candidate(
    *,
    finding: Mapping[str, Any],
    candidate_id: str,
    direction: str,
    candidate_type: str,
    title_zh: str,
    purpose_zh: str,
    suggested_change: Mapping[str, Any],
    validation_plan_zh: str,
    metrics: Mapping[str, Any],
    batch_sample_ids: Sequence[str],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "status": "candidate",
        "direction": direction,
        "candidate_type": candidate_type,
        "title_zh": title_zh,
        "purpose_zh": purpose_zh,
        "source_finding_id": finding.get("finding_id"),
        "why_from_findings_zh": finding.get("summary_zh"),
        "metrics": metrics,
        "evidence_refs": finding.get("evidence_refs", []),
        "sample_refs": finding.get("sample_refs", []),
        "sample_batch_ids": list(batch_sample_ids),
        "suggested_change": dict(suggested_change),
        "validation_plan_zh": validation_plan_zh,
        "caveat_zh": finding.get("caveat_zh"),
    }


def _candidate_sample_ids(batch: Mapping[str, Any] | None, refs: Sequence[Any]) -> list[str]:
    if batch is None:
        return []
    lookup = _expanded_sample_lookup(batch)
    sample_ids = []
    for ref in refs:
        sample = lookup.get(_sample_ref_key(_as_mapping(ref)))
        if sample is not None and sample.get("sample_id") is not None:
            sample_ids.append(str(sample["sample_id"]))
    return sample_ids


def _draft_id(candidate: Mapping[str, Any]) -> str:
    raw = str(candidate.get("candidate_id", "candidate")).removeprefix("candidate.")
    return raw.replace(".", "_").replace("-", "_")


def _draft_manual_steps(candidate: Mapping[str, Any]) -> list[str]:
    steps = [
        "读取 source_candidate_id 对应的 candidate 和 sample_refs。",
        "用 review_sample 或 review_sample_batch 核对证据是否完整。",
        "人工决定是否需要新增 evidence producer、分组维度或配置变体。",
        "确认后再把 run_plan_patch 转成合法 RunPlan YAML 并执行回测。",
    ]
    direction = candidate.get("direction")
    if direction == "evidence_validation":
        return ["先确认 evidence_validation.status == ok，再生成任何实验配置。"]
    if direction == "environment_fit_validation":
        return [
            "读取 source_candidate_id 对应的 environment_fit candidate 和 sample_refs。",
            "扩大股票池或年份后重跑相同策略；不要修改买入、卖出、加仓或仓位参数。",
            "比较新旧 environment_fit.json 的最佳环境、资金收益率、低样本组合数量和代表 trade_index。",
            "如果需要新增环境维度，先补 decision-time evidence producer，再重新生成报告和 review packet。",
        ]
    return steps


def _draft_run_plan_patch(base_run_id: Any, draft_id: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "run": {"id": f"{base_run_id}__review__{draft_id}"},
        "review_candidate": {
            "source_candidate_id": candidate.get("candidate_id"),
            "manual_confirmation_required": True,
            "validation_plan_zh": candidate.get("validation_plan_zh"),
        },
    }
    direction = candidate.get("direction")
    if direction == "post_exit_framework":
        patch["analysis"] = {
            "post_exit": {
                "enabled": True,
                "review_note": "人工确认是否新增退出证据分组；不要直接修改止损参数。",
            }
        }
    elif direction == "execution_constraint_review":
        patch["review_candidate"]["inspect_artifacts"] = ["signal_audit.json", "execution_audit.json", "sizing_audit.json"]
    elif direction == "add_on_framework_validation":
        patch["review_candidate"]["inspect_artifacts"] = ["trade_review.json", "trade_lifecycle.json", "execution_audit.json"]
    elif direction == "environment_fit_validation":
        patch["review_candidate"]["inspect_artifacts"] = [
            "environment_fit.json",
            "environment_fit_comparison.json",
            "environment_fit_comparison.zh.md",
            "review_packet.all.json",
            "review_findings.all.json",
        ]
        patch["review_candidate"]["comparison_dimensions"] = [
            "best_by_net_pnl",
            "best_by_return_on_entry_value",
            "low_sample_combination_count",
            "trade_contributions",
        ]
        patch["review_candidate"]["validation_note"] = "扩大样本验证环境适配稳定性，不直接修改策略参数。"
    elif direction == "evidence_validation":
        patch["review_candidate"]["inspect_artifacts"] = ["evidence_validation.json"]
    return patch


def _build_findings(packet: Mapping[str, Any], *, top: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for section in _as_sequence(packet.get("sections")):
        section_map = _as_mapping(section)
        name = section_map.get("name")
        if name == "validation":
            findings.append(_validation_finding(section_map, packet))
        elif name == "sold_too_early":
            findings.append(_sold_too_early_finding(section_map, top=top))
        elif name == "stop_loss_rebound":
            findings.append(_stop_loss_rebound_finding(section_map, top=top))
        elif name == "opportunity_cost":
            findings.append(_opportunity_cost_finding(section_map, top=top))
        elif name == "add_on":
            findings.append(_add_on_finding(section_map, top=top))
        elif name == "environment_fit":
            findings.append(_environment_fit_finding(section_map, top=top))
    return findings


def _validation_finding(section: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, Any]:
    overview = _as_mapping(packet.get("overview"))
    validation = _as_mapping(overview.get("evidence_validation"))
    status = validation.get("status")
    return {
        "finding_id": "validation-001",
        "direction": "evidence_validation",
        "title_zh": "证据校验状态",
        "summary_zh": f"当前复盘包的 evidence_validation 状态为 {status}。",
        "metrics": {
            "status": status,
            "error_count": validation.get("error_count"),
            "warning_count": validation.get("warning_count"),
        },
        "evidence_refs": [{"artifact": "review_packet", "section": section.get("name")}],
        "sample_refs": [],
        "next_action_zh": "如果 status 不是 ok，先用 validation section 的 issue 修正证据链，再做复盘。",
        "caveat_zh": "校验通过只说明 artifact 间一致性，不代表策略有效。",
    }


def _sold_too_early_finding(section: Mapping[str, Any], *, top: int) -> dict[str, Any]:
    samples = _as_sequence(section.get("samples"))
    top_samples = samples[:top]
    max_rebound = _max_metric(top_samples, "max_high_return_pct")
    return {
        "finding_id": "sold-too-early-001",
        "direction": "post_exit_review",
        "title_zh": "卖飞样本复盘入口",
        "summary_zh": (
            f"该 section 可用卖飞样本 {section.get('available_sample_count')} 个，"
            f"当前包选取 {section.get('selected_sample_count')} 个；样本内最大高点反弹为 {max_rebound}。"
        ),
        "metrics": {
            "available_sample_count": section.get("available_sample_count"),
            "selected_sample_count": section.get("selected_sample_count"),
            "max_high_return_pct_in_selected": max_rebound,
        },
        "evidence_refs": [{"artifact": "review_packet", "section": section.get("name")}],
        "sample_refs": _trade_refs(top_samples),
        "next_action_zh": "优先用 att-review-sample 反查反弹最大的 trade_index，查看入场和退出证据。",
        "caveat_zh": "卖飞标签是后验复盘线索，不是持仓规则或止损失效证明。",
    }


def _stop_loss_rebound_finding(section: Mapping[str, Any], *, top: int) -> dict[str, Any]:
    samples = _as_sequence(section.get("samples"))
    summaries = _as_sequence(section.get("summaries"))
    return {
        "finding_id": "stop-loss-rebound-001",
        "direction": "post_exit_review",
        "title_zh": "止损后反弹复盘入口",
        "summary_zh": (
            f"该 section 可用止损样本 {section.get('available_sample_count')} 个，"
            f"当前包选取 {section.get('selected_sample_count')} 个，profile 汇总 {len(summaries)} 个。"
        ),
        "metrics": {
            "available_sample_count": section.get("available_sample_count"),
            "selected_sample_count": section.get("selected_sample_count"),
            "top_profile": summaries[0] if summaries else None,
        },
        "evidence_refs": [{"artifact": "review_packet", "section": section.get("name")}],
        "sample_refs": _trade_refs(samples[:top]),
        "next_action_zh": "按最大反弹样本反查 exit_checks 和 entry_checks，判断需要新增哪些退出归因维度。",
        "caveat_zh": "止损后反弹不等价于止损错误，需要结合风险暴露和未来窗口完整性。",
    }


def _opportunity_cost_finding(section: Mapping[str, Any], *, top: int) -> dict[str, Any]:
    samples = _as_sequence(section.get("samples"))
    summaries = _as_sequence(section.get("summaries"))
    best_sample = _as_mapping(samples[0]) if samples else {}
    return {
        "finding_id": "opportunity-cost-001",
        "direction": "opportunity_review",
        "title_zh": "机会成本复盘入口",
        "summary_zh": (
            f"该 section 可用机会样本 {section.get('available_sample_count')} 个，"
            f"当前包选取 {section.get('selected_sample_count')} 个；最高样本 blocked_by={best_sample.get('blocked_by')}。"
        ),
        "metrics": {
            "available_sample_count": section.get("available_sample_count"),
            "selected_sample_count": section.get("selected_sample_count"),
            "top_summary": summaries[0] if summaries else None,
            "top_sample_follow_up": best_sample.get("follow_up"),
        },
        "evidence_refs": [{"artifact": "review_packet", "section": section.get("name")}],
        "sample_refs": _sample_refs(samples[:top], kind="opportunity"),
        "next_action_zh": "优先反查 sample_index 最大机会样本的 signal/execution 证据，确认阻断原因是否符合预期。",
        "caveat_zh": "机会成本只描述被阻断后的走势，不能推出当时应该成交。",
    }


def _add_on_finding(section: Mapping[str, Any], *, top: int) -> dict[str, Any]:
    samples = _as_sequence(section.get("samples"))
    best_sample = _as_mapping(samples[0]) if samples else {}
    return {
        "finding_id": "add-on-001",
        "direction": "add_on_review",
        "title_zh": "加仓入场点复盘入口",
        "summary_zh": (
            f"该 section 可用加仓样本 {section.get('available_sample_count')} 个，"
            f"当前包选取 {section.get('selected_sample_count')} 个。"
        ),
        "metrics": {
            "available_sample_count": section.get("available_sample_count"),
            "selected_sample_count": section.get("selected_sample_count"),
            "top_sample_trade_return_pct": best_sample.get("trade_return_pct"),
            "top_sample_follow_up": best_sample.get("follow_up"),
        },
        "evidence_refs": [{"artifact": "review_packet", "section": section.get("name")}],
        "sample_refs": _sample_refs(samples[:top], kind="add_on"),
        "next_action_zh": "反查加仓 sample_index 的 add_on_date、checks、原交易结果和后续窗口。",
        "caveat_zh": "真实加仓样本数量少时只能作为框架验证样本，不适合调参。",
    }


def _environment_fit_finding(section: Mapping[str, Any], *, top: int) -> dict[str, Any]:
    context = _as_mapping(section.get("context"))
    best = _as_mapping(context.get("best_environments"))
    overall = _as_mapping(context.get("overall"))
    warnings = _as_mapping(context.get("sample_warnings"))
    best_by_net = _as_mapping(best.get("best_by_net_pnl"))
    best_by_capital = _as_mapping(best.get("best_by_return_on_entry_value"))
    samples = _as_sequence(section.get("samples"))
    return {
        "finding_id": "environment-fit-001",
        "direction": "environment_fit_review",
        "title_zh": "策略适配环境复盘入口",
        "summary_zh": (
            f"该 section 可用交易贡献样本 {section.get('available_sample_count')} 个，"
            f"当前包选取 {section.get('selected_sample_count')} 个；"
            f"净利润最高环境为 {best_by_net.get('label_zh')}。"
        ),
        "metrics": {
            "overall_net_pnl": overall.get("net_pnl"),
            "overall_return_on_entry_value": overall.get("return_on_entry_value"),
            "best_by_net_pnl": best_by_net,
            "best_by_return_on_entry_value": best_by_capital,
            "low_sample_combination_count": warnings.get("low_sample_combination_count"),
        },
        "evidence_refs": [{"artifact": "review_packet", "section": section.get("name")}],
        "sample_refs": _trade_refs(samples[:top]),
        "next_action_zh": "优先阅读 environment_fit.zh.md 首页，再按 trade_index 反查最佳/最差环境中的代表交易。",
        "caveat_zh": "环境适配是统计复盘线索，不是因果结论，也不是自动调参建议。",
    }


def _ai_task(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "instruction_zh": "基于 review packet 和 findings 写复盘；必须引用 evidence_refs 和 sample_refs，不引入外部行情或主观调优建议。",
        "required_output_schema": {
            "summary_zh": "string",
            "findings": [
                {
                    "finding_id": "string",
                    "claim_zh": "string",
                    "evidence_refs": "list",
                    "sample_refs": "list",
                    "risk_zh": "string",
                    "next_check_zh": "string",
                }
            ],
        },
        "source_packet_schema": packet.get("schema"),
        "source_packet_focus": packet.get("focus"),
    }


def _select_sample(
    trade_review: Mapping[str, Any],
    *,
    kind: str,
    sample_index: int | None,
    trade_index: int | None,
) -> Mapping[str, Any]:
    if kind == "trade":
        if trade_index is None:
            raise ValueError("trade sample requires trade_index")
        return _find_by_index(_as_sequence(trade_review.get("trades")), "trade_index", trade_index)
    if kind == "opportunity":
        if sample_index is None:
            raise ValueError("opportunity sample requires sample_index")
        return _find_by_index(_as_sequence(trade_review.get("opportunities")), "sample_index", sample_index)
    if sample_index is None:
        raise ValueError("add_on sample requires sample_index")
    return _find_by_index(_as_sequence(trade_review.get("add_on_entry_points")), "sample_index", sample_index)


def _related_evidence(
    artifacts: Mapping[str, Any],
    sample: Mapping[str, Any],
    *,
    kind: str,
    context_limit: int,
) -> dict[str, Any]:
    trade_index = sample.get("trade_index")
    trade_review = _as_mapping(artifacts.get("trade_review"))
    trade = sample if kind == "trade" else _match_trade_review_trade(trade_review, sample)
    lifecycle = _match_lifecycle(_as_mapping(artifacts.get("trade_lifecycle")), sample, trade)
    post_exit = _match_post_exit(_as_mapping(artifacts.get("post_exit_analysis")), sample, trade)
    closed_trade = _match_closed_trade(_as_mapping(artifacts.get("trades")), sample, trade)
    signal_matches = _matching_signal_intents(
        _as_sequence(artifacts.get("signal_audit")),
        sample,
        trade=trade,
        kind=kind,
    )
    execution_matches = _matching_execution_events(
        _as_sequence(artifacts.get("execution_audit")),
        sample,
        trade=trade,
        kind=kind,
    )
    return {
        "trade_review_trade": trade,
        "trade_lifecycle": lifecycle,
        "post_exit_observation": post_exit,
        "closed_trade": closed_trade,
        "signal_intents": signal_matches[:context_limit],
        "signal_intent_match_count": len(signal_matches),
        "execution_events": execution_matches[:context_limit],
        "execution_event_match_count": len(execution_matches),
        "drill_down_hints": _drill_down_hints(kind, sample, trade_index),
    }


def _match_trade_review_trade(trade_review: Mapping[str, Any], sample: Mapping[str, Any]) -> Mapping[str, Any]:
    trade_index = sample.get("trade_index")
    if trade_index is not None:
        try:
            return _find_by_index(_as_sequence(trade_review.get("trades")), "trade_index", int(trade_index))
        except ValueError:
            pass
    return {}


def _match_lifecycle(
    lifecycle_report: Mapping[str, Any],
    sample: Mapping[str, Any],
    trade: Mapping[str, Any],
) -> Mapping[str, Any]:
    rows = _as_sequence(lifecycle_report.get("lifecycles"))
    trade_index = _first_present(sample.get("trade_index"), trade.get("trade_index"))
    if trade_index is not None:
        for row in rows:
            row_map = _as_mapping(row)
            if row_map.get("trade_index") == trade_index:
                return row_map
    return _find_by_trade_signature(rows, sample, trade)


def _match_post_exit(
    post_exit: Mapping[str, Any],
    sample: Mapping[str, Any],
    trade: Mapping[str, Any],
) -> Mapping[str, Any]:
    return _find_by_trade_signature(_as_sequence(post_exit.get("observations")), sample, trade)


def _match_closed_trade(
    trades_artifact: Mapping[str, Any],
    sample: Mapping[str, Any],
    trade: Mapping[str, Any],
) -> Mapping[str, Any]:
    return _find_by_trade_signature(_as_sequence(trades_artifact.get("closed_trades")), sample, trade)


def _find_by_trade_signature(rows: Sequence[Any], sample: Mapping[str, Any], trade: Mapping[str, Any]) -> Mapping[str, Any]:
    signature = {
        "symbol": _first_present(trade.get("symbol"), sample.get("symbol")),
        "entry_date": _first_present(trade.get("entry_date"), sample.get("entry_date")),
        "exit_date": _first_present(trade.get("exit_date"), sample.get("exit_date")),
    }
    if not all(signature.values()):
        return {}
    for row in rows:
        row_map = _as_mapping(row)
        if all(row_map.get(key) == value for key, value in signature.items()):
            return row_map
    return {}


def _matching_signal_intents(
    rows: Sequence[Any],
    sample: Mapping[str, Any],
    *,
    trade: Mapping[str, Any],
    kind: str,
) -> list[Mapping[str, Any]]:
    dates = _sample_dates(sample, trade=trade, kind=kind)
    reason_code = sample.get("reason_code") if kind != "trade" else None
    matches = []
    for row in rows:
        row_map = _as_mapping(row)
        if row_map.get("symbol") != sample.get("symbol"):
            continue
        if row_map.get("trade_date") not in dates:
            continue
        if reason_code is not None and row_map.get("reason_code") != reason_code:
            continue
        matches.append(row_map)
    return matches


def _matching_execution_events(
    rows: Sequence[Any],
    sample: Mapping[str, Any],
    *,
    trade: Mapping[str, Any],
    kind: str,
) -> list[Mapping[str, Any]]:
    dates = _sample_dates(sample, trade=trade, kind=kind)
    reason_code = sample.get("reason_code") if kind != "trade" else None
    matches = []
    for row in rows:
        row_map = _as_mapping(row)
        if row_map.get("symbol") != sample.get("symbol"):
            continue
        if not dates.intersection(
            {
                row_map.get("signal_date"),
                row_map.get("event_date"),
                row_map.get("executed_date"),
            }
        ):
            continue
        if reason_code is not None and row_map.get("reason_code") != reason_code:
            continue
        matches.append(row_map)
    return matches


def _sample_dates(sample: Mapping[str, Any], *, trade: Mapping[str, Any], kind: str) -> set[Any]:
    if kind == "opportunity":
        return {sample.get("trade_date")}
    if kind == "add_on":
        return {sample.get("add_on_date")}
    return {
        _first_present(sample.get("entry_date"), trade.get("entry_date")),
        _first_present(sample.get("exit_date"), trade.get("exit_date")),
    }


def _drill_down_hints(kind: str, sample: Mapping[str, Any], trade_index: Any) -> list[str]:
    hints = []
    if trade_index is not None:
        hints.append(f"trade_index={trade_index} 可回查 trade_review.trades 与 trade_lifecycle.lifecycles")
    if kind in {"opportunity", "add_on"}:
        source_name = "opportunities" if kind == "opportunity" else "add_on_entry_points"
        hints.append(f"sample_index={sample.get('sample_index')} 可回查 trade_review.{source_name}")
    reason = sample.get("reason_code")
    date_value = _first_present(sample.get("trade_date"), sample.get("add_on_date"), sample.get("entry_date"))
    if reason is not None and date_value is not None:
        hints.append(f"symbol/date/reason 可回查 signal_audit 和 execution_audit: {sample.get('symbol')} {date_value} {reason}")
    return hints


def _load_packet(packet_or_path: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(packet_or_path, Mapping):
        return packet_or_path, None
    path = Path(packet_or_path)
    return json.loads(path.read_text(encoding="utf-8")), path


def _load_run_artifacts(run_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    artifacts: dict[str, Any] = {}
    sources: dict[str, dict[str, Any]] = {}
    for key, filename in _ARTIFACT_FILENAMES.items():
        path = run_path / filename
        exists = path.exists()
        sources[key] = {"path": str(path), "exists": exists}
        if exists:
            artifacts[key] = json.loads(path.read_text(encoding="utf-8"))
    return artifacts, sources


def _run_id(run_path: Path, run_plan: Mapping[str, Any]) -> Any:
    return _as_mapping(run_plan.get("run")).get("id", run_path.name)


def _find_by_index(rows: Sequence[Any], key: str, value: int) -> Mapping[str, Any]:
    for row in rows:
        row_map = _as_mapping(row)
        if row_map.get(key) == value:
            return row_map
    raise ValueError(f"No sample found for {key}={value}")


def _sample_id(kind: str, sample: Mapping[str, Any]) -> str:
    if kind == "trade":
        return f"trade.{sample.get('trade_index')}"
    return f"{kind}.{sample.get('sample_index')}"


def _trade_refs(samples: Sequence[Any]) -> list[dict[str, Any]]:
    refs = []
    for sample in samples:
        sample_map = _as_mapping(sample)
        if "trade_index" in sample_map:
            refs.append(
                {
                    "kind": "trade",
                    "trade_index": sample_map.get("trade_index"),
                    "symbol": sample_map.get("symbol"),
                    "entry_date": sample_map.get("entry_date"),
                    "exit_date": sample_map.get("exit_date"),
                }
            )
    return refs


def _sample_refs(samples: Sequence[Any], *, kind: str) -> list[dict[str, Any]]:
    refs = []
    for sample in samples:
        sample_map = _as_mapping(sample)
        refs.append(
            {
                "kind": kind,
                "sample_index": sample_map.get("sample_index"),
                "trade_index": sample_map.get("trade_index"),
                "symbol": sample_map.get("symbol"),
                "trade_date": _first_present(sample_map.get("trade_date"), sample_map.get("add_on_date")),
            }
        )
    return refs


def _max_metric(samples: Sequence[Any], key: str) -> Any:
    values = [_as_mapping(sample).get(key) for sample in samples]
    numeric = [value for value in values if isinstance(value, (int, float))]
    return max(numeric) if numeric else None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return value
    return ()


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _pick_present(source: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source}


def _drop_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _markdown_table_value(value: Any) -> str:
    if isinstance(value, Mapping):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, (list, tuple)):
        text = ", ".join(str(item) for item in value)
    else:
        text = str(value)
    return text.replace("|", "\\|")


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
