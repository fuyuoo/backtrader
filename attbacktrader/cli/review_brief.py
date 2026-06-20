"""Build a Skill-ready AI review brief."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_ai_review_brief,
    render_ai_review_brief_markdown_zh,
    write_ai_review_brief,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    brief = build_ai_review_brief(
        args.findings,
        run_dir=args.run_dir,
        sample_batch=args.sample_batch,
        limit_per_finding=args.limit_per_finding,
    )
    json_path, markdown_path = write_ai_review_brief(brief, output_dir=args.output_dir or Path(str(brief["source_dir"])))
    payload = {
        "schema": brief["schema"],
        "run_id": brief["run_id"],
        "focus": brief["focus"],
        "section_count": brief["section_count"],
        "artifacts": {
            "review_brief_json_path": str(json_path),
            "review_brief_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_ai_review_brief_markdown_zh(brief))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Skill-ready AI review brief")
    parser.add_argument("--findings", required=True, help="Path to review_findings.<focus>.json")
    parser.add_argument("--run-dir", default=None, help="Run artifact directory; defaults to findings.source_dir")
    parser.add_argument("--sample-batch", default=None, help="Optional review_sample_batch.<focus>.json")
    parser.add_argument("--limit-per-finding", type=int, default=3)
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run directory")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
