"""Single-factor attribution reports from persisted attribution wide samples."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .attribution_wide_samples import (
    load_attribution_field_index,
    load_attribution_wide_samples,
)


SINGLE_FACTOR_ATTRIBUTION_SCHEMA = "attbacktrader.single_factor_attribution.v1"
MA25_PROFIT_EXIT_REASON = "BAOMA_MA25_PROFIT_EXIT_TRIGGERED"
MA60_STOP_EXIT_REASON = "BAOMA_MA60_STOP_TRIGGERED"


def build_single_factor_attribution_report(
    wide_samples: Mapping[str, Any] | str | Path,
    *,
    field_index: Mapping[str, Any] | str | Path | None = None,
    min_bucket_sample_count: int = 20,
    high_missing_ratio: float = 0.2,
) -> dict[str, Any]:
    """Build a full single-factor attribution report without rerunning a strategy."""

    if min_bucket_sample_count <= 0:
        raise ValueError("min_bucket_sample_count must be greater than 0")
    if not 0 <= high_missing_ratio <= 1:
        raise ValueError("high_missing_ratio must be between 0 and 1")

    wide = load_attribution_wide_samples(wide_samples)
    index = (
        load_attribution_field_index(field_index)
        if field_index is not None
        else _as_mapping(wide.get("field_index"))
    )
    fields = [_as_mapping(field) for field in _as_sequence(index.get("fields"))]
    samples = [_as_mapping(sample) for sample in _as_sequence(wide.get("samples"))]
    overall = _stats(samples)

    entry_field_summaries: list[dict[str, Any]] = []
    entry_bucket_summaries: list[dict[str, Any]] = []
    post_trade_field_summaries: list[dict[str, Any]] = []
    post_trade_bucket_summaries: list[dict[str, Any]] = []
    excluded_fields: list[dict[str, Any]] = []

    for field in fields:
        role = _field_role(field)
        field_summary, bucket_summaries = _summarize_field(
            field,
            samples=samples,
            min_bucket_sample_count=min_bucket_sample_count,
            high_missing_ratio=high_missing_ratio,
            overall=overall,
        )
        if role == "entry_factor":
            entry_field_summaries.append(field_summary)
            entry_bucket_summaries.extend(bucket_summaries)
        elif role == "post_trade_stat":
            post_trade_field_summaries.append(field_summary)
            post_trade_bucket_summaries.extend(bucket_summaries)
        else:
            excluded_fields.append(
                {
                    **field_summary,
                    "excluded_reason": _excluded_reason(field),
                }
            )

    return {
        "schema": SINGLE_FACTOR_ATTRIBUTION_SCHEMA,
        "run_id": wide.get("run_id"),
        "source_dir": wide.get("source_dir"),
        "source_artifacts": {
            "wide_samples": _source_path(wide_samples),
            "field_index": _source_path(field_index) if field_index is not None else None,
        },
        "sample_count": len(samples),
        "field_count": len(fields),
        "entry_factor_count": len(entry_field_summaries),
        "post_trade_stat_count": len(post_trade_field_summaries),
        "excluded_field_count": len(excluded_fields),
        "min_bucket_sample_count": min_bucket_sample_count,
        "high_missing_ratio": high_missing_ratio,
        "overall": overall,
        "entry_factor_fields": sorted(entry_field_summaries, key=lambda item: str(item.get("field_key"))),
        "entry_single_factor_summaries": sorted(
            entry_bucket_summaries,
            key=lambda item: (str(item.get("field_key")), -int(item.get("sample_count", 0)), str(item.get("value"))),
        ),
        "entry_rankings": _rankings(entry_bucket_summaries, min_bucket_sample_count=min_bucket_sample_count),
        "post_trade_fields": sorted(post_trade_field_summaries, key=lambda item: str(item.get("field_key"))),
        "post_trade_summaries": sorted(
            post_trade_bucket_summaries,
            key=lambda item: (str(item.get("field_key")), -int(item.get("sample_count", 0)), str(item.get("value"))),
        ),
        "excluded_fields": sorted(excluded_fields, key=lambda item: str(item.get("field_key"))),
        "ai_usage_rules": [
            "entry_single_factor_summaries 包含 timing=entry 字段，以及离散的 symbol/industry/market 旧版事前字段，可作为后续二因子组合候选池。",
            "post_trade_summaries 只用于持仓后路径统计，不能用于筛选入场环境或构造入场组合。",
            "rankings 只排序不筛除；low_sample、no_contrast、high_missing 等 flags 是风险提示，不是自动结论。",
            "该报告只消费已落盘 attribution_wide_samples 和 attribution_field_index，不重跑策略、不联网拉数据。",
        ],
    }


def render_single_factor_attribution_markdown_zh(report: Mapping[str, Any], *, ranking_limit: int = 30) -> str:
    """Render a Chinese Markdown report for single-factor attribution."""

    overall = _as_mapping(report.get("overall"))
    lines = [
        "# 单因子归因全景",
        "",
        "## 概览",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| run_id | `{report.get('run_id')}` |",
        f"| 交易样本 | {report.get('sample_count')} |",
        f"| 字段总数 | {report.get('field_count')} |",
        f"| 事前因子字段 | {report.get('entry_factor_count')} |",
        f"| 持仓后统计字段 | {report.get('post_trade_stat_count')} |",
        f"| 未进入本报告主归因字段 | {report.get('excluded_field_count')} |",
        f"| 全样本胜率 | {_format_percent(overall.get('win_rate'))} |",
        f"| 全样本平均收益 | {_format_percent(overall.get('average_return_pct'))} |",
        f"| 全样本中位收益 | {_format_percent(overall.get('median_return_pct'))} |",
        f"| 全样本最大单笔收益 | {_format_percent(overall.get('max_return_pct'))} |",
        f"| 全样本最差单笔收益 | {_format_percent(overall.get('min_return_pct'))} |",
        f"| 全样本单笔收益波动率 | {_format_percent(overall.get('return_volatility_pct'))} |",
        f"| 全样本交易PnL路径最大回撤/入场资金 | {_format_percent(overall.get('pnl_path_max_drawdown_on_entry_value'))} |",
        f"| 全样本净PnL | {_format_money(overall.get('net_pnl'))} |",
        f"| 全样本资金收益率 | {_format_percent(overall.get('return_on_entry_value'))} |",
    ]
    lines.extend(
        [
            "",
            "## 口径",
            "",
            "- 事前归因使用 `timing=entry` 字段，并纳入离散的 `symbol`、`industry`、`market` 旧版事前字段。",
            "- `timing=post_trade` 字段只做持仓后路径统计，不参与入场组合。",
            "- 平均收益、最大收益和波动率都基于单笔 `return_pct`，不是账户总权益曲线。",
            "- 表格里的 PnL 回撤按 `trade_index` 顺序累计每笔 `net_pnl`，再除以该桶总入场资金；不是账户总权益曲线。",
            "- JSON 额外保留 `return_path_max_drawdown_pct`，即等权复利串联单笔收益率后的交易收益路径回撤。",
            "- 所有桶都保留在 JSON 中；Markdown 的榜单只是多视角排序。",
            "- `low_sample`、`no_contrast`、`high_missing` 是风险标记，不会自动删除字段。",
        ]
    )

    lines.extend(_field_overview_section(_as_sequence(report.get("entry_factor_fields"))))
    lines.extend(_ranking_section("按平均收益排序", _as_mapping(report.get("entry_rankings")).get("by_average_return"), ranking_limit))
    lines.extend(_ranking_section("按风险调整收益排序", _as_mapping(report.get("entry_rankings")).get("by_risk_adjusted_return"), ranking_limit))
    lines.extend(_ranking_section("按最大单笔收益排序", _as_mapping(report.get("entry_rankings")).get("by_max_return"), ranking_limit))
    lines.extend(_ranking_section("按交易PnL路径低回撤排序", _as_mapping(report.get("entry_rankings")).get("by_low_pnl_path_drawdown"), ranking_limit))
    lines.extend(_ranking_section("按单笔收益低波动排序", _as_mapping(report.get("entry_rankings")).get("by_low_return_volatility"), ranking_limit))
    lines.extend(_ranking_section("按胜率排序", _as_mapping(report.get("entry_rankings")).get("by_win_rate"), ranking_limit))
    lines.extend(_ranking_section("按资金收益率排序", _as_mapping(report.get("entry_rankings")).get("by_return_on_entry_value"), ranking_limit))
    lines.extend(_ranking_section("按净PnL排序", _as_mapping(report.get("entry_rankings")).get("by_net_pnl"), ranking_limit))
    lines.extend(_ranking_section("按MA60退出高发排序", _as_mapping(report.get("entry_rankings")).get("by_ma60_stop_exit_rate"), ranking_limit))
    lines.extend(_ranking_section("按MA25盈利退出高发排序", _as_mapping(report.get("entry_rankings")).get("by_ma25_profit_exit_rate"), ranking_limit))
    lines.extend(_all_bucket_section("事前单因子全量桶明细", _as_sequence(report.get("entry_single_factor_summaries"))))
    lines.extend(_all_bucket_section("持仓后统计", _as_sequence(report.get("post_trade_summaries"))))
    lines.extend(_excluded_section(_as_sequence(report.get("excluded_fields"))))
    return "\n".join(lines) + "\n"


def write_single_factor_attribution_report(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
    artifact_stem: str = "single_factor_attribution",
) -> tuple[Path, Path]:
    """Write JSON and Chinese Markdown artifacts."""

    output_path = Path(output_dir or report.get("source_dir") or ".")
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{artifact_stem}.json"
    markdown_path = output_path / f"{artifact_stem}.zh.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_single_factor_attribution_markdown_zh(report), encoding="utf-8")
    return json_path, markdown_path


def _summarize_field(
    field: Mapping[str, Any],
    *,
    samples: Sequence[Mapping[str, Any]],
    min_bucket_sample_count: int,
    high_missing_ratio: float,
    overall: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    field_key = str(field.get("field_key"))
    buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    values: dict[str, Any] = {}
    exception_counts: Counter[str] = Counter()
    sample_count = 0
    missing_count = 0
    for sample in samples:
        payload = _as_mapping(_as_mapping(sample.get("field_values")).get(field_key))
        if not payload:
            continue
        sample_count += 1
        value = _field_value(field_key, field, payload)
        for code in _as_sequence(payload.get("exception_codes")):
            exception_counts[str(code)] += 1
        if value is None:
            missing_count += 1
            continue
        value_key = _stable_value_key(value)
        values[value_key] = value
        buckets[value_key].append(sample)

    valid_count = sample_count - missing_count
    missing_ratio = missing_count / sample_count if sample_count else None
    non_empty_bucket_count = len(buckets)
    field_flags = _field_flags(
        missing_ratio=missing_ratio,
        non_empty_bucket_count=non_empty_bucket_count,
        high_missing_ratio=high_missing_ratio,
    )
    field_summary = {
        "field_key": field_key,
        "label_zh": field.get("label_zh") or field_key,
        "timing": field.get("timing"),
        "scope": field.get("scope"),
        "value_type": field.get("value_type"),
        "default_in_environment_fit": bool(field.get("default_in_environment_fit")),
        "sample_count": sample_count,
        "valid_count": valid_count,
        "missing_count": missing_count,
        "missing_ratio": missing_ratio,
        "non_empty_bucket_count": non_empty_bucket_count,
        "exception_count": sum(exception_counts.values()),
        "exception_top_codes": [
            {"code": code, "count": count}
            for code, count in exception_counts.most_common(5)
        ],
        "flags": field_flags,
    }

    summaries = []
    for value_key, rows in buckets.items():
        stats = _stats(rows)
        flags = list(field_flags)
        if int(stats.get("sample_count", 0)) < min_bucket_sample_count:
            flags.append("low_sample")
        if _optional_float(stats.get("return_on_entry_value")) is not None and _optional_float(overall.get("return_on_entry_value")) is not None:
            if float(stats["return_on_entry_value"]) < float(overall["return_on_entry_value"]):
                flags.append("capital_below_overall")
        summaries.append(
            {
                **stats,
                "field_key": field_key,
                "field_label_zh": field.get("label_zh") or field_key,
                "timing": field.get("timing"),
                "scope": field.get("scope"),
                "value": _jsonable(values[value_key]),
                "value_label_zh": str(values[value_key]),
                "label_zh": f"{field.get('label_zh') or field_key}={values[value_key]}",
                "flags": sorted(set(flags)),
            }
        )
    return field_summary, summaries


def _stats(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    returns = [
        value
        for sample in samples
        if (value := _optional_float(sample.get("return_pct"))) is not None
    ]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    negative_returns = [value for value in returns if value < 0]
    average_return = _average(returns)
    average_win_return = _average(wins)
    average_loss_return = _average(losses)
    average_negative_return = _average(negative_returns)
    return_volatility = _population_stddev(returns)
    contributions = [
        _as_mapping(sample.get("profit_contribution"))
        for sample in samples
        if _as_mapping(sample.get("profit_contribution")).get("contribution_available") is True
    ]
    entry_values = [_optional_float(item.get("entry_gross_value")) or 0.0 for item in contributions]
    net_pnls = [_optional_float(item.get("net_pnl")) or 0.0 for item in contributions]
    total_entry_value = sum(entry_values)
    total_net_pnl = sum(net_pnls)
    exit_reasons = Counter(str(sample.get("exit_reason")) for sample in samples if sample.get("exit_reason") is not None)
    return {
        "sample_count": len(samples),
        "return_sample_count": len(returns),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": len(wins) / len(returns) if returns else None,
        "average_return_pct": average_return,
        "median_return_pct": _percentile(returns, 0.5),
        "p10_return_pct": _percentile(returns, 0.1),
        "p25_return_pct": _percentile(returns, 0.25),
        "p75_return_pct": _percentile(returns, 0.75),
        "p90_return_pct": _percentile(returns, 0.9),
        "max_return_pct": max(returns) if returns else None,
        "min_return_pct": min(returns) if returns else None,
        "return_volatility_pct": return_volatility,
        "return_path_max_drawdown_pct": _return_path_max_drawdown(samples),
        "pnl_path_max_drawdown_on_entry_value": _pnl_path_max_drawdown_on_entry_value(samples),
        "risk_adjusted_return": (
            average_return / return_volatility
            if average_return is not None and return_volatility not in (None, 0)
            else None
        ),
        "average_win_return_pct": average_win_return,
        "average_loss_return_pct": average_loss_return,
        "profit_loss_ratio": (
            average_win_return / abs(average_negative_return)
            if average_win_return is not None and average_negative_return not in (None, 0)
            else None
        ),
        "financial_trade_count": len(contributions),
        "total_entry_value": total_entry_value if contributions else None,
        "net_pnl": total_net_pnl if contributions else None,
        "return_on_entry_value": total_net_pnl / total_entry_value if total_entry_value > 0 else None,
        "ma25_profit_exit_count": exit_reasons.get(MA25_PROFIT_EXIT_REASON, 0),
        "ma25_profit_exit_rate": exit_reasons.get(MA25_PROFIT_EXIT_REASON, 0) / len(samples) if samples else None,
        "ma60_stop_exit_count": exit_reasons.get(MA60_STOP_EXIT_REASON, 0),
        "ma60_stop_exit_rate": exit_reasons.get(MA60_STOP_EXIT_REASON, 0) / len(samples) if samples else None,
        "exit_reason_counts": [
            {"code": code, "count": count}
            for code, count in sorted(exit_reasons.items(), key=lambda item: (-item[1], item[0]))
        ],
        "trade_indexes": [sample.get("trade_index") for sample in samples if sample.get("trade_index") is not None],
    }


def _rankings(summaries: Sequence[Mapping[str, Any]], *, min_bucket_sample_count: int) -> dict[str, list[dict[str, Any]]]:
    return {
        "by_win_rate": _rank(summaries, key="win_rate", min_bucket_sample_count=min_bucket_sample_count),
        "by_average_return": _rank(summaries, key="average_return_pct", min_bucket_sample_count=min_bucket_sample_count),
        "by_risk_adjusted_return": _rank(summaries, key="risk_adjusted_return", min_bucket_sample_count=min_bucket_sample_count),
        "by_max_return": _rank(summaries, key="max_return_pct", min_bucket_sample_count=min_bucket_sample_count),
        "by_low_return_volatility": _rank(
            summaries,
            key="return_volatility_pct",
            min_bucket_sample_count=min_bucket_sample_count,
            lower_is_better=True,
        ),
        "by_low_return_path_max_drawdown": _rank(
            summaries,
            key="return_path_max_drawdown_pct",
            min_bucket_sample_count=min_bucket_sample_count,
            lower_is_better=True,
        ),
        "by_low_pnl_path_drawdown": _rank(
            summaries,
            key="pnl_path_max_drawdown_on_entry_value",
            min_bucket_sample_count=min_bucket_sample_count,
            lower_is_better=True,
        ),
        "by_return_on_entry_value": _rank(summaries, key="return_on_entry_value", min_bucket_sample_count=min_bucket_sample_count),
        "by_net_pnl": _rank(summaries, key="net_pnl", min_bucket_sample_count=min_bucket_sample_count),
        "by_ma60_stop_exit_rate": _rank(summaries, key="ma60_stop_exit_rate", min_bucket_sample_count=min_bucket_sample_count),
        "by_ma25_profit_exit_rate": _rank(summaries, key="ma25_profit_exit_rate", min_bucket_sample_count=min_bucket_sample_count),
    }


def _rank(
    summaries: Sequence[Mapping[str, Any]],
    *,
    key: str,
    min_bucket_sample_count: int,
    lower_is_better: bool = False,
) -> list[dict[str, Any]]:
    ranked = [
        _compact_summary(summary)
        for summary in summaries
        if _optional_float(summary.get(key)) is not None
    ]
    ranked.sort(
        key=lambda item: (
            float(item.get(key) or 0.0),
            int(item.get("sample_count") or 0),
        ),
        reverse=not lower_is_better,
    )
    return [
        {
            **item,
            "ranking_sample_policy": (
                "meets_min_bucket_sample_count"
                if int(item.get("sample_count", 0)) >= min_bucket_sample_count
                else "low_sample_kept"
            ),
        }
        for item in ranked
    ]


def _compact_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    trade_indexes = _as_sequence(summary.get("trade_indexes"))
    return {
        "field_key": summary.get("field_key"),
        "field_label_zh": summary.get("field_label_zh"),
        "value": summary.get("value"),
        "value_label_zh": summary.get("value_label_zh"),
        "label_zh": summary.get("label_zh"),
        "sample_count": summary.get("sample_count"),
        "win_rate": summary.get("win_rate"),
        "average_return_pct": summary.get("average_return_pct"),
        "median_return_pct": summary.get("median_return_pct"),
        "max_return_pct": summary.get("max_return_pct"),
        "min_return_pct": summary.get("min_return_pct"),
        "return_volatility_pct": summary.get("return_volatility_pct"),
        "return_path_max_drawdown_pct": summary.get("return_path_max_drawdown_pct"),
        "pnl_path_max_drawdown_on_entry_value": summary.get("pnl_path_max_drawdown_on_entry_value"),
        "risk_adjusted_return": summary.get("risk_adjusted_return"),
        "profit_loss_ratio": summary.get("profit_loss_ratio"),
        "net_pnl": summary.get("net_pnl"),
        "return_on_entry_value": summary.get("return_on_entry_value"),
        "ma25_profit_exit_rate": summary.get("ma25_profit_exit_rate"),
        "ma60_stop_exit_rate": summary.get("ma60_stop_exit_rate"),
        "flags": summary.get("flags") or [],
        "sample_trade_indexes": list(trade_indexes[:5]),
    }


def _field_overview_section(fields: Sequence[Any]) -> list[str]:
    lines = [
        "",
        "## 事前字段覆盖总览",
        "",
        "| 字段 | scope | 样本 | 缺失 | 非空桶 | 默认环境归因 | 标记 |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for raw in sorted((_as_mapping(item) for item in fields), key=lambda item: str(item.get("field_key"))):
        lines.append(
            "| "
            f"{_escape(raw.get('label_zh') or raw.get('field_key'))} | "
            f"{_escape(raw.get('scope'))} | "
            f"{raw.get('sample_count')} | "
            f"{raw.get('missing_count')} | "
            f"{raw.get('non_empty_bucket_count')} | "
            f"{'是' if raw.get('default_in_environment_fit') else '否'} | "
            f"{_escape(','.join(_as_sequence(raw.get('flags'))) or '-') } |"
        )
    return lines


def _ranking_section(title: str, rows: Any, limit: int) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| 排名 | 因子桶 | 样本 | 平均收益 | 中位收益 | 最大收益 | 最差收益 | 波动率 | PnL回撤 | 胜率 | 盈亏比 | 标记 | trade_index样例 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for index, raw in enumerate(_as_sequence(rows)[:limit], start=1):
        row = _as_mapping(raw)
        lines.append(_summary_row(index, row))
    return lines


def _all_bucket_section(title: str, rows: Sequence[Any]) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| 因子桶 | 样本 | 平均收益 | 中位收益 | 最大收益 | 最差收益 | 波动率 | PnL回撤 | 胜率 | 盈亏比 | 标记 | trade_index样例 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for raw in rows:
        lines.append(_summary_row(None, _as_mapping(raw)))
    return lines


def _summary_row(index: int | None, row: Mapping[str, Any]) -> str:
    prefix = f"{index} | " if index is not None else ""
    return (
        "| "
        f"{prefix}"
        f"{_escape(row.get('label_zh'))} | "
        f"{row.get('sample_count')} | "
        f"{_format_percent(row.get('average_return_pct'))} | "
        f"{_format_percent(row.get('median_return_pct'))} | "
        f"{_format_percent(row.get('max_return_pct'))} | "
        f"{_format_percent(row.get('min_return_pct'))} | "
        f"{_format_percent(row.get('return_volatility_pct'))} | "
        f"{_format_percent(row.get('pnl_path_max_drawdown_on_entry_value'))} | "
        f"{_format_percent(row.get('win_rate'))} | "
        f"{_format_number(row.get('profit_loss_ratio'))} | "
        f"{_escape(','.join(_as_sequence(row.get('flags'))) or '-')} | "
        f"{_escape(','.join(str(item) for item in _as_sequence(row.get('sample_trade_indexes') or row.get('trade_indexes'))[:5]))} |"
    )


def _excluded_section(fields: Sequence[Any]) -> list[str]:
    lines = [
        "",
        "## 未进入本次主归因字段",
        "",
        "| 字段 | timing | scope | 有效 | 缺失 | 原因 |",
        "|---|---|---|---:|---:|---|",
    ]
    for raw in fields:
        field = _as_mapping(raw)
        lines.append(
            "| "
            f"{_escape(field.get('label_zh') or field.get('field_key'))} | "
            f"{_escape(field.get('timing'))} | "
            f"{_escape(field.get('scope'))} | "
            f"{field.get('valid_count')} | "
            f"{field.get('missing_count')} | "
            f"{_escape(field.get('excluded_reason'))} |"
        )
    return lines


def _field_role(field: Mapping[str, Any]) -> str:
    key = str(field.get("field_key") or "")
    timing = str(field.get("timing") or "")
    if timing == "entry" and not key.startswith("trade."):
        return "entry_factor"
    if timing in {"symbol", "industry", "market"} and _is_discrete_legacy_entry_field(field):
        return "entry_factor"
    if timing == "post_trade" or key.startswith("trade.path."):
        return "post_trade_stat"
    return "excluded"


def _is_discrete_legacy_entry_field(field: Mapping[str, Any]) -> bool:
    key = str(field.get("field_key") or "")
    value_type = str(field.get("value_type") or "")
    if key.startswith("trade."):
        return False
    if value_type in {"bucket", "category"} or key.endswith("_bucket"):
        return True
    discrete_suffixes = (
        ".code",
        ".energy_zone",
        ".source_index",
        ".state",
        ".trend_state",
        ".bullish_trend",
        ".loss_making",
    )
    if key.endswith(discrete_suffixes):
        return True
    discrete_fragments = (
        ".j_below_threshold",
        ".price_above_",
        ".ma20_above_",
        ".ma25_above_",
        ".ma60_above_",
    )
    return any(fragment in key for fragment in discrete_fragments)


def _excluded_reason(field: Mapping[str, Any]) -> str:
    timing = str(field.get("timing") or "")
    key = str(field.get("field_key") or "")
    if timing == "exit" or key.startswith("trade.exit."):
        return "exit_outcome_diagnostic"
    if timing == "sizing":
        return "sizing_diagnostic"
    if timing in {"symbol", "industry", "market"}:
        return "continuous_legacy_pre_entry_field"
    return "legacy_or_not_entry_timing"


def _field_value(field_key: str, field: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
    if field.get("value_type") == "bucket" or str(field_key).endswith("_bucket"):
        return payload.get("bucket")
    bucket = payload.get("bucket")
    if bucket is not None:
        return bucket
    raw = payload.get("raw")
    if isinstance(raw, (str, bool)) or raw is None:
        return raw
    return None


def _field_flags(*, missing_ratio: float | None, non_empty_bucket_count: int, high_missing_ratio: float) -> list[str]:
    flags = []
    if non_empty_bucket_count < 2:
        flags.append("no_contrast")
    if missing_ratio is not None and missing_ratio >= high_missing_ratio:
        flags.append("high_missing")
    return flags


def _average(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _population_stddev(values: Sequence[float]) -> float | None:
    if not values:
        return None
    average = sum(values) / len(values)
    return math.sqrt(sum((value - average) ** 2 for value in values) / len(values))


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return ordered[lower_index]
    lower = ordered[lower_index]
    upper = ordered[upper_index]
    return lower + (upper - lower) * (position - lower_index)


def _return_path_max_drawdown(samples: Sequence[Mapping[str, Any]]) -> float | None:
    ordered_returns = [
        _optional_float(sample.get("return_pct"))
        for sample in sorted(samples, key=_trade_sort_key)
    ]
    returns = [value for value in ordered_returns if value is not None]
    if not returns:
        return None
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= max(0.0, 1.0 + value)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return max_drawdown


def _pnl_path_max_drawdown_on_entry_value(samples: Sequence[Mapping[str, Any]]) -> float | None:
    ordered_contributions: list[Mapping[str, Any]] = []
    total_entry_value = 0.0
    for sample in sorted(samples, key=_trade_sort_key):
        contribution = _as_mapping(sample.get("profit_contribution"))
        if contribution.get("contribution_available") is not True:
            continue
        entry_value = _optional_float(contribution.get("entry_gross_value"))
        net_pnl = _optional_float(contribution.get("net_pnl"))
        if entry_value is None or entry_value <= 0 or net_pnl is None:
            continue
        total_entry_value += entry_value
        ordered_contributions.append(contribution)
    if not ordered_contributions or total_entry_value <= 0:
        return None

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for contribution in ordered_contributions:
        cumulative += _optional_float(contribution.get("net_pnl")) or 0.0
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    return max_drawdown / total_entry_value


def _trade_sort_key(sample: Mapping[str, Any]) -> tuple[int, str, str, str]:
    trade_index = sample.get("trade_index")
    try:
        index_value = int(trade_index)
    except (TypeError, ValueError):
        index_value = 10**12
    return (
        index_value,
        str(sample.get("entry_date") or ""),
        str(sample.get("exit_date") or ""),
        str(sample.get("symbol") or ""),
    )


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _stable_value_key(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return str(value)


def _source_path(source: Any) -> str | None:
    if source is None or isinstance(source, Mapping):
        return None
    return str(source)


def _format_percent(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:.2%}"


def _format_money(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:,.2f}"


def _format_number(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:.3f}"


def _escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")
