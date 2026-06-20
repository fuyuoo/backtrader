"""Build a compact persisted-run attribution summary for AI review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_data_attribution_summary,
    render_run_data_attribution_summary_markdown_zh,
    write_run_data_attribution_summary,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    summary = build_run_data_attribution_summary(
        run_dir,
        min_sample_count=args.min_sample_count,
        top_n=args.top_n,
        combination_size=args.combination_size,
    )
    json_path, markdown_path = write_run_data_attribution_summary(summary, output_dir=args.output_dir)
    payload = {
        "schema": summary["schema"],
        "run_id": summary["run_id"],
        "source_dir": summary["source_dir"],
        "trade_count": summary["overall"]["trade_count"],
        "preferred_count": len(summary["preferred_candidates"]),
        "avoid_count": len(summary["avoid_candidates"]),
        "preferred_combination_count": len(summary["preferred_combination_candidates"]),
        "avoid_combination_count": len(summary["avoid_combination_candidates"]),
        "artifacts": {
            "run_data_attribution_summary_json_path": str(json_path),
            "run_data_attribution_summary_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_run_data_attribution_summary_markdown_zh(summary))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact persisted-run attribution summary for AI review")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument("--min-sample-count", type=int, default=30)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--combination-size", type=int, default=2)
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
