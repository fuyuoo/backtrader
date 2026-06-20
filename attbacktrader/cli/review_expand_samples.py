"""Expand review finding sample refs into focused sample packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    expand_review_samples_from_findings,
    render_review_sample_batch_markdown_zh,
    write_review_sample_batch,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    batch = expand_review_samples_from_findings(
        args.findings,
        run_dir=args.run_dir,
        limit_per_finding=args.limit_per_finding,
        output_dir=args.output_dir,
        write_samples=not args.no_sample_files,
    )
    json_path, markdown_path = write_review_sample_batch(batch, output_dir=args.output_dir or Path(batch["source_dir"]))
    payload = {
        "schema": batch["schema"],
        "run_id": batch["run_id"],
        "focus": batch["focus"],
        "expanded_sample_count": batch["expanded_sample_count"],
        "artifacts": {
            "review_sample_batch_json_path": str(json_path),
            "review_sample_batch_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_review_sample_batch_markdown_zh(batch))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expand review finding sample refs into sample packets")
    parser.add_argument("--findings", required=True, help="Path to review_findings.<focus>.json")
    parser.add_argument("--run-dir", default=None, help="Run artifact directory; defaults to findings.source_dir")
    parser.add_argument("--limit-per-finding", type=int, default=3)
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run directory")
    parser.add_argument("--no-sample-files", action="store_true", help="Only write batch artifact, not individual samples")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
