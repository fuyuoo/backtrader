"""CLI for scored entry allocation tuning planning and reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from attbacktrader.reports import (
    build_scored_allocation_report_package,
    build_scored_entry_allocation_tuning_contract,
    render_scored_entry_allocation_tuning_contract_markdown,
    render_scored_allocation_report_package_markdown_zh,
    require_optuna_for_tuning,
    run_full_walk_forward_tuning,
    write_full_walk_forward_tuning_run,
    write_scored_allocation_report_package,
    write_scored_entry_allocation_tuning_contract,
)
from attbacktrader.reports.writer import to_jsonable


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.mode != "dry-run":
        require_optuna_for_tuning()

    output_dir = Path(args.output_dir)
    contract = build_scored_entry_allocation_tuning_contract(mode=args.mode, output_dir=output_dir)
    if args.run_full_study:
        return _run_full_study(args, contract=contract, output_dir=output_dir)

    _, _, payload = write_scored_entry_allocation_tuning_contract(contract, output_dir=output_dir)

    if args.print_markdown:
        print(render_scored_entry_allocation_tuning_contract_markdown(payload))
    else:
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def _run_full_study(args: argparse.Namespace, *, contract: dict[str, Any], output_dir: Path) -> int:
    if args.mode not in {"smoke", "standard"}:
        raise ValueError("--run-full-study supports only --mode smoke or --mode standard")

    decision_event_table = _load_json_mapping(args.decision_event_table, "--decision-event-table")
    stage_a_trials = _load_json_array_of_objects(args.stage_a_trials, "--stage-a-trials")
    stage_b_trials = _load_json_array_of_objects(args.stage_b_trials, "--stage-b-trials")
    completed_artifacts = (
        _load_json_mapping(args.completed_artifacts, "--completed-artifacts")
        if args.completed_artifacts
        else None
    )

    _, _, contract_payload = write_scored_entry_allocation_tuning_contract(contract, output_dir=output_dir)
    run_result = run_full_walk_forward_tuning(
        decision_event_table,
        contract=contract_payload,
        mode=args.mode,
        stage_a_trial_parameter_sets=stage_a_trials,
        stage_b_trial_parameter_sets=stage_b_trials,
        completed_artifacts=completed_artifacts,
        minimum_train_trades_per_year=args.minimum_train_trades_per_year,
    )
    _, run_payload = write_full_walk_forward_tuning_run(run_result, output_dir=output_dir)
    report_package = build_scored_allocation_report_package(run_result)
    _, package_payload = write_scored_allocation_report_package(report_package, output_dir=output_dir)

    payload = {
        "mode": args.mode,
        "contract": contract_payload,
        "full_walk_forward_run": run_payload,
        "report_package": package_payload,
    }
    if args.print_markdown:
        print(render_scored_allocation_report_package_markdown_zh(package_payload))
    else:
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def _load_json_mapping(path_value: str | None, option_name: str) -> dict[str, Any]:
    path = _required_path(path_value, option_name)
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{option_name} must point to a JSON object: {path}")
    return payload


def _load_json_array_of_objects(path_value: str | None, option_name: str) -> list[dict[str, Any]]:
    path = _required_path(path_value, option_name)
    payload = _load_json(path)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError(f"{option_name} must point to a JSON array of objects: {path}")
    return payload


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _required_path(path_value: str | None, option_name: str) -> Path:
    if not path_value:
        raise ValueError(f"{option_name} is required when --run-full-study is set")
    return Path(path_value)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan scored entry allocation tuning")
    parser.add_argument("--mode", choices=("dry-run", "smoke", "standard", "sensitivity"), default="dry-run")
    parser.add_argument("--output-dir", default=str(Path("reports") / "scored-entry-allocation-tuning"))
    parser.add_argument("--run-full-study", action="store_true")
    parser.add_argument("--decision-event-table")
    parser.add_argument("--stage-a-trials")
    parser.add_argument("--stage-b-trials")
    parser.add_argument("--completed-artifacts")
    parser.add_argument("--minimum-train-trades-per-year", type=int)
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
