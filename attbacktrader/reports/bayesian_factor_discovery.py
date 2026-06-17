"""Bayesian factor discovery from persisted attribution wide samples."""

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


BAYESIAN_FACTOR_DISCOVERY_SCHEMA = "attbacktrader.bayesian_factor_discovery.v1"

DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
    "capital_return": 0.25,
    "expected_trade_return": 0.20,
    "profit_factor": 0.20,
    "win_rate": 0.15,
    "drawdown_control": 0.10,
    "sample_reliability": 0.10,
}

TRADABLE_PRE_ENTRY_VIEW = "tradable_pre_entry"
LIFECYCLE_DIAGNOSTIC_VIEW = "lifecycle_diagnostic"
ALL_FIELDS_VIEW = "all_fields"


def build_bayesian_factor_discovery_report(
    wide_samples: Mapping[str, Any] | str | Path,
    *,
    field_index: Mapping[str, Any] | str | Path | None = None,
    min_bucket_sample_count: int = 30,
    high_missing_ratio: float = 0.2,
    prior_strength: float = 50.0,
    positive_score_threshold: float = 0.5,
    negative_score_threshold: float = -0.5,
    score_weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Rank factor buckets with empirical-Bayes shrinkage.

    This is a discovery report: it consumes completed-trade artifacts and does not
    produce strategy rule changes, parameter suggestions, or live trading signals.
    """

    if min_bucket_sample_count <= 0:
        raise ValueError("min_bucket_sample_count must be greater than 0")
    if not 0 <= high_missing_ratio <= 1:
        raise ValueError("high_missing_ratio must be between 0 and 1")
    if prior_strength < 0:
        raise ValueError("prior_strength must be greater than or equal to 0")
    if positive_score_threshold <= negative_score_threshold:
        raise ValueError("positive_score_threshold must be greater than negative_score_threshold")

    weights = _score_weights(score_weights)
    wide = load_attribution_wide_samples(wide_samples)
    index = (
        load_attribution_field_index(field_index)
        if field_index is not None
        else _as_mapping(wide.get("field_index"))
    )
    samples = [_as_mapping(sample) for sample in _as_sequence(wide.get("samples"))]
    fields = [_as_mapping(field) for field in _as_sequence(index.get("fields"))]
    overall = _outcome_stats(samples)

    usable_fields: list[dict[str, Any]] = []
    excluded_fields: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for field in fields:
        field_summary, bucket_rows = _field_buckets(
            field,
            samples=samples,
            high_missing_ratio=high_missing_ratio,
        )
        if field_summary["usable_in_discovery"]:
            usable_fields.append(field_summary)
        else:
            excluded_fields.append(field_summary)
            continue

        for value_key, bucket_samples in bucket_rows.items():
            value = field_summary["values_by_key"][value_key]
            stats = _outcome_stats(bucket_samples)
            candidates.append(
                {
                    **stats,
                    "field_key": field_summary["field_key"],
                    "field_label_zh": field_summary["label_zh"],
                    "timing": field_summary["timing"],
                    "scope": field_summary["scope"],
                    "value": _jsonable(value),
                    "value_label_zh": str(value),
                    "label_zh": f"{field_summary['label_zh']}={value}",
                    "eligibility": field_summary["eligibility"],
                    "future_function_guard": field_summary["future_function_guard"],
                    "field_flags": field_summary["flags"],
                    "flags": [],
                }
            )

    _apply_bayesian_scores(
        candidates,
        overall=overall,
        prior_strength=prior_strength,
        weights=weights,
        min_bucket_sample_count=min_bucket_sample_count,
        positive_score_threshold=positive_score_threshold,
        negative_score_threshold=negative_score_threshold,
    )

    return {
        "schema": BAYESIAN_FACTOR_DISCOVERY_SCHEMA,
        "run_id": wide.get("run_id"),
        "source_dir": wide.get("source_dir"),
        "source_artifacts": {
            "wide_samples": _source_path(wide_samples),
            "field_index": _source_path(field_index) if field_index is not None else None,
        },
        "discovery_mode": "research_only_not_strategy_optimization",
        "sample_count": len(samples),
        "field_count": len(fields),
        "usable_field_count": len(usable_fields),
        "excluded_field_count": len(excluded_fields),
        "candidate_bucket_count": len(candidates),
        "min_bucket_sample_count": min_bucket_sample_count,
        "high_missing_ratio": high_missing_ratio,
        "prior_strength": prior_strength,
        "positive_score_threshold": positive_score_threshold,
        "negative_score_threshold": negative_score_threshold,
        "score_weights": weights,
        "overall": overall,
        "usable_field_counts": _usable_field_counts(usable_fields),
        "usable_fields": {
            TRADABLE_PRE_ENTRY_VIEW: _fields_for_view(usable_fields, TRADABLE_PRE_ENTRY_VIEW),
            LIFECYCLE_DIAGNOSTIC_VIEW: _fields_for_view(usable_fields, LIFECYCLE_DIAGNOSTIC_VIEW),
            ALL_FIELDS_VIEW: _compact_fields(usable_fields),
        },
        "excluded_fields": _compact_fields(excluded_fields),
        "rankings": {
            TRADABLE_PRE_ENTRY_VIEW: _rankings_for_view(candidates, TRADABLE_PRE_ENTRY_VIEW),
            LIFECYCLE_DIAGNOSTIC_VIEW: _rankings_for_view(candidates, LIFECYCLE_DIAGNOSTIC_VIEW),
            ALL_FIELDS_VIEW: _rankings_for_view(candidates, ALL_FIELDS_VIEW),
        },
        "bucket_summaries": sorted(
            [_compact_candidate(candidate) for candidate in candidates],
            key=lambda item: (
                str(item.get("eligibility")),
                -float(item.get("factor_quality_score") or 0.0),
                str(item.get("field_key")),
                str(item.get("value")),
            ),
        ),
        "ai_usage_rules": [
            "该报告只做 Bayesian Factor Discovery，不做 Bayesian parameter tuning。",
            "tradable_pre_entry 只包含入场前或入场时可见的离散因子桶；任何 exit、post_exit、entry_to_exit、trade.path 字段都不得作为入场信号。",
            "lifecycle_diagnostic 可包含持仓、退出和退出后证据，只能解释交易生命周期，不能直接变成买入过滤条件。",
            "Factor Quality Score 是研究排序分，不是夏普率、不是实盘收益承诺，也不是自动调参目标。",
            "low_sample、high_missing、no_contrast 等标记必须在人工复核时保留，不能静默过滤。",
        ],
    }


def render_bayesian_factor_discovery_markdown_zh(report: Mapping[str, Any], *, ranking_limit: int = 30) -> str:
    """Render a Chinese Markdown report for Bayesian factor discovery."""

    overall = _as_mapping(report.get("overall"))
    lines = [
        "# 贝叶斯因子发现",
        "",
        "## 概览",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| run_id | `{report.get('run_id')}` |",
        f"| 交易样本 | {report.get('sample_count')} |",
        f"| 字段总数 | {report.get('field_count')} |",
        f"| 可用字段 | {report.get('usable_field_count')} |",
        f"| 候选因子桶 | {report.get('candidate_bucket_count')} |",
        f"| 最小桶样本 | {report.get('min_bucket_sample_count')} |",
        f"| 贝叶斯先验强度 | {report.get('prior_strength')} |",
        f"| 全样本胜率 | {_format_percent(overall.get('win_rate'))} |",
        f"| 全样本平均收益 | {_format_percent(overall.get('average_return_pct'))} |",
        f"| 全样本资金收益率 | {_format_percent(overall.get('return_on_entry_value'))} |",
        f"| 全样本 Profit Factor | {_format_number(overall.get('profit_factor'))} |",
        f"| 全样本最大回撤惩罚 | {_format_percent(overall.get('max_drawdown_pct'))} |",
    ]
    lines.extend(
        [
            "",
            "## 口径",
            "",
            "- 本报告是因子发现，不是参数优化，也不输出真实买入、卖出、减仓或仓位规则。",
            "- `tradable_pre_entry` 可作为后续候选规则复核池；`lifecycle_diagnostic` 只能解释交易过程。",
            "- Factor Quality Score 使用贝叶斯收缩后的收益、胜率、Profit Factor、回撤和样本可靠性加权排序。",
            "- 样本量过低、缺失过高或没有桶间对比的结果必须先人工复核。",
        ]
    )
    lines.extend(_usable_field_section(report))
    lines.extend(_ranking_section("正向入场候选", _ranking_rows(report, TRADABLE_PRE_ENTRY_VIEW, "positive"), ranking_limit))
    lines.extend(_ranking_section("负向入场候选", _ranking_rows(report, TRADABLE_PRE_ENTRY_VIEW, "negative"), ranking_limit))
    lines.extend(_ranking_section("生命周期正向诊断", _ranking_rows(report, LIFECYCLE_DIAGNOSTIC_VIEW, "positive"), ranking_limit))
    lines.extend(_ranking_section("生命周期负向诊断", _ranking_rows(report, LIFECYCLE_DIAGNOSTIC_VIEW, "negative"), ranking_limit))
    return "\n".join(lines) + "\n"


def write_bayesian_factor_discovery_report(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
    artifact_stem: str = "bayesian_factor_discovery",
) -> tuple[Path, Path]:
    """Write Bayesian factor discovery JSON and Chinese Markdown artifacts."""

    output_path = Path(output_dir or report.get("source_dir") or ".")
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{artifact_stem}.json"
    markdown_path = output_path / f"{artifact_stem}.zh.md"
    json_path.write_text(json.dumps(_jsonable(report), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_bayesian_factor_discovery_markdown_zh(report), encoding="utf-8")
    return json_path, markdown_path


def _field_buckets(
    field: Mapping[str, Any],
    *,
    samples: Sequence[Mapping[str, Any]],
    high_missing_ratio: float,
) -> tuple[dict[str, Any], dict[str, list[Mapping[str, Any]]]]:
    field_key = str(field.get("field_key") or "")
    buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    values_by_key: dict[str, Any] = {}
    exception_counts: Counter[str] = Counter()
    sample_count = 0
    missing_count = 0
    non_discrete_count = 0

    for sample in samples:
        payload = _as_mapping(_as_mapping(sample.get("field_values")).get(field_key))
        if not payload:
            continue
        sample_count += 1
        for code in _as_sequence(payload.get("exception_codes")):
            exception_counts[str(code)] += 1
        value = _field_value(field_key, field, payload)
        if value is None:
            missing_count += 1
            continue
        if not _is_discrete_value(value):
            non_discrete_count += 1
            continue
        value_key = _stable_value_key(value)
        values_by_key[value_key] = value
        buckets[value_key].append(sample)

    valid_count = sample_count - missing_count
    missing_ratio = missing_count / sample_count if sample_count else None
    eligibility = _field_eligibility(field)
    flags = _field_flags(
        field_key=field_key,
        missing_ratio=missing_ratio,
        high_missing_ratio=high_missing_ratio,
        non_empty_bucket_count=len(buckets),
        non_discrete_count=non_discrete_count,
    )
    usable = (
        sample_count > 0
        and len(buckets) > 0
        and "high_missing" not in flags
        and "no_discrete_bucket" not in flags
        and "metadata_time_anchor" not in flags
    )
    return (
        {
            "field_key": field_key,
            "label_zh": field.get("label_zh") or field_key,
            "timing": field.get("timing"),
            "scope": field.get("scope"),
            "value_type": field.get("value_type"),
            "sample_count": sample_count,
            "valid_count": valid_count,
            "missing_count": missing_count,
            "missing_ratio": missing_ratio,
            "non_empty_bucket_count": len(buckets),
            "non_discrete_count": non_discrete_count,
            "exception_count": sum(exception_counts.values()),
            "exception_top_codes": [
                {"code": code, "count": count}
                for code, count in exception_counts.most_common(5)
            ],
            "eligibility": eligibility,
            "future_function_guard": _future_function_guard(field),
            "usable_in_discovery": usable,
            "flags": flags,
            "values_by_key": values_by_key,
        },
        buckets,
    )


def _apply_bayesian_scores(
    candidates: list[dict[str, Any]],
    *,
    overall: Mapping[str, Any],
    prior_strength: float,
    weights: Mapping[str, float],
    min_bucket_sample_count: int,
    positive_score_threshold: float,
    negative_score_threshold: float,
) -> None:
    component_values: dict[str, list[float]] = {
        "capital_return": [],
        "expected_trade_return": [],
        "profit_factor": [],
        "win_rate": [],
        "drawdown_control": [],
        "sample_reliability": [],
    }

    for candidate in candidates:
        n = int(candidate.get("sample_count") or 0)
        posterior = {
            "capital_return": _shrink(
                candidate.get("return_on_entry_value"),
                overall.get("return_on_entry_value"),
                n=n,
                prior_strength=prior_strength,
            ),
            "expected_trade_return": _shrink(
                candidate.get("average_return_pct"),
                overall.get("average_return_pct"),
                n=n,
                prior_strength=prior_strength,
            ),
            "profit_factor_log": _shrink(
                candidate.get("profit_factor_log"),
                overall.get("profit_factor_log"),
                n=n,
                prior_strength=prior_strength,
            ),
            "win_rate": _shrink(
                candidate.get("win_rate"),
                overall.get("win_rate"),
                n=n,
                prior_strength=prior_strength,
            ),
            "max_drawdown_pct": _shrink(
                candidate.get("max_drawdown_pct"),
                overall.get("max_drawdown_pct"),
                n=n,
                prior_strength=prior_strength,
            ),
            "sample_reliability": n / (n + prior_strength) if n + prior_strength > 0 else 0.0,
        }
        components = {
            "capital_return": posterior["capital_return"],
            "expected_trade_return": posterior["expected_trade_return"],
            "profit_factor": posterior["profit_factor_log"],
            "win_rate": posterior["win_rate"],
            "drawdown_control": -posterior["max_drawdown_pct"],
            "sample_reliability": posterior["sample_reliability"],
        }
        candidate["bayesian_posterior"] = posterior
        candidate["score_components"] = components
        for key, value in components.items():
            if math.isfinite(value):
                component_values[key].append(value)

    component_stats = {
        key: _mean_std(values)
        for key, values in component_values.items()
    }
    for candidate in candidates:
        z_components: dict[str, float] = {}
        for key, value in _as_mapping(candidate.get("score_components")).items():
            mean, std = component_stats[key]
            z_components[key] = 0.0 if std <= 0 else (float(value) - mean) / std
        score = sum(float(weights[key]) * z_components.get(key, 0.0) for key in weights)
        candidate["component_z_scores"] = z_components
        candidate["factor_quality_score"] = score
        candidate["direction"] = _direction(
            candidate,
            overall=overall,
            min_bucket_sample_count=min_bucket_sample_count,
            positive_score_threshold=positive_score_threshold,
            negative_score_threshold=negative_score_threshold,
        )
        candidate["flags"] = _candidate_flags(
            candidate,
            min_bucket_sample_count=min_bucket_sample_count,
        )


def _outcome_stats(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = sorted(samples, key=lambda item: (str(item.get("entry_date") or ""), int(item.get("trade_index") or 0)))
    returns = [
        value
        for sample in rows
        if (value := _optional_float(sample.get("return_pct"))) is not None
    ]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    contributions = [
        _as_mapping(sample.get("profit_contribution"))
        for sample in rows
        if _as_mapping(sample.get("profit_contribution")).get("contribution_available") is True
    ]
    entry_values = [_optional_float(item.get("entry_gross_value")) or 0.0 for item in contributions]
    net_pnls = [_optional_float(item.get("net_pnl")) or 0.0 for item in contributions]
    total_entry_value = sum(entry_values)
    total_net_pnl = sum(net_pnls)
    gross_profit = sum(value for value in net_pnls if value > 0)
    gross_loss = abs(sum(value for value in net_pnls if value < 0))
    if not contributions:
        gross_profit = sum(value for value in returns if value > 0)
        gross_loss = abs(sum(value for value in returns if value < 0))
    smoothing = max((total_entry_value or len(returns) or 1) * 1e-9, 1e-9)
    profit_factor_log = math.log((gross_profit + smoothing) / (gross_loss + smoothing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else None)
    max_drawdown_pct = _max_drawdown_pct(net_pnls if contributions else returns, denominator=total_entry_value)
    exit_reasons = Counter(str(sample.get("exit_reason")) for sample in rows if sample.get("exit_reason") is not None)
    return {
        "sample_count": len(rows),
        "return_sample_count": len(returns),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": len(wins) / len(returns) if returns else None,
        "average_return_pct": _average(returns),
        "average_win_return_pct": _average(wins),
        "average_loss_return_pct": _average(losses),
        "financial_trade_count": len(contributions),
        "total_entry_value": total_entry_value if contributions else None,
        "net_pnl": total_net_pnl if contributions else None,
        "return_on_entry_value": total_net_pnl / total_entry_value if total_entry_value > 0 else _average(returns),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "profit_factor_log": profit_factor_log,
        "max_drawdown_pct": max_drawdown_pct,
        "exit_reason_counts": [
            {"code": code, "count": count}
            for code, count in sorted(exit_reasons.items(), key=lambda item: (-item[1], item[0]))
        ],
        "trade_indexes": [sample.get("trade_index") for sample in rows if sample.get("trade_index") is not None],
    }


def _field_eligibility(field: Mapping[str, Any]) -> str:
    key = str(field.get("field_key") or "")
    timing = str(field.get("timing") or "")
    if _is_future_or_lifecycle_field(key, timing):
        return LIFECYCLE_DIAGNOSTIC_VIEW
    if timing in {"entry", "symbol", "industry", "market"}:
        return TRADABLE_PRE_ENTRY_VIEW
    if key.startswith(("entry.", "symbol.", "industry.", "market.")):
        return TRADABLE_PRE_ENTRY_VIEW
    return LIFECYCLE_DIAGNOSTIC_VIEW


def _future_function_guard(field: Mapping[str, Any]) -> dict[str, Any]:
    key = str(field.get("field_key") or "")
    timing = str(field.get("timing") or "")
    future_or_lifecycle = _is_future_or_lifecycle_field(key, timing)
    return {
        "eligible_for_entry_rule_review": not future_or_lifecycle and _field_eligibility(field) == TRADABLE_PRE_ENTRY_VIEW,
        "reason": (
            "pre_entry_or_entry_visible"
            if not future_or_lifecycle and _field_eligibility(field) == TRADABLE_PRE_ENTRY_VIEW
            else "post_entry_or_future_evidence"
        ),
    }


def _is_future_or_lifecycle_field(field_key: str, timing: str) -> bool:
    key = field_key.lower()
    if timing in {"exit", "post_trade", "sizing"}:
        return True
    if key.startswith("trade.") or key.startswith("sizing."):
        return True
    return any(
        token in key
        for token in (
            ".exit_",
            ".exit.",
            "exit_stage",
            "entry_to_exit",
            "post_exit",
            "sold_too_early",
            "stop_loss_rebound",
        )
    )


def _field_value(field_key: str, field: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
    bucket = payload.get("bucket")
    if bucket is not None:
        return bucket
    raw = payload.get("raw")
    if field.get("value_type") == "bucket" or str(field_key).endswith("_bucket"):
        return raw if isinstance(raw, str) and raw else None
    if isinstance(raw, (bool, str)):
        return raw
    return None


def _is_discrete_value(value: Any) -> bool:
    return isinstance(value, (str, bool, int))


def _field_flags(
    *,
    field_key: str,
    missing_ratio: float | None,
    high_missing_ratio: float,
    non_empty_bucket_count: int,
    non_discrete_count: int,
) -> list[str]:
    flags = []
    if _is_metadata_anchor_field(field_key):
        flags.append("metadata_time_anchor")
    if missing_ratio is not None and missing_ratio >= high_missing_ratio:
        flags.append("high_missing")
    if non_empty_bucket_count == 0:
        flags.append("no_discrete_bucket")
    if non_empty_bucket_count < 2:
        flags.append("no_contrast")
    if non_discrete_count > 0:
        flags.append("continuous_raw_ignored")
    return flags


def _is_metadata_anchor_field(field_key: str) -> bool:
    key = field_key.lower()
    return key.endswith(".indicator_date") or key.endswith("_indicator_date")


def _candidate_flags(candidate: Mapping[str, Any], *, min_bucket_sample_count: int) -> list[str]:
    flags = list(_as_sequence(candidate.get("field_flags")))
    if int(candidate.get("sample_count") or 0) < min_bucket_sample_count:
        flags.append("low_sample")
    posterior = _as_mapping(candidate.get("bayesian_posterior"))
    if _optional_float(posterior.get("sample_reliability")) is not None and float(posterior.get("sample_reliability")) < 0.5:
        flags.append("strong_shrinkage")
    return sorted(set(str(flag) for flag in flags))


def _direction(
    candidate: Mapping[str, Any],
    *,
    overall: Mapping[str, Any],
    min_bucket_sample_count: int,
    positive_score_threshold: float,
    negative_score_threshold: float,
) -> str:
    if int(candidate.get("sample_count") or 0) < min_bucket_sample_count:
        return "weak"
    score = float(candidate.get("factor_quality_score") or 0.0)
    posterior = _as_mapping(candidate.get("bayesian_posterior"))
    capital_edge = float(posterior.get("capital_return") or 0.0) - float(overall.get("return_on_entry_value") or 0.0)
    trade_edge = float(posterior.get("expected_trade_return") or 0.0) - float(overall.get("average_return_pct") or 0.0)
    if score >= positive_score_threshold and (capital_edge > 0 or trade_edge > 0):
        return "positive"
    if score <= negative_score_threshold and (capital_edge < 0 or trade_edge < 0):
        return "negative"
    return "weak"


def _rankings_for_view(candidates: Sequence[Mapping[str, Any]], view: str) -> dict[str, list[dict[str, Any]]]:
    rows = [
        candidate
        for candidate in candidates
        if view == ALL_FIELDS_VIEW or candidate.get("eligibility") == view
    ]
    return {
        "positive": _rank_direction(rows, "positive", reverse=True),
        "negative": _rank_direction(rows, "negative", reverse=False),
        "weak": _rank_direction(rows, "weak", reverse=True),
    }


def _rank_direction(rows: Sequence[Mapping[str, Any]], direction: str, *, reverse: bool) -> list[dict[str, Any]]:
    filtered = [_compact_candidate(row) for row in rows if row.get("direction") == direction]
    filtered.sort(
        key=lambda item: (
            float(item.get("factor_quality_score") or 0.0),
            int(item.get("sample_count") or 0),
            str(item.get("label_zh")),
        ),
        reverse=reverse,
    )
    return filtered


def _compact_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    posterior = _as_mapping(candidate.get("bayesian_posterior"))
    trade_indexes = _as_sequence(candidate.get("trade_indexes"))
    return {
        "field_key": candidate.get("field_key"),
        "field_label_zh": candidate.get("field_label_zh"),
        "timing": candidate.get("timing"),
        "scope": candidate.get("scope"),
        "value": candidate.get("value"),
        "value_label_zh": candidate.get("value_label_zh"),
        "label_zh": candidate.get("label_zh"),
        "eligibility": candidate.get("eligibility"),
        "direction": candidate.get("direction"),
        "factor_quality_score": candidate.get("factor_quality_score"),
        "sample_count": candidate.get("sample_count"),
        "win_rate": candidate.get("win_rate"),
        "average_return_pct": candidate.get("average_return_pct"),
        "return_on_entry_value": candidate.get("return_on_entry_value"),
        "profit_factor": candidate.get("profit_factor"),
        "max_drawdown_pct": candidate.get("max_drawdown_pct"),
        "posterior": {
            "capital_return": posterior.get("capital_return"),
            "expected_trade_return": posterior.get("expected_trade_return"),
            "win_rate": posterior.get("win_rate"),
            "profit_factor_log": posterior.get("profit_factor_log"),
            "max_drawdown_pct": posterior.get("max_drawdown_pct"),
            "sample_reliability": posterior.get("sample_reliability"),
        },
        "flags": list(_as_sequence(candidate.get("flags"))),
        "future_function_guard": candidate.get("future_function_guard"),
        "sample_trade_indexes": list(trade_indexes[:5]),
    }


def _usable_field_counts(fields: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        TRADABLE_PRE_ENTRY_VIEW: sum(1 for field in fields if field.get("eligibility") == TRADABLE_PRE_ENTRY_VIEW),
        LIFECYCLE_DIAGNOSTIC_VIEW: sum(1 for field in fields if field.get("eligibility") == LIFECYCLE_DIAGNOSTIC_VIEW),
        ALL_FIELDS_VIEW: len(fields),
    }


def _fields_for_view(fields: Sequence[Mapping[str, Any]], view: str) -> list[dict[str, Any]]:
    return _compact_fields([field for field in fields if field.get("eligibility") == view])


def _compact_fields(fields: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "field_key": field.get("field_key"),
            "label_zh": field.get("label_zh"),
            "timing": field.get("timing"),
            "scope": field.get("scope"),
            "eligibility": field.get("eligibility"),
            "sample_count": field.get("sample_count"),
            "valid_count": field.get("valid_count"),
            "missing_count": field.get("missing_count"),
            "missing_ratio": field.get("missing_ratio"),
            "non_empty_bucket_count": field.get("non_empty_bucket_count"),
            "flags": list(_as_sequence(field.get("flags"))),
            "future_function_guard": field.get("future_function_guard"),
        }
        for field in sorted(fields, key=lambda item: str(item.get("field_key")))
    ]


def _ranking_rows(report: Mapping[str, Any], view: str, direction: str) -> Sequence[Any]:
    return _as_sequence(_as_mapping(_as_mapping(report.get("rankings")).get(view)).get(direction))


def _usable_field_section(report: Mapping[str, Any]) -> list[str]:
    counts = _as_mapping(report.get("usable_field_counts"))
    return [
        "",
        "## 可用字段",
        "",
        "| 视图 | 字段数 |",
        "|---|---:|",
        f"| tradable_pre_entry | {counts.get(TRADABLE_PRE_ENTRY_VIEW)} |",
        f"| lifecycle_diagnostic | {counts.get(LIFECYCLE_DIAGNOSTIC_VIEW)} |",
        f"| all_fields | {counts.get(ALL_FIELDS_VIEW)} |",
    ]


def _ranking_section(title: str, rows: Sequence[Any], limit: int) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| 排名 | 因子桶 | 样本 | FQS | 胜率 | 平均收益 | 资金收益率 | Profit Factor | 回撤 | 标记 | trade_index样例 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for index, raw in enumerate(rows[:limit], start=1):
        row = _as_mapping(raw)
        lines.append(
            "| "
            f"{index} | "
            f"{_escape(row.get('label_zh'))} | "
            f"{row.get('sample_count')} | "
            f"{_format_number(row.get('factor_quality_score'))} | "
            f"{_format_percent(row.get('win_rate'))} | "
            f"{_format_percent(row.get('average_return_pct'))} | "
            f"{_format_percent(row.get('return_on_entry_value'))} | "
            f"{_format_number(row.get('profit_factor'))} | "
            f"{_format_percent(row.get('max_drawdown_pct'))} | "
            f"{_escape(','.join(str(flag) for flag in _as_sequence(row.get('flags'))) or '-')} | "
            f"{_escape(','.join(str(item) for item in _as_sequence(row.get('sample_trade_indexes'))))} |"
        )
    return lines


def _score_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    raw = dict(DEFAULT_SCORE_WEIGHTS)
    if weights is not None:
        raw.update({str(key): float(value) for key, value in weights.items()})
    total = sum(value for value in raw.values() if value > 0)
    if total <= 0:
        raise ValueError("score weights must contain at least one positive value")
    return {key: value / total for key, value in raw.items() if value > 0}


def _shrink(value: Any, prior: Any, *, n: int, prior_strength: float) -> float:
    observed = _optional_float(value)
    prior_value = _optional_float(prior)
    if observed is None and prior_value is None:
        return 0.0
    if observed is None:
        return float(prior_value or 0.0)
    if prior_value is None or prior_strength == 0:
        return float(observed)
    return (n * float(observed) + prior_strength * float(prior_value)) / (n + prior_strength)


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, math.sqrt(variance)


def _max_drawdown_pct(values: Sequence[float], *, denominator: float | None) -> float:
    if not values:
        return 0.0
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    if denominator and denominator > 0:
        return max_drawdown / denominator
    return max_drawdown


def _average(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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


def _format_number(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:.4f}"


def _escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")
