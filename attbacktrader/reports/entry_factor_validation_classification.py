"""Classify Stage 1 entry-factor validation results by year and market stage."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


ENTRY_FACTOR_VALIDATION_CLASSIFICATION_SCHEMA = "attbacktrader.entry_factor_validation_classification.v1"
OBJECTIVE_ENTRY_STAGE_FIELD = "market.objective.entry_stage"
RUNTIME_ENTRY_STAGE_FIELD = "market.hs300.trend_state"

_STAGE_ORDER = {"bullish": 0, "mixed": 1, "bearish": 2, "unknown": 3}


def build_entry_factor_validation_classification(
    matrix_or_path: Mapping[str, Any] | str | Path,
    *,
    report_root: str | Path = "reports",
    baseline_run_dir: str | Path | None = None,
    min_total_trades: int = 50,
    min_year_trades: int = 30,
    min_stage_trades: int = 30,
    slice_score_threshold: float = 0.0,
) -> dict[str, Any]:
    """Classify real single-factor validation rows using persisted run artifacts only."""

    matrix, matrix_path = _load_matrix(matrix_or_path)
    baseline_info = _as_mapping(matrix.get("baseline"))
    baseline_run_id = _optional_str(baseline_info.get("run_id"))
    baseline_dir = Path(baseline_run_dir) if baseline_run_dir is not None else _baseline_run_dir(
        baseline_run_id,
        report_root=report_root,
    )
    baseline = _load_run_dataset(
        run_id=baseline_run_id or "baseline",
        artifacts={},
        run_dir=baseline_dir,
    )
    baseline_year = _slice_metrics(baseline["trades"], key_fn=lambda trade: str(trade.get("year") or "unknown"))
    baseline_overall = _metrics_for_trades(baseline["trades"])
    baseline_runtime: dict[str, Any] | None = None

    rows: list[dict[str, Any]] = []
    warnings: list[str] = list(baseline.get("warnings") or [])
    for row in _as_sequence(matrix.get("rows")):
        row_map = dict(_as_mapping(row))
        artifacts = _as_mapping(row_map.get("artifacts"))
        run_dir = _candidate_run_dir(row_map, artifacts)
        candidate = _load_run_dataset(
            run_id=_optional_str(row_map.get("run_id")) or f"candidate-{row_map.get('candidate_index')}",
            artifacts=artifacts,
            run_dir=run_dir,
        )
        warnings.extend(str(item) for item in candidate.get("warnings") or [])

        candidate_overall = _metrics_for_trades(candidate["trades"])
        baseline_for_stage = baseline
        if candidate.get("stage_source") != baseline.get("stage_source"):
            if candidate.get("stage_source") == "runtime_market_hs300_trend_state_fallback":
                if baseline_runtime is None:
                    baseline_runtime = _load_run_dataset(
                        run_id=baseline_run_id or "baseline",
                        artifacts={},
                        run_dir=baseline_dir,
                        prefer_runtime_stage=True,
                    )
                if baseline_runtime.get("stage_source") == candidate.get("stage_source"):
                    baseline_for_stage = baseline_runtime
        stage_source = _merged_stage_source(
            _optional_str(candidate.get("stage_source")),
            _optional_str(baseline_for_stage.get("stage_source")),
        )
        overall_comparison = _compare_metrics(
            "overall",
            "总样本",
            baseline_overall,
            candidate_overall,
            min_trade_count=min_total_trades,
            score_threshold=slice_score_threshold,
        )
        year_slices = _slice_comparisons(
            baseline_year,
            _slice_metrics(candidate["trades"], key_fn=lambda trade: str(trade.get("year") or "unknown")),
            min_trade_count=min_year_trades,
            score_threshold=slice_score_threshold,
            label_fn=lambda year: f"{year} 年",
        )
        market_stage_slices = _slice_comparisons(
            _slice_metrics(baseline_for_stage["trades"], key_fn=lambda trade: str(trade.get("entry_stage") or "unknown")),
            _slice_metrics(candidate["trades"], key_fn=lambda trade: str(trade.get("entry_stage") or "unknown")),
            min_trade_count=min_stage_trades,
            score_threshold=slice_score_threshold,
            label_fn=_stage_label_zh,
            sort_key=lambda stage: (_STAGE_ORDER.get(stage, 99), stage),
        )
        if candidate.get("stage_source") != baseline_for_stage.get("stage_source"):
            warnings.append(
                f"{row_map.get('run_id')}: market stage source mismatch "
                f"candidate={candidate.get('stage_source')} baseline={baseline_for_stage.get('stage_source')}"
            )
            market_stage_slices = [
                dict(item, status="insufficient_sample")
                for item in market_stage_slices
            ]
        row_warnings = _sample_warnings(
            row_map,
            candidate,
            overall_comparison=overall_comparison,
            year_slices=year_slices,
            market_stage_slices=market_stage_slices,
            min_total_trades=min_total_trades,
            min_year_trades=min_year_trades,
            min_stage_trades=min_stage_trades,
        )
        classification, reasons = _classify_row(
            row_map,
            overall_comparison=overall_comparison,
            year_slices=year_slices,
            market_stage_slices=market_stage_slices,
            candidate_trade_count=int(candidate_overall.get("trade_count") or 0),
            baseline_trade_count=int(baseline_overall.get("trade_count") or 0),
            min_total_trades=min_total_trades,
        )
        rows.append({
            "candidate_index": row_map.get("candidate_index"),
            "candidate_rank": row_map.get("candidate_rank"),
            "direction": row_map.get("direction"),
            "action": row_map.get("action"),
            "field_key": row_map.get("field_key"),
            "field_label_zh": row_map.get("field_label_zh"),
            "value": row_map.get("value"),
            "value_label_zh": row_map.get("value_label_zh"),
            "run_id": row_map.get("run_id"),
            "matrix_status": row_map.get("status"),
            "validation_score": row_map.get("validation_score"),
            "classification": classification,
            "classification_label_zh": _classification_label_zh(classification),
            "classification_reasons": reasons,
            "overall_comparison": overall_comparison,
            "year_slices": year_slices,
            "market_stage_slices": market_stage_slices,
            "stage_source": stage_source,
            "stage_coverage": {
                "candidate": candidate.get("stage_coverage"),
                "baseline": baseline_for_stage.get("stage_coverage"),
            },
            "sample_warnings": row_warnings,
            "artifacts": artifacts,
        })

    classification_counts = dict(Counter(str(row.get("classification")) for row in rows))
    return {
        "schema": ENTRY_FACTOR_VALIDATION_CLASSIFICATION_SCHEMA,
        "source_matrix": str(matrix_path) if matrix_path is not None else None,
        "source_manifest": matrix.get("source_manifest"),
        "baseline": {
            "run_id": baseline_run_id,
            "run_dir": str(baseline_dir),
            "metrics": baseline_overall,
            "stage_source": baseline.get("stage_source"),
            "stage_coverage": baseline.get("stage_coverage"),
        },
        "rules": {
            "min_total_trades": min_total_trades,
            "min_year_trades": min_year_trades,
            "min_stage_trades": min_stage_trades,
            "slice_score_threshold": slice_score_threshold,
            "stable_rule": "overall supports and no assessable year/stage slice fails",
            "positive_keep": "stable favorable",
            "negative_exclude": "stable unfavorable",
        },
        "record_count": len(rows),
        "classification_counts": classification_counts,
        "rows": rows,
        "rankings": {
            "stable_favorable": [row for row in rows if row.get("classification") == "stable_favorable"],
            "stable_unfavorable": [row for row in rows if row.get("classification") == "stable_unfavorable"],
            "market_stage_dependent": [row for row in rows if row.get("classification") == "market_stage_dependent"],
            "noise": [row for row in rows if row.get("classification") == "noise"],
            "insufficient_sample": [row for row in rows if row.get("classification") == "insufficient_sample"],
        },
        "validation_warnings": sorted(set(warnings)),
    }


def render_entry_factor_validation_classification_markdown_zh(report: Mapping[str, Any]) -> str:
    """Render the entry-factor classification report in Chinese Markdown."""

    baseline = _as_mapping(report.get("baseline"))
    rules = _as_mapping(report.get("rules"))
    lines = [
        "# 入场因子分层分类报告",
        "",
        f"- schema: `{report.get('schema')}`",
        f"- source_matrix: `{report.get('source_matrix')}`",
        f"- baseline_run_id: `{baseline.get('run_id')}`",
        f"- record_count: `{report.get('record_count')}`",
        f"- min_total_trades: `{rules.get('min_total_trades')}`",
        f"- min_year_trades: `{rules.get('min_year_trades')}`",
        f"- min_stage_trades: `{rules.get('min_stage_trades')}`",
        "",
        "## 分类汇总",
        "",
        "| 分类 | 数量 |",
        "|---|---:|",
    ]
    counts = _as_mapping(report.get("classification_counts"))
    for key in ("stable_favorable", "stable_unfavorable", "market_stage_dependent", "noise", "insufficient_sample"):
        lines.append(f"| {_classification_label_zh(key)} | {counts.get(key, 0)} |")

    warnings = _as_sequence(report.get("validation_warnings"))
    if warnings:
        lines.extend(["", "## 样本与阶段来源风险"])
        for warning in warnings:
            lines.append(f"- {_escape_cell(warning)}")

    lines.extend([
        "",
        "## 候选分类",
        "",
        "| 序号 | 分类 | 方向 | 动作 | 因子 | 值 | 总收益差 | 总胜率差 | 年份状态 | 阶段状态 | 阶段来源 | 理由 |",
        "|---:|---|---|---|---|---|---:|---:|---|---|---|---|",
    ])
    for row in _as_sequence(report.get("rows")):
        row_map = _as_mapping(row)
        overall = _as_mapping(row_map.get("overall_comparison"))
        lines.append(
            "| "
            f"{row_map.get('candidate_index')} | "
            f"{_escape_cell(row_map.get('classification_label_zh'))} | "
            f"{_escape_cell(row_map.get('direction'))} | "
            f"{_escape_cell(row_map.get('action'))} | "
            f"`{_escape_cell(row_map.get('field_key'))}` | "
            f"{_escape_cell(row_map.get('value_label_zh') or row_map.get('value'))} | "
            f"{_format_signed_percent(_as_mapping(overall.get('deltas')).get('return_on_entry_value'))} | "
            f"{_format_signed_percent(_as_mapping(overall.get('deltas')).get('win_rate'))} | "
            f"{_status_summary(row_map.get('year_slices'))} | "
            f"{_status_summary(row_map.get('market_stage_slices'))} | "
            f"{_escape_cell(row_map.get('stage_source'))} | "
            f"{_escape_cell('; '.join(str(item) for item in _as_sequence(row_map.get('classification_reasons'))))} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_entry_factor_validation_classification(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, dict[str, Any]]:
    """Write classification JSON and Chinese Markdown artifacts."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "entry_factor_validation_classification.json"
    markdown_path = output_path / "entry_factor_validation_classification.zh.md"

    payload = _jsonable(report)
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["classification_json"] = str(json_path)
    artifacts["classification_markdown_zh"] = str(markdown_path)
    payload["artifacts"] = artifacts

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_factor_validation_classification_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def safe_entry_factor_validation_classification_dir_name(matrix_path: str | Path) -> str:
    stem = Path(matrix_path).parent.name or Path(matrix_path).stem
    return f"entry-factor-validation-classification-{_safe_path_name(stem)}"


