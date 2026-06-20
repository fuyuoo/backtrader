"""Build review-derived experiment candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_review_experiment_candidates,
    render_review_experiment_candidates_markdown_zh,
    write_review_experiment_candidates,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    candidates = build_review_experiment_candidates(args.findings, sample_batch=args.sample_batch)
    json_path, markdown_path = write_review_experiment_candidates(
        candidates,
        output_dir=args.output_dir or Path(str(candidates["source_dir"])),
    )
    payload = {
        "schema": candidates["schema"],
        "run_id": candidates["run_id"],
        "focus": candidates["focus"],
        "candidate_count": candidates["candidate_count"],
        "artifacts": {
            "review_experiment_candidates_json_path": str(json_path),
            "review_experiment_candidates_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_review_experiment_candidates_markdown_zh(candidates))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build review-derived experiment candidates")
    parser.add_argument("--findings", required=True, help="Path to review_findings.<focus>.json")
    parser.add_argument("--sample-batch", default=None, help="Optional review_sample_batch.<focus>.json")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run directory")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
