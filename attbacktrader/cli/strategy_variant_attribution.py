"""Explain strategy variant behavior changes from persisted artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_strategy_variant_attribution,
    render_strategy_variant_attribution_markdown_zh,
    safe_strategy_variant_attribution_dir_name,
    write_strategy_variant_attribution,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    attribution = build_strategy_variant_attribution(
        args.baseline_manifest,
        args.variant_manifest,
        market_type_id=args.market_type_id,
        report_root=args.report_root,
        short_reentry_days=args.short_reentry_days,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args)
    json_path, markdown_path = write_strategy_variant_attribution(attribution, output_dir=output_dir)
    payload = {
        "schema": attribution["schema"],
        "market_type_id": attribution["market_type_id"],
        "segment_count": attribution["segment_count"],
        "artifacts": {
            "strategy_variant_attribution_json_path": str(json_path),
            "strategy_variant_attribution_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_strategy_variant_attribution_markdown_zh(attribution))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explain strategy variant behavior changes")
    parser.add_argument("--baseline-manifest", required=True, help="Path to baseline market_segment_run_manifest.json")
    parser.add_argument("--variant-manifest", required=True, help="Path to strategy_variant_run_manifest.json")
    parser.add_argument("--market-type-id", required=True, help="Market type to compare, for example bull_market")
    parser.add_argument("--report-root", default="reports", help="Root containing run artifact directories")
    parser.add_argument("--short-reentry-days", type=int, default=5)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


def _default_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.report_root) / safe_strategy_variant_attribution_dir_name(
        args.variant_manifest,
        args.market_type_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