def _load_run_dataset(
    *,
    run_id: str,
    artifacts: Mapping[str, Any],
    run_dir: Path,
    prefer_runtime_stage: bool = False,
) -> dict[str, Any]:
    trades_path = _resolve_existing_path(
        artifacts.get("trades"),
        run_dir / "trades.json",
    )
    warnings: list[str] = []
    if trades_path is None:
        warnings.append(f"{run_id}: missing trades.json")
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "trades": [],
            "stage_source": "missing",
            "stage_coverage": 0.0,
            "warnings": warnings,
        }

    trades_payload = _load_json_mapping(trades_path)
    raw_trades = _as_sequence(trades_payload.get("closed_trades") or trades_payload.get("trades"))
    stage_by_index, stage_source, stage_warnings = _load_stage_by_trade_index(
        artifacts,
        run_dir=run_dir,
        prefer_runtime_stage=prefer_runtime_stage,
    )
    warnings.extend(stage_warnings)

    trades: list[dict[str, Any]] = []
    stage_hit_count = 0
    for raw_trade in raw_trades:
        trade = _normalise_trade(_as_mapping(raw_trade))
        trade_index = trade.get("trade_index")
        stage = stage_by_index.get(trade_index) if trade_index is not None else None
        if stage is None:
            stage = _stage_from_trade(_as_mapping(raw_trade))
        if stage is None:
            stage = "unknown"
        else:
            stage_hit_count += 1
        trade["entry_stage"] = stage
        trades.append(trade)

    coverage = stage_hit_count / len(trades) if trades else 0.0
    if stage_source != "objective_wide_samples":
        warnings.append(f"{run_id}: market stage source is {stage_source}, not objective wide samples")
    if trades and coverage < 0.8:
        warnings.append(f"{run_id}: market stage coverage {coverage:.1%}")

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "trades_path": str(trades_path),
        "trades": trades,
        "stage_source": stage_source,
        "stage_coverage": coverage,
        "warnings": warnings,
    }


