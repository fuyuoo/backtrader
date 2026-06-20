"""Screen entry single-factor buckets into candidate review groups."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ENTRY_SINGLE_FACTOR_CANDIDATE_SCREENING_SCHEMA = "attbacktrader.entry_single_factor_candidate_screening.v1"

KEEP_CANDIDATES = "keep_candidates"
EXCLUDE_CANDIDATES = "exclude_candidates"
KEEP_WATCHLIST = "keep_watchlist"
EXCLUDE_WATCHLIST = "exclude_watchlist"
EXPOSURE_WATCHLIST = "exposure_watchlist"
_CATEGORY_ORDER = (
    KEEP_CANDIDATES,
    EXCLUDE_CANDIDATES,
    KEEP_WATCHLIST,
    EXCLUDE_WATCHLIST,
    EXPOSURE_WATCHLIST,
)
_EXCLUDE_FLAGS = {"high_missing", "no_contrast", "no_discrete_bucket"}
_CSV_COLUMNS = [
    "primary_category",
    "direction",
    "factor_kind",
    "field_key",
    "field_label_zh",
    "scope",
    "value",
    "value_label_zh",
    "sample_count",
    "win_rate",
    "average_return_pct",
    "median_return_pct",
    "return_on_entry_value",
    "profit_loss_ratio",
    "ma60_stop_exit_rate",
    "pnl_path_max_drawdown_on_entry_value",
    "return_path_max_drawdown_pct",
    "watchlist_score",
    "candidate_source",
    "flags",
    "category_reasons",
    "sample_trade_indexes",
]


def build_entry_single_factor_candidate_screening_report(
    single_factor_attribution: Mapping[str, Any] | str | Path,
    *,
    reverse_filter_candidate_summary: Mapping[str, Any] | str | Path | None = None,
    min_candidate_sample_count: int | None = None,
) -> dict[str, Any]:
    """Build a research-only candidate screen from persisted single-factor artifacts."""

    single, single_path = _load_json_mapping(single_factor_attribution, default_name="single_factor_attribution.json")
    reverse, reverse_path = _load_optional_json_mapping(
        reverse_filter_candidate_summary,
        default_name="reverse_filter_candidate_summary.json",
    )
    min_count = int(
        min_candidate_sample_count
        or reverse.get("min_candidate_sample_count")
        or single.get("min_bucket_sample_count")
        or 100
    )
    if min_count <= 0:
        raise ValueError("min_candidate_sample_count must be greater than 0")

    overall = dict(_as_mapping(single.get("overall")))
    positive_lookup = _candidate_lookup(reverse.get("positive_candidates"))
    negative_lookup = _candidate_lookup(reverse.get("negative_candidates"))
    screened_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []

    for raw_row in _as_sequence(single.get("entry_single_factor_summaries")):
        source_row = _as_mapping(raw_row)
        row = _normalise_bucket_row(source_row, min_candidate_sample_count=min_count)
        positive_match = _lookup_candidate(row, positive_lookup)
        negative_match = _lookup_candidate(row, negative_lookup)
        hard_candidate = positive_match is not None or negative_match is not None

        if not hard_candidate and _excluded_from_screen(row):
            skipped_rows.append(_skip_row(row))
            continue

        direction = None
        candidate_source = "strict_watchlist"
        reasons: list[str] = []
        if positive_match is not None:
            direction = "keep"
            candidate_source = "reverse_filter_positive"
            reasons.append("reverse_filter_positive_candidate")
            reasons.extend(str(item) for item in _as_sequence(positive_match.get("reverse_filter_positive_reasons")))
        elif negative_match is not None:
            direction = "exclude"
            candidate_source = "reverse_filter_negative"
            reasons.append("reverse_filter_negative_candidate")
            reasons.extend(str(item) for item in _as_sequence(negative_match.get("reverse_filter_negative_reasons")))
        else:
            direction, watch_reasons = _strict_watchlist_direction(row, overall)
            reasons.extend(watch_reasons)

        if direction is None:
            skipped_rows.append(_skip_row(row, reason="not_enough_edge_for_watchlist"))
            continue

        factor_kind = _factor_kind(row)
        if factor_kind == "entry_exposure":
            primary_category = EXPOSURE_WATCHLIST
            reasons.append("exposure_field_requires_separate_stability_review")
        elif direction == "keep" and candidate_source == "reverse_filter_positive":
            primary_category = KEEP_CANDIDATES
        elif direction == "exclude" and candidate_source == "reverse_filter_negative":
            primary_category = EXCLUDE_CANDIDATES
        elif direction == "keep":
            primary_category = KEEP_WATCHLIST
        else:
            primary_category = EXCLUDE_WATCHLIST

        row.update(
            {
                "primary_category": primary_category,
                "direction": direction,
                "factor_kind": factor_kind,
                "candidate_source": candidate_source,
                "category_reasons": sorted(set(reasons)),
                "watchlist_score": _watchlist_score(row, overall),
            }
        )
        screened_rows.append(row)

    category_rows = {
        category: _sort_rows(
            [row for row in screened_rows if row.get("primary_category") == category],
            category=category,
        )
        for category in _CATEGORY_ORDER
    }
    screened_rows = [row for category in _CATEGORY_ORDER for row in category_rows[category]]
    counts = Counter(str(row.get("primary_category")) for row in screened_rows)

    return {
        "schema": ENTRY_SINGLE_FACTOR_CANDIDATE_SCREENING_SCHEMA,
        "run_id": single.get("run_id") or reverse.get("run_id"),
        "source_dir": single.get("source_dir"),
        "source_artifacts": {
            "single_factor_attribution": str(single_path) if single_path is not None else None,
            "reverse_filter_candidate_summary": str(reverse_path) if reverse_path is not None else None,
        },
        "screening_mode": "research_only_not_strategy_validation",
        "screening_goal": "screen_entry_candidate_factors",
        "sample_count": single.get("sample_count"),
        "entry_factor_count": single.get("entry_factor_count"),
        "entry_single_factor_summary_count": len(_as_sequence(single.get("entry_single_factor_summaries"))),
        "screened_row_count": len(screened_rows),
        "skipped_row_count": len(skipped_rows),
        "min_candidate_sample_count": min_count,
        "overall": overall,
        "category_counts": {category: counts.get(category, 0) for category in _CATEGORY_ORDER},
        "hard_candidate_counts": {
            "positive": len(_as_sequence(reverse.get("positive_candidates"))),
            "negative": len(_as_sequence(reverse.get("negative_candidates"))),
        },
        "rules": [
            "本报告只筛入场候选因子，不解释全部收益来源，也不做主题归纳。",
            "reverse_filter_candidate_summary 中的正向/负向桶保留为硬候选；行业、市场等暴露字段转入 exposure_watchlist。",
            f"非硬候选要求 sample_count >= {min_count}，并排除 high_missing/no_contrast/no_discrete_bucket。",
            "watchlist 使用严格边际：收益、资金收益率、胜率为同向核心条件，并要求至少 4 个同向指标支持。",
            "entry.execution.signal_to_entry_return_bucket 作为入场执行因子保留，可用于后续验证开盘缺口对入场质量的影响。",
        ],
        KEEP_CANDIDATES: category_rows[KEEP_CANDIDATES],
        EXCLUDE_CANDIDATES: category_rows[EXCLUDE_CANDIDATES],
        KEEP_WATCHLIST: category_rows[KEEP_WATCHLIST],
        EXCLUDE_WATCHLIST: category_rows[EXCLUDE_WATCHLIST],
        EXPOSURE_WATCHLIST: category_rows[EXPOSURE_WATCHLIST],
        "entry_execution_factors": [
            row for row in screened_rows if row.get("factor_kind") == "entry_execution"
        ],
        "screened_rows": screened_rows,
        "skipped_rows": skipped_rows,
        "ai_usage_rules": [
            "这不是策略规则，也不是参数优化结果；只能作为后续真实回测验证候选池。",
            "keep_candidates/exclude_candidates 需要进入后续候选验证矩阵，不能直接改入场逻辑。",
            "exposure_watchlist 只提示风险暴露或环境依赖，默认不作为直接买入过滤条件。",
            "entry_execution 因子反映从信号日收盘到入场开盘的成交环境，应和入场信号因子分开复核。",
        ],
    }


def render_entry_single_factor_candidate_screening_markdown_zh(
    report: Mapping[str, Any],
    *,
    limit: int = 30,
) -> str:
    """Render the candidate screening report in Chinese Markdown."""

    overall = _as_mapping(report.get("overall"))
    counts = _as_mapping(report.get("category_counts"))
    lines = [
        "# 入场单因子候选筛选报告",
        "",
        "本报告的目标是筛入场候选因子，不是策略规则，不解释全部收益来源，也不做主题归纳。",
        "",
        "## 概览",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| run_id | `{report.get('run_id')}` |",
        f"| 全样本交易数 | {report.get('sample_count')} |",
        f"| 单因子桶数 | {report.get('entry_single_factor_summary_count')} |",
        f"| 入筛桶数 | {report.get('screened_row_count')} |",
        f"| 跳过桶数 | {report.get('skipped_row_count')} |",
        f"| 最小候选样本 | {report.get('min_candidate_sample_count')} |",
        f"| 全样本胜率 | {_format_percent(overall.get('win_rate'))} |",
        f"| 全样本平均收益 | {_format_percent(overall.get('average_return_pct'))} |",
        f"| 全样本资金收益率 | {_format_percent(overall.get('return_on_entry_value'))} |",
    ]
    lines.extend(
        [
            "",
            "## 分类汇总",
            "",
            "| 分类 | 数量 |",
            "|---|---:|",
            f"| Keep Candidates | {counts.get(KEEP_CANDIDATES, 0)} |",
            f"| Exclude Candidates | {counts.get(EXCLUDE_CANDIDATES, 0)} |",
            f"| Keep Watchlist | {counts.get(KEEP_WATCHLIST, 0)} |",
            f"| Exclude Watchlist | {counts.get(EXCLUDE_WATCHLIST, 0)} |",
            f"| Exposure Watchlist | {counts.get(EXPOSURE_WATCHLIST, 0)} |",
        ]
    )
    lines.extend(_rules_section(report))
    lines.extend(_row_section("Keep Candidates", report.get(KEEP_CANDIDATES), limit))
    lines.extend(_row_section("Exclude Candidates", report.get(EXCLUDE_CANDIDATES), limit))
    lines.extend(_row_section("Keep Watchlist", report.get(KEEP_WATCHLIST), limit))
    lines.extend(_row_section("Exclude Watchlist", report.get(EXCLUDE_WATCHLIST), limit))
    lines.extend(_row_section("Exposure Watchlist", report.get(EXPOSURE_WATCHLIST), limit))
    lines.extend(_row_section("Entry Execution Factors", report.get("entry_execution_factors"), limit))
    return "\n".join(lines) + "\n"


def write_entry_single_factor_candidate_screening_report(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
    artifact_stem: str = "entry_single_factor_candidate_screening",
) -> tuple[Path, Path, Path]:
    """Write JSON, Chinese Markdown, and CSV row artifacts."""

    output_path = Path(output_dir or report.get("source_dir") or ".")
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{artifact_stem}.json"
    markdown_path = output_path / f"{artifact_stem}.zh.md"
    csv_path = output_path / f"{artifact_stem}_rows.csv"

    payload = _jsonable(report)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_single_factor_candidate_screening_markdown_zh(payload), encoding="utf-8")
    _write_rows_csv(csv_path, _as_sequence(payload.get("screened_rows")))
    return json_path, markdown_path, csv_path


def _normalise_bucket_row(row: Mapping[str, Any], *, min_candidate_sample_count: int) -> dict[str, Any]:
    flags = sorted(set(str(flag) for flag in _as_sequence(row.get("flags"))))
    sample_count = int(row.get("sample_count") or 0)
    if sample_count < min_candidate_sample_count:
        flags.append("low_sample")
    result = {
        "field_key": row.get("field_key"),
        "field_label_zh": row.get("field_label_zh") or row.get("label_zh") or row.get("field_key"),
        "timing": row.get("timing"),
        "scope": row.get("scope"),
        "value": row.get("value"),
        "value_label_zh": row.get("value_label_zh") if row.get("value_label_zh") is not None else str(row.get("value")),
        "label_zh": row.get("label_zh"),
        "sample_count": sample_count,
        "return_sample_count": row.get("return_sample_count"),
        "win_count": row.get("win_count"),
        "loss_count": row.get("loss_count"),
        "win_rate": row.get("win_rate"),
        "average_return_pct": row.get("average_return_pct"),
        "median_return_pct": row.get("median_return_pct"),
        "p25_return_pct": row.get("p25_return_pct"),
        "p75_return_pct": row.get("p75_return_pct"),
        "return_volatility_pct": row.get("return_volatility_pct"),
        "pnl_path_max_drawdown_on_entry_value": row.get("pnl_path_max_drawdown_on_entry_value"),
        "return_path_max_drawdown_pct": row.get("return_path_max_drawdown_pct"),
        "risk_adjusted_return": row.get("risk_adjusted_return"),
        "profit_loss_ratio": row.get("profit_loss_ratio"),
        "return_on_entry_value": row.get("return_on_entry_value"),
        "net_pnl": row.get("net_pnl"),
        "ma60_stop_exit_rate": row.get("ma60_stop_exit_rate"),
        "ma25_profit_exit_rate": row.get("ma25_profit_exit_rate"),
        "flags": sorted(set(flags)),
        "candidate_marks": list(_as_sequence(row.get("candidate_marks"))),
        "sample_trade_indexes": list(_as_sequence(row.get("trade_indexes"))[:10]),
    }
    if result["label_zh"] is None:
        result["label_zh"] = f"{result['field_label_zh']}={result['value_label_zh']}"
    return result


def _strict_watchlist_direction(row: Mapping[str, Any], overall: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    if _excluded_from_screen(row):
        return None, []

    positive = _positive_conditions(row, overall)
    negative = _negative_conditions(row, overall)
    positive_hits = [key for key, passed in positive.items() if passed]
    negative_hits = [key for key, passed in negative.items() if passed]
    positive_core = all(positive.get(key) for key in ("average_return_pct", "return_on_entry_value", "win_rate"))
    negative_core = all(negative.get(key) for key in ("average_return_pct", "return_on_entry_value", "win_rate"))

    if positive_core and len(positive_hits) >= 4:
        return "keep", [f"strict_positive_watchlist:{','.join(positive_hits)}"]
    if negative_core and len(negative_hits) >= 4:
        return "exclude", [f"strict_negative_watchlist:{','.join(negative_hits)}"]
    return None, []


def _positive_conditions(row: Mapping[str, Any], overall: Mapping[str, Any]) -> dict[str, bool]:
    average_return = _number_or_none(row.get("average_return_pct"))
    return_on_entry = _number_or_none(row.get("return_on_entry_value"))
    return {
        "average_return_pct": _greater_than(row.get("average_return_pct"), overall.get("average_return_pct")) and (average_return or 0.0) > 0,
        "return_on_entry_value": _greater_than(row.get("return_on_entry_value"), overall.get("return_on_entry_value")) and (return_on_entry or 0.0) > 0,
        "win_rate": _greater_than(row.get("win_rate"), overall.get("win_rate")),
        "median_return_pct": _greater_than(row.get("median_return_pct"), overall.get("median_return_pct")),
        "profit_loss_ratio": _greater_than(row.get("profit_loss_ratio"), overall.get("profit_loss_ratio")),
        "ma60_stop_exit_rate": _less_than(row.get("ma60_stop_exit_rate"), overall.get("ma60_stop_exit_rate")),
    }


def _negative_conditions(row: Mapping[str, Any], overall: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "average_return_pct": _less_than(row.get("average_return_pct"), overall.get("average_return_pct")),
        "return_on_entry_value": _less_than(row.get("return_on_entry_value"), overall.get("return_on_entry_value")),
        "win_rate": _less_than(row.get("win_rate"), overall.get("win_rate")),
        "median_return_pct": _less_than(row.get("median_return_pct"), overall.get("median_return_pct")),
        "profit_loss_ratio": _less_than(row.get("profit_loss_ratio"), overall.get("profit_loss_ratio")),
        "ma60_stop_exit_rate": _greater_than(row.get("ma60_stop_exit_rate"), overall.get("ma60_stop_exit_rate")),
    }


def _watchlist_score(row: Mapping[str, Any], overall: Mapping[str, Any]) -> int:
    positive_hits = sum(1 for passed in _positive_conditions(row, overall).values() if passed)
    negative_hits = sum(1 for passed in _negative_conditions(row, overall).values() if passed)
    return positive_hits - negative_hits


def _candidate_lookup(rows: Any) -> dict[tuple[str, str], Mapping[str, Any]]:
    lookup: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in _as_sequence(rows):
        row_map = _as_mapping(row)
        field_key = str(row_map.get("field_key") or "")
        if not field_key:
            continue
        for value in (row_map.get("value"), row_map.get("value_label_zh")):
            if value is not None:
                lookup[(field_key, _stable_identity_value(value))] = row_map
    return lookup


def _lookup_candidate(row: Mapping[str, Any], lookup: Mapping[tuple[str, str], Mapping[str, Any]]) -> Mapping[str, Any] | None:
    field_key = str(row.get("field_key") or "")
    for value in (row.get("value"), row.get("value_label_zh")):
        if value is not None:
            match = lookup.get((field_key, _stable_identity_value(value)))
            if match is not None:
                return match
    return None


def _factor_kind(row: Mapping[str, Any]) -> str:
    field_key = str(row.get("field_key") or "").lower()
    scope = str(row.get("scope") or "").lower()
    if field_key.startswith("entry.execution.") or scope == "execution":
        return "entry_execution"
    if field_key.startswith("industry.") or scope == "industry":
        return "entry_exposure"
    if field_key.startswith("market.") or scope == "market":
        return "entry_context"
    return "entry_signal"


def _excluded_from_screen(row: Mapping[str, Any]) -> bool:
    flags = {str(flag) for flag in _as_sequence(row.get("flags"))}
    return bool(flags & (_EXCLUDE_FLAGS | {"low_sample"}))


def _skip_row(row: Mapping[str, Any], *, reason: str | None = None) -> dict[str, Any]:
    flags = list(_as_sequence(row.get("flags")))
    reasons = []
    if flags:
        reasons.extend(flags)
    if reason:
        reasons.append(reason)
    return {
        "field_key": row.get("field_key"),
        "value": row.get("value"),
        "value_label_zh": row.get("value_label_zh"),
        "sample_count": row.get("sample_count"),
        "flags": flags,
        "skip_reasons": sorted(set(str(item) for item in reasons)),
    }


def _sort_rows(rows: Sequence[Mapping[str, Any]], *, category: str) -> list[dict[str, Any]]:
    reverse = category in {KEEP_CANDIDATES, KEEP_WATCHLIST, EXPOSURE_WATCHLIST}
    return sorted(
        [dict(row) for row in rows],
        key=lambda row: (
            _number_or_none(row.get("return_on_entry_value")) or 0.0,
            _number_or_none(row.get("average_return_pct")) or 0.0,
            _number_or_none(row.get("win_rate")) or 0.0,
            int(row.get("sample_count") or 0),
            str(row.get("field_key")),
            str(row.get("value_label_zh")),
        ),
        reverse=reverse,
    )


def _rules_section(report: Mapping[str, Any]) -> list[str]:
    lines = ["", "## 口径", ""]
    for rule in _as_sequence(report.get("rules")):
        lines.append(f"- {rule}")
    return lines


def _row_section(title: str, rows: Any, limit: int) -> list[str]:
    row_list = [_as_mapping(row) for row in _as_sequence(rows)]
    lines = [
        "",
        f"## {title}",
        "",
        "| 序号 | 分类 | 方向 | 因子 | 值 | 样本 | 胜率 | 平均收益 | 资金收益率 | 盈亏比 | 止损率 | 标记 | 理由 |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for index, row in enumerate(row_list[:limit], start=1):
        lines.append(
            "| "
            f"{index} | "
            f"{_escape(row.get('primary_category'))} | "
            f"{_escape(row.get('direction'))} | "
            f"`{_escape(row.get('field_key'))}` | "
            f"{_escape(row.get('value_label_zh') or row.get('value'))} | "
            f"{row.get('sample_count')} | "
            f"{_format_percent(row.get('win_rate'))} | "
            f"{_format_percent(row.get('average_return_pct'))} | "
            f"{_format_percent(row.get('return_on_entry_value'))} | "
            f"{_format_number(row.get('profit_loss_ratio'))} | "
            f"{_format_percent(row.get('ma60_stop_exit_rate'))} | "
            f"{_escape(','.join(str(item) for item in _as_sequence(row.get('flags'))) or '-')} | "
            f"{_escape('; '.join(str(item) for item in _as_sequence(row.get('category_reasons'))))} |"
        )
    return lines


def _write_rows_csv(path: Path, rows: Sequence[Any]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for raw_row in rows:
            row = _as_mapping(raw_row)
            writer.writerow(
                {
                    column: _csv_value(row.get(column))
                    for column in _CSV_COLUMNS
                }
            )


def _load_optional_json_mapping(value: Mapping[str, Any] | str | Path | None, *, default_name: str) -> tuple[dict[str, Any], Path | None]:
    if value is None:
        return {}, None
    return _load_json_mapping(value, default_name=default_name)


def _load_json_mapping(value: Mapping[str, Any] | str | Path, *, default_name: str) -> tuple[dict[str, Any], Path | None]:
    if isinstance(value, Mapping):
        return dict(value), None
    path = Path(value)
    if path.is_dir():
        path = path / default_name
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload, path


def _greater_than(value: Any, baseline: Any) -> bool:
    left = _number_or_none(value)
    right = _number_or_none(baseline)
    return left is not None and right is not None and left > right


def _less_than(value: Any, baseline: Any) -> bool:
    left = _number_or_none(value)
    right = _number_or_none(baseline)
    return left is not None and right is not None and left < right


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    return number if math.isfinite(number) else None


def _stable_identity_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return str(value)


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _format_percent(value: Any) -> str:
    number = _number_or_none(value)
    return "-" if number is None else f"{number:.2%}"


def _format_number(value: Any) -> str:
    number = _number_or_none(value)
    return "-" if number is None else f"{number:.4f}"


def _escape(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")
