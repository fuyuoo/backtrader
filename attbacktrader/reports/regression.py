"""Validate persisted real-run artifacts against accepted metric baselines."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


MetricCheckStatus = Literal["ok", "failed", "missing"]
_KNOWN_REJECTION_REASONS = (
    "BOARD_LOT_TOO_SMALL",
    "CASH_NOT_ENOUGH",
    "LIMIT_DOWN_SELL_BLOCKED",
    "LIMIT_UP_BUY_BLOCKED",
    "SUSPENDED",
    "T_PLUS_ONE_SELL_BLOCKED",
)


@dataclass(frozen=True)
class RunRegressionMetricCheck:
    run_id: str
    metric: str
    expected: Any
    actual: Any
    tolerance: float | None
    status: MetricCheckStatus


@dataclass(frozen=True)
class RunRegressionReport:
    status: Literal["ok", "failed"]
    baseline_path: Path | None
    run_count: int
    check_count: int
    failed_count: int
    checks: tuple[RunRegressionMetricCheck, ...]


def load_run_regression_baseline(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_ids_from_regression_baseline(baseline: Mapping[str, Any]) -> tuple[str, ...]:
    runs = baseline.get("runs")
    if isinstance(runs, Mapping):
        return tuple(str(run_id) for run_id in runs)
    if isinstance(runs, list):
        return tuple(str(run.get("run_id")) for run in runs if isinstance(run, Mapping) and run.get("run_id"))
    return ()


def build_run_regression_report(
    run_dirs: Sequence[str | Path],
    baseline: Mapping[str, Any],
    *,
    baseline_path: str | Path | None = None,
) -> RunRegressionReport:
    baseline_runs = _baseline_runs(baseline)
    run_dir_by_id = {_run_id_from_dir(Path(run_dir)): Path(run_dir) for run_dir in run_dirs}
    checks: list[RunRegressionMetricCheck] = []

    for run_id, expectation in baseline_runs.items():
        run_dir = run_dir_by_id.get(run_id)
        if run_dir is None:
            checks.append(
                RunRegressionMetricCheck(
                    run_id=run_id,
                    metric="run_artifact",
                    expected="present",
                    actual=None,
                    tolerance=None,
                    status="missing",
                )
            )
            continue

        actual_metrics = _run_metrics(run_dir)
        expected_metrics = _mapping(expectation.get("metrics"))
        tolerances = _mapping(expectation.get("tolerances"))
        for metric, expected in expected_metrics.items():
            tolerance = _optional_float(tolerances.get(metric))
            actual = actual_metrics.get(metric)
            checks.append(
                RunRegressionMetricCheck(
                    run_id=run_id,
                    metric=str(metric),
                    expected=expected,
                    actual=actual,
                    tolerance=tolerance,
                    status=_metric_status(expected, actual, tolerance),
                )
            )

    failed_count = sum(1 for check in checks if check.status != "ok")
    return RunRegressionReport(
        status="ok" if failed_count == 0 else "failed",
        baseline_path=Path(baseline_path) if baseline_path is not None else None,
        run_count=len(baseline_runs),
        check_count=len(checks),
        failed_count=failed_count,
        checks=tuple(checks),
    )


def write_run_regression_report(
    report: RunRegressionReport,
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "run_regression.json"
    markdown_path = output_path / "run_regression.zh.md"
    json_path.write_text(json.dumps(run_regression_to_jsonable(report), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_run_regression_markdown_zh(report), encoding="utf-8")
    return json_path, markdown_path


def run_regression_to_jsonable(report: RunRegressionReport) -> dict[str, Any]:
    return {
        "status": report.status,
        "baseline_path": str(report.baseline_path) if report.baseline_path is not None else None,
        "run_count": report.run_count,
        "check_count": report.check_count,
        "failed_count": report.failed_count,
        "checks": [
            {
                "run_id": check.run_id,
                "metric": check.metric,
                "expected": check.expected,
                "actual": check.actual,
                "tolerance": check.tolerance,
                "status": check.status,
            }
            for check in report.checks
        ],
    }


def render_run_regression_markdown_zh(report: RunRegressionReport) -> str:
    lines = [
        "# 真实 Run 回归校验",
        "",
        f"状态：{report.status}",
        f"基线：{report.baseline_path or '-'}",
        f"运行数：{report.run_count}",
        f"检查数：{report.check_count}",
        f"失败数：{report.failed_count}",
        "",
        "| 运行 | 指标 | 期望 | 实际 | 容差 | 状态 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for check in report.checks:
        lines.append(
            "| "
            f"{check.run_id} | "
            f"{check.metric} | "
            f"{_format_value(check.expected)} | "
            f"{_format_value(check.actual)} | "
            f"{_format_value(check.tolerance)} | "
            f"{check.status} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _baseline_runs(baseline: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    runs = baseline.get("runs")
    if isinstance(runs, Mapping):
        return {str(run_id): _mapping(expectation) for run_id, expectation in runs.items()}
    if isinstance(runs, list):
        result: dict[str, Mapping[str, Any]] = {}
        for run in runs:
            if not isinstance(run, Mapping) or not run.get("run_id"):
                continue
            result[str(run["run_id"])] = run
        return result
    return {}


def _run_metrics(run_dir: Path) -> dict[str, Any]:
    report = _read_json(run_dir / "report.json")
    diagnostics = _read_json(run_dir / "result_diagnostics.json")
    signal_audit = _read_json(run_dir / "signal_audit.json")
    validation = _read_json(run_dir / "evidence_validation.json")

    returns = _mapping(report.get("returns"))
    risk = _mapping(report.get("risk"))
    quality = _mapping(report.get("trade_quality"))
    execution_costs = _mapping(report.get("execution_costs"))
    rejection_reason_counts = _rejection_reason_counts(diagnostics)

    metrics = {
        "evidence_validation_status": validation.get("status"),
        "evidence_validation_error_count": validation.get("error_count"),
        "evidence_validation_warning_count": validation.get("warning_count"),
        "final_value": _optional_float(returns.get("final_equity")),
        "cumulative_return": _optional_float(returns.get("cumulative_return")),
        "max_drawdown": _optional_float(risk.get("max_drawdown")),
        "trade_count": quality.get("trade_count"),
        "win_rate": _optional_float(quality.get("win_rate")),
        "profit_loss_ratio": _optional_float(quality.get("profit_loss_ratio")),
        "completed_order_count": execution_costs.get("completed_count"),
        "execution_rejection_count": sum(rejection_reason_counts.values()),
        "entry_filter_count": sum(
            1
            for intent in signal_audit
            if isinstance(intent, Mapping) and intent.get("reason_code") == "ENTRY_ATTRIBUTION_FILTERED"
        ),
        "add_on_signal_count": diagnostics.get("portfolio_add_on_signal_count"),
    }
    for reason in _KNOWN_REJECTION_REASONS:
        metrics[f"rejection_reason_count.{reason}"] = rejection_reason_counts.get(reason, 0)
    for reason, count in rejection_reason_counts.items():
        metrics[f"rejection_reason_count.{reason}"] = count
    return metrics


def _rejection_reason_counts(diagnostics: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    symbols = diagnostics.get("symbols")
    if not isinstance(symbols, list):
        return counts
    for symbol in symbols:
        if not isinstance(symbol, Mapping):
            continue
        rows = symbol.get("execution_rejection_counts")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            reason = str(row.get("reason") or "")
            if not reason:
                continue
            counts[reason] = counts.get(reason, 0) + int(row.get("count") or 0)
    return counts


def _run_id_from_dir(run_dir: Path) -> str:
    run_plan_path = run_dir / "run_plan.json"
    if not run_plan_path.exists():
        return run_dir.name
    run_plan = _read_json(run_plan_path)
    run_config = _mapping(run_plan.get("run"))
    return str(run_config.get("id") or run_dir.name)


def _metric_status(expected: Any, actual: Any, tolerance: float | None) -> MetricCheckStatus:
    if actual is None:
        return "missing"
    if _is_number(expected) and _is_number(actual):
        allowed = tolerance if tolerance is not None else 0.0
        return "ok" if abs(float(actual) - float(expected)) <= allowed else "failed"
    return "ok" if actual == expected else "failed"


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"missing run artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)
