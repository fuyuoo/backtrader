"""Run a validated attbacktrader YAML run plan."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from attbacktrader.config import load_run_plan
from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
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
    progress_logger = _ProgressLogger(Path(args.progress_log)) if args.progress_log is not None else None
    try:
        _emit_cli_progress(progress_logger, stage="load_run_plan", status="started", config=args.config)
        run_plan = load_run_plan(args.config)

        if args.engine is not None:
            run_plan = run_plan.model_copy(
                update={"execution": run_plan.execution.model_copy(update={"engine": args.engine})}
            )
        _emit_cli_progress(
            progress_logger,
            stage="load_run_plan",
            status="completed",
            run_id=run_plan.run.id,
            engine=run_plan.execution.engine,
        )

        provider = None
        if run_plan.data.refresh_snapshots:
            if run_plan.data.provider != "tushare":
                raise SystemExit(f"Unsupported data provider: {run_plan.data.provider}")
            _emit_cli_progress(progress_logger, stage="build_provider", status="started", provider="tushare")
            provider = TushareProvider(
                read_tushare_token(args.token_file),
                rate_limit=tushare_rate_limit_config_from_args(args),
            )
            _emit_cli_progress(progress_logger, stage="build_provider", status="completed", provider="tushare")

        _emit_cli_progress(progress_logger, stage="execute_run_plan", status="started", run_id=run_plan.run.id)
        result = _execute_run_plan(
            run_plan,
            provider=provider,
            progress_logger=progress_logger,
            progress_interval_days=args.progress_interval_days,
        )
        _emit_cli_progress(progress_logger, stage="execute_run_plan", status="completed", run_id=result.run_id)

        artifact_paths = None
        if run_plan.output.persist and not args.no_persist:
            _emit_cli_progress(progress_logger, stage="write_artifacts", status="started", run_id=result.run_id)
            artifact_kwargs = {
                "output_root": args.output_root or run_plan.output.report_root,
            }
            if progress_logger is not None:
                artifact_kwargs["progress_callback"] = progress_logger.emit
            artifact_paths = write_run_artifacts(
                run_plan,
                result,
                **artifact_kwargs,
            )
            _emit_cli_progress(progress_logger, stage="write_artifacts", status="completed", run_id=result.run_id)

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
    except BaseException as exc:
        _emit_cli_progress(
            progress_logger,
            stage="run_plan_cli",
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise
    finally:
        if progress_logger is not None:
            progress_logger.close()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run attbacktrader from a YAML run plan")
    parser.add_argument("--config", required=True, help="Path to run.yaml")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    add_tushare_rate_limit_args(parser)
    parser.add_argument(
        "--engine",
        choices=["business", "backtrader", "baoma_v1_business"],
        default=None,
        help="Override execution.engine",
    )
    parser.add_argument("--output-root", default=None, help="Override output.report_root for persisted artifacts")
    parser.add_argument("--no-persist", action="store_true", help="Run without writing reports/{run_id} artifacts")
    parser.add_argument("--progress-log", default=None, help="Write NDJSON progress events to this file")
    parser.add_argument(
        "--progress-interval-days",
        type=int,
        default=50,
        help="Emit Baoma engine progress every N trade dates",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--summary-json", action="store_true", help="Print concise run summary JSON")
    output_group.add_argument("--full-json", action="store_true", help="Print the full execution payload JSON")
    args = parser.parse_args(argv)
    if args.progress_interval_days <= 0:
        parser.error("--progress-interval-days must be positive")
    return args


def _execute_run_plan(
    run_plan,
    *,
    provider,
    progress_logger: "_ProgressLogger | None",
    progress_interval_days: int,
):
    if progress_logger is None:
        return execute_run_plan(run_plan, provider=provider)
    return execute_run_plan(
        run_plan,
        provider=provider,
        progress_callback=progress_logger.emit,
        progress_interval_days=progress_interval_days,
    )


def _emit_cli_progress(
    progress_logger: "_ProgressLogger | None",
    *,
    stage: str,
    status: str,
    **fields: object,
) -> None:
    if progress_logger is None:
        return
    progress_logger.emit({"stage": stage, "status": status, **fields})


class _ProgressLogger:
    def __init__(self, path: Path) -> None:
        self._started_at = time.monotonic()
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("w", encoding="utf-8")

    def emit(self, event: dict[str, object]) -> None:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "elapsed_seconds": round(time.monotonic() - self._started_at, 3),
            **event,
        }
        self._file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


if __name__ == "__main__":
    raise SystemExit(main())
