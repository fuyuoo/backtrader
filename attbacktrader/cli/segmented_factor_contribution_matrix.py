"""Build a segmented factor contribution matrix from environment-fit artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from attbacktrader.reports import (
    ANNUAL_MATRIX_METRIC_DEFINITIONS,
    build_segmented_factor_contribution_matrix,
    render_segmented_factor_contribution_matrix_markdown_zh,
    safe_segmented_factor_contribution_matrix_dir_name,
    write_segmented_factor_contribution_matrix,
)
from attbacktrader.reports.writer import to_jsonable


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_path = _resolve_environment_fit_path(args.environment_fit)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(source_path, args.report_root)
    segments = [_parse_segment(value) for value in args.segment] if args.segment else None
    report = build_segmented_factor_contribution_matrix(
        source_path,
        segments=segments,
        annual_matrix_metrics=args.annual_matrix_metric,
        min_segment_sample_count=args.min_segment_sample_count,
        min_total_sample_count=args.min_total_sample_count,
    )
    _, _, payload = write_segmented_factor_contribution_matrix(report, output_dir=output_dir)
    if args.print_markdown:
        print(render_segmented_factor_contribution_matrix_markdown_zh(payload))
    else:
        print(
            json.dumps(
                to_jsonable(
                    {
                        "schema": payload["schema"],
                        "run_id": payload.get("run_id"),
                        "trade_count": payload.get("trade_count"),
                        "field_count": payload.get("field_count"),
                        "factor_bucket_count": payload.get("factor_bucket_count"),
                        "annual_factor_bucket_count": payload.get("annual_factor_bucket_count"),
                        "annual_matrix_metrics": [
                            item.get("metric")
                            for item in (payload.get("annual_matrix_metrics") or [])
                        ],
                        "artifacts": payload.get("artifacts"),
                    }
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a segmented factor contribution matrix")
    parser.add_argument(
        "--environment-fit",
        required=True,
        help="Path to environment_fit.enriched.json/environment_fit.json, or a directory containing one",
    )
    parser.add_argument("--output-dir", help="Output directory for segmented_factor_contribution_matrix artifacts")
    parser.add_argument("--report-root", default="reports", help="Default report root when --output-dir is omitted")
    parser.add_argument(
        "--segment",
        action="append",
        default=[],
        help="Optional custom segment as segment_id:start:end:label_zh; repeatable",
    )
    parser.add_argument(
        "--annual-matrix-metric",
        action="append",
        choices=list(ANNUAL_MATRIX_METRIC_DEFINITIONS),
        help=(
            "Metric to render in annual factor matrices; repeatable. "
            "Defaults to sample_count, average_return_pct, win_rate, return_on_entry_value, max_return_pct, min_return_pct."
        ),
    )
    parser.add_argument("--min-segment-sample-count", type=int, default=30)
    parser.add_argument("--min-total-sample-count", type=int, default=100)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown report instead of JSON summary")
    return parser.parse_args(argv)


def _resolve_environment_fit_path(value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        enriched = path / "environment_fit.enriched.json"
        if enriched.exists():
            return enriched
        plain = path / "environment_fit.json"
        if plain.exists():
            return plain
        raise FileNotFoundError(f"no environment_fit.enriched.json or environment_fit.json under {path}")
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _default_output_dir(source_path: Path, report_root: str) -> Path:
    return Path(report_root) / safe_segmented_factor_contribution_matrix_dir_name(source_path)


def _parse_segment(value: str) -> dict[str, Any]:
    parts = value.split(":", 3)
    if len(parts) != 4:
        raise ValueError("--segment must be formatted as segment_id:start:end:label_zh")
    segment_id, start, end, label_zh = parts
    return {
        "segment_id": segment_id,
        "start": start,
        "end": end,
        "label_zh": label_zh,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
