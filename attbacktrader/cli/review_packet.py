"""Build an AI-friendly review packet from persisted run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    REVIEW_PACKET_FOCUSES,
    build_review_packet,
    render_review_packet_markdown_zh,
    write_review_packet,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_review_packet(args.run_dir, focus=args.focus, top=args.top)
    json_path, markdown_path = write_review_packet(packet, output_dir=args.output_dir)

    payload = {
        "schema": packet["schema"],
        "run_id": packet["run_id"],
        "focus": packet["focus"],
        "overview": packet["overview"],
        "artifacts": {
            "review_packet_json_path": str(json_path),
            "review_packet_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_review_packet_markdown_zh(packet))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AI-friendly review packet from persisted artifacts")
    parser.add_argument("--run-dir", required=True, help="Persisted run artifact directory")
    parser.add_argument("--focus", choices=REVIEW_PACKET_FOCUSES, default="all")
    parser.add_argument("--top", type=int, default=30, help="Maximum rows per summary/sample section")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to --run-dir")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
