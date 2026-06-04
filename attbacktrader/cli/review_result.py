"""Persist an AI review result from a review brief."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_ai_review_result,
    render_ai_review_result_markdown_zh,
    write_ai_review_result,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = build_ai_review_result(
        args.brief,
        environment_fit_comparison=args.environment_fit_comparison,
        reviewer=args.reviewer,
    )
    json_path, markdown_path = write_ai_review_result(result, output_dir=args.output_dir or Path(str(result["source_dir"])))
    payload = {
        "schema": result["schema"],
        "run_id": result["run_id"],
        "focus": result["focus"],
        "status": result["status"],
        "finding_result_count": result["finding_result_count"],
        "artifacts": {
            "ai_review_result_json_path": str(json_path),
            "ai_review_result_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_ai_review_result_markdown_zh(result))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist an AI review result from a review brief")
    parser.add_argument("--brief", required=True, help="Path to review_brief.<focus>.json")
    parser.add_argument(
        "--environment-fit-comparison",
        default=None,
        help="Optional path to environment_fit_comparison.json for structured environment stability review",
    )
    parser.add_argument("--reviewer", default="deterministic_brief_renderer")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run directory")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
