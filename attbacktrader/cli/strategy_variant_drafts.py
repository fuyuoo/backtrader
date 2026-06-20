"""Build manually confirmable strategy variant drafts from a matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_strategy_variant_drafts,
    render_strategy_variant_drafts_markdown_zh,
    safe_strategy_variant_drafts_dir_name,
    write_strategy_variant_drafts,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    drafts = build_strategy_variant_drafts(
        args.matrix,
        base_config_path=args.base_config,
        top_factor_refs=args.top_factor_refs,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args)
    json_path, markdown_path, yaml_paths = write_strategy_variant_drafts(drafts, output_dir=output_dir)
    payload = {
        "schema": drafts["schema"],
        "draft_count": drafts["draft_count"],
        "artifacts": {
            "strategy_variant_drafts_json_path": str(json_path),
            "strategy_variant_drafts_chinese_markdown_path": str(markdown_path),
            "strategy_variant_draft_yaml_paths": [str(path) for path in yaml_paths],
        },
    }
    if args.print_markdown:
        print(render_strategy_variant_drafts_markdown_zh(drafts))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build strategy variant validation drafts")
    parser.add_argument("--matrix", required=True, help="Path to strategy_adaptation_matrix.json")
    parser.add_argument("--base-config", default=None, help="Base RunPlan YAML for suggested run ids")
    parser.add_argument("--top-factor-refs", type=int, default=3)
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


def _default_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.report_root) / safe_strategy_variant_drafts_dir_name(args.matrix)


if __name__ == "__main__":
    raise SystemExit(main())