def _load_stage_by_trade_index(
    artifacts: Mapping[str, Any],
    *,
    run_dir: Path,
    prefer_runtime_stage: bool = False,
) -> tuple[dict[int, str], str, list[str]]:
    if prefer_runtime_stage:
        runtime = _load_runtime_stage_by_trade_index(artifacts, run_dir=run_dir)
        if runtime is not None:
            return runtime

    wide_path = _resolve_existing_path(
        artifacts.get("attribution_wide_samples"),
        run_dir / "full_entry_scope_environment_fit_review" / "attribution_wide_samples.json",
        run_dir / "attribution_wide_samples.json",
    )
    if wide_path is not None:
        payload = _load_json_mapping(wide_path)
        stages: dict[int, str] = {}
        for sample in _as_sequence(payload.get("samples")):
            sample_map = _as_mapping(sample)
            trade_index = _optional_int(sample_map.get("trade_index"))
            stage = _stage_from_wide_sample(sample_map)
            if trade_index is not None and stage is not None:
                stages[trade_index] = stage
        return stages, "objective_wide_samples", []

    runtime = _load_runtime_stage_by_trade_index(artifacts, run_dir=run_dir)
    if runtime is not None:
        return runtime

    return {}, "missing", [f"{run_dir}: missing attribution wide samples and trade attribution"]


