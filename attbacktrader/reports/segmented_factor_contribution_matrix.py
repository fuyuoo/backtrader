"""Segmented factor contribution matrix from persisted environment-fit evidence."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SEGMENTED_FACTOR_CONTRIBUTION_MATRIX_SCHEMA = "attbacktrader.segmented_factor_contribution_matrix.v1"

DEFAULT_FACTOR_CONTRIBUTION_SEGMENTS: tuple[dict[str, str], ...] = (
    {
        "segment_id": "2015_2016_high_volatility_bear_shock",
        "label_zh": "2015-2016 高波动/熊市冲击",
        "start": "2015-01-01",
        "end": "2016-12-31",
    },
    {
        "segment_id": "2017_2018_structural_to_bear",
        "label_zh": "2017-2018 结构分化到熊市",
        "start": "2017-01-01",
        "end": "2018-12-31",
    },
    {
        "segment_id": "2019_2020_recovery_structural_bull",
        "label_zh": "2019-2020 修复/结构牛",
        "start": "2019-01-01",
        "end": "2020-12-31",
    },
    {
        "segment_id": "2021_2022_range_to_bear",
        "label_zh": "2021-2022 震荡转弱/熊市",
        "start": "2021-01-01",
        "end": "2022-12-31",
    },
    {
        "segment_id": "2023_2024_weak_range_repair",
        "label_zh": "2023-2024 弱势震荡/修复",
        "start": "2023-01-01",
        "end": "2024-12-31",
    },
)


def build_segmented_factor_contribution_matrix(
    environment_fit: Mapping[str, Any] | str | Path,
    *,
    segments: Sequence[Mapping[str, Any]] | None = None,
    min_segment_sample_count: int = 30,
    min_total_sample_count: int = 100,
) -> dict[str, Any]:
    """Build a factor contribution matrix by entry-date segment without rerunning strategies."""

    if min_segment_sample_count <= 0:
        raise ValueError("min_segment_sample_count must be greater than 0")
    if min_total_sample_count <= 0:
        raise ValueError("min_total_sample_count must be greater than 0")

    source = _load_environment_fit(environment_fit)
    segment_defs = _normalize_segments(segments or DEFAULT_FACTOR_CONTRIBUTION_SEGMENTS)
    trades = [
        _as_mapping(row)
        for row in _as_sequence(source.get("trade_contributions"))
        if _as_mapping(row.get("environment"))
    ]
    if not trades:
        raise ValueError("environment_fit must include non-empty trade_contributions with environment fields")

    field_labels = _field_labels(source, trades)
    segment_overall = _segment_overall(trades, segment_defs)
    overall = _stats(trades)
    bucket_rows = _factor_bucket_rows(
        trades,
        field_labels=field_labels,
        segments=segment_defs,
        segment_overall=segment_overall,
        min_segment_sample_count=min_segment_sample_count,
        min_total_sample_count=min_total_sample_count,
    )
    field_summaries = _field_summaries(bucket_rows, field_labels=field_labels)
    rankings = _rankings(bucket_rows)

    return {
        "schema": SEGMENTED_FACTOR_CONTRIBUTION_MATRIX_SCHEMA,
        "source_artifacts": {
            "environment_fit": _source_path(environment_fit),
        },
        "run_id": source.get("run_id"),
        "source_dir": source.get("source_dir"),
        "segment_policy": {
            "type": "manual_entry_date_interval",
            "caveat_zh": "区间是研究镜头，不是自动市场识别；贡献统计是归因线索，不是因果结论。",
        },
        "segments": segment_defs,
        "min_segment_sample_count": min_segment_sample_count,
        "min_total_sample_count": min_total_sample_count,
        "trade_count": len(trades),
        "field_count": len(field_labels),
        "factor_bucket_count": len(bucket_rows),
        "overall": overall,
        "segment_overall": segment_overall,
        "field_summaries": field_summaries,
        "factor_bucket_matrix": bucket_rows,
        "rankings": rankings,
        "ai_usage_rules": [
            "本报告只消费已落盘 environment_fit.trade_contributions，不重跑策略、不重新计算指标、不联网取数。",
            "segment_id 是人工研究区间；不要把它当作自动牛熊市识别结果。",
            "assessment 是基于分区间贡献稳定性的候选标签；不能直接作为策略开关，需后续样本外组合验证。",
            "low_sample、insufficient_segment_coverage 等风险标签优先于收益排序。",
        ],
    }


def render_segmented_factor_contribution_matrix_markdown_zh(
    report: Mapping[str, Any],
    *,
    ranking_limit: int = 30,
) -> str:
    """Render a concise Chinese Markdown view for the segmented matrix."""

    overall = _as_mapping(report.get("overall"))
    lines = [
        "# 10年分区间因子贡献矩阵",
        "",
        "## 概览",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| run_id | `{report.get('run_id')}` |",
        f"| 交易样本 | {report.get('trade_count')} |",
        f"| 因子字段 | {report.get('field_count')} |",
        f"| 因子桶 | {report.get('factor_bucket_count')} |",
        f"| 全样本胜率 | {_format_percent(overall.get('win_rate'))} |",
        f"| 全样本平均收益 | {_format_percent(overall.get('average_return_pct'))} |",
        f"| 全样本资金收益率 | {_format_percent(overall.get('return_on_entry_value'))} |",
        f"| 全样本净PnL | {_format_money(overall.get('net_pnl'))} |",
        "",
        "## 口径",
        "",
        "- 只读取 `environment_fit.trade_contributions` 中已落盘的事前环境字段和交易结果。",
        "- 区间按 `entry_date` 归属；跨区间持仓的收益归入入场所在区间。",
        "- `lift_vs_segment` 是该因子桶相对同区间全体交易的差值，不是因果贡献。",
        "- 默认候选榜单只纳入 `entry_decision` 字段；包含 `entry_to_exit`、`exit` 或 `trade` 语义的字段仅作诊断。",
        "- `stable_positive` 表示多个有样本区间为正且相对区间有优势；`environment_specific` 表示更像阶段性因子。",
        "- 低样本和缺区间覆盖不删除，但必须作为风险处理。",
        "",
        "## 区间",
        "",
        "| 区间 | 日期 | 样本 | 资金收益率 | 胜率 | 净PnL |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for segment in _as_sequence(report.get("segment_overall")):
        item = _as_mapping(segment)
        lines.append(
            f"| {item.get('label_zh') or item.get('segment_id')} | "
            f"{item.get('start')}~{item.get('end')} | "
            f"{item.get('sample_count')} | "
            f"{_format_percent(item.get('return_on_entry_value'))} | "
            f"{_format_percent(item.get('win_rate'))} | "
            f"{_format_money(item.get('net_pnl'))} |"
        )

    lines.extend(_ranking_section("稳定正向候选", _as_sequence(_as_mapping(report.get("rankings")).get("stable_positive")), ranking_limit))
    lines.extend(_ranking_section("环境型候选", _as_sequence(_as_mapping(report.get("rankings")).get("environment_specific")), ranking_limit))
    lines.extend(_ranking_section("偏负向/风险候选", _as_sequence(_as_mapping(report.get("rankings")).get("mostly_negative")), ranking_limit))
    lines.extend(_ranking_section("诊断字段（不进入可实操候选）", _as_sequence(_as_mapping(report.get("rankings")).get("diagnostic_only")), ranking_limit))
    lines.extend(_field_section(_as_sequence(report.get("field_summaries"))))
    return "\n".join(lines) + "\n"


def write_segmented_factor_contribution_matrix(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
    artifact_stem: str = "segmented_factor_contribution_matrix",
) -> tuple[Path, Path, dict[str, Any]]:
    """Write JSON and Chinese Markdown artifacts."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    payload = _jsonable(dict(report))
    json_path = output_path / f"{artifact_stem}.json"
    markdown_path = output_path / f"{artifact_stem}.zh.md"
    payload["artifacts"] = {
        "matrix_json": str(json_path),
        "matrix_markdown_zh": str(markdown_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_segmented_factor_contribution_matrix_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def safe_segmented_factor_contribution_matrix_dir_name(source_path: str | Path) -> str:
    """Build a stable report directory name from a source artifact path."""

    path = Path(source_path)
    name = path.parent.name if path.name.startswith("environment_fit") else path.name
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return f"segmented-factor-contribution-matrix-{safe or 'environment-fit'}"


def _factor_bucket_rows(
    trades: Sequence[Mapping[str, Any]],
    *,
    field_labels: Mapping[str, str],
    segments: Sequence[Mapping[str, Any]],
    segment_overall: Sequence[Mapping[str, Any]],
    min_segment_sample_count: int,
    min_total_sample_count: int,
) -> list[dict[str, Any]]:
    by_bucket: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    values_by_key: dict[tuple[str, str], Any] = {}
    by_bucket_segment: dict[tuple[str, str], dict[str, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    segment_by_id = {str(segment["segment_id"]): segment for segment in segments}

    for trade in trades:
        segment = _segment_for_trade(trade, segments)
        if segment is None:
            continue
        segment_id = str(segment["segment_id"])
        environment = _as_mapping(trade.get("environment"))
        for field in field_labels:
            value = environment.get(field)
            if value is None:
                continue
            value_key = _stable_value_key(value)
            key = (field, value_key)
            values_by_key[key] = value
            by_bucket[key].append(trade)
            by_bucket_segment[key][segment_id].append(trade)

    segment_stats_by_id = {str(item["segment_id"]): item for item in segment_overall}
    rows: list[dict[str, Any]] = []
    for key, all_rows in by_bucket.items():
        field, value_key = key
        segment_rows: list[dict[str, Any]] = []
        supported = 0
        positive = 0
        negative = 0
        outperform = 0
        best: dict[str, Any] | None = None
        worst: dict[str, Any] | None = None
        for segment_id, segment in segment_by_id.items():
            stats = _stats(by_bucket_segment[key].get(segment_id, []))
            base = _as_mapping(segment_stats_by_id.get(segment_id))
            enriched = {
                "segment_id": segment_id,
                "label_zh": segment.get("label_zh"),
                "start": segment.get("start"),
                "end": segment.get("end"),
                **stats,
                "lift_vs_segment": _lift(stats, base),
            }
            segment_rows.append(enriched)
            if int(stats.get("sample_count") or 0) >= min_segment_sample_count:
                supported += 1
                roev = _optional_float(stats.get("return_on_entry_value"))
                lift_roev = _optional_float(_as_mapping(enriched["lift_vs_segment"]).get("return_on_entry_value"))
                if roev is not None and roev > 0:
                    positive += 1
                if roev is not None and roev < 0:
                    negative += 1
                if lift_roev is not None and lift_roev > 0:
                    outperform += 1
                if best is None or _rank_value(stats) > _rank_value(best):
                    best = enriched
                if worst is None or _rank_value(stats) < _rank_value(worst):
                    worst = enriched

        all_stats = _stats(all_rows)
        assessment = _assessment(
            all_stats,
            supported_segment_count=supported,
            positive_segment_count=positive,
            negative_segment_count=negative,
            outperform_segment_count=outperform,
            min_total_sample_count=min_total_sample_count,
        )
        rows.append(
            {
                "field": field,
                "field_label_zh": field_labels[field],
                "field_usage": _field_usage(field),
                "value": _jsonable(values_by_key[key]),
                "value_label_zh": str(values_by_key[key]),
                "label_zh": f"{field_labels[field]}={values_by_key[key]}",
                "summary": all_stats,
                "segment_count": len(segments),
                "supported_segment_count": supported,
                "positive_segment_count": positive,
                "negative_segment_count": negative,
                "outperform_segment_count": outperform,
                "positive_segment_ratio": positive / supported if supported else None,
                "outperform_segment_ratio": outperform / supported if supported else None,
                "assessment": assessment,
                "best_segment": _segment_ref(best),
                "worst_segment": _segment_ref(worst),
                "segments": segment_rows,
            }
        )
    return sorted(rows, key=lambda item: (str(item.get("field")), str(item.get("value_label_zh"))))


def _segment_overall(
    trades: Sequence[Mapping[str, Any]],
    segments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment in segments:
        segment_trades = [trade for trade in trades if _date_in_segment(str(trade.get("entry_date") or ""), segment)]
        rows.append(
            {
                "segment_id": segment["segment_id"],
                "label_zh": segment.get("label_zh"),
                "start": segment["start"],
                "end": segment["end"],
                **_stats(segment_trades),
            }
        )
    return rows


def _stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    returns = [value for row in rows if (value := _optional_float(row.get("return_pct"))) is not None]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    contributions = [
        row
        for row in rows
        if row.get("contribution_available") is True
        and _optional_float(row.get("entry_gross_value")) is not None
        and _optional_float(row.get("net_pnl")) is not None
    ]
    entry_values = [_optional_float(row.get("entry_gross_value")) or 0.0 for row in contributions]
    pnls = [_optional_float(row.get("net_pnl")) or 0.0 for row in contributions]
    pnl_wins = [value for value in pnls if value > 0]
    pnl_losses = [value for value in pnls if value < 0]
    total_entry_value = sum(entry_values)
    net_pnl = sum(pnls)
    exit_reasons = Counter(str(row.get("exit_reason")) for row in rows if row.get("exit_reason") is not None)
    return {
        "sample_count": len(rows),
        "return_sample_count": len(returns),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": len(wins) / len(returns) if returns else None,
        "average_return_pct": _average(returns),
        "median_return_pct": _percentile(returns, 0.5),
        "average_win_return_pct": _average(wins),
        "average_loss_return_pct": _average(losses),
        "financial_trade_count": len(contributions),
        "total_entry_value": total_entry_value if contributions else None,
        "net_pnl": net_pnl if contributions else None,
        "return_on_entry_value": net_pnl / total_entry_value if total_entry_value > 0 else None,
        "pnl_win_count": len(pnl_wins),
        "pnl_loss_count": len(pnl_losses),
        "pnl_win_rate": len(pnl_wins) / len(contributions) if contributions else None,
        "profit_factor": sum(pnl_wins) / abs(sum(pnl_losses)) if pnl_losses else None,
        "exit_reason_counts": [
            {"code": code, "count": count}
            for code, count in sorted(exit_reasons.items(), key=lambda item: (-item[1], item[0]))
        ],
        "trade_indexes": [row.get("trade_index") for row in rows if row.get("trade_index") is not None],
    }


def _field_summaries(
    bucket_rows: Sequence[Mapping[str, Any]],
    *,
    field_labels: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows_by_field: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in bucket_rows:
        rows_by_field[str(row.get("field"))].append(row)
    summaries = []
    for field, rows in rows_by_field.items():
        assessments = Counter(str(row.get("assessment")) for row in rows)
        stable_count = assessments.get("stable_positive", 0)
        environment_count = assessments.get("environment_specific", 0)
        negative_count = assessments.get("mostly_negative", 0)
        summaries.append(
            {
                "field": field,
                "field_label_zh": field_labels.get(field, field),
                "field_usage": _field_usage(field),
                "bucket_count": len(rows),
                "stable_positive_bucket_count": stable_count,
                "environment_specific_bucket_count": environment_count,
                "mostly_negative_bucket_count": negative_count,
                "low_sample_bucket_count": assessments.get("low_sample", 0),
                "top_bucket_by_return_on_entry_value": _bucket_ref(
                    max(rows, key=lambda item: _optional_float(_as_mapping(item.get("summary")).get("return_on_entry_value")) or -math.inf)
                ),
            }
        )
    return sorted(summaries, key=lambda item: str(item.get("field")))


def _rankings(bucket_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    entry_rows = [row for row in bucket_rows if row.get("field_usage") == "entry_decision"]
    diagnostic_rows = [row for row in bucket_rows if row.get("field_usage") != "entry_decision"]
    stable = [row for row in entry_rows if row.get("assessment") == "stable_positive"]
    environment = [row for row in entry_rows if row.get("assessment") == "environment_specific"]
    negative = [row for row in entry_rows if row.get("assessment") == "mostly_negative"]
    return {
        "stable_positive": [_ranking_ref(row) for row in sorted(stable, key=_stable_rank_key, reverse=True)],
        "environment_specific": [_ranking_ref(row) for row in sorted(environment, key=_environment_rank_key, reverse=True)],
        "mostly_negative": [_ranking_ref(row) for row in sorted(negative, key=_negative_rank_key)],
        "diagnostic_only": [_ranking_ref(row) for row in sorted(diagnostic_rows, key=_environment_rank_key, reverse=True)],
    }


def _assessment(
    stats: Mapping[str, Any],
    *,
    supported_segment_count: int,
    positive_segment_count: int,
    negative_segment_count: int,
    outperform_segment_count: int,
    min_total_sample_count: int,
) -> str:
    sample_count = int(stats.get("sample_count") or 0)
    if sample_count < min_total_sample_count:
        return "low_sample"
    if supported_segment_count < 2:
        return "insufficient_segment_coverage"
    positive_ratio = positive_segment_count / supported_segment_count
    outperform_ratio = outperform_segment_count / supported_segment_count
    negative_ratio = negative_segment_count / supported_segment_count
    if positive_ratio >= 0.8 and outperform_ratio >= 0.6:
        return "stable_positive"
    if negative_ratio >= 0.6:
        return "mostly_negative"
    return "environment_specific"


def _lift(stats: Mapping[str, Any], base: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "win_rate": _diff(stats.get("win_rate"), base.get("win_rate")),
        "average_return_pct": _diff(stats.get("average_return_pct"), base.get("average_return_pct")),
        "return_on_entry_value": _diff(stats.get("return_on_entry_value"), base.get("return_on_entry_value")),
        "profit_factor": _diff(stats.get("profit_factor"), base.get("profit_factor")),
    }


def _ranking_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    summary = _as_mapping(row.get("summary"))
    return {
        "field": row.get("field"),
        "field_label_zh": row.get("field_label_zh"),
        "field_usage": row.get("field_usage"),
        "value": row.get("value"),
        "value_label_zh": row.get("value_label_zh"),
        "label_zh": row.get("label_zh"),
        "assessment": row.get("assessment"),
        "sample_count": summary.get("sample_count"),
        "return_on_entry_value": summary.get("return_on_entry_value"),
        "win_rate": summary.get("win_rate"),
        "net_pnl": summary.get("net_pnl"),
        "positive_segment_count": row.get("positive_segment_count"),
        "supported_segment_count": row.get("supported_segment_count"),
        "outperform_segment_count": row.get("outperform_segment_count"),
        "best_segment": row.get("best_segment"),
        "worst_segment": row.get("worst_segment"),
    }


def _bucket_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    summary = _as_mapping(row.get("summary"))
    return {
        "field": row.get("field"),
        "value": row.get("value"),
        "value_label_zh": row.get("value_label_zh"),
        "assessment": row.get("assessment"),
        "sample_count": summary.get("sample_count"),
        "return_on_entry_value": summary.get("return_on_entry_value"),
    }


def _segment_ref(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "segment_id": row.get("segment_id"),
        "label_zh": row.get("label_zh"),
        "sample_count": row.get("sample_count"),
        "return_on_entry_value": row.get("return_on_entry_value"),
        "win_rate": row.get("win_rate"),
        "lift_vs_segment": row.get("lift_vs_segment"),
    }


def _stable_rank_key(row: Mapping[str, Any]) -> tuple[float, float, float, int]:
    summary = _as_mapping(row.get("summary"))
    return (
        float(row.get("positive_segment_ratio") or 0.0),
        float(row.get("outperform_segment_ratio") or 0.0),
        _optional_float(summary.get("return_on_entry_value")) or -math.inf,
        int(summary.get("sample_count") or 0),
    )


def _environment_rank_key(row: Mapping[str, Any]) -> tuple[float, float, int]:
    best = _as_mapping(row.get("best_segment"))
    worst = _as_mapping(row.get("worst_segment"))
    spread = (_optional_float(best.get("return_on_entry_value")) or 0.0) - (
        _optional_float(worst.get("return_on_entry_value")) or 0.0
    )
    summary = _as_mapping(row.get("summary"))
    return (spread, _optional_float(best.get("return_on_entry_value")) or -math.inf, int(summary.get("sample_count") or 0))


def _negative_rank_key(row: Mapping[str, Any]) -> tuple[float, int]:
    summary = _as_mapping(row.get("summary"))
    return (_optional_float(summary.get("return_on_entry_value")) or math.inf, -int(summary.get("sample_count") or 0))


def _rank_value(stats: Mapping[str, Any]) -> float:
    value = _optional_float(stats.get("return_on_entry_value"))
    if value is not None:
        return value
    value = _optional_float(stats.get("average_return_pct"))
    return value if value is not None else -math.inf


def _field_labels(source: Mapping[str, Any], trades: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in _as_sequence(source.get("environment_fields")):
        field = str(_as_mapping(item).get("field") or "")
        if field:
            labels[field] = str(_as_mapping(item).get("label_zh") or field)
    if labels:
        return dict(sorted(labels.items()))
    fields = sorted({str(key) for trade in trades for key in _as_mapping(trade.get("environment")).keys()})
    return {field: field for field in fields}


def _field_usage(field: str) -> str:
    lowered = field.lower()
    if "entry_to_exit" in lowered or lowered.startswith("exit.") or lowered.startswith("trade."):
        return "diagnostic_only"
    return "entry_decision"


def _segment_for_trade(
    trade: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    entry_date = str(trade.get("entry_date") or "")
    for segment in segments:
        if _date_in_segment(entry_date, segment):
            return segment
    return None


def _date_in_segment(entry_date: str, segment: Mapping[str, Any]) -> bool:
    return bool(entry_date) and str(segment["start"]) <= entry_date <= str(segment["end"])


def _normalize_segments(segments: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in segments:
        segment_id = str(item.get("segment_id") or "")
        start = str(item.get("start") or "")
        end = str(item.get("end") or "")
        if not segment_id or not start or not end:
            raise ValueError("each segment must include segment_id, start, and end")
        if start > end:
            raise ValueError(f"segment start must be <= end: {segment_id}")
        if segment_id in seen:
            raise ValueError(f"duplicate segment_id: {segment_id}")
        seen.add(segment_id)
        normalized.append(
            {
                "segment_id": segment_id,
                "label_zh": str(item.get("label_zh") or segment_id),
                "start": start,
                "end": end,
            }
        )
    return normalized


def _load_environment_fit(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = _resolve_environment_fit_path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"environment fit artifact must be a JSON object: {path}")
    return payload


def _resolve_environment_fit_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_dir():
        enriched = path / "environment_fit.enriched.json"
        if enriched.exists():
            return enriched
        plain = path / "environment_fit.json"
        if plain.exists():
            return plain
        raise FileNotFoundError(f"no environment_fit.enriched.json or environment_fit.json under {path}")
    return path


def _source_path(value: Mapping[str, Any] | str | Path) -> str | None:
    if isinstance(value, Mapping):
        return None
    return str(_resolve_environment_fit_path(value))


def _ranking_section(title: str, rows: Sequence[Any], limit: int) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| 因子桶 | 评估 | 样本 | 资金收益率 | 胜率 | 正区间/覆盖 | 最好区间 | 最差区间 |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    if not rows:
        lines.append("| 无 | - | - | - | - | - | - | - |")
        return lines
    for row in rows[:limit]:
        item = _as_mapping(row)
        best = _as_mapping(item.get("best_segment"))
        worst = _as_mapping(item.get("worst_segment"))
        lines.append(
            f"| {item.get('label_zh')} | "
            f"{item.get('assessment')} | "
            f"{item.get('sample_count')} | "
            f"{_format_percent(item.get('return_on_entry_value'))} | "
            f"{_format_percent(item.get('win_rate'))} | "
            f"{item.get('positive_segment_count')}/{item.get('supported_segment_count')} | "
            f"{best.get('label_zh') or '-'} {_format_percent(best.get('return_on_entry_value'))} | "
            f"{worst.get('label_zh') or '-'} {_format_percent(worst.get('return_on_entry_value'))} |"
        )
    return lines


def _field_section(rows: Sequence[Any]) -> list[str]:
    lines = [
        "",
        "## 字段概览",
        "",
        "| 字段 | 用途 | 桶数 | 稳定正向 | 环境型 | 偏负向 | 低样本 | 最优桶 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        item = _as_mapping(row)
        top = _as_mapping(item.get("top_bucket_by_return_on_entry_value"))
        lines.append(
            f"| {item.get('field_label_zh')} `{item.get('field')}` | "
            f"{item.get('field_usage')} | "
            f"{item.get('bucket_count')} | "
            f"{item.get('stable_positive_bucket_count')} | "
            f"{item.get('environment_specific_bucket_count')} | "
            f"{item.get('mostly_negative_bucket_count')} | "
            f"{item.get('low_sample_bucket_count')} | "
            f"{top.get('value_label_zh')} {_format_percent(top.get('return_on_entry_value'))} |"
        )
    return lines


def _diff(left: Any, right: Any) -> float | None:
    left_value = _optional_float(left)
    right_value = _optional_float(right)
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def _average(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _stable_value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return value


def _format_percent(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:.2%}"


def _format_money(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:,.0f}"
