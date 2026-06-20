"""Build a Bayesian factor discovery report from attribution wide samples."""

from __future__ import annotations

import argparse
import json

from attbacktrader.reports import (
    build_bayesian_factor_discovery_report,
    load_attribution_field_index,
    load_attribution_wide_samples,
    render_bayesian_factor_discovery_markdown_zh,
    write_bayesian_factor_discovery_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    wide_samples = load_attribution_wide_samples(args.wide_samples)
    field_index = load_attribution_field_index(args.field_index) if args.field_index is not None else wide_samples.get("field_index")
    report = build_bayesian_factor_discovery_report(
        wide_samples,
        field_index=field_index,
        min_bucket_sample_count=args.min_bucket_sample_count,
        high_missing_ratio=args.high_missing_ratio,
        prior_strength=args.prior_strength,
        positive_score_threshold=args.positive_score_threshold,
        negative_score_threshold=args.negative_score_threshold,
    )
    json_path, markdown_path = write_bayesian_factor_discovery_report(
        report,
        output_dir=args.output_dir,
    )
    payload = {
        "schema": report["schema"],
        "run_id": report["run_id"],
        "sample_count": report["sample_count"],
        "field_count": report["field_count"],
        "usable_field_count": report["usable_field_count"],
        "candidate_bucket_count": report["candidate_bucket_count"],
        "usable_field_counts": report["usable_field_counts"],
        "ranking_counts": {
            view: {
                direction: len(rows)
                for direction, rows in rankings.items()
            }
            for view, rankings in report["rankings"].items()
        },
        "artifacts": {
            "bayesian_factor_discovery_json_path": str(json_path),
            "bayesian_factor_discovery_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_bayesian_factor_discovery_markdown_zh(report))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Bayesian factor discovery report")
    parser.add_argument("--wide-samples", required=True, help="attribution_wide_samples.json or output directory")
    parser.add_argument("--field-index", default=None, help="attribution_field_index.json or output directory")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to wide sample source dir")
    parser.add_argument("--min-bucket-sample-count", type=int, default=30)
    parser.add_argument("--high-missing-ratio", type=float, default=0.2)
    parser.add_argument("--prior-strength", type=float, default=50.0)
    parser.add_argument("--positive-score-threshold", type=float, default=0.5)
    parser.add_argument("--negative-score-threshold", type=float, default=-0.5)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
