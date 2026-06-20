"""Generate Stage 1 single-factor entry validation manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_entry_factor_validation_manifest,
    build_entry_factor_validation_manifest_from_screening,
    render_entry_factor_validation_manifest_markdown_zh,
    safe_entry_factor_validation_manifest_dir_name,
    write_entry_factor_validation_manifest,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_path = args.discovery or args.screening
    if args.screening:
        manifest = build_entry_factor_validation_manifest_from_screening(
            args.screening,
            args.baseline_run_plan,
            positive_limit=args.positive_limit,
            negative_limit=args.negative_limit,
            include_watchlist=args.include_watchlist,
            include_exposure_watchlist=args.include_exposure_watchlist,
            reuse_snapshots=not args.refresh_snapshots,
            missing_policy=args.missing_policy,
        )
    else:
        manifest = build_entry_factor_validation_manifest(
            args.discovery,
            args.baseline_run_plan,
            positive_limit=args.positive_limit if args.positive_limit is not None else 10,
            negative_limit=args.negative_limit if args.negative_limit is not None else 10,
            reuse_snapshots=not args.refresh_snapshots,
            missing_policy=args.missing_policy,
        )
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(source_path)
    json_path, markdown_path, yaml_paths = write_entry_factor_validation_manifest(
        manifest,
        output_dir=output_dir,
    )
    source_run_id = manifest.get("source_discovery_run_id") or manifest.get("source_screening_run_id")
    payload = {
        "schema": manifest["schema"],
        "base_run_id": manifest["base_run_id"],
        "source_mode": manifest.get("source_mode"),
        "source_run_id": source_run_id,
        "source_discovery_run_id": manifest.get("source_discovery_run_id"),
        "source_screening_run_id": manifest.get("source_screening_run_id"),
        "generated_count": manifest["generated_count"],
        "skipped_count": manifest.get("skipped_count", 0),
        "reuse_snapshots": manifest["reuse_snapshots"],
        "artifacts": {
            "entry_factor_validation_manifest_json_path": str(json_path),
            "entry_factor_validation_manifest_chinese_markdown_path": str(markdown_path),
            "entry_factor_validation_run_plan_paths": [str(path) for path in yaml_paths],
        },
    }
    if args.print_markdown:
        print(render_entry_factor_validation_manifest_markdown_zh(manifest))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Stage 1 single-factor entry validation RunPlans")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--discovery", help="Path to bayesian_factor_discovery.json")
    source.add_argument("--screening", help="Path to entry_single_factor_candidate_screening.json")
    parser.add_argument("--baseline-run-plan", required=True, help="Baseline RunPlan YAML")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--positive-limit", type=int, default=None)
    parser.add_argument("--negative-limit", type=int, default=None)
    parser.add_argument(
        "--include-watchlist",
        action="store_true",
        help="Include keep_watchlist/exclude_watchlist rows from screening reports.",
    )
    parser.add_argument(
        "--include-exposure-watchlist",
        action="store_true",
        help="Include exposure_watchlist rows from screening reports.",
    )
    parser.add_argument("--missing-policy", choices=("block", "pass"), default="block")
    parser.add_argument(
        "--refresh-snapshots",
        action="store_true",
        help="Keep generated RunPlans refreshing snapshots; default reuses existing snapshots.",
    )
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


def _default_output_dir(discovery_path: str | Path) -> Path:
    return Path("examples") / "generated-entry-factor-validation" / safe_entry_factor_validation_manifest_dir_name(
        discovery_path
    ).removeprefix("entry-factor-validation-manifest-")


if __name__ == "__main__":
    raise SystemExit(main())
