"""Build a persisted-run data dictionary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_data_dictionary,
    render_run_data_dictionary_markdown_zh,
    write_run_data_dictionary,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    dictionary = build_run_data_dictionary(run_dir)
    output_dir = Path(args.output_dir) if args.output_dir is not None else Path(run_dir) if run_dir is not None else Path("reports")
    json_path, markdown_path = write_run_data_dictionary(dictionary, output_dir=output_dir)
    payload = {
        "schema": dictionary["schema"],
        "run_id": dictionary.get("run_id"),
        "source_dir": dictionary.get("source_dir"),
        "artifact_count": dictionary["artifact_count"],
        "artifacts": {
            "run_data_dictionary_json_path": str(json_path),
            "run_data_dictionary_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_run_data_dictionary_markdown_zh(dictionary))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a persisted-run data dictionary")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run dir or reports/")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _resolve_run_dir(args: argparse.Namespace) -> Path | None:
    if args.run_dir is not None:
        return Path(args.run_dir)
    if args.run_id is not None:
        return Path(args.report_root) / args.run_id
    return None


if __name__ == "__main__":
    raise SystemExit(main())
