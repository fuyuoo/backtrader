"""Build structured AI review findings from a review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    REVIEW_PACKET_FOCUSES,
    build_ai_review_findings,
    build_review_packet,
    render_ai_review_findings_markdown_zh,
    write_ai_review_findings,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.packet is not None:
        source = Path(args.packet)
        default_output_dir = source.parent
    else:
        if args.run_dir is None:
            raise SystemExit("--packet or --run-dir is required")
        source = build_review_packet(args.run_dir, focus=args.focus, top=args.packet_top)
        default_output_dir = Path(args.run_dir)

    findings = build_ai_review_findings(source, top=args.top)
    json_path, markdown_path = write_ai_review_findings(
        findings,
        output_dir=args.output_dir or default_output_dir,
    )
    payload = {
        "schema": findings["schema"],
        "run_id": findings["run_id"],
        "focus": findings["focus"],
        "finding_count": findings["finding_count"],
        "artifacts": {
            "review_findings_json_path": str(json_path),
            "review_findings_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_ai_review_findings_markdown_zh(findings))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build structured AI review findings")
    parser.add_argument("--packet", default=None, help="Path to review_packet.<focus>.json")
    parser.add_argument("--run-dir", default=None, help="Run artifact directory; used when --packet is omitted")
    parser.add_argument("--focus", choices=REVIEW_PACKET_FOCUSES, default="all")
    parser.add_argument("--packet-top", type=int, default=30, help="Rows per section when building a packet from run-dir")
    parser.add_argument("--top", type=int, default=10, help="Maximum sample refs per finding")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to packet/run directory")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
