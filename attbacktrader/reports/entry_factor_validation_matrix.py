"""Aggregate Stage 1 entry-factor validation runs into a ranking matrix."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ENTRY_FACTOR_VALIDATION_MATRIX_SCHEMA = "attbacktrader.entry_factor_validation_matrix.v1"


def build_entry_factor_validation_matrix(
    validation_records_or_paths: Sequence[Mapping[str, Any] | str | Path],
    *,
    baseline_metrics: Mapping[str, Any] | None = None,
    baseline_run_id: str | None = None,
    source_manifest: str | Path | None = None,
) -> dict[str, Any]:
    """Build a Stage 1 real-validation matrix from executed single-factor records."""

    records = [_load_record(record) for record in validation_records_or_paths]
    baseline = dict(baseline_metrics or {})
    rows = [
        _matrix_row(record, baseline_metrics=baseline)
        for record in records
    ]
    ranked_rows = sorted(rows, key=lambda row: _number(row.get("validation_score")), reverse=True)

    return {
        "schema": ENTRY_FACTOR_VALIDATION_MATRIX_SCHEMA,
        "source_manifest": str(source_manifest) if source_manifest is not None else None,
        "baseline": {
            "run_id": baseline_run_id,
            "metrics": baseline,
        },
        "record_count": len(rows),
        "status_counts": dict(Counter(str(row.get("status")) for row in rows)),
        "rows": rows,
        "rankings": {
            "by_validation_score": ranked_rows,
            "supports_candidate": [row for row in ranked_rows if row.get("status") == "supports_candidate"],
            "mixed": [row for row in ranked_rows if row.get("status") == "mixed"],
            "rejects_candidate": [row for row in ranked_rows if row.get("status") == "rejects_candidate"],
            "invalid": [row for row in ranked_rows if row.get("status") == "invalid"],
        },
        "scoring": {
            "formula": (
                "100*return_delta_or_return - 50*drawdown_delta_or_drawdown "
                "+ 20*win_rate_delta_or_edge + 2*profit_loss_ratio_delta_or_edge "
                "+ 50*average_benchmark_excess_return + trade_count_reliability + evidence_penalty"
            ),
            "thresholds": {
                "supports_candidate": "score >= 1 and trade_count > 0 and evidence ok",
                "rejects_candidate": "score <= -1 and trade_count > 0 and evidence ok",
                "mixed": "-1 < score < 1",
                "invalid": "trade_count <= 0 or evidence not ok",
            },
        },
    }


def render_entry_factor_validation_matrix_markdown_zh(matrix: Mapping[str, Any]) -> str:
    """Render the Stage 1 entry-factor validation matrix in Chinese Markdown."""

    baseline = _as_mapping(matrix.get("baseline"))
    lines = [
        "# 入场单因子真实验证矩阵",
        "",
        f"- schema: `{matrix.get('schema')}`",
        f"- source_manifest: `{matrix.get('source_manifest')}`",
        f"- baseline_run_id: `{baseline.get('run_id')}`",
        f"- record_count: `{matrix.get('record_count')}`",
        "",
        "## 排名",
        "",
        "| 排名 | 状态 | 序号 | 方向 | 动作 | 因子 | 值 | 收益 | 回撤 | 胜率 | 盈亏比 | 交易数 | 分数 |",
        "|---:|---|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(_as_sequence(_as_mapping(matrix.get("rankings")).get("by_validation_score")), start=1):
        item = _as_mapping(row)
        metrics = _as_mapping(item.get("metrics"))
        lines.append(
            "| "
            f"{rank} | "
            f"{_escape_cell(item.get('status'))} | "
            f"{item.get('candidate_index')} | "
            f"{_escape_cell(item.get('direction'))} | "
            f"{_escape_cell(item.get('action'))} | "
            f"`{_escape_cell(item.get('field_key'))}` | "
            f"{_escape_cell(item.get('value_label_zh') or item.get('value'))} | "
            f"{_format_percent(metrics.get('cumulative_return'))} | "
            f"{_format_percent(metrics.get('max_drawdown'))} | "
            f"{_format_percent(metrics.get('win_rate'))} | "
            f"{_format_number(metrics.get('profit_loss_ratio'))} | "
            f"{_format_int(metrics.get('trade_count'))} | "
            f"{_format_number(item.get('validation_score'))} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_entry_factor_validation_matrix(
    matrix: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, dict[str, Any]]:
    """Write Stage 1 matrix JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "entry_factor_validation_matrix.json"
    markdown_path = output_path / "entry_factor_validation_matrix.zh.md"

    payload = _jsonable(matrix)
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["matrix_json"] = str(json_path)
    artifacts["matrix_markdown_zh"] = str(markdown_path)
    payload["artifacts"] = artifacts

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_factor_validation_matrix_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def _matrix_row(record: Mapping[str, Any], *, baseline_metrics: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _as_mapping(record.get("candidate"))
    run = _as_mapping(record.get("run"))
    summary = _as_mapping(record.get("run_summary"))
    metrics = _core_metrics(_as_mapping(summary.get("metrics")))
    deltas = _metric_deltas(metrics, baseline_metrics)
    benchmarks = [_as_mapping(benchmark) for benchmark in _as_sequence(summary.get("benchmarks"))]
    average_excess_return = _average(
        _number_or_none(benchmark.get("excess_return"))
        for benchmark in benchmarks
    )
    evidence = _as_mapping(summary.get("evidence"))
    score_components = _score_components(
        metrics,
        deltas=deltas,
        average_excess_return=average_excess_return,
        evidence=evidence,
    )
    validation_score = sum(score_components.values())
    status = _status(
        validation_score,
        trade_count=metrics.get("trade_count"),
        evidence=evidence,
    )

    return {
        "candidate_index": candidate.get("candidate_index"),
        "candidate_rank": candidate.get("candidate_rank"),
        "direction": candidate.get("direction"),
        "action": candidate.get("action"),
        "field_key": candidate.get("field_key"),
        "field_label_zh": candidate.get("field_label_zh"),
        "value": candidate.get("value"),
        "value_label_zh": candidate.get("value_label_zh"),
        "sample_count": candidate.get("sample_count"),
        "factor_quality_score": candidate.get("factor_quality_score"),
        "run_id": run.get("id") or candidate.get("run_id"),
        "metrics": metrics,
        "deltas": deltas,
        "benchmark_excess": {
            "average": average_excess_return,
            "items": [
                {
                    "symbol": benchmark.get("symbol"),
                    "excess_return": benchmark.get("excess_return"),
                }
                for benchmark in benchmarks
            ],
        },
        "evidence": evidence,
        "score_components": score_components,
        "validation_score": validation_score,
        "status": status,
        "artifacts": _as_mapping(record.get("artifacts")),
    }


def _core_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "cumulative_return",
        "max_drawdown",
        "trade_count",
        "win_rate",
        "profit_loss_ratio",
        "average_win",
        "average_loss",
    )
    return {key: metrics.get(key) for key in keys if key in metrics}


