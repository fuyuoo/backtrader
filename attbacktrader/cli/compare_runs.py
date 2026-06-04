"""Compare persisted attbacktrader run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_comparison,
    render_run_comparison_markdown_zh,
    run_comparison_to_jsonable,
    safe_comparison_dir_name,
    write_run_comparison,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dirs = tuple(_run_dir(args.report_root, run_id) for run_id in args.run_id)
    comparison = build_run_comparison(run_dirs)

    payload = run_comparison_to_jsonable(comparison)
    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(args.report_root) / safe_comparison_dir_name(tuple(row.run_id for row in comparison.rows))

    json_path, markdown_path = write_run_comparison(comparison, output_dir=output_dir)
    payload["artifacts"] = {
        "comparison_json_path": str(json_path),
        "comparison_chinese_markdown_path": str(markdown_path),
    }
    if args.print_markdown:
        print(render_run_comparison_markdown_zh(comparison))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare persisted attbacktrader run artifacts")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", action="append", required=True, help="Run id under report root; repeat for each run")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _run_dir(report_root: str | Path, run_id: str) -> Path:
    path = Path(run_id)
    if path.exists() and path.is_dir():
        return path
    return Path(report_root) / run_id


if __name__ == "__main__":
    raise SystemExit(main())
