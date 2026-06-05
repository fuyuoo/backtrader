"""Check Backtest Workbench V1 closure docs against the baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_workbench_closure_golden_check,
    render_workbench_closure_golden_check_markdown_zh,
    safe_workbench_closure_golden_check_dir_name,
    write_workbench_closure_golden_check,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    check = build_workbench_closure_golden_check(
        baseline=args.baseline,
        closure_doc=args.closure_doc,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else Path("reports") / safe_workbench_closure_golden_check_dir_name()
    json_path, markdown_path = write_workbench_closure_golden_check(check, output_dir=output_dir)
    payload = {
        "schema": check["schema"],
        "status": check["status"],
        "golden_for": check["golden_for"],
        "check_count": check["check_count"],
        "failed_count": check["failed_count"],
        "artifacts": {
            "workbench_closure_golden_check_json_path": str(json_path),
            "workbench_closure_golden_check_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_workbench_closure_golden_check_markdown_zh(check))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if check["status"] == "ok" or args.allow_fail else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Backtest Workbench V1 closure docs against the baseline")
    parser.add_argument("--baseline", default="examples/backtest-workbench-v1-baseline.json")
    parser.add_argument("--closure-doc", default="docs/backtest-workbench-v1-closure.md")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    parser.add_argument("--allow-fail", action="store_true", help="Return 0 even when the check status is failed")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
