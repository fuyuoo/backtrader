"""Build attribution wide samples and field index artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_attribution_wide_samples,
    render_attribution_field_index_markdown_zh,
    write_attribution_wide_samples,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    wide_samples = build_attribution_wide_samples(
        run_dir,
        reference_snapshot=args.reference_snapshot,
        daily_price_cache_dir=args.daily_price_cache_dir,
        snapshot_root=args.snapshot_root,
        industry_source=args.industry_source,
        max_staleness_trading_days=args.max_staleness_trading_days,
    )
    wide_path, csv_path, index_path, markdown_path = write_attribution_wide_samples(
        wide_samples,
        output_dir=args.output_dir,
    )
    payload = {
        "schema": wide_samples["schema"],
        "run_id": wide_samples["run_id"],
        "source_dir": wide_samples["source_dir"],
        "sample_count": wide_samples["sample_count"],
        "field_count": wide_samples["field_count"],
        "environment_fit_default_fields": wide_samples["environment_fit_default_fields"],
        "artifacts": {
            "attribution_wide_samples_json_path": str(wide_path),
            "attribution_wide_samples_csv_path": str(csv_path),
            "attribution_field_index_json_path": str(index_path),
            "attribution_field_index_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_attribution_field_index_markdown_zh(wide_samples["field_index"]))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build attribution wide samples and field index artifacts")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument("--reference-snapshot", required=True, help="Prepared attribution reference JSON/Parquet/dir")
    parser.add_argument(
        "--daily-price-cache-dir",
        default=None,
        help="Optional Tushare daily raw cache root or daily subdirectory for holding-path attribution",
    )
    parser.add_argument(
        "--snapshot-root",
        default=None,
        help="Optional snapshot root used to read industry index bars for industry daily/weekly factors",
    )
    parser.add_argument("--industry-source", default="SW2021")
    parser.add_argument("--max-staleness-trading-days", type=int, default=5)
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run dir")
    parser.add_argument("--print-markdown", action="store_true", help="Print field index Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir is not None:
        return Path(args.run_dir)
    if args.run_id is not None:
        return Path(args.report_root) / args.run_id
    raise ValueError("--run-dir or --run-id is required")


if __name__ == "__main__":
    raise SystemExit(main())
