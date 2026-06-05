"""Generate legal RunPlan YAMLs from strategy variant drafts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_strategy_variant_run_manifest,
    render_strategy_variant_run_manifest_markdown_zh,
    safe_strategy_variant_run_manifest_dir_name,
    write_strategy_variant_run_manifest,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest = build_strategy_variant_run_manifest(
        args.drafts,
        args.market_segment_manifest,
        reuse_snapshots=not args.refresh_snapshots,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args)
    json_path, markdown_path, yaml_paths = write_strategy_variant_run_manifest(manifest, output_dir=output_dir)
    payload = {
        "schema": manifest["schema"],
        "generated_count": manifest["generated_count"],
        "reuse_snapshots": manifest["reuse_snapshots"],
        "artifacts": {
            "strategy_variant_run_manifest_json_path": str(json_path),
            "strategy_variant_run_manifest_chinese_markdown_path": str(markdown_path),
            "strategy_variant_run_plan_paths": [str(path) for path in yaml_paths],
        },
    }
    if args.print_markdown:
        print(render_strategy_variant_run_manifest_markdown_zh(manifest))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate strategy variant segment RunPlans")
    parser.add_argument("--drafts", required=True, help="Path to strategy_variant_drafts.json")
    parser.add_argument("--market-segment-manifest", required=True, help="Path to market_segment_run_manifest.json")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--refresh-snapshots",
        action="store_true",
        help="Keep generated RunPlans refreshing snapshots; default reuses existing snapshots.",
    )
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


def _default_output_dir(args: argparse.Namespace) -> Path:
    return Path("examples") / "generated-strategy-variant-runs" / safe_strategy_variant_run_manifest_dir_name(
        args.drafts
    ).removeprefix("generated-strategy-variant-runs-")


if __name__ == "__main__":
    raise SystemExit(main())
