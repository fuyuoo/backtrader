"""Build a catalog of persisted backtest runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_catalog,
    render_run_catalog_markdown_zh,
    safe_run_catalog_dir_name,
    write_run_catalog,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifests = list(args.manifest or [])
    if not args.no_default_manifests:
        manifests = [str(path) for path in _default_manifests()] + manifests
    catalog = build_run_catalog(report_root=args.report_root, manifests=manifests)
    output_dir = Path(args.output_dir) if args.output_dir is not None else Path(args.report_root) / safe_run_catalog_dir_name()
    json_path, markdown_path = write_run_catalog(catalog, output_dir=output_dir)
    payload = {
        "schema": catalog["schema"],
        "report_root": catalog["report_root"],
        "run_count": catalog["run_count"],
        "group_count": catalog["group_count"],
        "missing_required_artifact_run_count": catalog["missing_required_artifact_run_count"],
        "artifacts": {
            "run_catalog_json_path": str(json_path),
            "run_catalog_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_run_catalog_markdown_zh(catalog))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a catalog of persisted backtest runs")
    parser.add_argument("--report-root", default="reports", help="Root containing run artifact directories")
    parser.add_argument("--manifest", action="append", default=None, help="Optional market segment or strategy variant manifest")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--no-default-manifests", action="store_true")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _default_manifests() -> tuple[Path, ...]:
    candidates = (
        Path("examples/generated-market-segment-runs/tushare-market-type-add-on/market_segment_run_manifest.json"),
        Path("examples/generated-strategy-variant-runs/tushare-market-type-add-on/strategy_variant_run_manifest.json"),
    )
    return tuple(path for path in candidates if path.exists())


if __name__ == "__main__":
    raise SystemExit(main())
