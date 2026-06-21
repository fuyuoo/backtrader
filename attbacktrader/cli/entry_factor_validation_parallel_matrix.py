"""Run entry-factor validation candidates with a bounded process pool."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from attbacktrader.cli.entry_factor_validation_matrix import (
    _default_output_dir,
    _load_baseline,
    _load_json_mapping,
    _selected_candidates,
)
from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args
from attbacktrader.reports import (
    build_entry_factor_validation_matrix,
    render_entry_factor_validation_matrix_markdown_zh,
    to_jsonable,
    write_entry_factor_validation_matrix,
)


PARALLEL_MATRIX_STATUS_SCHEMA = "attbacktrader.entry_factor_validation_parallel_matrix_status.v1"


@dataclass
class _RunningCandidate:
    candidate: dict[str, Any]
    process: Any
    stdout_handle: TextIO
    stderr_handle: TextIO
    stdout_path: Path
    stderr_path: Path
    validation_json_path: Path
    started_at: float


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = run_parallel_matrix(args)

    if args.print_markdown:
        print(render_entry_factor_validation_matrix_markdown_zh(payload))
        return 0

    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def run_parallel_matrix(
    args: argparse.Namespace,
    *,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run selected candidates in parallel and write an aggregate matrix."""

    if args.max_workers <= 0:
        raise ValueError("--max-workers must be greater than 0")

    manifest_path = Path(args.manifest)
    manifest = _load_json_mapping(manifest_path)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(manifest, args.output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "parallel-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    selected = _selected_candidates(
        manifest,
        from_index=args.from_index,
        to_index=args.to_index,
        max_candidates=args.max_candidates,
    )
    selected_indexes = [int(candidate.get("candidate_index")) for candidate in selected]
    selected_by_index = {int(candidate.get("candidate_index")): candidate for candidate in selected}
    status_path = output_dir / "entry_factor_validation_parallel_status.json"
    statuses: dict[int, dict[str, Any]] = {}
    status_payload = _status_payload(
        args=args,
        manifest_path=manifest_path,
        output_dir=output_dir,
        selected_indexes=selected_indexes,
        statuses=statuses,
    )
    _write_status(status_path, status_payload)

    pending: deque[dict[str, Any]] = deque(selected)
    running: dict[int, _RunningCandidate] = {}
    failures: list[dict[str, Any]] = []
    stop_launching = False

    while pending or running:
        while pending and len(running) < args.max_workers and not stop_launching:
            candidate = pending.popleft()
            candidate_index = int(candidate.get("candidate_index"))
            validation_json_path = _validation_json_path(output_dir, candidate_index)

            if args.resume and validation_json_path.exists():
                statuses[candidate_index] = _candidate_status(
                    candidate,
                    status="resumed",
                    validation_json_path=validation_json_path,
                )
                _log(f"[resume] candidate-{candidate_index:03d} {validation_json_path}", quiet=args.quiet_progress)
                status_payload = _status_payload(
                    args=args,
                    manifest_path=manifest_path,
                    output_dir=output_dir,
                    selected_indexes=selected_indexes,
                    statuses=statuses,
                )
                _write_status(status_path, status_payload)
                continue

            running_candidate = _start_candidate(
                candidate,
                manifest_path=manifest_path,
                output_dir=output_dir,
                logs_dir=logs_dir,
                args=args,
                popen_factory=popen_factory,
                monotonic=monotonic,
            )
            running[candidate_index] = running_candidate
            statuses[candidate_index] = _candidate_status(
                candidate,
                status="running",
                validation_json_path=validation_json_path,
                stdout_log=running_candidate.stdout_path,
                stderr_log=running_candidate.stderr_path,
                started_at=_now_iso(),
            )
            _log(f"[start] candidate-{candidate_index:03d}", quiet=args.quiet_progress)
            status_payload = _status_payload(
                args=args,
                manifest_path=manifest_path,
                output_dir=output_dir,
                selected_indexes=selected_indexes,
                statuses=statuses,
            )
            _write_status(status_path, status_payload)

        completed_indexes: list[int] = []
        for candidate_index, running_candidate in list(running.items()):
            return_code = running_candidate.process.poll()
            if return_code is None:
                continue

            completed_indexes.append(candidate_index)
            _close_candidate_handles(running_candidate)
            duration_seconds = monotonic() - running_candidate.started_at
            record_exists = running_candidate.validation_json_path.exists()
            if return_code == 0 and record_exists:
                statuses[candidate_index] = _candidate_status(
                    running_candidate.candidate,
                    status="completed",
                    exit_code=return_code,
                    duration_seconds=duration_seconds,
                    validation_json_path=running_candidate.validation_json_path,
                    stdout_log=running_candidate.stdout_path,
                    stderr_log=running_candidate.stderr_path,
                    finished_at=_now_iso(),
                )
                _log(
                    f"[done] candidate-{candidate_index:03d} duration={duration_seconds:.1f}s",
                    quiet=args.quiet_progress,
                )
            else:
                status = "missing_record" if return_code == 0 else "failed"
                failure = _candidate_status(
                    running_candidate.candidate,
                    status=status,
                    exit_code=return_code,
                    duration_seconds=duration_seconds,
                    validation_json_path=running_candidate.validation_json_path,
                    stdout_log=running_candidate.stdout_path,
                    stderr_log=running_candidate.stderr_path,
                    finished_at=_now_iso(),
                )
                statuses[candidate_index] = failure
                failures.append(failure)
                _log(
                    f"[{status}] candidate-{candidate_index:03d} exit={return_code} duration={duration_seconds:.1f}s",
                    quiet=args.quiet_progress,
                )
                if args.fail_fast:
                    stop_launching = True

        for candidate_index in completed_indexes:
            running.pop(candidate_index, None)

        status_payload = _status_payload(
            args=args,
            manifest_path=manifest_path,
            output_dir=output_dir,
            selected_indexes=selected_indexes,
            statuses=statuses,
        )
        _write_status(status_path, status_payload)

        if running or (pending and not stop_launching):
            sleep(args.poll_seconds)

    if failures and not args.allow_partial:
        status_payload = _status_payload(
            args=args,
            manifest_path=manifest_path,
            output_dir=output_dir,
            selected_indexes=selected_indexes,
            statuses=statuses,
            finished_at=_now_iso(),
            failed=True,
        )
        _write_status(status_path, status_payload)
        raise SystemExit(f"{len(failures)} candidate validation run(s) failed; see {status_path}")

    matrix_candidates = _matrix_candidates(
        manifest,
        output_dir=output_dir,
        selected_by_index=selected_by_index,
        matrix_scope=args.matrix_scope,
    )
    record_paths = [_validation_json_path(output_dir, int(candidate.get("candidate_index"))) for candidate in matrix_candidates]
    missing_records = [path for path in record_paths if not path.exists()]
    if missing_records and not args.allow_partial:
        missing = ", ".join(str(path) for path in missing_records[:5])
        raise SystemExit(f"missing validation record(s), first missing: {missing}")

    existing_record_paths = [path for path in record_paths if path.exists()]
    if not existing_record_paths:
        raise SystemExit("no validation records available for matrix")

    baseline_run_id, baseline_metrics = _load_baseline(
        manifest,
        output_root=args.output_root,
        baseline_run_dir=args.baseline_run_dir,
    )
    matrix = build_entry_factor_validation_matrix(
        existing_record_paths,
        baseline_metrics=baseline_metrics,
        baseline_run_id=baseline_run_id,
        source_manifest=manifest_path,
    )
    matrix["artifacts"] = {
        "validation_records": [str(path) for path in existing_record_paths],
        "parallel_status": str(status_path),
    }
    _, _, payload = write_entry_factor_validation_matrix(matrix, output_dir=output_dir)

    status_payload = _status_payload(
        args=args,
        manifest_path=manifest_path,
        output_dir=output_dir,
        selected_indexes=selected_indexes,
        statuses=statuses,
        finished_at=_now_iso(),
        matrix_json=_as_path(payload.get("artifacts"), "matrix_json"),
        matrix_markdown_zh=_as_path(payload.get("artifacts"), "matrix_markdown_zh"),
    )
    _write_status(status_path, status_payload)
    return payload


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 1 entry-factor validation candidates in parallel")
    parser.add_argument("--manifest", required=True, help="Path to entry_factor_validation_manifest.json")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    add_tushare_rate_limit_args(parser)
    parser.add_argument("--output-root", default=None, help="Override output.report_root for normal run artifacts")
    parser.add_argument("--output-dir", default=None, help="Matrix output directory")
    parser.add_argument("--baseline-run-dir", default=None, help="Optional baseline reports/{base_run_id} directory")
    parser.add_argument("--from-index", type=int, default=None, help="First candidate_index to run")
    parser.add_argument("--to-index", type=int, default=None, help="Last candidate_index to run")
    parser.add_argument("--max-candidates", type=int, default=None, help="Limit number of candidates selected")
    parser.add_argument("--max-workers", type=int, default=min(os.cpu_count() or 1, 4), help="Maximum concurrent candidates")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Seconds between process-pool polls")
    parser.add_argument("--resume", action="store_true", help="Reuse existing candidate validation records")
    parser.add_argument("--no-persist", action="store_true", help="Run candidates without normal reports/{run_id} artifacts")
    parser.add_argument("--allow-partial", action="store_true", help="Build a matrix from completed records after failures")
    parser.add_argument("--fail-fast", action="store_true", help="Stop launching new candidates after the first failure")
    parser.add_argument(
        "--matrix-scope",
        choices=("available", "selected"),
        default="available",
        help="Use all available records in output-dir or only this invocation's selected candidates",
    )
    parser.add_argument("--python-executable", default=sys.executable, help="Python executable used for child candidates")
    parser.add_argument("--quiet-progress", action="store_true", help="Suppress progress logs on stderr")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _start_candidate(
    candidate: Mapping[str, Any],
    *,
    manifest_path: Path,
    output_dir: Path,
    logs_dir: Path,
    args: argparse.Namespace,
    popen_factory: Callable[..., Any],
    monotonic: Callable[[], float],
) -> _RunningCandidate:
    candidate_index = int(candidate.get("candidate_index"))
    validation_output_dir = output_dir / f"candidate-{candidate_index:03d}"
    validation_output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / f"candidate-{candidate_index:03d}.out.log"
    stderr_path = logs_dir / f"candidate-{candidate_index:03d}.err.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    command = _child_command(
        candidate_index,
        manifest_path=manifest_path,
        validation_output_dir=validation_output_dir,
        args=args,
    )
    process = popen_factory(
        command,
        stdout=stdout_handle,
        stderr=stderr_handle,
        cwd=Path.cwd(),
    )
    return _RunningCandidate(
        candidate=dict(candidate),
        process=process,
        stdout_handle=stdout_handle,
        stderr_handle=stderr_handle,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        validation_json_path=validation_output_dir / "entry_factor_validation_run.json",
        started_at=monotonic(),
    )


