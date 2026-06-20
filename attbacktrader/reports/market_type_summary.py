"""Aggregate manually grouped market-type validation runs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence


MARKET_TYPE_SUMMARY_SCHEMA = "attbacktrader.market_type_summary.v1"
STRATEGY_VARIANT_VALIDATION_SCHEMA = "attbacktrader.strategy_variant_validation.v1"


def build_market_type_summary(
    manifest_or_path: Mapping[str, Any] | str | Path,
    *,
    report_root: str | Path = "reports",
    min_segment_trades: int = 5,
) -> dict[str, Any]:
    """Build a market-type summary from persisted run artifacts.

    The input manifest is produced by ``att-generate-market-segment-runs``.
    This function only reads existing artifacts; it does not rerun backtests.
    """

    if min_segment_trades <= 0:
        raise ValueError("min_segment_trades must be greater than 0")
    manifest, manifest_path = _load_manifest(manifest_or_path)
    market_types = [_as_mapping(item) for item in _as_sequence(manifest.get("market_types"))]
    if not market_types:
        raise ValueError("manifest.market_types must be non-empty")

    report_root_path = Path(report_root)
    segment_rows = [
        _segment_row(segment, report_root=report_root_path, min_segment_trades=min_segment_trades)
        for segment in _as_sequence(manifest.get("segments"))
    ]
    type_rows = [
        _market_type_row(market_type, segment_rows, min_segment_trades=min_segment_trades)
        for market_type in market_types
    ]
    missing_type_ids = sorted(
        {
            str(row.get("market_type_id") or "")
            for row in segment_rows
            if row.get("market_type_id")
        }
        - {str(item.get("market_type_id") or "") for item in market_types}
    )
    return {
        "schema": MARKET_TYPE_SUMMARY_SCHEMA,
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "report_root": str(report_root_path),
        "base_run_id": manifest.get("base_run_id"),
        "market_type_count": len(market_types),
        "segment_count": len(segment_rows),
        "min_segment_trades": min_segment_trades,
        "market_types": type_rows,
        "segments": segment_rows,
        "validation_warnings": _validation_warnings(type_rows, missing_type_ids),
        "rules": [
            "只读取已落盘的 run artifacts，不重跑策略、不重算指标。",
            "market_type 来自人工 manifest；本汇总不自动判断牛市、震荡市或熊市。",
            "先看同一市场类型下多个样本的统计，再考虑是否形成策略切换线索。",
            "样本不足的段只作为线索，不能作为稳定规律或调参依据。",
            "当前输出是数据汇总，不输出策略适配结论。",
        ],
    }


def render_market_type_summary_markdown_zh(summary: Mapping[str, Any]) -> str:
    """Render market-type summary as Chinese Markdown."""

    lines = [
        "# 市场类型验证汇总",
        "",
        f"- schema: `{summary.get('schema')}`",
        f"- base_run_id: `{summary.get('base_run_id')}`",
        f"- segment_count: `{summary.get('segment_count')}`",
        f"- min_segment_trades: `{summary.get('min_segment_trades')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(summary.get("rules")):
        lines.append(f"- {rule}")

    warnings = _as_sequence(summary.get("validation_warnings"))
    if warnings:
        lines.extend(["", "## 样本风险"])
        for warning in warnings:
            lines.append(f"- {_escape_cell(warning)}")

    lines.extend(
        [
            "",
            "## 类型汇总",
            "",
            "| 类型 | 段数 | 交易数 | 平均收益 | 平均回撤 | 加权胜率 | 盈利段 | 5日卖飞率 | 样本不足段 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in _as_sequence(summary.get("market_types")):
        row_map = _as_mapping(row)
        lines.append(
            "| "
            f"{_escape_cell(row_map.get('market_type_label_zh'))} | "
            f"{row_map.get('segment_count')} | "
            f"{row_map.get('total_trade_count')} | "
            f"{_format_optional_percent(row_map.get('average_return_pct'))} | "
            f"{_format_optional_percent(row_map.get('average_max_drawdown'))} | "
            f"{_format_optional_percent(row_map.get('weighted_win_rate'))} | "
            f"{row_map.get('profitable_segment_count')} | "
            f"{_format_optional_percent(row_map.get('average_sold_too_early_rate_5d'))} | "
            f"{row_map.get('low_sample_segment_count')} |"
        )

    lines.extend(
        [
            "",
            "## 分段明细",
            "",
            "| 类型 | 行情段 | 日期 | 收益 | 回撤 | 交易 | 胜率 | 5日卖飞率 | 报告目录 |",
            "|---|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in _as_sequence(summary.get("segments")):
        row_map = _as_mapping(row)
        lines.append(
            "| "
            f"{_escape_cell(row_map.get('market_type_label_zh'))} | "
            f"{_escape_cell(row_map.get('segment_label_zh'))} | "
            f"{row_map.get('from_date')} 至 {row_map.get('to_date')} | "
            f"{_format_optional_percent(row_map.get('cumulative_return'))} | "
            f"{_format_optional_percent(row_map.get('max_drawdown'))} | "
            f"{row_map.get('trade_count')} | "
            f"{_format_optional_percent(row_map.get('win_rate'))} | "
            f"{_format_optional_percent(row_map.get('sold_too_early_rate_5d'))} | "
            f"`{row_map.get('report_dir')}` |"
        )

    lines.append("")
    return "\n".join(lines)


def write_market_type_summary(
    summary: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write market type summary JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "market_type_summary.json"
    markdown_path = output_path / "market_type_summary.zh.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_market_type_summary_markdown_zh(summary), encoding="utf-8")
    return json_path, markdown_path


def safe_market_type_summary_dir_name(manifest_path: str | Path) -> str:
    path = Path(manifest_path)
    stem = path.parent.name if path.parent.name else path.stem
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem.strip())
    return f"market-type-summary-{safe or 'runs'}"


def build_strategy_variant_validation(
    baseline_summary_or_path: Mapping[str, Any] | str | Path,
    variant_summary_or_path: Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Compare baseline and strategy-variant market-type summaries."""

    baseline, baseline_path = _load_summary(baseline_summary_or_path)
    variant, variant_path = _load_summary(variant_summary_or_path)
    baseline_rows = {
        str(row.get("market_type_id") or ""): _as_mapping(row)
        for row in _as_sequence(baseline.get("market_types"))
    }
    variant_rows = {
        str(row.get("market_type_id") or ""): _as_mapping(row)
        for row in _as_sequence(variant.get("market_types"))
    }
    market_type_ids = sorted(set(baseline_rows) | set(variant_rows))
    rows = [_variant_validation_row(market_type_id, baseline_rows.get(market_type_id), variant_rows.get(market_type_id)) for market_type_id in market_type_ids]
    return {
        "schema": STRATEGY_VARIANT_VALIDATION_SCHEMA,
        "baseline_summary_path": str(baseline_path) if baseline_path is not None else None,
        "variant_summary_path": str(variant_path) if variant_path is not None else None,
        "baseline_base_run_id": baseline.get("base_run_id"),
        "variant_base_run_id": variant.get("base_run_id"),
        "market_type_count": len(rows),
        "rows": rows,
        "validation_warnings": _variant_validation_warnings(baseline, variant),
        "rules": [
            "只比较已落盘的 market_type_summary.json，不重跑策略、不重算指标。",
            "对比结果只说明变体相对基线的变化，不自动确认上线或调参。",
            "收益、回撤、胜率、交易数需要一起看；交易数大幅变化时优先人工复盘样本。",
            "样本不足的市场类型只能作为开发线索，不能作为稳定规律。",
        ],
    }