def _load_runtime_stage_by_trade_index(
    artifacts: Mapping[str, Any],
    *,
    run_dir: Path,
) -> tuple[dict[int, str], str, list[str]] | None:
    attribution_path = _resolve_existing_path(
        artifacts.get("trade_attribution"),
        run_dir / "trade_attribution.json",
    )
    if attribution_path is None:
        return None
    payload = _load_json_mapping(attribution_path)
    stages = {}
    for attribution in _as_sequence(payload.get("attributions")):
        item = _as_mapping(attribution)
        trade_index = _optional_int(item.get("trade_index"))
        stage = _stage_from_runtime_attribution(item)
        if trade_index is not None and stage is not None:
            stages[trade_index] = stage
    return stages, "runtime_market_hs300_trend_state_fallback", []


def _normalise_trade(raw: Mapping[str, Any]) -> dict[str, Any]:
    entry_value = _number_or_none(raw.get("entry_gross_value"))
    if entry_value is None:
        entry_value = _number_or_none(raw.get("entry_value"))
    net_pnl = _number_or_none(raw.get("net_pnl"))
    return_pct = _number_or_none(raw.get("realized_return_pct"))
    if return_pct is None:
        return_pct = _number_or_none(raw.get("return_pct"))
    if net_pnl is None and return_pct is not None and entry_value is not None:
        net_pnl = return_pct * entry_value
    if return_pct is None and net_pnl is not None and entry_value:
        return_pct = net_pnl / entry_value
    entry_date = _optional_str(raw.get("entry_date")) or ""
    return {
        "trade_index": _optional_int(raw.get("trade_index")),
        "symbol": raw.get("symbol"),
        "entry_date": entry_date,
        "exit_date": raw.get("exit_date"),
        "year": entry_date[:4] if len(entry_date) >= 4 else "unknown",
        "entry_value": entry_value,
        "net_pnl": net_pnl,
        "return_pct": return_pct,
    }


