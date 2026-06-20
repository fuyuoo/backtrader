"""Build an entry single-factor candidate screening report."""

from __future__ import annotations

import argparse
import json

from attbacktrader.reports import (
    build_entry_single_factor_candidate_screening_report,
    render_entry_single_factor_candidate_screening_markdown_zh,
    write_entry_single_factor_candidate_screening_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_entry_single_factor_candidate_screening_report(
        args.single_factor_attribution,
        reverse_filter_candidate_summary=args.reverse_filter_summary,
        min_candidate_sample_count=args.min_candidate_sample_count,
    )
    json_path, markdown_path, csv_path = write_entry_single_factor_candidate_screening_report(
        report,
        output_dir=args.output_dir,
    )
    payload = {
        "schema": report["schema"],
        "run_id": report["run_id"],
        "screening_mode": report["screening_mode"],
        "screened_row_count": report["screened_row_count"],
        "category_counts": report["category_counts"],
        "artifacts": {
            "entry_single_factor_candidate_screening_json_path": str(json_path),
            "entry_single_factor_candidate_screening_chinese_markdown_path": str(markdown_path),
            "entry_single_factor_candidate_screening_rows_csv_path": str(csv_path),
        },
    }
    if args.print_markdown:
        print(render_entry_single_factor_candidate_screening_markdown_zh(report))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an entry single-factor candidate screening report")
    parser.add_argument("--single-factor-attribution", required=True, help="single_factor_attribution.json or its directory")
    parser.add_argument("--reverse-filter-summary", default=None, help="reverse_filter_candidate_summary.json or its directory")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to the source report directory")
    parser.add_argument("--min-candidate-sample-count", type=int, default=None)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
