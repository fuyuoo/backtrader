"""Compare persisted environment-fit reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_environment_fit_comparison,
    render_environment_fit_comparison_markdown_zh,
    safe_environment_fit_comparison_dir_name,
    write_environment_fit_comparison,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sources = _resolve_sources(args)
    comparison = build_environment_fit_comparison(
        sources,
        common_limit=args.common_limit,
        sample_ref_limit=args.sample_ref_limit,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args.report_root, comparison)
    json_path, markdown_path = write_environment_fit_comparison(comparison, output_dir=output_dir)

    payload = {
        "schema": comparison["schema"],
        "baseline_run_id": comparison["baseline_run_id"],
        "run_ids": comparison["run_ids"],
        "source_count": comparison["source_count"],
        "common_environment_count": comparison["common_environment_count"],
        "drill_down_sample_count": comparison["drill_down_sample_count"],
        "best_environment_statuses": [
            {
                "criterion": check.get("criterion"),
                "status": check.get("status"),
                "status_zh": check.get("status_zh"),
            }
            for check in comparison["best_environment_stability"]
        ],
        "artifacts": {
            "environment_fit_comparison_json_path": str(json_path),
            "environment_fit_comparison_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_environment_fit_comparison_markdown_zh(comparison))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare persisted environment-fit reports")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", action="append", default=None, help="Run id under report root; repeat for each run")
    parser.add_argument("--run-dir", action="append", default=None, help="Run artifact directory; repeat for each run")
    parser.add_argument(
        "--environment-fit",
        action="append",
        default=None,
        help="Path to environment_fit.json; repeat for each report",
    )
    parser.add_argument("--common-limit", type=int, default=20, help="Maximum common environment rows in output")
    parser.add_argument("--sample-ref-limit", type=int, default=3, help="Representative trade refs per best environment")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _resolve_sources(args: argparse.Namespace) -> list[Path]:
    sources: list[Path] = []
    for path in args.environment_fit or []:
        sources.append(Path(path))
    for path in args.run_dir or []:
        sources.append(Path(path))
    for run_id in args.run_id or []:
        sources.append(Path(args.report_root) / run_id)
    if len(sources) < 2:
        raise ValueError("at least two --environment-fit, --run-dir, or --run-id values are required")
    return sources


def _default_output_dir(report_root: str | Path, comparison: dict) -> Path:
    return Path(report_root) / safe_environment_fit_comparison_dir_name(tuple(str(run_id) for run_id in comparison["run_ids"]))


if __name__ == "__main__":
    raise SystemExit(main())