def _metrics_for_trades(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total_entry_value = sum(_number_or_none(trade.get("entry_value")) or 0.0 for trade in trades)
    pnl_values = [_number_or_none(trade.get("net_pnl")) for trade in trades]
    pnl_numbers = [value for value in pnl_values if value is not None]
    total_net_pnl = sum(pnl_numbers)
    returns = [_number_or_none(trade.get("return_pct")) for trade in trades]
    return_numbers = [value for value in returns if value is not None]
    gross_profit = sum(value for value in pnl_numbers if value > 0)
    gross_loss = abs(sum(value for value in pnl_numbers if value < 0))
    win_count = sum(1 for value in pnl_numbers if value > 0)
    loss_count = sum(1 for value in pnl_numbers if value < 0)
    trade_count = len(trades)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    return {
        "trade_count": trade_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_count / trade_count if trade_count else None,
        "average_return_pct": _average(return_numbers),
        "total_entry_value": total_entry_value,
        "net_pnl": total_net_pnl,
        "return_on_entry_value": total_net_pnl / total_entry_value if total_entry_value else None,
        "profit_factor": profit_factor,
        "max_drawdown_proxy": _max_drawdown_proxy(pnl_numbers, total_entry_value=total_entry_value),
    }


def _slice_metrics(
    trades: Sequence[Mapping[str, Any]],
    *,
    key_fn: Callable[[Mapping[str, Any]], str],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[key_fn(trade)].append(trade)
    return {
        key: _metrics_for_trades(value)
        for key, value in grouped.items()
    }


def _slice_comparisons(
    baseline_slices: Mapping[str, Mapping[str, Any]],
    candidate_slices: Mapping[str, Mapping[str, Any]],
    *,
    min_trade_count: int,
    score_threshold: float,
    label_fn: Callable[[str], str],
    sort_key: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    keys = set(baseline_slices) | set(candidate_slices)
    ordered = sorted(keys, key=sort_key or (lambda value: value))
    return [
        _compare_metrics(
            key,
            label_fn(key),
            baseline_slices.get(key, {}),
            candidate_slices.get(key, {}),
            min_trade_count=min_trade_count,
            score_threshold=score_threshold,
        )
        for key in ordered
    ]


def _compare_metrics(
    slice_key: str,
    label_zh: str,
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    min_trade_count: int,
    score_threshold: float,
) -> dict[str, Any]:
    deltas = _metric_deltas(candidate, baseline)
    score_components = _slice_score_components(deltas)
    score = sum(score_components.values())
    status = _comparison_status(
        candidate,
        baseline,
        deltas=deltas,
        score=score,
        min_trade_count=min_trade_count,
        score_threshold=score_threshold,
    )
    return {
        "slice_key": slice_key,
        "label_zh": label_zh,
        "status": status,
        "baseline": dict(baseline),
        "candidate": dict(candidate),
        "deltas": deltas,
        "score_components": score_components,
        "score": score,
    }


def _metric_deltas(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("trade_count", "win_rate", "average_return_pct", "return_on_entry_value", "profit_factor", "max_drawdown_proxy"):
        candidate_value = _number_or_none(candidate.get(key))
        baseline_value = _number_or_none(baseline.get(key))
        if candidate_value is not None and baseline_value is not None:
            result[key] = candidate_value - baseline_value
    return result


def _slice_score_components(deltas: Mapping[str, Any]) -> dict[str, float]:
    return_delta = _number_or_none(deltas.get("return_on_entry_value"))
    if return_delta is None:
        return_delta = _number_or_none(deltas.get("average_return_pct")) or 0.0
    drawdown_delta = _number_or_none(deltas.get("max_drawdown_proxy")) or 0.0
    win_rate_delta = _number_or_none(deltas.get("win_rate")) or 0.0
    profit_factor_delta = _number_or_none(deltas.get("profit_factor")) or 0.0
    return {
        "return": 100.0 * return_delta,
        "drawdown": -50.0 * drawdown_delta,
        "win_rate": 20.0 * win_rate_delta,
        "profit_factor": 2.0 * profit_factor_delta,
    }


def _comparison_status(
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    deltas: Mapping[str, Any],
    score: float,
    min_trade_count: int,
    score_threshold: float,
) -> str:
    if int(candidate.get("trade_count") or 0) < min_trade_count or int(baseline.get("trade_count") or 0) < min_trade_count:
        return "insufficient_sample"
    return_delta = _number_or_none(deltas.get("return_on_entry_value"))
    if return_delta is None:
        return_delta = _number_or_none(deltas.get("average_return_pct"))
    if return_delta is None:
        return "insufficient_sample"
    if return_delta > 0 and score >= score_threshold:
        return "supports_candidate"
    if return_delta < 0 and score <= -score_threshold:
        return "fails_candidate"
    return "mixed"


def _classify_row(
    row: Mapping[str, Any],
    *,
    overall_comparison: Mapping[str, Any],
    year_slices: Sequence[Mapping[str, Any]],
    market_stage_slices: Sequence[Mapping[str, Any]],
    candidate_trade_count: int,
    baseline_trade_count: int,
    min_total_trades: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if candidate_trade_count < min_total_trades:
        return "insufficient_sample", [f"候选总交易数 {candidate_trade_count} 低于阈值 {min_total_trades}"]
    if baseline_trade_count < min_total_trades:
        return "insufficient_sample", [f"基线总交易数 {baseline_trade_count} 低于阈值 {min_total_trades}"]
    if row.get("status") != "supports_candidate":
        return "noise", [f"矩阵整体状态为 {row.get('status')}，未支持候选"]
    if overall_comparison.get("status") == "insufficient_sample":
        return "insufficient_sample", ["总样本对比样本不足"]
    if overall_comparison.get("status") != "supports_candidate":
        return "noise", [f"总样本切片状态为 {overall_comparison.get('status')}"]

    assessable_year = [item for item in year_slices if item.get("status") != "insufficient_sample"]
    assessable_stage = [item for item in market_stage_slices if item.get("status") != "insufficient_sample"]
    if not assessable_year:
        return "insufficient_sample", ["没有可评估的年份切片"]
    if not assessable_stage:
        return "insufficient_sample", ["没有可评估的市场阶段切片"]

    failed_year = [item for item in assessable_year if item.get("status") == "fails_candidate"]
    failed_stage = [item for item in assessable_stage if item.get("status") == "fails_candidate"]
    supported_stage = [item for item in assessable_stage if item.get("status") == "supports_candidate"]
    supported_year = [item for item in assessable_year if item.get("status") == "supports_candidate"]
    if failed_stage:
        reasons.append("至少一个可评估市场阶段失败")
    if failed_year:
        reasons.append("至少一个可评估年份失败")
    if failed_stage or failed_year:
        if supported_stage or supported_year:
            return "market_stage_dependent", reasons or ["切片表现不一致"]
        return "noise", reasons or ["切片表现不支持候选"]

    if str(row.get("action")) == "exclude" or str(row.get("direction")) == "negative":
        return "stable_unfavorable", ["整体改善，年份和市场阶段切片未明显失败；负向桶适合继续作为排除规则验证"]
    return "stable_favorable", ["整体改善，年份和市场阶段切片未明显失败；正向桶适合继续作为保留规则验证"]


def _sample_warnings(
    row: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    overall_comparison: Mapping[str, Any],
    year_slices: Sequence[Mapping[str, Any]],
    market_stage_slices: Sequence[Mapping[str, Any]],
    min_total_trades: int,
    min_year_trades: int,
    min_stage_trades: int,
) -> list[str]:
    warnings: list[str] = []
    candidate_count = int(_as_mapping(overall_comparison.get("candidate")).get("trade_count") or 0)
    if candidate_count < min_total_trades:
        warnings.append(f"candidate {row.get('candidate_index')}: total trade count {candidate_count} < {min_total_trades}")
    for item in year_slices:
        if item.get("status") == "insufficient_sample":
            warnings.append(f"candidate {row.get('candidate_index')}: year {item.get('slice_key')} sample below {min_year_trades}")
    for item in market_stage_slices:
        if item.get("status") == "insufficient_sample":
            warnings.append(f"candidate {row.get('candidate_index')}: stage {item.get('slice_key')} sample below {min_stage_trades}")
    if candidate.get("stage_source") != "objective_wide_samples":
        warnings.append(f"candidate {row.get('candidate_index')}: market stage source is {candidate.get('stage_source')}")
    return warnings


def _stage_from_wide_sample(sample: Mapping[str, Any]) -> str | None:
    field_values = _as_mapping(sample.get("field_values"))
    payload = _as_mapping(field_values.get(OBJECTIVE_ENTRY_STAGE_FIELD))
    stage = _optional_str(payload.get("bucket"))
    if stage:
        return _normalise_stage(stage)
    raw = _as_mapping(payload.get("raw"))
    return _normalise_stage(raw.get("stage"))


def _stage_from_runtime_attribution(attribution: Mapping[str, Any]) -> str | None:
    entry = _as_mapping(attribution.get("entry"))
    for factor in _as_sequence(entry.get("factors")):
        factor_map = _as_mapping(factor)
        if factor_map.get("key") != RUNTIME_ENTRY_STAGE_FIELD or factor_map.get("missing") is True:
            continue
        return _normalise_runtime_stage(factor_map.get("value"))
    return None


def _stage_from_trade(trade: Mapping[str, Any]) -> str | None:
    for key in ("entry_stage", OBJECTIVE_ENTRY_STAGE_FIELD, RUNTIME_ENTRY_STAGE_FIELD):
        stage = _normalise_stage(trade.get(key))
        if stage:
            return stage
    return None


def _normalise_runtime_stage(value: Any) -> str | None:
    text = _optional_str(value)
    if text in {"bullish", "bearish", "mixed"}:
        return text
    if text == "not_bullish":
        return "mixed"
    return None


def _normalise_stage(value: Any) -> str | None:
    text = _optional_str(value)
    if text in {"bullish", "bearish", "mixed", "unknown"}:
        return text
    if text == "not_bullish":
        return "mixed"
    return None


def _baseline_run_dir(run_id: str | None, *, report_root: str | Path) -> Path:
    if not run_id:
        return Path(report_root)
    return Path(report_root) / _safe_path_name(run_id)


def _candidate_run_dir(row: Mapping[str, Any], artifacts: Mapping[str, Any]) -> Path:
    output_dir = _optional_str(artifacts.get("output_dir"))
    if output_dir:
        return Path(output_dir)
    run_id = _optional_str(row.get("run_id")) or f"candidate-{row.get('candidate_index')}"
    return Path("reports") / _safe_path_name(run_id)


def _resolve_existing_path(*candidates: Any) -> Path | None:
    for candidate in candidates:
        text = _optional_str(candidate)
        if not text:
            continue
        path = Path(text)
        if path.exists():
            return path
    return None


def _load_matrix(value: Mapping[str, Any] | str | Path) -> tuple[dict[str, Any], Path | None]:
    if isinstance(value, Mapping):
        return dict(value), None
    path = Path(value)
    return _load_json_mapping(path), path


def _load_json_mapping(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{target} must contain a JSON object")
    return payload


def _max_drawdown_proxy(pnl_values: Sequence[float], *, total_entry_value: float) -> float | None:
    if not pnl_values or total_entry_value <= 0:
        return None
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in pnl_values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    return max_drawdown / total_entry_value


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _merged_stage_source(candidate_source: str | None, baseline_source: str | None) -> str:
    if candidate_source == baseline_source:
        return candidate_source or "missing"
    return f"candidate:{candidate_source or 'missing'};baseline:{baseline_source or 'missing'}"


def _stage_label_zh(stage: str) -> str:
    return {
        "bullish": "多头",
        "mixed": "震荡",
        "bearish": "空头",
        "unknown": "未知",
    }.get(stage, stage)


def _classification_label_zh(classification: str) -> str:
    return {
        "stable_favorable": "稳定有利",
        "stable_unfavorable": "稳定不利",
        "market_stage_dependent": "阶段依赖",
        "noise": "噪声",
        "insufficient_sample": "样本不足",
    }.get(str(classification), str(classification))


def _status_summary(value: Any) -> str:
    counts = Counter(str(_as_mapping(item).get("status")) for item in _as_sequence(value))
    if not counts:
        return "-"
    labels = {
        "supports_candidate": "支持",
        "fails_candidate": "失败",
        "mixed": "混合",
        "insufficient_sample": "不足",
    }
    return "; ".join(f"{labels.get(key, key)}:{count}" for key, count in sorted(counts.items()))


def _safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe or "run"


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _escape_cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _format_signed_percent(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    prefix = "+" if number > 0 else ""
    return f"{prefix}{number * 100:.2f}%"
