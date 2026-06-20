"""Build overall attribution summary report for a persisted run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_attribution_summary,
    render_attribution_summary_markdown_zh,
    write_attribution_summary,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    report = build_attribution_summary(run_dir, top_n=args.top_n)
    json_path, markdown_path = write_attribution_summary(report, output_dir=args.output_dir)
    payload = {
        "schema": report["schema"],
        "run_id": report["run_id"],
        "source_dir": report["source_dir"],
        "summary_card_count": len(report["summary_cards"]),
        "matrix_focus_count": len(report["matrix_focus"]),
        "artifacts": {
            "attribution_summary_json_path": str(json_path),
            "attribution_summary_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_attribution_summary_markdown_zh(report))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build overall attribution summary report for a persisted run")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument("--top-n", type=int, default=5)
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
