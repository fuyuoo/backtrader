"""Summarize market-type validation run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_market_type_summary,
    render_market_type_summary_markdown_zh,
    safe_market_type_summary_dir_name,
    write_market_type_summary,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    summary = build_market_type_summary(
        args.manifest,
        report_root=args.report_root,
        min_segment_trades=args.min_segment_trades,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args)
    json_path, markdown_path = write_market_type_summary(summary, output_dir=output_dir)
    payload = {
        "schema": summary["schema"],
        "manifest_path": summary["manifest_path"],
        "market_type_count": summary["market_type_count"],
        "segment_count": summary["segment_count"],
        "validation_warning_count": len(summary["validation_warnings"]),
        "artifacts": {
            "market_type_summary_json_path": str(json_path),
            "market_type_summary_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_market_type_summary_markdown_zh(summary))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize market-type validation run artifacts")
    parser.add_argument("--manifest", required=True, help="market_segment_run_manifest.json")
    parser.add_argument("--report-root", default="reports", help="Root containing run artifact directories")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--min-segment-trades", type=int, default=5)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _default_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.report_root) / safe_market_type_summary_dir_name(args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
