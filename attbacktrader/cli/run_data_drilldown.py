"""Drill down into one trade, opportunity, or add-on sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    REVIEW_SAMPLE_KINDS,
    build_run_data_drilldown,
    render_run_data_drilldown_markdown_zh,
    write_run_data_drilldown,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    drilldown = build_run_data_drilldown(
        run_dir,
        kind=args.kind,
        sample_index=args.sample_index,
        trade_index=args.trade_index,
        context_limit=args.context_limit,
    )
    json_path, markdown_path = write_run_data_drilldown(drilldown, output_dir=args.output_dir)
    payload = {
        "schema": drilldown["schema"],
        "run_id": drilldown["run_id"],
        "source_dir": drilldown["source_dir"],
        "sample_kind": drilldown["sample_kind"],
        "sample_id": drilldown["sample_id"],
        "summary": drilldown["summary"],
        "artifacts": {
            "run_data_drilldown_json_path": str(json_path),
            "run_data_drilldown_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_run_data_drilldown_markdown_zh(drilldown))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drill down into one persisted run sample")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument("--kind", choices=REVIEW_SAMPLE_KINDS, required=True)
    parser.add_argument("--trade-index", type=int, default=None, help="trade_index for trade samples")
    parser.add_argument("--sample-index", type=int, default=None, help="sample_index for opportunity/add_on samples")
    parser.add_argument("--context-limit", type=int, default=20)
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
