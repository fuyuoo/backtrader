"""Build and optionally filter a persisted-run attribution field index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_data_attribution_index,
    render_run_data_attribution_index_markdown_zh,
    write_run_data_attribution_index,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    index = build_run_data_attribution_index(
        run_dir,
        filters=args.filter,
        max_samples=args.max_samples,
        top_samples_per_value=args.top_samples_per_value,
    )
    json_path, markdown_path = write_run_data_attribution_index(index, output_dir=args.output_dir)
    payload = {
        "schema": index["schema"],
        "run_id": index["run_id"],
        "source_dir": index["source_dir"],
        "row_count": index["row_count"],
        "field_count": index["field_count"],
        "match_count": index["match_count"],
        "matching_sample_ids": [sample["sample_id"] for sample in index["matching_samples"]],
        "artifacts": {
            "run_data_attribution_index_json_path": str(json_path),
            "run_data_attribution_index_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_run_data_attribution_index_markdown_zh(index))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and optionally filter a persisted-run attribution field index")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Repeatable equals filter, e.g. entry.symbol.ma.bullish_trend=true",
    )
    parser.add_argument("--max-samples", type=int, default=100)
    parser.add_argument("--top-samples-per-value", type=int, default=20)
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
