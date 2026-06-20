"""Build a focused AI drill-down packet for one review sample."""

from __future__ import annotations

import argparse
import json

from attbacktrader.reports import (
    REVIEW_SAMPLE_KINDS,
    build_review_sample,
    render_review_sample_markdown_zh,
    write_review_sample,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_review_sample(
        args.run_dir,
        kind=args.kind,
        sample_index=args.sample_index,
        trade_index=args.trade_index,
        context_limit=args.context_limit,
    )
    json_path, markdown_path = write_review_sample(packet, output_dir=args.output_dir)
    payload = {
        "schema": packet["schema"],
        "run_id": packet["run_id"],
        "sample_kind": packet["sample_kind"],
        "sample_id": packet["sample_id"],
        "artifacts": {
            "review_sample_json_path": str(json_path),
            "review_sample_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_review_sample_markdown_zh(packet))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build one review sample drill-down packet")
    parser.add_argument("--run-dir", required=True, help="Persisted run artifact directory")
    parser.add_argument("--kind", choices=REVIEW_SAMPLE_KINDS, required=True)
    parser.add_argument("--sample-index", type=int, default=None, help="sample_index for opportunity/add_on samples")
    parser.add_argument("--trade-index", type=int, default=None, help="trade_index for trade samples")
    parser.add_argument("--context-limit", type=int, default=20, help="Maximum matched signal/execution rows to include")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to --run-dir")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
