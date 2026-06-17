"""Generate Stage 1 single-factor entry validation manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_entry_factor_validation_manifest,
    render_entry_factor_validation_manifest_markdown_zh,
    safe_entry_factor_validation_manifest_dir_name,
    write_entry_factor_validation_manifest,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest = build_entry_factor_validation_manifest(
        args.discovery,
        args.baseline_run_plan,
        positive_limit=args.positive_limit,
        negative_limit=args.negative_limit,
        reuse_snapshots=not args.refresh_snapshots,
        missing_policy=args.missing_policy,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args.discovery)
    json_path, markdown_path, yaml_paths = write_entry_factor_validation_manifest(
        manifest,
        output_dir=output_dir,
    )
    payload = {
        "schema": manifest["schema"],
        "base_run_id": manifest["base_run_id"],
        "source_discovery_run_id": manifest["source_discovery_run_id"],
        "generated_count": manifest["generated_count"],
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
    parser.add_argument("--discovery", required=True, help="Path to bayesian_factor_discovery.json")
    parser.add_argument("--baseline-run-plan", required=True, help="Baseline RunPlan YAML")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--positive-limit", type=int, default=10)
    parser.add_argument("--negative-limit", type=int, default=10)
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