def _metric_deltas(metrics: Mapping[str, Any], baseline_metrics: Mapping[str, Any]) -> dict[str, Any]:
    if not baseline_metrics:
        return {}
    result: dict[str, Any] = {}
    for key in ("cumulative_return", "max_drawdown", "trade_count", "win_rate", "profit_loss_ratio"):
        value = _number_or_none(metrics.get(key))
        baseline = _number_or_none(baseline_metrics.get(key))
        if value is not None and baseline is not None:
            result[key] = value - baseline
    return result


def _score_components(
    metrics: Mapping[str, Any],
    *,
    deltas: Mapping[str, Any],
    average_excess_return: float | None,
    evidence: Mapping[str, Any],
) -> dict[str, float]:
    return_basis = _number_or_none(deltas.get("cumulative_return"))
    if return_basis is None:
        return_basis = _number_or_none(metrics.get("cumulative_return")) or 0.0
    drawdown_basis = _number_or_none(deltas.get("max_drawdown"))
    if drawdown_basis is None:
        drawdown_basis = _number_or_none(metrics.get("max_drawdown")) or 0.0
    win_basis = _number_or_none(deltas.get("win_rate"))
    if win_basis is None:
        win_rate = _number_or_none(metrics.get("win_rate"))
        win_basis = (win_rate - 0.5) if win_rate is not None else 0.0
    profit_loss_basis = _number_or_none(deltas.get("profit_loss_ratio"))
    if profit_loss_basis is None:
        profit_loss_ratio = _number_or_none(metrics.get("profit_loss_ratio"))
        profit_loss_basis = min(profit_loss_ratio, 3.0) - 1.0 if profit_loss_ratio is not None else 0.0
    trade_count = _number_or_none(metrics.get("trade_count")) or 0.0

    return {
        "return": 100.0 * return_basis,
        "drawdown": -50.0 * drawdown_basis,
        "win_rate": 20.0 * win_basis,
        "profit_loss_ratio": 2.0 * profit_loss_basis,
        "benchmark_excess": 50.0 * (average_excess_return or 0.0),
        "trade_count_reliability": min(max(trade_count, 0.0) / 200.0, 1.0),
        "evidence_penalty": 0.0 if evidence.get("status") in {None, "ok"} else -5.0,
    }


def _status(score: float, *, trade_count: Any, evidence: Mapping[str, Any]) -> str:
    if (_number_or_none(trade_count) or 0.0) <= 0 or evidence.get("status") not in {None, "ok"}:
        return "invalid"
    if score >= 1.0:
        return "supports_candidate"
    if score <= -1.0:
        return "rejects_candidate"
    return "mixed"


def _load_record(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _average(values: Sequence[float | None] | Any) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float:
    return _number_or_none(value) or 0.0


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _escape_cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _format_number(value: object) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "-"


def _format_int(value: object) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "-"


def _format_percent(value: object) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"