def render_strategy_variant_validation_markdown_zh(validation: Mapping[str, Any]) -> str:
    """Render strategy variant validation comparison as Chinese Markdown."""

    lines = [
        "# 策略变体验证对比",
        "",
        f"- schema: `{validation.get('schema')}`",
        f"- baseline_base_run_id: `{validation.get('baseline_base_run_id')}`",
        f"- variant_base_run_id: `{validation.get('variant_base_run_id')}`",
        f"- market_type_count: `{validation.get('market_type_count')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(validation.get("rules")):
        lines.append(f"- {rule}")

    warnings = _as_sequence(validation.get("validation_warnings"))
    if warnings:
        lines.extend(["", "## 样本风险"])
        for warning in warnings:
            lines.append(f"- {_escape_cell(warning)}")

    lines.extend(
        [
            "",
            "## 类型对比",
            "",
            "| 类型 | 基线收益 | 变体收益 | Δ收益 | 基线回撤 | 变体回撤 | Δ回撤 | 基线胜率 | 变体胜率 | Δ胜率 | 基线交易 | 变体交易 | 方向 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in _as_sequence(validation.get("rows")):
        row_map = _as_mapping(row)
        baseline = _as_mapping(row_map.get("baseline"))
        variant = _as_mapping(row_map.get("variant"))
        delta = _as_mapping(row_map.get("delta"))
        lines.append(
            "| "
            f"{_escape_cell(row_map.get('market_type_label_zh'))} | "
            f"{_format_optional_percent(baseline.get('average_return_pct'))} | "
            f"{_format_optional_percent(variant.get('average_return_pct'))} | "
            f"{_format_signed_percent(delta.get('average_return_pct'))} | "
            f"{_format_optional_percent(baseline.get('average_max_drawdown'))} | "
            f"{_format_optional_percent(variant.get('average_max_drawdown'))} | "
            f"{_format_signed_percent(delta.get('average_max_drawdown'))} | "
            f"{_format_optional_percent(baseline.get('weighted_win_rate'))} | "
            f"{_format_optional_percent(variant.get('weighted_win_rate'))} | "
            f"{_format_signed_percent(delta.get('weighted_win_rate'))} | "
            f"{baseline.get('total_trade_count', '-')} | "
            f"{variant.get('total_trade_count', '-')} | "
            f"{_escape_cell(row_map.get('direction_zh'))} |"
        )

    lines.append("")
    return "\n".join(lines)


def write_strategy_variant_validation(
    validation: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write strategy variant validation JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "strategy_variant_validation.json"
    markdown_path = output_path / "strategy_variant_validation.zh.md"
    json_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_strategy_variant_validation_markdown_zh(validation), encoding="utf-8")
    return json_path, markdown_path


def safe_strategy_variant_validation_dir_name(variant_summary_path: str | Path) -> str:
    path = Path(variant_summary_path)
    stem = path.parent.name.replace("market-type-summary-", "") if path.parent.name else path.stem
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem.strip())
    return f"strategy-variant-validation-{safe or 'runs'}"


def _variant_validation_row(
    market_type_id: str,
    baseline: Mapping[str, Any] | None,
    variant: Mapping[str, Any] | None,
) -> dict[str, Any]:
    baseline_row = _metric_snapshot(baseline)
    variant_row = _metric_snapshot(variant)
    delta = {
        "average_return_pct": _delta_float(variant_row.get("average_return_pct"), baseline_row.get("average_return_pct")),
        "average_max_drawdown": _delta_float(variant_row.get("average_max_drawdown"), baseline_row.get("average_max_drawdown")),
        "weighted_win_rate": _delta_float(variant_row.get("weighted_win_rate"), baseline_row.get("weighted_win_rate")),
        "total_trade_count": _delta_int(variant_row.get("total_trade_count"), baseline_row.get("total_trade_count")),
        "average_sold_too_early_rate_5d": _delta_float(
            variant_row.get("average_sold_too_early_rate_5d"),
            baseline_row.get("average_sold_too_early_rate_5d"),
        ),
    }
    return _drop_none(
        {
            "market_type_id": market_type_id,
            "market_type_label_zh": (variant or baseline or {}).get("market_type_label_zh"),
            "baseline": baseline_row,
            "variant": variant_row,
            "delta": _drop_none(delta),
            "direction_zh": _variant_direction_zh(delta),
        }
    )


def _metric_snapshot(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    return _drop_none(
        {
            "segment_count": _optional_int(row.get("segment_count")),
            "total_trade_count": _optional_int(row.get("total_trade_count")),
            "average_return_pct": _optional_float(row.get("average_return_pct")),
            "average_max_drawdown": _optional_float(row.get("average_max_drawdown")),
            "weighted_win_rate": _optional_float(row.get("weighted_win_rate")),
            "profitable_segment_count": _optional_int(row.get("profitable_segment_count")),
            "loss_segment_count": _optional_int(row.get("loss_segment_count")),
            "low_sample_segment_count": _optional_int(row.get("low_sample_segment_count")),
            "average_sold_too_early_rate_5d": _optional_float(row.get("average_sold_too_early_rate_5d")),
        }
    )


def _variant_direction_zh(delta: Mapping[str, Any]) -> str:
    return_delta = _optional_float(delta.get("average_return_pct"))
    drawdown_delta = _optional_float(delta.get("average_max_drawdown"))
    win_rate_delta = _optional_float(delta.get("weighted_win_rate"))
    trade_count_delta = _optional_int(delta.get("total_trade_count"))
    if return_delta is None:
        return "缺少可比收益"
    if return_delta > 0 and (drawdown_delta is None or drawdown_delta <= 0):
        return "收益提升且回撤未扩大"
    if return_delta > 0:
        return "收益提升但回撤扩大"
    if return_delta < 0 and win_rate_delta is not None and win_rate_delta < 0:
        return "收益和胜率下降"
    if return_delta < 0 and trade_count_delta is not None and abs(trade_count_delta) > 20:
        return "收益下降且交易数变化大"
    if return_delta < 0:
        return "收益下降"
    if drawdown_delta is not None and drawdown_delta < 0:
        return "收益持平但回撤下降"
    return "变化不明显"


def _variant_validation_warnings(baseline: Mapping[str, Any], variant: Mapping[str, Any]) -> list[str]:
    warnings = []
    for prefix, summary in (("基线", baseline), ("变体", variant)):
        for warning in _as_sequence(summary.get("validation_warnings")):
            warnings.append(f"{prefix}: {warning}")
    return warnings


def _load_summary(source: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return source, None
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"missing market type summary: {path}")
    return json.loads(path.read_text(encoding="utf-8")), path


def _delta_float(new_value: Any, old_value: Any) -> float | None:
    new_number = _optional_float(new_value)
    old_number = _optional_float(old_value)
    if new_number is None or old_number is None:
        return None
    return new_number - old_number


def _delta_int(new_value: Any, old_value: Any) -> int | None:
    new_number = _optional_int(new_value)
    old_number = _optional_int(old_value)
    if new_number is None or old_number is None:
        return None
    return new_number - old_number


def _segment_row(
    segment: Any,
    *,
    report_root: Path,
    min_segment_trades: int,
) -> dict[str, Any]:
    segment_map = _as_mapping(segment)
    run_id = str(segment_map.get("run_id") or "")
    if not run_id:
        raise ValueError("manifest segment run_id is required")
    report_dir = report_root / run_id
    report = _read_json(report_dir / "report.json")
    post_exit = _read_optional_json(report_dir / "post_exit_analysis.json")
    environment_fit = _read_optional_json(report_dir / "environment_fit.json")
    profile = _read_optional_json(report_dir / "strategy_environment_profile.json")

    returns = _as_mapping(report.get("returns"))
    risk = _as_mapping(report.get("risk"))
    trade_quality = _as_mapping(report.get("trade_quality"))
    post_exit_summary = _post_exit_all_summary(post_exit)
    environment_overall = _as_mapping(environment_fit.get("overall")) if environment_fit else {}
    profile_summary = _as_mapping(profile.get("profile_summary")) if profile else {}
    trade_count = _optional_int(trade_quality.get("trade_count"))
    return _drop_none(
        {
            "segment_id": segment_map.get("segment_id"),
            "segment_label_zh": segment_map.get("label_zh"),
            "market_type_id": segment_map.get("market_type_id"),
            "market_type_label_zh": segment_map.get("market_type_label_zh"),
            "validation_role": segment_map.get("validation_role"),
            "from_date": segment_map.get("from_date"),
            "to_date": segment_map.get("to_date"),
            "run_id": run_id,
            "report_dir": str(report_dir),
            "report_path": str(report_dir / "report.json"),
            "cumulative_return": _optional_float(returns.get("cumulative_return")),
            "final_equity": _optional_float(returns.get("final_equity")),
            "max_drawdown": _optional_float(risk.get("max_drawdown")),
            "trade_count": trade_count,
            "win_rate": _optional_float(trade_quality.get("win_rate")),
            "average_win": _optional_float(trade_quality.get("average_win")),
            "average_loss": _optional_float(trade_quality.get("average_loss")),
            "profit_loss_ratio": _optional_float(trade_quality.get("profit_loss_ratio")),
            "sold_too_early_rate_5d": _optional_float(post_exit_summary.get("sold_too_early_rate")),
            "avg_max_high_after_exit_5d": _optional_float(post_exit_summary.get("average_max_high_return_pct")),
            "avg_window_close_after_exit_5d": _optional_float(post_exit_summary.get("average_fifth_day_close_return_pct")),
            "environment_trade_count": _optional_int(environment_fit.get("trade_count")) if environment_fit else None,
            "environment_net_pnl": _optional_float(environment_overall.get("net_pnl")),
            "environment_return_on_entry_value": _optional_float(environment_overall.get("return_on_entry_value")),
            "preferred_environment_count": _optional_int(profile_summary.get("preferred_count")),
            "avoid_environment_count": _optional_int(profile_summary.get("avoid_count")),
            "uncertain_environment_count": _optional_int(profile_summary.get("uncertain_count")),
            "low_sample": trade_count is None or trade_count < min_segment_trades,
        }
    )


def _market_type_row(
    market_type: Mapping[str, Any],
    segment_rows: Sequence[Mapping[str, Any]],
    *,
    min_segment_trades: int,
) -> dict[str, Any]:
    market_type_id = str(market_type.get("market_type_id") or "")
    rows = [row for row in segment_rows if row.get("market_type_id") == market_type_id]
    trade_count = sum(_optional_int(row.get("trade_count")) or 0 for row in rows)
    weighted_win_rate = None
    if trade_count > 0:
        weighted_win_rate = sum(
            (_optional_float(row.get("win_rate")) or 0.0) * (_optional_int(row.get("trade_count")) or 0)
            for row in rows
        ) / trade_count
    sold_rates = [_optional_float(row.get("sold_too_early_rate_5d")) for row in rows]
    returns = [_optional_float(row.get("cumulative_return")) for row in rows]
    drawdowns = [_optional_float(row.get("max_drawdown")) for row in rows]
    return _drop_none(
        {
            "market_type_id": market_type_id,
            "market_type_label_zh": market_type.get("label_zh"),
            "strategy_switching_use_zh": market_type.get("strategy_switching_use_zh"),
            "selection_rule_zh": market_type.get("selection_rule_zh"),
            "segment_count": len(rows),
            "total_trade_count": trade_count,
            "average_return_pct": _mean_present(returns),
            "average_max_drawdown": _mean_present(drawdowns),
            "weighted_win_rate": weighted_win_rate,
            "profitable_segment_count": sum(1 for value in returns if value is not None and value > 0),
            "loss_segment_count": sum(1 for value in returns if value is not None and value < 0),
            "low_sample_segment_count": sum(
                1
                for row in rows
                if (_optional_int(row.get("trade_count")) or 0) < min_segment_trades
            ),
            "average_sold_too_early_rate_5d": _mean_present(sold_rates),
            "best_segment_by_return": _segment_ref(max(rows, key=lambda row: _sort_number(row.get("cumulative_return"), missing=float("-inf"))))
            if rows
            else None,
            "worst_segment_by_return": _segment_ref(min(rows, key=lambda row: _sort_number(row.get("cumulative_return"), missing=float("inf"))))
            if rows
            else None,
        }
    )


def _segment_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "segment_id": row.get("segment_id"),
        "segment_label_zh": row.get("segment_label_zh"),
        "run_id": row.get("run_id"),
        "cumulative_return": row.get("cumulative_return"),
        "trade_count": row.get("trade_count"),
    }


def _validation_warnings(type_rows: Sequence[Mapping[str, Any]], missing_type_ids: Sequence[str]) -> list[str]:
    warnings = []
    for market_type in type_rows:
        segment_count = _optional_int(market_type.get("segment_count")) or 0
        low_sample = _optional_int(market_type.get("low_sample_segment_count")) or 0
        if segment_count < 3:
            warnings.append(f"{market_type.get('market_type_label_zh') or market_type.get('market_type_id')} 样本段少于 3 段")
        if low_sample:
            warnings.append(
                f"{market_type.get('market_type_label_zh') or market_type.get('market_type_id')} 有 {low_sample} 段交易样本不足"
            )
    for market_type_id in missing_type_ids:
        warnings.append(f"manifest 中存在未声明的 market_type_id: {market_type_id}")
    return warnings


def _post_exit_all_summary(post_exit: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not post_exit:
        return {}
    for summary in _as_sequence(post_exit.get("summaries")):
        summary_map = _as_mapping(summary)
        if summary_map.get("group") == "all":
            return summary_map
    return {}


def _load_manifest(source: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return source, None
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"missing market segment manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8")), path


def _read_json(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing run artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _mean_present(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return mean(present) if present else None


def _sort_number(value: Any, *, missing: float) -> float:
    number = _optional_float(value)
    return number if number is not None else missing


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
