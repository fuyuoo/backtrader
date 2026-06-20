"""Strategy environment profile conclusions from persisted environment-fit evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


STRATEGY_ENVIRONMENT_PROFILE_SCHEMA = "attbacktrader.strategy_environment_profile.v1"

_STRENGTH_RANK = {
    "strong": 3,
    "medium": 2,
    "weak": 1,
    "low_sample": 0,
    "incomplete": 0,
}


def build_strategy_environment_profile_from_run_dir(
    run_dir: str | Path,
    *,
    environment_fit_comparison: Mapping[str, Any] | str | Path | None = None,
    top: int = 20,
) -> dict[str, Any]:
    """Build a strategy environment profile from a persisted run directory."""

    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    environment_fit_path = run_path / "environment_fit.json"
    if not environment_fit_path.exists():
        raise FileNotFoundError(f"missing environment fit artifact: {environment_fit_path}")

    return build_strategy_environment_profile_from_artifacts(
        environment_fit=_load_json(environment_fit_path),
        environment_fit_comparison=_load_optional_mapping(environment_fit_comparison),
        source_dir=str(run_path),
        environment_fit_path=str(environment_fit_path),
        environment_fit_comparison_path=_optional_path_string(environment_fit_comparison),
        top=top,
    )


def build_strategy_environment_profile_from_artifacts(
    *,
    environment_fit: Mapping[str, Any],
    environment_fit_comparison: Mapping[str, Any] | None = None,
    source_dir: str | None = None,
    environment_fit_path: str | None = None,
    environment_fit_comparison_path: str | None = None,
    top: int = 20,
) -> dict[str, Any]:
    """Classify environment-fit summaries into preferred, avoid, and uncertain candidates.

    The profile only consumes persisted environment-fit artifacts. It does not
    rerun strategies, recalculate indicators, or fill missing values.
    """

    if top <= 0:
        raise ValueError("top must be greater than 0")

    fit = _as_mapping(environment_fit)
    comparison = _as_mapping(environment_fit_comparison)
    run_id = fit.get("run_id")
    min_sample_count = _optional_int(fit.get("min_sample_count")) or 5
    overall = _as_mapping(fit.get("overall"))
    comparison_context = _comparison_context(comparison, run_id=run_id)

    candidates = [
        _candidate_from_summary(
            summary,
            overall=overall,
            min_sample_count=min_sample_count,
            comparison_by_summary_key=comparison_context["by_summary_key"],
        )
        for summary in _environment_summaries(fit)
    ]
    candidates = [candidate for candidate in candidates if candidate]

    preferred = _limit_sorted(
        (
            candidate
            for candidate in candidates
            if candidate.get("classification") == "preferred"
        ),
        top=top,
        kind="preferred",
    )
    avoid = _limit_sorted(
        (
            candidate
            for candidate in candidates
            if candidate.get("classification") == "avoid"
        ),
        top=top,
        kind="avoid",
    )
    uncertain = _limit_sorted(
        (
            candidate
            for candidate in candidates
            if candidate.get("classification") == "uncertain"
        ),
        top=top,
        kind="uncertain",
    )

    return {
        "schema": STRATEGY_ENVIRONMENT_PROFILE_SCHEMA,
        "run_id": run_id,
        "source_dir": source_dir or fit.get("source_dir"),
        "source_artifacts": _drop_none(
            {
                "environment_fit": environment_fit_path,
                "environment_fit_comparison": environment_fit_comparison_path,
            }
        ),
        "trade_count": fit.get("trade_count"),
        "min_sample_count": min_sample_count,
        "top": top,
        "overall": {
            "win_rate": _optional_float(overall.get("win_rate")),
            "average_return_pct": _optional_float(overall.get("average_return_pct")),
            "net_pnl": _optional_float(overall.get("net_pnl")),
            "return_on_entry_value": _optional_float(overall.get("return_on_entry_value")),
        },
        "profile_summary": {
            "environment_count": len(candidates),
            "preferred_count": sum(1 for candidate in candidates if candidate.get("classification") == "preferred"),
            "avoid_count": sum(1 for candidate in candidates if candidate.get("classification") == "avoid"),
            "uncertain_count": sum(1 for candidate in candidates if candidate.get("classification") == "uncertain"),
            "evidence_strength_counts": _evidence_strength_counts(candidates),
        },
        "preferred_environments": preferred,
        "avoid_environments": avoid,
        "uncertain_environments": uncertain,
        "stability_checks": comparison_context["checks"],
        "ai_usage_rules": [
            "该画像只消费已落盘的 environment_fit.json 和可选 environment_fit_comparison.json。",
            "适合/规避都是候选结论，不是因果证明，也不是自动调参指令。",
            "样本数低于 min_sample_count 的环境必须进入不确定，不能当成稳定结论。",
            "缺失指标、缺失资金贡献或混合指标会降低证据强度，不会被补成 0、false 或中性。",
            "优先用 sample_refs 下钻代表交易，再决定是否设计下一轮验证 run。",
        ],
    }


def render_strategy_environment_profile_markdown_zh(profile: Mapping[str, Any], *, limit: int = 20) -> str:
    """Render a strategy environment profile in Chinese Markdown."""

    overall = _as_mapping(profile.get("overall"))
    summary = _as_mapping(profile.get("profile_summary"))
    lines = [
        "# 策略环境画像",
        "",
        "## 概览",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| run_id | `{profile.get('run_id')}` |",
        f"| 交易样本 | {profile.get('trade_count')} |",
        f"| 最小结论样本数 | {profile.get('min_sample_count')} |",
        f"| 总胜率 | {_format_optional_percent(overall.get('win_rate'))} |",
        f"| 平均单笔收益 | {_format_optional_percent(overall.get('average_return_pct'))} |",
        f"| 总净 PnL | {_format_optional_money(overall.get('net_pnl'))} |",
        f"| 入场资金收益率 | {_format_optional_percent(overall.get('return_on_entry_value'))} |",
        f"| 环境候选数 | {summary.get('environment_count')} |",
        f"| 适合候选 | {summary.get('preferred_count')} |",
        f"| 规避候选 | {summary.get('avoid_count')} |",
        f"| 不确定候选 | {summary.get('uncertain_count')} |",
    ]

    lines.extend(_candidate_section("## 适合环境候选", profile.get("preferred_environments"), limit=limit))
    lines.extend(_candidate_section("## 规避环境候选", profile.get("avoid_environments"), limit=limit))
    lines.extend(_candidate_section("## 不确定环境", profile.get("uncertain_environments"), limit=limit))

    stability_checks = _as_sequence(profile.get("stability_checks"))
    if stability_checks:
        lines.extend(
            [
                "",
                "## 跨 Run 稳定性",
                "",
                "| 口径 | 状态 | 当前环境 | 样本风险 |",
                "|---|---|---|---|",
            ]
        )
        for check in stability_checks:
            check_map = _as_mapping(check)
            lines.append(
                "| "
                f"{_escape_cell(check_map.get('criterion_zh'))} | "
                f"{_escape_cell(check_map.get('status_zh'))} | "
                f"{_escape_cell(check_map.get('label_zh'))} | "
                f"{_yes_no(check_map.get('low_sample'))} |"
            )

    lines.extend(["", "## AI 使用规则"])
    for rule in _as_sequence(profile.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_strategy_environment_profile(
    profile: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write strategy environment profile JSON and Chinese Markdown artifacts."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(profile["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "strategy_environment_profile.json"
    markdown_path = target_dir / "strategy_environment_profile.zh.md"
    json_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_strategy_environment_profile_markdown_zh(profile), encoding="utf-8")
    return json_path, markdown_path


def _candidate_from_summary(
    summary: Any,
    *,
    overall: Mapping[str, Any],
    min_sample_count: int,
    comparison_by_summary_key: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    item = _as_mapping(summary)
    summary_key = _summary_key(item)
    if summary_key is None:
        return {}

    sample_count = _optional_int(item.get("sample_count")) or 0
    metrics = {
        "win_rate": _optional_float(item.get("win_rate")),
        "average_return_pct": _optional_float(item.get("average_return_pct")),
        "net_pnl": _optional_float(item.get("net_pnl")),
        "return_on_entry_value": _optional_float(item.get("return_on_entry_value")),
    }
    deltas = {
        "win_rate": _optional_delta(metrics["win_rate"], overall.get("win_rate")),
        "average_return_pct": _optional_delta(metrics["average_return_pct"], overall.get("average_return_pct")),
        "return_on_entry_value": _optional_delta(
            metrics["return_on_entry_value"],
            overall.get("return_on_entry_value"),
        ),
    }
    risk_flags = _risk_flags(
        sample_count=sample_count,
        min_sample_count=min_sample_count,
        metrics=metrics,
        deltas=deltas,
    )
    classification = _classification(metrics=metrics, deltas=deltas, risk_flags=risk_flags)
    comparison_stability = [
        dict(stability)
        for stability in comparison_by_summary_key.get(summary_key, ())
    ]
    evidence_strength = _evidence_strength(
        sample_count=sample_count,
        min_sample_count=min_sample_count,
        risk_flags=risk_flags,
        comparison_stability=comparison_stability,
    )
    trade_indexes = [_optional_int(index) for index in _as_sequence(item.get("trade_indexes"))]
    trade_indexes = [index for index in trade_indexes if index is not None]
    return _drop_none(
        {
            "summary_key": summary_key,
            "summary_kind": item.get("summary_kind"),
            "summary_kind_zh": _summary_kind_zh(item.get("summary_kind")),
            "classification": classification,
            "classification_zh": _classification_zh(classification),
            "label_zh": item.get("label_zh"),
            "field": item.get("field"),
            "value": item.get("value"),
            "fields": item.get("fields"),
            "sample_count": sample_count,
            "min_sample_count": min_sample_count,
            "evidence_strength": evidence_strength,
            "evidence_strength_zh": _evidence_strength_zh(evidence_strength),
            "metrics": metrics,
            "deltas_vs_overall": deltas,
            "risk_flags": risk_flags,
            "reason_zh": _reason_zh(classification, risk_flags),
            "comparison_stability": comparison_stability,
            "trade_indexes": trade_indexes,
            "sample_refs": [
                {
                    "kind": "trade",
                    "trade_index": index,
                    "reason": "environment_profile_representative_trade",
                    "reason_zh": "环境画像代表交易，用于反查入场证据和交易生命周期。",
                }
                for index in trade_indexes[:5]
            ],
        }
    )


def _risk_flags(
    *,
    sample_count: int,
    min_sample_count: int,
    metrics: Mapping[str, float | None],
    deltas: Mapping[str, float | None],
) -> list[str]:
    flags: list[str] = []
    if sample_count < min_sample_count:
        flags.append("low_sample")
    if metrics.get("net_pnl") is None or metrics.get("return_on_entry_value") is None:
        flags.append("missing_profit_contribution")
    if metrics.get("win_rate") is None or metrics.get("average_return_pct") is None:
        flags.append("missing_return_stats")

    net_pnl = metrics.get("net_pnl")
    capital_return = metrics.get("return_on_entry_value")
    win_delta = deltas.get("win_rate")
    capital_delta = deltas.get("return_on_entry_value")
    if (
        net_pnl is not None
        and capital_return is not None
        and win_delta is not None
        and capital_delta is not None
    ):
        positive_money = net_pnl > 0 and capital_return > 0
        positive_relative = win_delta >= 0 or capital_delta > 0
        negative_money = net_pnl < 0 and capital_return < 0
        negative_relative = win_delta <= 0 or capital_delta < 0
        if not (positive_money and positive_relative) and not (negative_money and negative_relative):
            flags.append("mixed_metrics")
    return flags


def _classification(
    *,
    metrics: Mapping[str, float | None],
    deltas: Mapping[str, float | None],
    risk_flags: Sequence[str],
) -> str:
    if "low_sample" in risk_flags:
        return "uncertain"
    if "missing_profit_contribution" in risk_flags or "missing_return_stats" in risk_flags:
        return "uncertain"

    net_pnl = metrics.get("net_pnl")
    capital_return = metrics.get("return_on_entry_value")
    win_delta = deltas.get("win_rate")
    capital_delta = deltas.get("return_on_entry_value")
    if net_pnl is None or capital_return is None:
        return "uncertain"

    if net_pnl > 0 and capital_return > 0 and ((win_delta is not None and win_delta >= 0) or (capital_delta is not None and capital_delta > 0)):
        return "preferred"
    if net_pnl < 0 and capital_return < 0 and ((win_delta is not None and win_delta <= 0) or (capital_delta is not None and capital_delta < 0)):
        return "avoid"
    return "uncertain"


def _evidence_strength(
    *,
    sample_count: int,
    min_sample_count: int,
    risk_flags: Sequence[str],
    comparison_stability: Sequence[Mapping[str, Any]],
) -> str:
    if "low_sample" in risk_flags:
        return "low_sample"
    if "missing_profit_contribution" in risk_flags or "missing_return_stats" in risk_flags:
        return "incomplete"
    if any(stability.get("status") == "stable" for stability in comparison_stability):
        return "strong"
    if sample_count >= max(30, min_sample_count * 4):
        return "medium"
    if sample_count >= min_sample_count * 2:
        return "medium"
    return "weak"


def _comparison_context(comparison: Mapping[str, Any], *, run_id: Any) -> dict[str, Any]:
    by_summary_key: dict[str, list[dict[str, Any]]] = {}
    checks: list[dict[str, Any]] = []
    if not comparison:
        return {"by_summary_key": by_summary_key, "checks": checks}

    for check in _as_sequence(comparison.get("best_environment_stability")):
        check_map = _as_mapping(check)
        for environment in _as_sequence(check_map.get("run_environments")):
            environment_map = _as_mapping(environment)
            if run_id is not None and environment_map.get("run_id") != run_id:
                continue
            summary_key = environment_map.get("summary_key")
            if not summary_key:
                continue
            stability = _drop_none(
                {
                    "criterion": check_map.get("criterion"),
                    "criterion_zh": check_map.get("criterion_zh"),
                    "status": check_map.get("status"),
                    "status_zh": check_map.get("status_zh"),
                    "label_zh": environment_map.get("label_zh"),
                    "sample_count": environment_map.get("sample_count"),
                    "low_sample": environment_map.get("low_sample"),
                }
            )
            by_summary_key.setdefault(str(summary_key), []).append(stability)
            checks.append(stability)
    return {"by_summary_key": by_summary_key, "checks": checks}


def _environment_summaries(environment_fit: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        _as_mapping(summary)
        for summary in (
            *list(_as_sequence(environment_fit.get("single_factor_summaries"))),
            *list(_as_sequence(environment_fit.get("combination_summaries"))),
        )
    ]


def _limit_sorted(candidates: Sequence[Mapping[str, Any]] | Any, *, top: int, kind: str) -> list[dict[str, Any]]:
    items = [dict(_as_mapping(candidate)) for candidate in candidates]
    if kind == "preferred":
        items.sort(
            key=lambda item: (
                -_STRENGTH_RANK.get(str(item.get("evidence_strength")), 0),
                -_metric_value(item, "return_on_entry_value", default=float("-inf")),
                -_metric_value(item, "net_pnl", default=float("-inf")),
                -int(item.get("sample_count") or 0),
            )
        )
    elif kind == "avoid":
        items.sort(
            key=lambda item: (
                -_STRENGTH_RANK.get(str(item.get("evidence_strength")), 0),
                _metric_value(item, "return_on_entry_value", default=float("inf")),
                _metric_value(item, "net_pnl", default=float("inf")),
                -int(item.get("sample_count") or 0),
            )
        )
    else:
        items.sort(
            key=lambda item: (
                _STRENGTH_RANK.get(str(item.get("evidence_strength")), 0),
                -abs(_optional_float(_as_mapping(item.get("metrics")).get("return_on_entry_value")) or 0.0),
                -abs(_optional_float(_as_mapping(item.get("metrics")).get("net_pnl")) or 0.0),
                -int(item.get("sample_count") or 0),
            )
        )
    return items[:top]


def _metric_value(candidate: Mapping[str, Any], key: str, *, default: float) -> float:
    value = _optional_float(_as_mapping(candidate.get("metrics")).get(key))
    return default if value is None else value


def _evidence_strength_counts(candidates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        key = str(candidate.get("evidence_strength"))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _candidate_section(title: str, candidates: Any, *, limit: int) -> list[str]:
    rows = _as_sequence(candidates)
    lines = ["", title, ""]
    if not rows:
        lines.append("当前没有该类环境。")
        return lines
    lines.extend(
        [
            "| 证据强度 | 环境 | 样本 | 胜率 | 平均收益 | 净 PnL | 入场资金收益率 | 原因 | 交易编号 |",
            "|---|---|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for candidate in rows[:limit]:
        item = _as_mapping(candidate)
        metrics = _as_mapping(item.get("metrics"))
        lines.append(
            "| "
            f"{_escape_cell(item.get('evidence_strength_zh'))} | "
            f"{_escape_cell(item.get('label_zh'))} | "
            f"{item.get('sample_count')} | "
            f"{_format_optional_percent(metrics.get('win_rate'))} | "
            f"{_format_optional_percent(metrics.get('average_return_pct'))} | "
            f"{_format_optional_money(metrics.get('net_pnl'))} | "
            f"{_format_optional_percent(metrics.get('return_on_entry_value'))} | "
            f"{_escape_cell(item.get('reason_zh'))} | "
            f"{_format_indexes(item.get('trade_indexes'))} |"
        )
    if len(rows) > limit:
        lines.append("")
        lines.append(f"仅展示前 {limit} 条，完整明细见 `strategy_environment_profile.json`。")
    return lines


def _reason_zh(classification: str, risk_flags: Sequence[str]) -> str:
    if "low_sample" in risk_flags:
        return "样本数低于最小结论阈值，只能作为线索。"
    if "missing_profit_contribution" in risk_flags:
        return "缺少实际资金贡献口径，不能判断环境适配。"
    if "missing_return_stats" in risk_flags:
        return "缺少收益或胜率口径，不能判断环境适配。"
    if "mixed_metrics" in risk_flags:
        return "胜率、收益或资金贡献方向不一致，需要下钻样本。"
    if classification == "preferred":
        return "样本达到阈值，净 PnL 和入场资金收益率为正，且相对整体有优势。"
    if classification == "avoid":
        return "样本达到阈值，净 PnL 和入场资金收益率为负，且相对整体偏弱。"
    return "指标方向不足以归入适合或规避，需要继续验证。"


def _summary_key(summary: Mapping[str, Any]) -> str | None:
    kind = summary.get("summary_kind")
    if kind == "single_factor":
        field = summary.get("field")
        if field is None:
            return None
        return f"single:{field}={_value_token(summary.get('value'))}"
    if kind == "combination":
        fields = _as_mapping(summary.get("fields"))
        if fields:
            values = "|".join(f"{field}={_value_token(fields[field])}" for field in sorted(fields))
            return f"combination:{values}"
        profile_key = summary.get("profile_key")
        if profile_key is not None:
            return f"combination:{profile_key}"
    return None


def _value_token(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "missing"
    return str(value)


def _summary_kind_zh(value: Any) -> str:
    return {
        "single_factor": "单因子",
        "combination": "组合",
    }.get(str(value), str(value))


def _classification_zh(value: str) -> str:
    return {
        "preferred": "适合候选",
        "avoid": "规避候选",
        "uncertain": "不确定",
    }.get(value, value)


def _evidence_strength_zh(value: str) -> str:
    return {
        "strong": "强",
        "medium": "中",
        "weak": "弱",
        "low_sample": "样本不足",
        "incomplete": "证据不完整",
    }.get(value, value)


def _optional_delta(value: Any, baseline: Any) -> float | None:
    current = _optional_float(value)
    base = _optional_float(baseline)
    if current is None or base is None:
        return None
    return current - base


def _format_indexes(value: Any, *, limit: int = 12) -> str:
    indexes = _as_sequence(value)
    if not indexes:
        return "-"
    suffix = "..." if len(indexes) > limit else ""
    return ", ".join(str(index) for index in indexes[:limit]) + suffix


def _format_optional_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number * 100:.2f}%"


def _format_optional_money(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:,.2f}"


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "/") if value is not None else "-"


def _yes_no(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    return "-"


def _load_optional_mapping(source: Mapping[str, Any] | str | Path | None) -> Mapping[str, Any] | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source
    return _load_json(Path(source))


def _optional_path_string(source: Mapping[str, Any] | str | Path | None) -> str | None:
    if isinstance(source, (str, Path)):
        return str(source)
    return None


def _load_json(path: Path) -> Mapping[str, Any]:
    return _as_mapping(json.loads(path.read_text(encoding="utf-8")))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError:
        return None


def _drop_none(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