def _child_command(
    candidate_index: int,
    *,
    manifest_path: Path,
    validation_output_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        str(args.python_executable),
        "-m",
        "attbacktrader.cli.entry_factor_validation_run",
        "--manifest",
        str(manifest_path),
        "--candidate-index",
        str(candidate_index),
        "--output-dir",
        str(validation_output_dir),
        "--token-file",
        str(args.token_file),
    ]
    if args.output_root:
        command.extend(["--output-root", str(args.output_root)])
    if args.no_persist:
        command.append("--no-persist")
    _append_optional_arg(command, "--tushare-requests-per-minute", args.tushare_requests_per_minute)
    _append_optional_arg(command, "--tushare-retry-attempts", args.tushare_retry_attempts)
    _append_optional_arg(command, "--tushare-date-window-days", args.tushare_date_window_days)
    return command


def _matrix_candidates(
    manifest: Mapping[str, Any],
    *,
    output_dir: Path,
    selected_by_index: Mapping[int, Mapping[str, Any]],
    matrix_scope: str,
) -> list[dict[str, Any]]:
    manifest_candidates = {
        int(candidate.get("candidate_index")): dict(candidate)
        for candidate in _selected_candidates(manifest, from_index=None, to_index=None, max_candidates=None)
    }
    if matrix_scope == "selected":
        return [dict(candidate) for _, candidate in sorted(selected_by_index.items())]
    return [
        candidate
        for candidate_index, candidate in sorted(manifest_candidates.items())
        if _validation_json_path(output_dir, candidate_index).exists()
    ]


