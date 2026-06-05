"""Build experiment decision records from explicit decision inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_experiment_decisions_from_files,
    render_experiment_decisions_markdown_zh,
    safe_experiment_decisions_dir_name,
    write_experiment_decisions,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    decision_log = build_experiment_decisions_from_files(
        lifecycle_path=args.lifecycle,
        decision_file=args.decision_file,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else Path("reports") / safe_experiment_decisions_dir_name()
    json_path, markdown_path = write_experiment_decisions(decision_log, output_dir=output_dir)
    payload = {
        "schema": decision_log["schema"],
        "decision_count": decision_log["decision_count"],
        "recorded_decision_count": decision_log["recorded_decision_count"],
        "invalid_decision_count": decision_log["invalid_decision_count"],
        "open_decision_gap_count": decision_log["open_decision_gap_count"],
        "artifacts": {
            "experiment_decisions_json_path": str(json_path),
            "experiment_decisions_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_experiment_decisions_markdown_zh(decision_log))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build experiment decision records from explicit decision inputs")
    parser.add_argument("--lifecycle", default="reports/experiment-lifecycle/experiment_lifecycle.json")
    parser.add_argument(
        "--decision-file",
        default="examples/experiment-decisions/workbench-v1-strategy-variant-decisions.json",
    )
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
