"""Run Stage 1 entry-factor validation candidates and build a matrix."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from attbacktrader.cli.entry_factor_validation_run import load_candidate_run_plan
from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
from attbacktrader.data.providers import TushareProvider, read_tushare_token
from attbacktrader.reports import (
    build_entry_factor_validation_matrix,
    build_entry_factor_validation_run_record,
    build_run_execution_summary,
    render_entry_factor_validation_matrix_markdown_zh,
    to_jsonable,
    write_entry_factor_validation_matrix,
    write_entry_factor_validation_run_record,
    write_run_artifacts,
)
from attbacktrader.runners import execute_run_plan, run_entry_factor_validation_batch
from attbacktrader.runners.prepared_data import PreparedRunDataCache


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest_path = Path(args.manifest)
    manifest = _load_json_mapping(manifest_path)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(manifest, args.output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_data_cache = PreparedRunDataCache()

    batch_result = run_entry_factor_validation_batch(
        manifest=manifest,
        manifest_path=manifest_path,
        output_dir=output_dir,
        from_index=args.from_index,
        to_index=args.to_index,
        max_candidates=args.max_candidates,
        resume=args.resume,
        execute_candidate=lambda candidate, validation_output_dir: _execute_candidate(
                manifest=manifest,
                candidate=candidate,
                manifest_path=manifest_path,
                validation_output_dir=validation_output_dir,
                output_root=args.output_root,
                no_persist=args.no_persist,
                token_file=args.token_file,
                tushare_args=args,
                prepared_data_cache=prepared_data_cache,
        ),
    )

    baseline_run_id, baseline_metrics = _load_baseline(manifest, output_root=args.output_root, baseline_run_dir=args.baseline_run_dir)
    matrix = build_entry_factor_validation_matrix(
        batch_result.records,
        baseline_metrics=baseline_metrics,
        baseline_run_id=baseline_run_id,
        source_manifest=manifest_path,
    )
    matrix["artifacts"] = {
        "validation_records": [str(path) for path in batch_result.record_paths],
        "batch_status": str(batch_result.status_path),
    }
    _, _, payload = write_entry_factor_validation_matrix(matrix, output_dir=output_dir)

    if args.print_markdown:
        print(render_entry_factor_validation_matrix_markdown_zh(payload))
        return 0

    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def _execute_candidate(
    *,
    manifest: Mapping[str, Any],
    candidate: Mapping[str, Any],
    manifest_path: Path,
    validation_output_dir: Path,
    output_root: str | Path | None,
    no_persist: bool,
    token_file: str,
    tushare_args: argparse.Namespace,
    prepared_data_cache: PreparedRunDataCache | None = None,
) -> dict[str, Any]:
    run_plan, run_plan_path = load_candidate_run_plan(candidate, manifest_path=manifest_path)
    provider = None
    if run_plan.data.refresh_snapshots:
        if run_plan.data.provider != "tushare":
            raise SystemExit(f"Unsupported data provider: {run_plan.data.provider}")
        provider = TushareProvider(
            read_tushare_token(token_file),
            rate_limit=tushare_rate_limit_config_from_args(tushare_args),
        )

    result = execute_run_plan(run_plan, provider=provider, prepared_data_cache=prepared_data_cache)
    artifact_paths = None
    if run_plan.output.persist and not no_persist:
        artifact_paths = write_run_artifacts(
            run_plan,
            result,
            output_root=output_root or run_plan.output.report_root,
        )

    run_summary = build_run_execution_summary(run_plan, result, artifact_paths=artifact_paths)
    record = build_entry_factor_validation_run_record(
        manifest=manifest,
        candidate=candidate,
        run_plan=run_plan,
        run_plan_path=run_plan_path,
        run_summary=run_summary,
        artifact_paths=artifact_paths,
        validation_output_dir=validation_output_dir,
    )
    _, _, payload = write_entry_factor_validation_run_record(record, output_dir=validation_output_dir)
    return payload


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 1 single-factor entry validation matrix")
    parser.add_argument("--manifest", required=True, help="Path to entry_factor_validation_manifest.json")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    add_tushare_rate_limit_args(parser)
    parser.add_argument("--output-root", default=None, help="Override output.report_root for normal run artifacts")
    parser.add_argument("--output-dir", default=None, help="Matrix output directory")
    parser.add_argument("--baseline-run-dir", default=None, help="Optional baseline reports/{base_run_id} directory")
    parser.add_argument("--from-index", type=int, default=None, help="First candidate_index to run")
    parser.add_argument("--to-index", type=int, default=None, help="Last candidate_index to run")
    parser.add_argument("--max-candidates", type=int, default=None, help="Limit number of candidates for this invocation")
    parser.add_argument("--resume", action="store_true", help="Reuse existing candidate validation records")
    parser.add_argument("--no-persist", action="store_true", help="Run candidates without normal reports/{run_id} artifacts")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _selected_candidates(
    manifest: Mapping[str, Any],
    *,
    from_index: int | None,
    to_index: int | None,
    max_candidates: int | None,
) -> list[dict[str, Any]]:
    candidates = sorted(
        (dict(_as_mapping(candidate)) for candidate in _as_sequence(manifest.get("candidates"))),
        key=lambda candidate: int(candidate.get("candidate_index") or 0),
    )
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        index = int(candidate.get("candidate_index") or 0)
        if from_index is not None and index < from_index:
            continue
        if to_index is not None and index > to_index:
            continue
        selected.append(candidate)
        if max_candidates is not None and len(selected) >= max_candidates:
            break
    if not selected:
        raise ValueError("no manifest candidates selected")
    return selected


def _load_baseline(
    manifest: Mapping[str, Any],
    *,
    output_root: str | Path | None,
    baseline_run_dir: str | Path | None,
) -> tuple[str | None, dict[str, Any]]:
    base_run_id = str(manifest.get("base_run_id") or "") or None
    baseline_dir = Path(baseline_run_dir) if baseline_run_dir else None
    if baseline_dir is None and base_run_id:
        baseline_dir = Path(output_root or "reports") / _safe_path_name(base_run_id)
    if baseline_dir is None:
        return base_run_id, {}

    report_path = baseline_dir / "report.json"
    if not report_path.exists():
        return base_run_id, {}
    report = _load_json_mapping(report_path)
    return base_run_id, _baseline_metrics_from_report(report)


def _baseline_metrics_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    returns = _as_mapping(report.get("returns"))
    risk = _as_mapping(report.get("risk"))
    trade_quality = _as_mapping(report.get("trade_quality"))
    return {
        "cumulative_return": returns.get("cumulative_return"),
        "max_drawdown": risk.get("max_drawdown"),
        "trade_count": trade_quality.get("trade_count"),
        "win_rate": trade_quality.get("win_rate"),
        "profit_loss_ratio": trade_quality.get("profit_loss_ratio"),
    }


def _default_output_dir(manifest: Mapping[str, Any], output_root: str | Path | None) -> Path:
    root = Path(output_root or "reports")
    base_run_id = str(manifest.get("base_run_id") or "entry-factor-validation")
    return root / f"entry-factor-validation-matrix-{_safe_path_name(base_run_id)}"


def _load_json_mapping(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{target} must contain a JSON object")
    return payload


def _safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe or "run"


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


if __name__ == "__main__":
    raise SystemExit(main())
