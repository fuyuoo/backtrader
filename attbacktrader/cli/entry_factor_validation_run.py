"""Execute one entry-factor validation candidate from a manifest."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
from attbacktrader.config import RunPlan
from attbacktrader.data.providers import TushareProvider, read_tushare_token
from attbacktrader.reports import (
    build_entry_factor_validation_run_record,
    build_run_execution_summary,
    render_entry_factor_validation_run_markdown_zh,
    to_jsonable,
    write_entry_factor_validation_run_record,
    write_run_artifacts,
)
from attbacktrader.runners import execute_run_plan


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest_path = Path(args.manifest)
    manifest = _load_json_mapping(manifest_path)
    candidate = select_entry_factor_validation_candidate(
        manifest,
        candidate_index=args.candidate_index,
        run_id=args.run_id,
    )
    run_plan, run_plan_path = load_candidate_run_plan(candidate, manifest_path=manifest_path)

    provider = None
    if run_plan.data.refresh_snapshots:
        if run_plan.data.provider != "tushare":
            raise SystemExit(f"Unsupported data provider: {run_plan.data.provider}")
        provider = TushareProvider(
            read_tushare_token(args.token_file),
            rate_limit=tushare_rate_limit_config_from_args(args),
        )

    result = execute_run_plan(run_plan, provider=provider)
    artifact_paths = None
    if run_plan.output.persist and not args.no_persist:
        artifact_paths = write_run_artifacts(
            run_plan,
            result,
            output_root=args.output_root or run_plan.output.report_root,
        )

    run_summary = build_run_execution_summary(run_plan, result, artifact_paths=artifact_paths)
    validation_output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(run_plan, args.output_root)
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

    if args.print_markdown:
        print(render_entry_factor_validation_run_markdown_zh(payload))
        return 0

    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def select_entry_factor_validation_candidate(
    manifest: Mapping[str, Any],
    *,
    candidate_index: int | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Select exactly one candidate from an entry-factor validation manifest."""

    candidates = [dict(_as_mapping(candidate)) for candidate in _as_sequence(manifest.get("candidates"))]
    if not candidates:
        raise ValueError("manifest has no candidates")

    if run_id:
        for candidate in candidates:
            if candidate.get("run_id") == run_id:
                return candidate
        raise ValueError(f"run_id not found in manifest: {run_id}")

    index = 1 if candidate_index is None else int(candidate_index)
    for candidate in candidates:
        if int(candidate.get("candidate_index") or -1) == index:
            return candidate
    raise ValueError(f"candidate_index not found in manifest: {index}")


def load_candidate_run_plan(
    candidate: Mapping[str, Any],
    *,
    manifest_path: str | Path,
) -> tuple[RunPlan, Path | None]:
    """Load the candidate RunPlan from its YAML path or embedded manifest payload."""

    run_plan_path_value = candidate.get("run_plan_path")
    if run_plan_path_value:
        run_plan_path = _resolve_candidate_path(run_plan_path_value, manifest_path=Path(manifest_path))
        payload = yaml.safe_load(run_plan_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"{run_plan_path} must contain a YAML mapping")
        return RunPlan.from_mapping(payload), run_plan_path

    embedded = candidate.get("run_plan")
    if not isinstance(embedded, Mapping):
        raise ValueError("candidate must include run_plan_path or embedded run_plan")
    return RunPlan.from_mapping(embedded), None


def build_entry_factor_validation_run_record(*args, **kwargs):
    from attbacktrader.reports.entry_factor_validation_run import build_entry_factor_validation_run_record as _build

    return _build(*args, **kwargs)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one entry-factor validation candidate from a manifest")
    parser.add_argument("--manifest", required=True, help="Path to entry_factor_validation_manifest.json")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--candidate-index", type=int, default=None, help="1-based manifest candidate_index")
    selector.add_argument("--run-id", default=None, help="Candidate run_id to execute")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    add_tushare_rate_limit_args(parser)
    parser.add_argument("--output-root", default=None, help="Override output.report_root for normal run artifacts")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for entry_factor_validation_run.json/zh.md; defaults under report root",
    )
    parser.add_argument("--no-persist", action="store_true", help="Run without writing normal reports/{run_id} artifacts")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _load_json_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _resolve_candidate_path(value: object, *, manifest_path: Path) -> Path:
    path = Path(str(value))
    if path.is_absolute() or path.exists():
        return path
    manifest_relative = manifest_path.parent / path
    if manifest_relative.exists():
        return manifest_relative
    return path


def _default_output_dir(run_plan: RunPlan, output_root: str | Path | None) -> Path:
    root = Path(output_root or run_plan.output.report_root)
    return root / "entry-factor-validation" / _safe_path_name(run_plan.run.id)


def _safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe or "run"


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


if __name__ == "__main__":
    raise SystemExit(main())
