"""Build a persisted-run environment fit and profit contribution report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    DEFAULT_ENVIRONMENT_FIELDS,
    build_environment_fit_report_from_run_dir,
    render_environment_fit_markdown_zh,
    write_environment_fit_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    report = build_environment_fit_report_from_run_dir(
        run_dir,
        environment_fields=args.environment_field or DEFAULT_ENVIRONMENT_FIELDS,
        min_sample_count=args.min_sample_count,
    )
    json_path, markdown_path = write_environment_fit_report(report, output_dir=args.output_dir)
    payload = {
        "schema": report["schema"],
        "run_id": report["run_id"],
        "source_dir": report["source_dir"],
        "trade_count": report["trade_count"],
        "contribution_available_count": report["contribution_available_count"],
        "single_factor_summary_count": len(report["single_factor_summaries"]),
        "combination_summary_count": len(report["combination_summaries"]),
        "artifacts": {
            "environment_fit_json_path": str(json_path),
            "environment_fit_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_environment_fit_markdown_zh(report))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a persisted-run environment fit report")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument(
        "--environment-field",
        action="append",
        default=None,
        help="Repeatable entry environment field. Defaults to the built-in market/industry/symbol factors.",
    )
    parser.add_argument("--min-sample-count", type=int, default=5)
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run dir")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir is not None:
        return Path(args.run_dir)
    if args.run_id is not None:
        return Path(args.report_root) / args.run_id
    raise ValueError("--run-dir or --run-id is required")


if __name__ == "__main__":
    raise SystemExit(main())
