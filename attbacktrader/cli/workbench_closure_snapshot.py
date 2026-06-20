"""Write the Backtest Workbench V1 closure snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from attbacktrader.reports import (
    DEFAULT_BASELINE_PATH,
    DEFAULT_CLOSURE_DOC_PATH,
    build_workbench_closure_snapshot,
    render_workbench_closure_markdown_zh,
    write_workbench_closure_snapshot,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    snapshot = build_workbench_closure_snapshot(
        sealed_on=args.sealed_on,
        source_branch=args.source_branch,
        mvp_base_commit=args.mvp_base_commit,
        strategy_adaptation_v1_commit=args.strategy_adaptation_v1_commit,
        run_catalog=args.run_catalog,
        experiment_lifecycle=args.experiment_lifecycle,
        strategy_adaptation_golden_check=args.strategy_adaptation_golden_check,
    )
    baseline_path, closure_doc_path = write_workbench_closure_snapshot(
        snapshot,
        baseline_path=args.baseline_output,
        closure_doc_path=args.doc_output,
    )
    payload = {
        "schema": snapshot["schema"],
        "sealed_on": snapshot["sealed_on"],
        "run_count": snapshot["run_catalog_summary"].get("run_count"),
        "chain_count": snapshot["experiment_lifecycle_summary"].get("chain_count"),
        "decision_gap_count": snapshot["experiment_lifecycle_summary"].get("decision_gap_count"),
        "artifacts": {
            "workbench_closure_baseline_path": str(baseline_path),
            "workbench_closure_markdown_path": str(closure_doc_path),
        },
    }
    if args.print_markdown:
        print(render_workbench_closure_markdown_zh(snapshot))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write the Backtest Workbench V1 closure snapshot")
    parser.add_argument("--sealed-on", default=date.today().isoformat())
    parser.add_argument("--source-branch", default="autoBacktrader")
    parser.add_argument("--mvp-base-commit", default="d339bfc")
    parser.add_argument("--strategy-adaptation-v1-commit", default="8c63fdf")
    parser.add_argument("--run-catalog", default="reports/run-catalog/run_catalog.json")
    parser.add_argument("--experiment-lifecycle", default="reports/experiment-lifecycle/experiment_lifecycle.json")
    parser.add_argument(
        "--strategy-adaptation-golden-check",
        default="reports/strategy-adaptation-v1-ai-review-golden-check/ai_review_golden_check.json",
    )
    parser.add_argument("--baseline-output", default=str(DEFAULT_BASELINE_PATH))
    parser.add_argument("--doc-output", default=str(DEFAULT_CLOSURE_DOC_PATH))
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
