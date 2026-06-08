"""Build AI-friendly review packets from persisted run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .run_data import build_run_data_attribution_summary


REVIEW_PACKET_FOCUSES = (
    "all",
    "sold_too_early",
    "stop_loss_rebound",
    "opportunity_cost",
    "add_on",
    "environment_fit",
    "attribution_summary",
    "validation",
)

_REVIEW_PACKET_SCHEMA = "attbacktrader.review_packet.v1"
_ARTIFACT_FILENAMES = {
    "run_plan": "run_plan.json",
    "report": "report.json",
    "result_diagnostics": "result_diagnostics.json",
    "trade_lifecycle": "trade_lifecycle.json",
    "trade_attribution": "trade_attribution.json",
    "run_data_attribution_summary": "run_data_attribution_summary.json",
    "trade_review": "trade_review.json",
    "environment_fit": "environment_fit.json",
    "post_exit_analysis": "post_exit_analysis.json",
    "evidence_validation": "evidence_validation.json",
}
_SUMMARY_LIST_LIMIT = 50


def build_review_packet(
    run_dir: str | Path,
    *,
    focus: str = "all",
    top: int = 30,
) -> dict[str, Any]:
    """Build a compact packet for AI review from already persisted artifacts."""

    if focus not in REVIEW_PACKET_FOCUSES:
        raise ValueError(f"Unsupported review packet focus: {focus}")
    if top <= 0:
        raise ValueError("top must be greater than 0")

    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    artifacts, source_artifacts = _load_artifacts(run_path)
    run_plan = _as_mapping(artifacts.get("run_plan"))
    report = _as_mapping(artifacts.get("report"))
    trade_review = _as_mapping(artifacts.get("trade_review"))
    environment_fit = _as_mapping(artifacts.get("environment_fit"))
    attribution_summary = _load_or_build_attribution_summary(run_path, artifacts, source_artifacts, top=top)
    post_exit = _as_mapping(artifacts.get("post_exit_analysis"))
    validation = _as_mapping(artifacts.get("evidence_validation"))

    overview = _build_overview(
        run_path=run_path,
        run_plan=run_plan,
        report=report,
        trade_review=trade_review,
        environment_fit=environment_fit,
        validation=validation,
    )

    return {
        "schema": _REVIEW_PACKET_SCHEMA,
        "focus": focus,
        "run_id": overview["run_id"],
        "source_dir": str(run_path),
        "source_artifacts": source_artifacts,
        "ai_contract": _build_ai_contract(focus),
        "overview": overview,
        "sections": _build_sections(
            focus=focus,
            trade_review=trade_review,
            environment_fit=environment_fit,
            attribution_summary=attribution_summary,
            post_exit=post_exit,
            validation=validation,
            top=top,
        ),
    }


def render_review_packet_markdown_zh(packet: Mapping[str, Any]) -> str:
    """Render a Chinese Markdown surface that keeps machine-readable blocks."""

    overview = _as_mapping(packet.get("overview"))
    lines = [
        "# AI 复盘包",
        "",
        f"- schema: `{packet.get('schema')}`",
        f"- run_id: `{packet.get('run_id')}`",
        f"- focus: `{packet.get('focus')}`",
        f"- source_dir: `{packet.get('source_dir')}`",
        (
            "- evidence_validation: "
            f"`{_nested(overview, 'evidence_validation', 'status')}` "
            f"errors=`{_nested(overview, 'evidence_validation', 'error_count')}` "
            f"warnings=`{_nested(overview, 'evidence_validation', 'warning_count')}`"
        ),
        "",
        "## AI 使用规则",
    ]

    contract = _as_mapping(packet.get("ai_contract"))
    for rule in _as_sequence(contract.get("rules")):
        lines.append(f"- {rule}")
    lines.extend(
        [
            "",
            "## 建议任务",
        ]
    )
    for task in _as_sequence(contract.get("suggested_tasks")):
        lines.append(f"- {task}")

    lines.extend(
        [
            "",
            "## 概览",
            "```json",
            _to_pretty_json(packet.get("overview", {})),
            "```",
            "",
            "## 来源 Artifact",
            "| artifact | exists | path |",
            "|---|---:|---|",
        ]
    )
    for artifact, source in _as_mapping(packet.get("source_artifacts")).items():
        source_map = _as_mapping(source)
        lines.append(f"| `{artifact}` | `{source_map.get('exists')}` | `{source_map.get('path')}` |")

    for section in _as_sequence(packet.get("sections")):
        section_map = _as_mapping(section)
        lines.extend(
            [
                "",
                f"## {section_map.get('title_zh', section_map.get('name'))}",
                "",
                f"- focus: `{section_map.get('focus')}`",
                f"- source: `{section_map.get('source_artifact')}`",
                f"- why: {section_map.get('why_it_matters')}",
            ]
        )
        if "available_sample_count" in section_map:
            lines.append(f"- available_sample_count: `{section_map.get('available_sample_count')}`")
        if "selected_sample_count" in section_map:
            lines.append(f"- selected_sample_count: `{section_map.get('selected_sample_count')}`")
        if section_map.get("context"):
            lines.extend(["", "### context", "```json", _to_pretty_json(section_map["context"]), "```"])
        lines.extend(["", "### summaries", "```json", _to_pretty_json(section_map.get("summaries", [])), "```"])
        lines.extend(["", "### samples", "```json", _to_pretty_json(section_map.get("samples", [])), "```"])

    lines.append("")
    return "\n".join(lines)


def write_review_packet(
    packet: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write JSON and Chinese Markdown review packet artifacts."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(packet["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    focus = str(packet["focus"])
    json_path = target_dir / f"review_packet.{focus}.json"
    markdown_path = target_dir / f"review_packet.{focus}.zh.md"
    json_path.write_text(_to_pretty_json(packet), encoding="utf-8")
    markdown_path.write_text(render_review_packet_markdown_zh(packet), encoding="utf-8")
    return json_path, markdown_path


def _load_artifacts(run_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    artifacts: dict[str, Any] = {}
    sources: dict[str, dict[str, Any]] = {}
    for key, filename in _ARTIFACT_FILENAMES.items():
        path = run_path / filename
        exists = path.exists()
        sources[key] = {"path": str(path), "exists": exists}
        if exists:
            artifacts[key] = json.loads(path.read_text(encoding="utf-8"))
    return artifacts, sources


def _load_or_build_attribution_summary(
    run_path: Path,
    artifacts: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    *,
    top: int,
) -> Mapping[str, Any]:
    existing = _as_mapping(artifacts.get("run_data_attribution_summary"))
    if existing:
        return existing
    if not _as_mapping(artifacts.get("trade_attribution")):
        return {}
    try:
        summary = build_run_data_attribution_summary(run_path, top_n=top)
    except (FileNotFoundError, ValueError):
        return {}
    artifacts["run_data_attribution_summary"] = summary
    source = sources.setdefault(
        "run_data_attribution_summary",
        {"path": str(run_path / "run_data_attribution_summary.json"), "exists": False},
    )
    source["generated_from"] = "trade_attribution.json"
    source["generated_in_packet"] = True
    return summary


def _build_ai_contract(focus: str) -> dict[str, Any]:
    base_tasks = {
        "sold_too_early": "找出止盈/止损后可能卖飞的样本，按 trade_index 回到原始交易证据。",
        "stop_loss_rebound": "检查止损卖出后的反弹层级和对应入场/退出上下文。",
        "opportunity_cost": "分析被过滤、Sizing 阻断或执行拒绝后的机会成本样本，但不要断言应该交易。",
        "add_on": "复盘真实加仓入场点的后续走势和原交易结果，用于判断加仓框架是否可解释。",
        "environment_fit": "分析策略在哪些入场环境下胜率、收益和实际净 PnL 更高，但不要把统计关系写成因果或调参结论。",
        "attribution_summary": "先读后验归因摘要，复核单因子和组合环境候选，并用 query_filters 下钻样本。",
        "validation": "先检查证据链是否可靠，只有 status=ok 时才继续做结论性复盘。",
    }
    tasks = list(base_tasks.values()) if focus == "all" else [base_tasks[focus]]
    return {
        "purpose": "给 AI/Skill 使用的稳定复盘输入，聚焦已有回测证据的下游分析。",
        "rules": [
            "只使用本 packet 和 source_artifacts 指向的持久化证据。",
            "引用样本时必须带上 sample_index 或 trade_index，便于回查原始 JSON。",
            "缺失字段保持缺失；不要把缺失收益、缺失指标、缺失检查当成 0 或 False。",
            "不要重新计算指标、不要重跑策略、不要在报告层推导新的交易事实。",
            "把统计关系视为复盘线索，不要写成因果结论或策略调优结论。",
        ],
        "suggested_tasks": tasks,
    }


def _build_overview(
    *,
    run_path: Path,
    run_plan: Mapping[str, Any],
    report: Mapping[str, Any],
    trade_review: Mapping[str, Any],
    environment_fit: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    run_config = _as_mapping(run_plan.get("run"))
    execution = _as_mapping(run_plan.get("execution"))
    validation_counts = _as_mapping(validation.get("counts"))
    symbols = _as_sequence(_as_mapping(run_plan.get("data")).get("symbols"))
    symbol_count = validation_counts.get("symbol_count")
    if symbol_count is None and symbols:
        symbol_count = len(symbols)

    return {
        "run_id": run_config.get("id", run_path.name),
        "from_date": run_config.get("from_date"),
        "to_date": run_config.get("to_date"),
        "engine": execution.get("engine"),
        "symbol_count": symbol_count,
        "final_equity": _first_present(
            _nested(report, "returns", "final_equity"),
            _nested(report, "returns", "final_value"),
        ),
        "cumulative_return": _nested(report, "returns", "cumulative_return"),
        "max_drawdown": _nested(report, "risk", "max_drawdown"),
        "trade_count": _first_present(
            _nested(report, "trade_quality", "trade_count"),
            trade_review.get("trade_count"),
            validation_counts.get("closed_trade_count"),
        ),
        "sold_too_early_count": trade_review.get("sold_too_early_count"),
        "opportunity_count": trade_review.get("opportunity_count"),
        "opportunity_window_days": trade_review.get("opportunity_window_days"),
        "add_on_entry_count": trade_review.get("add_on_entry_count"),
        "add_on_window_days": trade_review.get("add_on_window_days"),
        "environment_fit": _environment_overview(environment_fit),
        "evidence_validation": {
            "status": validation.get("status"),
            "error_count": validation.get("error_count"),
            "warning_count": validation.get("warning_count"),
        },
    }


def _build_sections(
    *,
    focus: str,
    trade_review: Mapping[str, Any],
    environment_fit: Mapping[str, Any],
    attribution_summary: Mapping[str, Any],
    post_exit: Mapping[str, Any],
    validation: Mapping[str, Any],
    top: int,
) -> list[dict[str, Any]]:
    section_builders = {
        "sold_too_early": lambda: _sold_too_early_section(trade_review, post_exit, top),
        "stop_loss_rebound": lambda: _stop_loss_rebound_section(trade_review, post_exit, top),
        "opportunity_cost": lambda: _opportunity_cost_section(trade_review, top),
        "add_on": lambda: _add_on_section(trade_review, top),
        "environment_fit": lambda: _environment_fit_section(environment_fit, top),
        "attribution_summary": lambda: _attribution_summary_section(attribution_summary, top),
        "validation": lambda: _validation_section(validation, top),
    }
    if focus == "all":
        return [builder() for builder in section_builders.values()]
    return [section_builders[focus]()]


def _sold_too_early_section(
    trade_review: Mapping[str, Any],
    post_exit: Mapping[str, Any],
    top: int,
) -> dict[str, Any]:
    trades = _as_sequence(trade_review.get("trades"))
    samples = [trade for trade in trades if _as_mapping(trade).get("sold_too_early") is True]
    ranked_samples = _rank_by_metric(samples, ("max_high_return_pct", "primary_window_close_return_pct"))[:top]
    return {
        "name": "sold_too_early",
        "title_zh": "卖飞复盘",
        "focus": "sold_too_early",
        "source_artifact": "trade_review.json; post_exit_analysis.json",
        "why_it_matters": "识别卖出后短窗口反弹最大的交易，作为后续止盈/止损复盘线索。",
        "context": _post_exit_context(post_exit),
        "summaries": _compact_rows(
            _rank_by_metric(
                _as_sequence(trade_review.get("sold_too_early_profiles")),
                ("sold_too_early_rate", "average_max_high_return_pct"),
            )[:top]
        ),
        "available_sample_count": len(samples),
        "selected_sample_count": len(ranked_samples),
        "samples": [_trade_sample(sample) for sample in ranked_samples],
    }


def _stop_loss_rebound_section(
    trade_review: Mapping[str, Any],
    post_exit: Mapping[str, Any],
    top: int,
) -> dict[str, Any]:
    stop_loss_samples = []
    for trade in _as_sequence(trade_review.get("trades")):
        trade_map = _as_mapping(trade)
        exit_checks = _as_mapping(trade_map.get("exit_checks"))
        exit_reason = str(trade_map.get("exit_reason", ""))
        if "STOP" in exit_reason or exit_checks.get("current_price_at_or_below_stop") is True:
            stop_loss_samples.append(trade)
    ranked_samples = _rank_by_metric(stop_loss_samples, ("max_high_return_pct", "primary_window_close_return_pct"))[:top]
    return {
        "name": "stop_loss_rebound",
        "title_zh": "止损后反弹",
        "focus": "stop_loss_rebound",
        "source_artifact": "trade_review.json; post_exit_analysis.json",
        "why_it_matters": "查看止损样本卖出后的反弹层级，判断止损退出证据是否需要更细的复盘维度。",
        "context": _post_exit_context(post_exit),
        "summaries": _compact_rows(
            _rank_by_metric(
                _as_sequence(trade_review.get("stop_loss_rebound_profiles")),
                ("rebound_rate", "average_max_high_return_pct"),
            )[:top]
        ),
        "available_sample_count": len(stop_loss_samples),
        "selected_sample_count": len(ranked_samples),
        "samples": [_trade_sample(sample) for sample in ranked_samples],
    }


def _opportunity_cost_section(trade_review: Mapping[str, Any], top: int) -> dict[str, Any]:
    opportunities = _rank_by_metric(
        _as_sequence(trade_review.get("opportunities")),
        ("follow_up.max_high_return_pct", "follow_up.window_close_return_pct"),
    )
    selected = opportunities[:top]
    return {
        "name": "opportunity_cost",
        "title_zh": "机会成本",
        "focus": "opportunity_cost",
        "source_artifact": "trade_review.json",
        "why_it_matters": "复盘被过滤、Sizing 阻断或执行拒绝后的后续走势，帮助定位框架证据是否充分。",
        "summaries": _compact_rows(
            _rank_by_metric(
                _as_sequence(trade_review.get("opportunity_cost_summaries")),
                ("positive_max_high_rate", "average_max_high_return_pct"),
            )[:top]
        ),
        "available_sample_count": len(opportunities),
        "selected_sample_count": len(selected),
        "samples": [_opportunity_sample(sample) for sample in selected],
    }


def _add_on_section(trade_review: Mapping[str, Any], top: int) -> dict[str, Any]:
    add_on_points = _rank_by_metric(
        _as_sequence(trade_review.get("add_on_entry_points")),
        ("follow_up.max_high_return_pct", "follow_up.window_close_return_pct", "trade_return_pct"),
    )
    selected = add_on_points[:top]
    return {
        "name": "add_on",
        "title_zh": "加仓入场点",
        "focus": "add_on",
        "source_artifact": "trade_review.json",
        "why_it_matters": "复盘真实加仓点的决策证据、原交易结果和加仓后短窗口走势。",
        "summaries": _compact_rows(
            _rank_by_metric(
                _as_sequence(trade_review.get("add_on_entry_summaries")),
                ("positive_max_high_rate", "average_max_high_return_pct", "average_trade_return_pct"),
            )[:top]
        ),
        "available_sample_count": len(add_on_points),
        "selected_sample_count": len(selected),
        "samples": [_add_on_sample(sample) for sample in selected],
    }


def _environment_fit_section(environment_fit: Mapping[str, Any], top: int) -> dict[str, Any]:
    trade_contributions = _as_sequence(environment_fit.get("trade_contributions"))
    selected = _environment_trade_samples(trade_contributions, top)
    return {
        "name": "environment_fit",
        "title_zh": "环境适配与利润贡献",
        "focus": "environment_fit",
        "source_artifact": "environment_fit.json",
        "why_it_matters": "按入场环境分组查看胜率、收益率、实际成交净 PnL 和入场资金收益率，判断策略适用环境线索。",
        "context": _pick_present(
            environment_fit,
            (
                "environment_fields",
                "min_sample_count",
                "trade_count",
                "contribution_available_count",
                "overall",
                "best_environments",
                "sample_warnings",
            ),
        ),
        "summaries": _environment_summaries(environment_fit, top),
        "available_sample_count": len(trade_contributions),
        "selected_sample_count": len(selected),
        "samples": selected,
    }


def _attribution_summary_section(attribution_summary: Mapping[str, Any], top: int) -> dict[str, Any]:
    candidate_groups = (
        ("preferred_combination_candidates", "适合组合候选"),
        ("avoid_combination_candidates", "规避组合候选"),
        ("preferred_candidates", "适合单因子候选"),
        ("avoid_candidates", "规避单因子候选"),
    )
    summaries: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    seen_trade_indexes = set()
    for group_key, group_label in candidate_groups:
        for candidate in _as_sequence(attribution_summary.get(group_key))[:top]:
            candidate_map = dict(_compact_row(candidate))
            candidate_map["candidate_group"] = group_key
            candidate_map["candidate_group_zh"] = group_label
            summaries.append(candidate_map)
            for trade_index in _as_sequence(_as_mapping(candidate).get("trade_indexes")):
                if trade_index in seen_trade_indexes:
                    continue
                seen_trade_indexes.add(trade_index)
                samples.append(
                    {
                        "kind": "trade",
                        "trade_index": trade_index,
                        "source_candidate_group": group_key,
                        "source_query_filters": _as_sequence(_as_mapping(candidate).get("query_filters")),
                    }
                )
                if len(samples) >= top:
                    break
            if len(samples) >= top:
                break
    return {
        "name": "attribution_summary",
        "title_zh": "后验归因环境候选",
        "focus": "attribution_summary",
        "source_artifact": "run_data_attribution_summary.json; trade_attribution.json",
        "why_it_matters": "用已成交交易的后验归因统计单因子和组合环境候选，并提供可复制到 run_data_attribution_index 的 query_filters。",
        "context": _pick_present(
            attribution_summary,
            (
                "source_artifact",
                "parameters",
                "overall",
                "coverage",
                "high_missing_factors",
                "ai_usage_rules",
            ),
        ),
        "summaries": summaries[: top * len(candidate_groups)],
        "available_sample_count": _nested(attribution_summary, "overall", "trade_count"),
        "selected_sample_count": len(samples),
        "samples": samples,
    }


def _validation_section(validation: Mapping[str, Any], top: int) -> dict[str, Any]:
    issues = _as_sequence(validation.get("issues"))
    return {
        "name": "validation",
        "title_zh": "证据校验",
        "focus": "validation",
        "source_artifact": "evidence_validation.json",
        "why_it_matters": "确认复盘输入是否通过跨 artifact 一致性校验，避免基于损坏证据分析。",
        "summaries": [
            {
                "status": validation.get("status"),
                "error_count": validation.get("error_count"),
                "warning_count": validation.get("warning_count"),
                "counts": validation.get("counts"),
            }
        ],
        "available_sample_count": len(issues),
        "selected_sample_count": min(len(issues), top),
        "samples": _compact_rows(issues[:top]),
    }


def _environment_overview(environment_fit: Mapping[str, Any]) -> dict[str, Any]:
    if not environment_fit:
        return {}
    best = _as_mapping(environment_fit.get("best_environments"))
    overall = _as_mapping(environment_fit.get("overall"))
    warnings = _as_mapping(environment_fit.get("sample_warnings"))
    return _drop_empty(
        {
            "trade_count": environment_fit.get("trade_count"),
            "contribution_available_count": environment_fit.get("contribution_available_count"),
            "overall_net_pnl": overall.get("net_pnl"),
            "overall_return_on_entry_value": overall.get("return_on_entry_value"),
            "best_by_net_pnl": best.get("best_by_net_pnl"),
            "best_by_return_on_entry_value": best.get("best_by_return_on_entry_value"),
            "low_sample_combination_count": warnings.get("low_sample_combination_count"),
        }
    )


def _environment_summaries(environment_fit: Mapping[str, Any], top: int) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    best = _as_mapping(environment_fit.get("best_environments"))
    for key, label in (
        ("best_by_net_pnl", "净利润最高"),
        ("best_by_return_on_entry_value", "资金收益率最高"),
        ("best_by_win_rate", "胜率最高"),
        ("worst_by_net_pnl", "净利润最低"),
    ):
        candidate = _as_mapping(best.get(key))
        if candidate:
            row = dict(_compact_row(candidate))
            row["summary_type"] = key
            row["summary_type_zh"] = label
            summaries.append(row)
    ranked_single = _rank_by_metric(
        _as_sequence(environment_fit.get("single_factor_summaries")),
        ("net_pnl", "return_on_entry_value", "win_rate"),
    )[:top]
    ranked_combinations = _rank_by_metric(
        _as_sequence(environment_fit.get("combination_summaries")),
        ("net_pnl", "return_on_entry_value", "win_rate"),
    )[:top]
    summaries.extend(
        {
            **dict(_compact_row(summary)),
            "summary_type": "single_factor",
            "summary_type_zh": "单因子表现",
        }
        for summary in ranked_single
    )
    summaries.extend(
        {
            **dict(_compact_row(summary)),
            "summary_type": "combination",
            "summary_type_zh": "组合环境表现",
        }
        for summary in ranked_combinations
    )
    return summaries


def _environment_trade_samples(rows: Sequence[Any], top: int) -> list[dict[str, Any]]:
    if top <= 0:
        return []
    row_maps = [_as_mapping(row) for row in rows]
    positive_count = max(1, top // 2)
    negative_count = max(0, top - positive_count)
    top_positive = sorted(
        row_maps,
        key=lambda row: row.get("net_pnl") if isinstance(row.get("net_pnl"), (int, float)) else float("-inf"),
        reverse=True,
    )[:positive_count]
    top_negative = sorted(
        row_maps,
        key=lambda row: row.get("net_pnl") if isinstance(row.get("net_pnl"), (int, float)) else float("inf"),
    )[:negative_count]
    samples: list[dict[str, Any]] = []
    seen = set()
    for role, selected in (("top_net_pnl", top_positive), ("worst_net_pnl", top_negative)):
        for row in selected:
            trade_index = row.get("trade_index")
            if trade_index in seen:
                continue
            seen.add(trade_index)
            sample = _pick_present(
                row,
                (
                    "trade_index",
                    "symbol",
                    "entry_date",
                    "exit_date",
                    "outcome",
                    "exit_reason",
                    "return_pct",
                    "net_pnl",
                    "return_on_entry_value",
                    "environment",
                ),
            )
            sample["sample_role"] = role
            samples.append(sample)
    return samples[:top]


def _post_exit_context(post_exit: Mapping[str, Any]) -> dict[str, Any]:
    return _pick_present(
        post_exit,
        (
            "window_days",
            "configured_window_days",
            "sold_too_early_threshold",
            "rebound_thresholds",
            "trade_count",
            "summaries",
            "window_summaries",
            "threshold_summaries",
        ),
    )


def _trade_sample(sample: Any) -> dict[str, Any]:
    return _pick_present(
        _as_mapping(sample),
        (
            "trade_index",
            "symbol",
            "outcome",
            "entry_date",
            "exit_date",
            "exit_reason",
            "return_pct",
            "entry_method_name",
            "exit_method_name",
            "add_on_count",
            "sold_too_early",
            "max_high_return_pct",
            "primary_window_close_return_pct",
            "entry_checks",
            "exit_checks",
            "add_on_checks",
            "review_flags",
        ),
    )


def _opportunity_sample(sample: Any) -> dict[str, Any]:
    return _pick_present(
        _as_mapping(sample),
        (
            "sample_index",
            "source",
            "opportunity_group",
            "symbol",
            "trade_date",
            "intent_type",
            "method_name",
            "reason_code",
            "blocked_by",
            "failed_checks",
            "checks",
            "categories",
            "opportunity_price",
            "follow_up",
        ),
    )


def _add_on_sample(sample: Any) -> dict[str, Any]:
    return _pick_present(
        _as_mapping(sample),
        (
            "sample_index",
            "trade_index",
            "symbol",
            "outcome",
            "trade_return_pct",
            "add_on_date",
            "method_name",
            "reason_code",
            "checks",
            "categories",
            "add_on_price",
            "follow_up",
        ),
    )


def _pick_present(source: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source}


def _compact_rows(rows: Sequence[Any]) -> list[Any]:
    return [_compact_row(row) for row in rows]


def _compact_row(row: Any) -> Any:
    if not isinstance(row, Mapping):
        return row
    compact: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, list) and len(value) > _SUMMARY_LIST_LIMIT:
            compact[key] = value[:_SUMMARY_LIST_LIMIT]
            compact[f"{key}_omitted_count"] = len(value) - _SUMMARY_LIST_LIMIT
        else:
            compact[key] = value
    return compact


def _drop_empty(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in source.items()
        if value is not None and value != {} and value != []
    }


def _rank_by_metric(rows: Sequence[Any], metric_paths: Sequence[str]) -> list[Any]:
    return sorted(rows, key=lambda row: tuple(_metric(row, path) for path in metric_paths), reverse=True)


def _metric(row: Any, path: str) -> float:
    value = _path_value(row, path)
    if isinstance(value, (int, float)):
        return float(value)
    return float("-inf")


def _path_value(row: Any, path: str) -> Any:
    value = row
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


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


def _nested(source: Mapping[str, Any], *keys: str) -> Any:
    value: Any = source
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
