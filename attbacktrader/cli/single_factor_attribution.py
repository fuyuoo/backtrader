"""Build a full single-factor attribution report from attribution wide samples."""

from __future__ import annotations

import argparse
import json

from attbacktrader.reports import (
    build_single_factor_attribution_report,
    load_attribution_field_index,
    load_attribution_wide_samples,
    render_single_factor_attribution_markdown_zh,
    write_single_factor_attribution_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    wide_samples = load_attribution_wide_samples(args.wide_samples)
    field_index = load_attribution_field_index(args.field_index) if args.field_index is not None else wide_samples.get("field_index")
    report = build_single_factor_attribution_report(
        wide_samples,
        field_index=field_index,
        min_bucket_sample_count=args.min_bucket_sample_count,
        high_missing_ratio=args.high_missing_ratio,
    )
    json_path, markdown_path = write_single_factor_attribution_report(
        report,
        output_dir=args.output_dir,
    )
    payload = {
        "schema": report["schema"],
        "run_id": report["run_id"],
        "sample_count": report["sample_count"],
        "field_count": report["field_count"],
        "entry_factor_count": report["entry_factor_count"],
        "post_trade_stat_count": report["post_trade_stat_count"],
        "excluded_field_count": report["excluded_field_count"],
        "entry_single_factor_summary_count": len(report["entry_single_factor_summaries"]),
        "post_trade_summary_count": len(report["post_trade_summaries"]),
        "artifacts": {
            "single_factor_attribution_json_path": str(json_path),
            "single_factor_attribution_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_single_factor_attribution_markdown_zh(report))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a full single-factor attribution report")
    parser.add_argument("--wide-samples", required=True, help="attribution_wide_samples.json or output directory")
    parser.add_argument("--field-index", default=None, help="attribution_field_index.json or output directory")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to current directory")
    parser.add_argument("--min-bucket-sample-count", type=int, default=20)
    parser.add_argument("--high-missing-ratio", type=float, default=0.2)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