def _candidate_status(
    candidate: Mapping[str, Any],
    *,
    status: str,
    validation_json_path: Path,
    exit_code: int | None = None,
    duration_seconds: float | None = None,
    stdout_log: Path | None = None,
    stderr_log: Path | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "candidate_index": candidate.get("candidate_index"),
        "run_id": candidate.get("run_id"),
        "field_key": candidate.get("field_key"),
        "value": candidate.get("value"),
        "action": candidate.get("action"),
        "status": status,
        "validation_json": str(validation_json_path),
    }
    if exit_code is not None:
        payload["exit_code"] = exit_code
    if duration_seconds is not None:
        payload["duration_seconds"] = round(duration_seconds, 3)
    if stdout_log is not None:
        payload["stdout_log"] = str(stdout_log)
    if stderr_log is not None:
        payload["stderr_log"] = str(stderr_log)
    if started_at is not None:
        payload["started_at"] = started_at
    if finished_at is not None:
        payload["finished_at"] = finished_at
    return payload


def _status_payload(
    *,
    args: argparse.Namespace,
    manifest_path: Path,
    output_dir: Path,
    selected_indexes: Sequence[int],
    statuses: Mapping[int, Mapping[str, Any]],
    finished_at: str | None = None,
    failed: bool = False,
    matrix_json: str | None = None,
    matrix_markdown_zh: str | None = None,
) -> dict[str, Any]:
    ordered_statuses = [dict(statuses[index]) for index in sorted(statuses)]
    status_counts: dict[str, int] = {}
    for item in ordered_statuses:
        status = str(item.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
    payload: dict[str, Any] = {
        "schema": PARALLEL_MATRIX_STATUS_SCHEMA,
        "manifest": str(manifest_path),
        "output_dir": str(output_dir),
        "selected_indexes": list(selected_indexes),
        "selected_count": len(selected_indexes),
        "max_workers": args.max_workers,
        "resume": bool(args.resume),
        "no_persist": bool(args.no_persist),
        "matrix_scope": args.matrix_scope,
        "status": "failed" if failed else ("complete" if finished_at else "running"),
        "status_counts": status_counts,
        "candidates": ordered_statuses,
        "updated_at": _now_iso(),
    }
    if finished_at is not None:
        payload["finished_at"] = finished_at
    if matrix_json is not None:
        payload["matrix_json"] = matrix_json
    if matrix_markdown_zh is not None:
        payload["matrix_markdown_zh"] = matrix_markdown_zh
    return payload


def _write_status(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _append_optional_arg(command: list[str], name: str, value: Any) -> None:
    if value is not None:
        command.extend([name, str(value)])


def _validation_json_path(output_dir: Path, candidate_index: int) -> Path:
    return output_dir / f"candidate-{candidate_index:03d}" / "entry_factor_validation_run.json"


def _close_candidate_handles(running_candidate: _RunningCandidate) -> None:
    running_candidate.stdout_handle.close()
    running_candidate.stderr_handle.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_path(artifacts: object, key: str) -> str | None:
    if isinstance(artifacts, Mapping) and artifacts.get(key) is not None:
        return str(artifacts.get(key))
    return None


def _log(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
