"""Build a compact overview for a persisted run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_data_overview,
    render_run_data_overview_markdown_zh,
    write_run_data_overview,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    overview = build_run_data_overview(run_dir, top_symbols=args.top_symbols)
    json_path, markdown_path = write_run_data_overview(overview, output_dir=args.output_dir)
    payload = {
        "schema": overview["schema"],
        "run_id": overview["run_id"],
        "source_dir": overview["source_dir"],
        "evidence_validation": overview["evidence_validation"],
        "closed_trade_count": overview["trades"]["closed_trade_count"],
        "signal_intent_count": overview["signals"]["signal_intent_count"],
        "execution_event_count": overview["execution"]["event_count"],
        "artifacts": {
            "run_data_overview_json_path": str(json_path),
            "run_data_overview_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_run_data_overview_markdown_zh(overview))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact overview for a persisted run")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument("--top-symbols", type=int, default=10)
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run dir")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir is not None:
        return Path(args.run_dir)
    if args.run_id is not None:
        return Path(args.report_root) / args.run_id
    raise ValueError("--run-dir or --run-id is required")


if __name__ == "__main__":
    raise SystemExit(main())
