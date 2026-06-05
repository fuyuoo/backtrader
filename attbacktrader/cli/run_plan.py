"""Run a validated attbacktrader YAML run plan."""

from __future__ import annotations

import argparse
import json

from attbacktrader.config import load_run_plan
from attbacktrader.data.providers import TushareProvider, read_tushare_token
from attbacktrader.reports import (
    build_run_execution_summary,
    render_run_execution_summary_text_zh,
    to_jsonable,
    write_run_artifacts,
)
from attbacktrader.runners import execute_run_plan


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_plan = load_run_plan(args.config)

    if args.engine is not None:
        run_plan = run_plan.model_copy(
            update={"execution": run_plan.execution.model_copy(update={"engine": args.engine})}
        )

    provider = None
    if run_plan.data.refresh_snapshots:
        if run_plan.data.provider != "tushare":
            raise SystemExit(f"Unsupported data provider: {run_plan.data.provider}")
        provider = TushareProvider(read_tushare_token(args.token_file))

    result = execute_run_plan(run_plan, provider=provider)
    artifact_paths = None
    if run_plan.output.persist and not args.no_persist:
        artifact_paths = write_run_artifacts(
            run_plan,
            result,
            output_root=args.output_root or run_plan.output.report_root,
        )

    if args.full_json:
        payload = to_jsonable(result)
        if artifact_paths is not None:
            payload["artifacts"] = to_jsonable(artifact_paths)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    summary = build_run_execution_summary(run_plan, result, artifact_paths=artifact_paths)
    if args.summary_json:
        print(json.dumps(to_jsonable(summary), ensure_ascii=False, indent=2))
        return 0

    print(render_run_execution_summary_text_zh(summary))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run attbacktrader from a YAML run plan")
    parser.add_argument("--config", required=True, help="Path to run.yaml")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    parser.add_argument("--engine", choices=["business", "backtrader"], default=None, help="Override execution.engine")
    parser.add_argument("--output-root", default=None, help="Override output.report_root for persisted artifacts")
    parser.add_argument("--no-persist", action="store_true", help="Run without writing reports/{run_id} artifacts")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--summary-json", action="store_true", help="Print concise run summary JSON")
    output_group.add_argument("--full-json", action="store_true", help="Print the full execution payload JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
