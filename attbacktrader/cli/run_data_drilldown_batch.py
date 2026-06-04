"""Build a batch of persisted-run sample drill-downs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from attbacktrader.reports import (
    build_run_data_drilldown_batch,
    render_run_data_drilldown_batch_markdown_zh,
    write_run_data_drilldown_batch,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir = _resolve_run_dir(args)
    sample_refs = _sample_refs_from_args(args)
    batch = build_run_data_drilldown_batch(
        run_dir,
        sample_refs=sample_refs,
        context_limit=args.context_limit,
    )
    json_path, markdown_path = write_run_data_drilldown_batch(batch, output_dir=args.output_dir)
    payload = {
        "schema": batch["schema"],
        "run_id": batch["run_id"],
        "source_dir": batch["source_dir"],
        "sample_count": batch["sample_count"],
        "sample_ids": [sample["sample_id"] for sample in batch["samples"]],
        "artifacts": {
            "run_data_drilldown_batch_json_path": str(json_path),
            "run_data_drilldown_batch_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_run_data_drilldown_batch_markdown_zh(batch))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a batch of persisted-run sample drill-downs")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument("--trade-index", type=int, action="append", default=[])
    parser.add_argument("--opportunity-sample-index", type=int, action="append", default=[])
    parser.add_argument("--add-on-sample-index", type=int, action="append", default=[])
    parser.add_argument(
        "--sample-ref",
        action="append",
        default=[],
        help="Repeatable ref in the form trade:117, opportunity:12, or add_on:1",
    )
    parser.add_argument("--refs-json", default=None, help="Optional JSON file containing sample ref objects")
    parser.add_argument("--context-limit", type=int, default=20)
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run dir")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir is not None:
        return Path(args.run_dir)
    if args.run_id is not None:
        return Path(args.report_root) / args.run_id
    raise ValueError("--run-dir or --run-id is required")


def _sample_refs_from_args(args: argparse.Namespace) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    refs.extend({"kind": "trade", "trade_index": index} for index in args.trade_index)
    refs.extend({"kind": "opportunity", "sample_index": index} for index in args.opportunity_sample_index)
    refs.extend({"kind": "add_on", "sample_index": index} for index in args.add_on_sample_index)
    refs.extend(_parse_sample_ref(value) for value in args.sample_ref)
    if args.refs_json is not None:
        payload = json.loads(Path(args.refs_json).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("--refs-json must contain a JSON list")
        refs.extend(dict(item) for item in payload)
    if not refs:
        raise ValueError("At least one sample ref is required")
    return refs


def _parse_sample_ref(value: str) -> dict[str, Any]:
    if ":" not in value:
        raise ValueError(f"Invalid --sample-ref, expected kind:id: {value}")
    kind, raw_id = value.split(":", 1)
    if kind == "trade":
        return {"kind": "trade", "trade_index": int(raw_id)}
    if kind in {"opportunity", "add_on"}:
        return {"kind": kind, "sample_index": int(raw_id)}
    raise ValueError(f"Unsupported --sample-ref kind: {kind}")


if __name__ == "__main__":
    raise SystemExit(main())
