"""Build Stage 1 entry-factor validation classification artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_entry_factor_validation_classification,
    render_entry_factor_validation_classification_markdown_zh,
    safe_entry_factor_validation_classification_dir_name,
    to_jsonable,
    write_entry_factor_validation_classification,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(args.matrix, args.report_root)
    report = build_entry_factor_validation_classification(
        args.matrix,
        report_root=args.report_root,
        baseline_run_dir=args.baseline_run_dir,
        min_total_trades=args.min_total_trades,
        min_year_trades=args.min_year_trades,
        min_stage_trades=args.min_stage_trades,
        slice_score_threshold=args.slice_score_threshold,
    )
    _, _, payload = write_entry_factor_validation_classification(report, output_dir=output_dir)

    if args.print_markdown:
        print(render_entry_factor_validation_classification_markdown_zh(payload))
        return 0

    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify Stage 1 entry-factor validation matrix by year and market stage")
    parser.add_argument("--matrix", required=True, help="Path to entry_factor_validation_matrix.json")
    parser.add_argument("--report-root", default="reports", help="Run artifact root used for baseline lookup")
    parser.add_argument("--baseline-run-dir", default=None, help="Optional baseline run artifact directory")
    parser.add_argument("--output-dir", default=None, help="Output directory for classification artifacts")
    parser.add_argument("--min-total-trades", type=int, default=50)
    parser.add_argument("--min-year-trades", type=int, default=30)
    parser.add_argument("--min-stage-trades", type=int, default=30)
    parser.add_argument("--slice-score-threshold", type=float, default=0.0)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _default_output_dir(matrix_path: str, report_root: str) -> Path:
    return Path(report_root) / safe_entry_factor_validation_classification_dir_name(matrix_path)


if __name__ == "__main__":
    raise SystemExit(main())
