"""Check new entry-score runner artifacts against the old formal result."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_OLD_FORMAL_DIR = Path("reports/ew-seed-only-v2-formal-backtest-hs300-only-2013-2025")
DEFAULT_NEW_RUN_DIR = Path(
    "reports/ew-seed-only-v2-entry-score-runner-warmup-2006-filter-2013-2025-replay-cash-10m"
)
DEFAULT_STRATEGY_ID = "ew_seed_only_v2"
DEFAULT_MAX_NEW_POSITIONS_PER_DAY = 5
DEFAULT_MAX_HOLDING_COUNT = 20
DEFAULT_EXPECTED_CONTRACT = {
    "enter_event_count": 11061,
    "matched_enter_score_count": 11004,
    "missing_enter_score_count": 57,
    "score_keys_not_in_enter_events_count": 0,
}
METRIC_KEYS = (
    "cumulative_return",
    "annualized_return",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "trade_count",
    "closed_trade_count",
    "win_rate",
    "profit_factor",
    "average_trade_return",
    "median_trade_return",
    "average_win_return",
    "average_loss_return",
    "maximum_win_trade",
    "maximum_loss_trade",
    "average_holding_count",
    "maximum_holding_count",
    "average_cash_ratio",
    "average_exposure",
    "turnover",
)
EQUITY_COLUMNS = (
    "cash",
    "position_value",
    "total_value",
    "drawdown",
    "holding_count",
    "exposure",
    "cash_ratio",
)


@dataclass(frozen=True)
class ParityCheck:
    name: str
    expected: Any
    actual: Any
    status: str
    tolerance: float | None = None


@dataclass(frozen=True)
class ParityReport:
    status: str
    old_formal_dir: Path
    new_run_dir: Path
    check_count: int
    failed_count: int
    checks: tuple[ParityCheck, ...]


def build_entry_score_formal_parity_report(
    *,
    old_formal_dir: str | Path = DEFAULT_OLD_FORMAL_DIR,
    new_run_dir: str | Path = DEFAULT_NEW_RUN_DIR,
    strategy_id: str = DEFAULT_STRATEGY_ID,
    max_new_positions_per_day: int = DEFAULT_MAX_NEW_POSITIONS_PER_DAY,
    max_holding_count: int = DEFAULT_MAX_HOLDING_COUNT,
    abs_tol: float = 1e-12,
) -> ParityReport:
    old_dir = Path(old_formal_dir)
    new_dir = Path(new_run_dir)
    checks: list[ParityCheck] = []

    contract = _read_json(new_dir / "entry_score_contract.json")
    summary = _read_json(new_dir / "entry_score_replay_summary.json")
    new_metrics = _mapping(summary.get("metrics"))
    old_metric = _old_metric_row(
        old_dir,
        strategy_id=strategy_id,
        max_new_positions_per_day=max_new_positions_per_day,
        max_holding_count=max_holding_count,
    )

    for key, expected in DEFAULT_EXPECTED_CONTRACT.items():
        checks.append(_check_equal(f"contract.{key}", expected, contract.get(key)))
    checks.append(
        _check_equal(
            "summary.precomputed_score_contract",
            contract,
            summary.get("precomputed_score_contract"),
        )
    )

    for key in METRIC_KEYS:
        checks.append(_check_metric(f"metrics.{key}", old_metric.get(key), new_metrics.get(key), abs_tol))

    old_selected = _old_parameter_rows(old_dir / "formal_backtest_selected_entries.parquet", strategy_id, max_new_positions_per_day, max_holding_count)
    new_selected = pd.read_parquet(new_dir / "entry_score_selected_entries.parquet")
    _append_keyset_checks(checks, "selected", old_selected, new_selected)

    old_blocked = _old_parameter_rows(old_dir / "formal_backtest_blocked_entries.parquet", strategy_id, max_new_positions_per_day, max_holding_count)
    new_blocked = pd.read_parquet(new_dir / "entry_score_blocked_entries.parquet")
    _append_keyset_checks(checks, "blocked", old_blocked, new_blocked)

    old_equity = _old_parameter_rows(old_dir / "formal_backtest_equity_curves.parquet", strategy_id, max_new_positions_per_day, max_holding_count)
    new_equity = pd.read_parquet(new_dir / "entry_score_equity_curve.parquet")
    _append_equity_checks(checks, old_equity, new_equity, abs_tol)

    failed_count = sum(1 for check in checks if check.status != "ok")
    return ParityReport(
        status="ok" if failed_count == 0 else "failed",
        old_formal_dir=old_dir,
        new_run_dir=new_dir,
        check_count=len(checks),
        failed_count=failed_count,
        checks=tuple(checks),
    )


def write_entry_score_formal_parity_report(report: ParityReport, *, output_dir: str | Path) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "entry_score_formal_parity.json"
    markdown_path = output_path / "entry_score_formal_parity.zh.md"
    json_path.write_text(json.dumps(parity_report_to_jsonable(report), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_score_formal_parity_markdown_zh(report), encoding="utf-8")
    return json_path, markdown_path


def parity_report_to_jsonable(report: ParityReport) -> dict[str, Any]:
    return {
        "status": report.status,
        "old_formal_dir": str(report.old_formal_dir),
        "new_run_dir": str(report.new_run_dir),
        "check_count": report.check_count,
        "failed_count": report.failed_count,
        "checks": [
            {
                "name": check.name,
                "expected": _jsonable(check.expected),
                "actual": _jsonable(check.actual),
                "tolerance": check.tolerance,
                "status": check.status,
            }
            for check in report.checks
        ],
    }


def render_entry_score_formal_parity_markdown_zh(report: ParityReport) -> str:
    lines = [
        "# Entry Score Formal Parity 回归检查",
        "",
        f"状态：{report.status}",
        f"旧 formal 目录：`{report.old_formal_dir}`",
        f"新 runner 目录：`{report.new_run_dir}`",
        f"检查数：{report.check_count}",
        f"失败数：{report.failed_count}",
        "",
        "| 检查项 | 期望 | 实际 | 容差 | 状态 |",
        "|---|---:|---:|---:|---|",
    ]
    for check in report.checks:
        lines.append(
            "| "
            f"{check.name} | "
            f"{_format_value(check.expected)} | "
            f"{_format_value(check.actual)} | "
            f"{_format_value(check.tolerance)} | "
            f"{check.status} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_entry_score_formal_parity_report(
        old_formal_dir=args.old_formal_dir,
        new_run_dir=args.new_run_dir,
        strategy_id=args.strategy_id,
        max_new_positions_per_day=args.max_new_positions_per_day,
        max_holding_count=args.max_holding_count,
        abs_tol=args.abs_tol,
    )
    json_path, markdown_path = write_entry_score_formal_parity_report(report, output_dir=args.output_dir or args.new_run_dir)
    print(f"status={report.status} checks={report.check_count} failed={report.failed_count}")
    print(f"json={json_path}")
    print(f"markdown={markdown_path}")
    return 0 if report.status == "ok" else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check entry-score runner formal-result parity")
    parser.add_argument("--old-formal-dir", type=Path, default=DEFAULT_OLD_FORMAL_DIR)
    parser.add_argument("--new-run-dir", type=Path, default=DEFAULT_NEW_RUN_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--strategy-id", default=DEFAULT_STRATEGY_ID)
    parser.add_argument("--max-new-positions-per-day", type=int, default=DEFAULT_MAX_NEW_POSITIONS_PER_DAY)
    parser.add_argument("--max-holding-count", type=int, default=DEFAULT_MAX_HOLDING_COUNT)
    parser.add_argument("--abs-tol", type=float, default=1e-12)
    return parser.parse_args(argv)


def _old_metric_row(
    old_dir: Path,
    *,
    strategy_id: str,
    max_new_positions_per_day: int,
    max_holding_count: int,
) -> dict[str, Any]:
    frame = pd.read_csv(old_dir / "formal_backtest_metrics.csv")
    rows = _filter_parameter_rows(frame, strategy_id, max_new_positions_per_day, max_holding_count)
    if len(rows) != 1:
        raise ValueError(f"expected exactly one formal metric row, got {len(rows)}")
    return rows.iloc[0].to_dict()


def _old_parameter_rows(
    path: Path,
    strategy_id: str,
    max_new_positions_per_day: int,
    max_holding_count: int,
) -> pd.DataFrame:
    return _filter_parameter_rows(
        pd.read_parquet(path),
        strategy_id,
        max_new_positions_per_day,
        max_holding_count,
    )


def _filter_parameter_rows(
    frame: pd.DataFrame,
    strategy_id: str,
    max_new_positions_per_day: int,
    max_holding_count: int,
) -> pd.DataFrame:
    return frame[
        (frame["strategy_id"] == strategy_id)
        & (frame["max_new_positions_per_day"] == max_new_positions_per_day)
        & (frame["max_holding_count"] == max_holding_count)
    ].copy()


def _append_keyset_checks(checks: list[ParityCheck], name: str, old_rows: pd.DataFrame, new_rows: pd.DataFrame) -> None:
    old_keys = _entry_keyset(old_rows)
    new_keys = _entry_keyset(new_rows)
    checks.append(_check_equal(f"{name}.row_count", len(old_rows), len(new_rows)))
    checks.append(_check_equal(f"{name}.key_intersection_count", len(old_keys), len(old_keys & new_keys)))
    checks.append(_check_equal(f"{name}.old_only_count", 0, len(old_keys - new_keys)))
    checks.append(_check_equal(f"{name}.new_only_count", 0, len(new_keys - old_keys)))


def _append_equity_checks(checks: list[ParityCheck], old_rows: pd.DataFrame, new_rows: pd.DataFrame, abs_tol: float) -> None:
    old_equity = old_rows.sort_values("trade_date").reset_index(drop=True)
    new_equity = new_rows.sort_values("trade_date").reset_index(drop=True)
    checks.append(_check_equal("equity.row_count", len(old_equity), len(new_equity)))
    if len(old_equity) != len(new_equity):
        return
    old_dates = pd.to_datetime(old_equity["trade_date"]).dt.date.astype(str)
    new_dates = pd.to_datetime(new_equity["trade_date"]).dt.date.astype(str)
    checks.append(_check_equal("equity.date_mismatch_count", 0, int((old_dates != new_dates).sum())))
    for column in EQUITY_COLUMNS:
        if column not in old_equity.columns or column not in new_equity.columns:
            checks.append(_check_equal(f"equity.{column}.column_present", True, False))
            continue
        max_diff = float((old_equity[column].astype(float) - new_equity[column].astype(float)).abs().max())
        checks.append(_check_metric(f"equity.{column}.max_abs_diff", 0.0, max_diff, abs_tol))


def _entry_keyset(frame: pd.DataFrame) -> set[tuple[str, str]]:
    return {
        (str(row.symbol), str(pd.Timestamp(row.trade_date).date()))
        for row in frame.itertuples(index=False)
    }


def _check_equal(name: str, expected: Any, actual: Any) -> ParityCheck:
    return ParityCheck(
        name=name,
        expected=expected,
        actual=actual,
        tolerance=None,
        status="ok" if expected == actual else "failed",
    )


def _check_metric(name: str, expected: Any, actual: Any, tolerance: float) -> ParityCheck:
    if _is_number(expected) and _is_number(actual):
        status = "ok" if math.isclose(float(expected), float(actual), rel_tol=0.0, abs_tol=tolerance) else "failed"
    else:
        status = "ok" if expected == actual else "failed"
    return ParityCheck(name=name, expected=expected, actual=actual, tolerance=tolerance, status=status)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    return value


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.12g}"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
