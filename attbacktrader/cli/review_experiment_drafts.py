"""Build manually confirmable YAML drafts from review experiment candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_review_experiment_drafts,
    render_review_experiment_drafts_markdown_zh,
    write_review_experiment_drafts,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    drafts = build_review_experiment_drafts(args.candidates, base_config_path=args.base_config)
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = Path("examples") / "generated-review-experiments" / str(drafts["run_id"])
    json_path, markdown_path, yaml_paths = write_review_experiment_drafts(drafts, output_dir=output_dir)
    payload = {
        "schema": drafts["schema"],
        "run_id": drafts["run_id"],
        "focus": drafts["focus"],
        "draft_count": drafts["draft_count"],
        "artifacts": {
            "review_experiment_drafts_json_path": str(json_path),
            "review_experiment_drafts_chinese_markdown_path": str(markdown_path),
            "review_experiment_draft_yaml_paths": [str(path) for path in yaml_paths],
        },
    }
    if args.print_markdown:
        print(render_review_experiment_drafts_markdown_zh(drafts))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review experiment YAML drafts")
    parser.add_argument("--candidates", required=True, help="Path to review_experiment_candidates.<focus>.json")
    parser.add_argument("--base-config", default=None, help="Base run YAML used for suggested run ids")
    parser.add_argument("--output-dir", default=None, help="Output directory for manifest and YAML drafts")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
