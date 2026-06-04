"""Confirm a review experiment draft into a validated RunPlan YAML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_review_experiment_confirmed_run_plan,
    render_review_experiment_confirmed_run_plan_markdown_zh,
    write_review_experiment_confirmed_run_plan,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.confirm:
        raise SystemExit("--confirm is required to generate a legal RunPlan from a review draft")

    confirmation = build_review_experiment_confirmed_run_plan(
        args.draft,
        base_config_path=args.base_config,
        confirmed_by=args.confirmed_by,
        confirmation_note=args.note,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else Path(args.draft).parent / "confirmed"
    json_path, markdown_path, run_plan_path = write_review_experiment_confirmed_run_plan(
        confirmation,
        output_dir=output_dir,
    )
    payload = {
        "schema": confirmation["schema"],
        "status": confirmation["status"],
        "draft_id": confirmation["draft_id"],
        "source_candidate_id": confirmation["source_candidate_id"],
        "run_id": confirmation["run_id"],
        "omitted_patch_keys": confirmation["omitted_patch_keys"],
        "artifacts": {
            "confirmation_json_path": str(json_path),
            "confirmation_chinese_markdown_path": str(markdown_path),
            "run_plan_yaml_path": str(run_plan_path),
        },
    }
    if args.print_markdown:
        print(render_review_experiment_confirmed_run_plan_markdown_zh(confirmation))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Confirm a review experiment draft into a validated RunPlan YAML")
    parser.add_argument("--draft", required=True, help="Path to one review experiment draft YAML")
    parser.add_argument("--base-config", default=None, help="Override base RunPlan YAML path")
    parser.add_argument("--confirmed-by", default="manual")
    parser.add_argument("--note", default=None, help="Optional confirmation note stored in the manifest")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--confirm", action="store_true", help="Required guard for generating a legal RunPlan")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
