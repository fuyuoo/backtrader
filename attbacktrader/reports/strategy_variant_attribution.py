"""Explain baseline-vs-variant changes from persisted trade evidence."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping, Sequence


STRATEGY_VARIANT_ATTRIBUTION_SCHEMA = "attbacktrader.strategy_variant_attribution.v1"


def build_strategy_variant_attribution(
    baseline_manifest_or_path: Mapping[str, Any] | str | Path,
    variant_manifest_or_path: Mapping[str, Any] | str | Path,
    *,
    market_type_id: str,
    report_root: str | Path = "reports",
    short_reentry_days: int = 5,
) -> dict[str, Any]:
    """Compare baseline and variant run artifacts for one market type."""

    if not market_type_id:
        raise ValueError("market_type_id is required")
    if short_reentry_days < 0:
        raise ValueError("short_reentry_days must be non-negative")

    baseline_manifest, baseline_manifest_path = _load_manifest(baseline_manifest_or_path)
    variant_manifest, variant_manifest_path = _load_manifest(variant_manifest_or_path)
    report_root_path = Path(report_root)
    baseline_segments = _segments_by_id(baseline_manifest, market_type_id=market_type_id)
    variant_segments = _segments_by_id(variant_manifest, market_type_id=market_type_id)
    segment_ids = sorted(set(baseline_segments) & set(variant_segments))
    if not segment_ids:
        raise ValueError(f"no comparable segments for market_type_id={market_type_id}")

    rows = [
        _segment_attribution_row(
            baseline_segments[segment_id],
            variant_segments[segment_id],
            report_root=report_root_path,
            short_reentry_days=short_reentry_days,
        )
        for segment_id in segment_ids
    ]
    overall = _overall_attribution(rows, short_reentry_days=short_reentry_days)
    return {
        "schema": STRATEGY_VARIANT_ATTRIBUTION_SCHEMA,
        "baseline_manifest_path": str(baseline_manifest_path) if baseline_manifest_path is not None else None,
        "variant_manifest_path": str(variant_manifest_path) if variant_manifest_path is not None else None,
        "report_root": str(report_root_path),
        "market_type_id": market_type_id,
        "market_type_label_zh": _market_type_label(baseline_manifest, variant_manifest, market_type_id),
        "segment_count": len(rows),
        "short_reentry_days": short_reentry_days,
        "overall": overall,
        "segments": rows,
        "conclusion_candidates_zh": _conclusion_candidates(overall, rows, short_reentry_days=short_reentry_days),
        "rules": [
            "只读取已落盘 run artifacts，不重跑策略、不重算指标、不补默认值。",
            "本报告解释变体相对基线的交易行为变化，不确认策略上线，也不自动调参。",
            "重入密度按同一标的上一笔退出到下一笔入场的间隔统计。",
            "样本 refs 使用 run_id + trade_index，供 AI 继续下钻 lifecycle/post-exit 证据。",
        ],
    }


def render_strategy_variant_attribution_markdown_zh(attribution: Mapping[str, Any]) -> str:
    """Render strategy-variant attribution as Chinese Markdown."""

    overall = _as_mapping(attribution.get("overall"))
    baseline = _as_mapping(overall.get("baseline"))
    variant = _as_mapping(overall.get("variant"))
    delta = _as_mapping(overall.get("delta"))
    lines = [
        "# 策略变体归因复盘",
        "",
        f"- schema: `{attribution.get('schema')}`",
        f"- market_type_id: `{attribution.get('market_type_id')}`",
        f"- market_type_label_zh: `{attribution.get('market_type_label_zh')}`",
        f"- segment_count: `{attribution.get('segment_count')}`",
        f"- short_reentry_days: `{attribution.get('short_reentry_days')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(attribution.get("rules")):
        lines.append(f"- {rule}")

    lines.extend(["", "## 结论候选"])
    for conclusion in _as_sequence(attribution.get("conclusion_candidates_zh")):
        lines.append(f"- {_escape_cell(conclusion)}")

    lines.extend(
        [
            "",
            "## 总体对比",
            "",
            "| 指标 | 基线 | 变体 | Δ |",
            "|---|---:|---:|---:|",
            _metric_row("平均收益", baseline.get("average_return_pct"), variant.get("average_return_pct"), delta.get("average_return_pct"), percent=True),
            _metric_row("平均回撤", baseline.get("average_max_drawdown"), variant.get("average_max_drawdown"), delta.get("average_max_drawdown"), percent=True),
            _metric_row("交易数", baseline.get("trade_count"), variant.get("trade_count"), delta.get("trade_count")),
            _metric_row("加权胜率", baseline.get("weighted_win_rate"), variant.get("weighted_win_rate"), delta.get("weighted_win_rate"), percent=True),
            _metric_row("平均盈利", baseline.get("average_win"), variant.get("average_win"), delta.get("average_win"), percent=True),
            _metric_row("平均亏损", baseline.get("average_loss"), variant.get("average_loss"), delta.get("average_loss"), percent=True),
            _metric_row("平均持仓天数", baseline.get("average_holding_days"), variant.get("average_holding_days"), delta.get("average_holding_days")),
            _metric_row("短间隔重入次数", baseline.get("short_reentry_count"), variant.get("short_reentry_count"), delta.get("short_reentry_count")),
        ]
    )

    lines.extend(
        [
            "",
            "## 分段对比",
            "",
            "| 行情段 | 基线收益 | 变体收益 | Δ收益 | 基线交易 | 变体交易 | 平均持仓Δ | 短重入Δ | 主退出变化 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in _as_sequence(attribution.get("segments")):
        row_map = _as_mapping(row)
        b = _as_mapping(row_map.get("baseline"))
        v = _as_mapping(row_map.get("variant"))
        d = _as_mapping(row_map.get("delta"))
        lines.append(
            "| "
            f"{_escape_cell(row_map.get('segment_label_zh'))} | "
            f"{_format_optional_percent(b.get('cumulative_return'))} | "
            f"{_format_optional_percent(v.get('cumulative_return'))} | "
            f"{_format_signed_percent(d.get('cumulative_return'))} | "
            f"{b.get('trade_count', '-')} | "
            f"{v.get('trade_count', '-')} | "
            f"{_format_signed_number(d.get('average_holding_days'))} | "
            f"{_format_signed_number(d.get('short_reentry_count'))} | "
            f"{_escape_cell(row_map.get('primary_exit_change_zh'))} |"
        )

    lines.extend(["", "## 快速重入样本"])
    sample_count = 0
    for row in _as_sequence(attribution.get("segments")):
        row_map = _as_mapping(row)
        for sample in _as_sequence(_as_mapping(row_map.get("variant")).get("short_reentry_samples"))[:3]:
            sample_map = _as_mapping(sample)
            sample_count += 1
            lines.append(
                "- "
                f"{_escape_cell(row_map.get('segment_label_zh'))} / `{sample_map.get('symbol')}`: "
                f"前一笔 `{sample_map.get('previous_trade_index')}` {sample_map.get('previous_exit_date')} 退出，"
                f"{sample_map.get('gap_days')} 天后 `{sample_map.get('current_trade_index')}` {sample_map.get('current_entry_date')} 入场。"
            )
    if sample_count == 0:
        lines.append("- 无短间隔重入样本。")

    lines.append("")
    return "\n".join(lines)


def write_strategy_variant_attribution(
    attribution: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write strategy variant attribution JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "strategy_variant_attribution.json"
    markdown_path = output_path / "strategy_variant_attribution.zh.md"
    json_path.write_text(json.dumps(attribution, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_strategy_variant_attribution_markdown_zh(attribution), encoding="utf-8")
    return json_path, markdown_path


def safe_strategy_variant_attribution_dir_name(variant_manifest_path: str | Path, market_type_id: str) -> str:
    path = Path(variant_manifest_path)
    stem = path.parent.name.replace("generated-strategy-variant-runs-", "") if path.parent.name else path.stem
    safe_stem = _safe_token(stem)
    safe_market = _safe_token(market_type_id)
    return f"strategy-variant-attribution-{safe_stem}-{safe_market}"


def _segment_attribution_row(
    baseline_segment: Mapping[str, Any],
    variant_segment: Mapping[str, Any],
    *,
    report_root: Path,
    short_reentry_days: int,
) -> dict[str, Any]:
    baseline_run_id = str(baseline_segment.get("run_id") or baseline_segment.get("baseline_run_id") or "")
    variant_run_id = str(variant_segment.get("run_id") or "")
    baseline = _run_stats(baseline_run_id, report_root=report_root, short_reentry_days=short_reentry_days)
    variant = _run_stats(variant_run_id, report_root=report_root, short_reentry_days=short_reentry_days)
    delta = _run_delta(baseline, variant)
    return {
        "segment_id": baseline_segment.get("segment_id") or variant_segment.get("segment_id"),
        "segment_label_zh": baseline_segment.get("label_zh") or variant_segment.get("segment_label_zh"),
        "from_date": baseline_segment.get("from_date") or variant_segment.get("from_date"),
        "to_date": baseline_segment.get("to_date") or variant_segment.get("to_date"),
        "baseline_run_id": baseline_run_id,
        "variant_run_id": variant_run_id,
        "baseline": baseline,
        "variant": variant,
        "delta": delta,
        "primary_exit_change_zh": _primary_exit_change_zh(baseline, variant),
        "diagnosis_flags": _diagnosis_flags(delta, baseline, variant, short_reentry_days=short_reentry_days),
    }


def _run_stats(run_id: str, *, report_root: Path, short_reentry_days: int) -> dict[str, Any]:
    if not run_id:
        raise ValueError("run_id is required")
    run_dir = report_root / run_id
    report = _read_json(run_dir / "report.json")
    lifecycle = _read_json(run_dir / "trade_lifecycle.json")
    trade_quality = _as_mapping(report.get("trade_quality"))
    returns = _as_mapping(report.get("returns"))
    risk = _as_mapping(report.get("risk"))
    trades = [_as_mapping(item) for item in _as_sequence(lifecycle.get("lifecycles"))]
    holding_days = [_holding_days(trade) for trade in trades]
    holding_days = [value for value in holding_days if value is not None]
    trade_returns = [_optional_float(trade.get("return_pct")) for trade in trades]
    trade_returns = [value for value in trade_returns if value is not None]
    exit_method_counts: Counter[str] = Counter()
    exit_reason_counts: Counter[str] = Counter()
    entry_method_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    add_on_count = 0
    by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        symbol = str(trade.get("symbol") or "")
        if symbol:
            symbol_counts[symbol] += 1
            by_symbol[symbol].append(trade)
        outcome_counts[str(trade.get("outcome") or "unknown")] += 1
        fallback_exit_reason = str(trade.get("exit_reason") or "")
        for event in _as_sequence(trade.get("events")):
            event_map = _as_mapping(event)
            event_type = event_map.get("event_type")
            if event_type == "entry":
                entry_method_counts[str(event_map.get("method_name") or "unknown")] += 1
            elif event_type == "exit":
                exit_method_counts[str(event_map.get("method_name") or "unknown")] += 1
                exit_reason_counts[str(event_map.get("reason_code") or fallback_exit_reason or "unknown")] += 1
            elif event_type == "add_on":
                add_on_count += 1
        if fallback_exit_reason and not any(_as_mapping(event).get("event_type") == "exit" for event in _as_sequence(trade.get("events"))):
            exit_reason_counts[fallback_exit_reason] += 1

    reentry_gaps, reentry_samples = _reentry_gaps(by_symbol, run_id=run_id, short_reentry_days=short_reentry_days)
    return _drop_none(
        {
            "run_id": run_id,
            "cumulative_return": _optional_float(returns.get("cumulative_return")),
            "max_drawdown": _optional_float(risk.get("max_drawdown")),
            "trade_count": _optional_int(trade_quality.get("trade_count")) or len(trades),
            "win_rate": _optional_float(trade_quality.get("win_rate")),
            "average_win": _optional_float(trade_quality.get("average_win")),
            "average_loss": _optional_float(trade_quality.get("average_loss")),
            "average_trade_return_pct": mean(trade_returns) if trade_returns else None,
            "average_holding_days": mean(holding_days) if holding_days else None,
            "median_holding_days": median(holding_days) if holding_days else None,
            "exit_method_counts": _count_rows(exit_method_counts),
            "exit_reason_counts": _count_rows(exit_reason_counts),
            "entry_method_counts": _count_rows(entry_method_counts),
            "outcome_counts": _count_rows(outcome_counts),
            "symbol_trade_counts": _count_rows(symbol_counts),
            "add_on_count": add_on_count,
            "reentry_count": len(reentry_gaps),
            "average_reentry_gap_days": mean(reentry_gaps) if reentry_gaps else None,
            "median_reentry_gap_days": median(reentry_gaps) if reentry_gaps else None,
            "short_reentry_count": sum(1 for gap in reentry_gaps if gap <= short_reentry_days),
            "short_reentry_samples": reentry_samples[:12],
        }
    )


def _reentry_gaps(
    by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    run_id: str,
    short_reentry_days: int,
) -> tuple[list[int], list[dict[str, Any]]]:
    gaps: list[int] = []
    samples: list[dict[str, Any]] = []
    for symbol, trades in by_symbol.items():
        sorted_trades = sorted(trades, key=lambda item: str(item.get("entry_date") or ""))
        for previous, current in zip(sorted_trades, sorted_trades[1:]):
            previous_exit = _parse_date(previous.get("exit_date"))
            current_entry = _parse_date(current.get("entry_date"))
            if previous_exit is None or current_entry is None:
                continue
            gap_days = (current_entry - previous_exit).days
            gaps.append(gap_days)
            if gap_days <= short_reentry_days:
                samples.append(
                    {
                        "run_id": run_id,
                        "symbol": symbol,
                        "gap_days": gap_days,
                        "previous_trade_index": previous.get("trade_index"),
                        "previous_exit_date": previous.get("exit_date"),
                        "previous_exit_reason": previous.get("exit_reason"),
                        "previous_return_pct": previous.get("return_pct"),
                        "current_trade_index": current.get("trade_index"),
                        "current_entry_date": current.get("entry_date"),
                        "current_exit_date": current.get("exit_date"),
                        "current_exit_reason": current.get("exit_reason"),
                        "current_return_pct": current.get("return_pct"),
                    }
                )
    samples.sort(key=lambda item: (int(item.get("gap_days") or 0), str(item.get("symbol") or ""), int(item.get("current_trade_index") or 0)))
    return gaps, samples


def _overall_attribution(rows: Sequence[Mapping[str, Any]], *, short_reentry_days: int) -> dict[str, Any]:
    baseline = _aggregate_run_stats([_as_mapping(row.get("baseline")) for row in rows])
    variant = _aggregate_run_stats([_as_mapping(row.get("variant")) for row in rows])
    return {
        "baseline": baseline,
        "variant": variant,
        "delta": _run_delta(baseline, variant),
        "short_reentry_days": short_reentry_days,
    }


def _aggregate_run_stats(stats: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    trade_count = sum(_optional_int(item.get("trade_count")) or 0 for item in stats)
    win_rate = None
    if trade_count > 0:
        win_rate = sum(
            (_optional_float(item.get("win_rate")) or 0.0) * (_optional_int(item.get("trade_count")) or 0)
            for item in stats
        ) / trade_count
    return _drop_none(
        {
            "segment_count": len(stats),
            "trade_count": trade_count,
            "average_return_pct": _mean_key(stats, "cumulative_return"),
            "average_max_drawdown": _mean_key(stats, "max_drawdown"),
            "weighted_win_rate": win_rate,
            "average_win": _weighted_mean_key(stats, "average_win", "trade_count"),
            "average_loss": _weighted_mean_key(stats, "average_loss", "trade_count"),
            "average_trade_return_pct": _weighted_mean_key(stats, "average_trade_return_pct", "trade_count"),
            "average_holding_days": _weighted_mean_key(stats, "average_holding_days", "trade_count"),
            "add_on_count": sum(_optional_int(item.get("add_on_count")) or 0 for item in stats),
            "reentry_count": sum(_optional_int(item.get("reentry_count")) or 0 for item in stats),
            "short_reentry_count": sum(_optional_int(item.get("short_reentry_count")) or 0 for item in stats),
            "average_reentry_gap_days": _weighted_mean_key(stats, "average_reentry_gap_days", "reentry_count"),
        }
    )


def _run_delta(baseline: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "cumulative_return",
        "max_drawdown",
        "trade_count",
        "win_rate",
        "average_win",
        "average_loss",
        "average_trade_return_pct",
        "average_holding_days",
        "median_holding_days",
        "add_on_count",
        "reentry_count",
        "short_reentry_count",
        "average_reentry_gap_days",
        "average_return_pct",
        "average_max_drawdown",
        "weighted_win_rate",
    )
    return _drop_none({key: _delta_number(variant.get(key), baseline.get(key)) for key in keys})


def _diagnosis_flags(
    delta: Mapping[str, Any],
    baseline: Mapping[str, Any],
    variant: Mapping[str, Any],
    *,
    short_reentry_days: int,
) -> list[str]:
    flags: list[str] = []
    if (_optional_float(delta.get("trade_count")) or 0) > 0:
        flags.append("trade_count_increased")
    if (_optional_float(delta.get("average_holding_days")) or 0) < 0:
        flags.append("holding_period_compressed")
    if (_optional_float(delta.get("short_reentry_count")) or 0) > 0:
        flags.append(f"same_symbol_reentry_within_{short_reentry_days}d_increased")
    if (_optional_float(delta.get("average_win")) or 0) < 0:
        flags.append("average_win_compressed")
    if _top_count_key(variant.get("exit_method_counts")) != _top_count_key(baseline.get("exit_method_counts")):
        flags.append("primary_exit_method_changed")
    if (_optional_float(delta.get("max_drawdown")) or 0) < 0:
        flags.append("drawdown_reduced")
    return flags


def _conclusion_candidates(
    overall: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    short_reentry_days: int,
) -> list[str]:
    delta = _as_mapping(overall.get("delta"))
    baseline = _as_mapping(overall.get("baseline"))
    variant = _as_mapping(overall.get("variant"))
    conclusions = []
    trade_delta = _optional_int(delta.get("trade_count")) or 0
    holding_delta = _optional_float(delta.get("average_holding_days")) or 0.0
    short_reentry_delta = _optional_int(delta.get("short_reentry_count")) or 0
    avg_win_delta = _optional_float(delta.get("average_win")) or 0.0
    if trade_delta > 0 and holding_delta < 0 and short_reentry_delta > 0:
        conclusions.append(
            f"交易数增加主要候选原因是退出后快速释放仓位并重入：交易数增加 {trade_delta}，"
            f"平均持仓减少 {abs(holding_delta):.2f} 天，{short_reentry_days} 天内同标的重入增加 {short_reentry_delta} 次。"
        )
    if avg_win_delta < 0:
        conclusions.append(
            f"盈利被切薄：平均盈利从 {_format_optional_percent(baseline.get('average_win'))} "
            f"降至 {_format_optional_percent(variant.get('average_win'))}。"
        )
    if (_optional_float(delta.get("average_max_drawdown")) or 0.0) < 0:
        conclusions.append(
            f"回撤下降但不是充分胜出理由：平均回撤下降 {_format_signed_percent(delta.get('average_max_drawdown'))}，"
            "需要同时解释收益和胜率下降。"
        )
    exit_changes = sorted(
        {
            str(row.get("primary_exit_change_zh"))
            for row in rows
            if row.get("primary_exit_change_zh")
        }
    )
    if exit_changes:
        conclusions.append("主退出方式变化：" + "；".join(exit_changes) + "。")
    return conclusions or ["暂无足够差异形成归因候选。"]


def _primary_exit_change_zh(baseline: Mapping[str, Any], variant: Mapping[str, Any]) -> str:
    baseline_exit = _top_count_key(baseline.get("exit_method_counts"))
    variant_exit = _top_count_key(variant.get("exit_method_counts"))
    if variant_exit is None and (_optional_int(variant.get("trade_count")) or 0) == 0:
        return "变体无成交"
    if baseline_exit is None and (_optional_int(baseline.get("trade_count")) or 0) == 0:
        return f"基线无成交 -> {variant_exit or '-'}"
    if baseline_exit == variant_exit:
        return f"主退出方式未变：{baseline_exit or '-'}"
    return f"{baseline_exit or '-'} -> {variant_exit or '-'}"


def _segments_by_id(manifest: Mapping[str, Any], *, market_type_id: str) -> dict[str, Mapping[str, Any]]:
    rows = {}
    for item in _as_sequence(manifest.get("segments")):
        segment = _as_mapping(item)
        if segment.get("market_type_id") == market_type_id and segment.get("segment_id"):
            rows[str(segment["segment_id"])] = segment
    return rows


def _market_type_label(
    baseline_manifest: Mapping[str, Any],
    variant_manifest: Mapping[str, Any],
    market_type_id: str,
) -> str | None:
    for manifest in (variant_manifest, baseline_manifest):
        for item in _as_sequence(manifest.get("market_types")):
            row = _as_mapping(item)
            if row.get("market_type_id") == market_type_id:
                return row.get("label_zh") or row.get("market_type_label_zh")
    return None


def _holding_days(trade: Mapping[str, Any]) -> int | None:
    entry_date = _parse_date(trade.get("entry_date"))
    exit_date = _parse_date(trade.get("exit_date"))
    if entry_date is None or exit_date is None:
        return None
    return (exit_date - entry_date).days


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _load_manifest(source: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return source, None
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"missing manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8")), path


def _read_json(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing run artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _count_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"key": key, "count": count}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if key
    ]


def _top_count_key(rows: Any) -> str | None:
    sequence = _as_sequence(rows)
    if not sequence:
        return None
    first = _as_mapping(sequence[0])
    return str(first.get("key")) if first.get("key") is not None else None


def _mean_key(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [_optional_float(row.get(key)) for row in rows]
    present = [value for value in values if value is not None]
    return mean(present) if present else None


def _weighted_mean_key(rows: Sequence[Mapping[str, Any]], key: str, weight_key: str) -> float | None:
    values = []
    weights = []
    for row in rows:
        value = _optional_float(row.get(key))
        weight = _optional_float(row.get(weight_key))
        if value is not None and weight is not None and weight > 0:
            values.append(value * weight)
            weights.append(weight)
    return sum(values) / sum(weights) if weights else None


def _delta_number(new_value: Any, old_value: Any) -> float | int | None:
    new_number = _optional_float(new_value)
    old_number = _optional_float(old_value)
    if new_number is None or old_number is None:
        return None
    delta = new_number - old_number
    if isinstance(new_value, int) and isinstance(old_value, int):
        return int(delta)
    return delta


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _drop_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _metric_row(label: str, baseline: Any, variant: Any, delta: Any, *, percent: bool = False) -> str:
    formatter = _format_optional_percent if percent else _format_optional_number
    delta_formatter = _format_signed_percent if percent else _format_signed_number
    return f"| {label} | {formatter(baseline)} | {formatter(variant)} | {delta_formatter(delta)} |"


def _format_optional_number(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}"


def _format_signed_number(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:+.2f}"


def _format_optional_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:.2%}"


def _format_signed_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:+.2%}"


def _escape_cell(value: Any) -> str:
    if value is None:
        return "-"
    return " ".join(str(value).replace("|", "/").split())


def _safe_token(value: Any) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return safe or "item"
