"""Validate persisted run artifacts against an accepted regression baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_regression_report,
    load_run_regression_baseline,
    render_run_regression_markdown_zh,
    run_ids_from_regression_baseline,
    run_regression_to_jsonable,
    write_run_regression_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    baseline_path = Path(args.baseline)
    baseline = load_run_regression_baseline(baseline_path)
    run_ids = tuple(args.run_id or run_ids_from_regression_baseline(baseline))
    run_dirs = tuple(_run_dir(args.report_root, run_id) for run_id in run_ids)

    report = build_run_regression_report(run_dirs, baseline, baseline_path=baseline_path)
    payload = run_regression_to_jsonable(report)

    if args.output_dir is not None:
        json_path, markdown_path = write_run_regression_report(report, output_dir=args.output_dir)
        payload["artifacts"] = {
            "run_regression_json_path": str(json_path),
            "run_regression_chinese_markdown_path": str(markdown_path),
        }

    if args.print_markdown:
        print(render_run_regression_markdown_zh(report))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.status == "ok" else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate persisted run artifacts against a regression baseline")
    parser.add_argument("--baseline", default="examples/real-run-regression-baseline.json")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", action="append", help="Run id under report root; defaults to all baseline runs")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


def _run_dir(report_root: str | Path, run_id: str) -> Path:
    path = Path(run_id)
    if path.exists() and path.is_dir():
        return path
    return Path(report_root) / run_id


if __name__ == "__main__":
    raise SystemExit(main())
