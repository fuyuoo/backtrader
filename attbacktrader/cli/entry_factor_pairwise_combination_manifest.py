"""Build A-anchored pairwise entry-factor combination RunPlan manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports.entry_factor_pairwise_combination_manifest import (
    build_entry_factor_pairwise_combination_manifest,
    render_entry_factor_pairwise_combination_manifest_markdown_zh,
    safe_entry_factor_pairwise_combination_manifest_dir_name,
    write_entry_factor_pairwise_combination_manifest,
)
from attbacktrader.reports import to_jsonable


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(args.screening_layers, args.output_root)
    manifest = build_entry_factor_pairwise_combination_manifest(
        args.screening_layers,
        args.baseline_run_plan,
        anchor_layer=args.anchor_layer,
        layers=args.layers,
        require_strict_pre_entry=not args.include_non_u0,
        reuse_snapshots=not args.refresh_snapshots,
        missing_policy=args.missing_policy,
    )
    _, _, _, payload = write_entry_factor_pairwise_combination_manifest(manifest, output_dir=output_dir)

    if args.print_markdown:
        print(render_entry_factor_pairwise_combination_manifest_markdown_zh(payload))
        return 0

    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build A-anchored pairwise entry-factor combination manifest")
    parser.add_argument("--screening-layers", required=True, help="Path to entry_factor_final_screening_layers.json/csv")
    parser.add_argument("--baseline-run-plan", required=True, help="Baseline RunPlan YAML")
    parser.add_argument("--output-root", default="reports", help="Default root when --output-dir is omitted")
    parser.add_argument("--output-dir", default=None, help="Manifest output directory")
    parser.add_argument("--anchor-layer", default="A", help="Layer that every pair must include")
    parser.add_argument("--layers", nargs="+", default=["A", "B", "C"], help="Screening layers included in the pool")
    parser.add_argument("--include-non-u0", action="store_true", help="Allow non-U0 usability rows into the pair pool")
    parser.add_argument("--missing-policy", choices=("block", "pass"), default="block")
    parser.add_argument("--refresh-snapshots", action="store_true", help="Refresh data snapshots for generated variants")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _default_output_dir(screening_layers_path: str, output_root: str | Path) -> Path:
    return Path(output_root) / safe_entry_factor_pairwise_combination_manifest_dir_name(screening_layers_path)


if __name__ == "__main__":
    raise SystemExit(main())
