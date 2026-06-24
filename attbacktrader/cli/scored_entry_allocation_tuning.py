"""CLI for scored entry allocation tuning planning and reports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from attbacktrader.reports import (
    build_scored_allocation_report_package,
    build_scored_entry_allocation_tuning_contract,
    build_strategy_decision_event_table_from_signal_audit,
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
    output_dir = Path(args.output_dir)

    if args.build_decision_event_table and args.run_full_study:
        raise ValueError("--build-decision-event-table cannot be combined with --run-full-study")

    if args.build_decision_event_table:
        return _build_decision_event_table(args, output_dir=output_dir)

    if args.mode != "dry-run":
        require_optuna_for_tuning()

    contract = build_scored_entry_allocation_tuning_contract(mode=args.mode, output_dir=output_dir)
    if args.run_full_study:
        return _run_full_study(args, contract=contract, output_dir=output_dir)

    _, _, payload = write_scored_entry_allocation_tuning_contract(contract, output_dir=output_dir)

    if args.print_markdown:
        print(render_scored_entry_allocation_tuning_contract_markdown(payload))
    else:
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def _build_decision_event_table(args: argparse.Namespace, *, output_dir: Path) -> int:
    signal_audit_path = _required_path(args.signal_audit, "--signal-audit", context="--build-decision-event-table")
    run_plan_path = _required_path(args.run_plan, "--run-plan", context="--build-decision-event-table")
    signal_audit = _load_json(signal_audit_path)
    run_plan = _load_json_mapping(str(run_plan_path), "--run-plan", context="--build-decision-event-table")
    stock_pool_path = _stock_pool_file_from_args(args, run_plan=run_plan, run_plan_path=run_plan_path)
    stock_pool_order_by_symbol = _read_stock_pool_order_by_symbol(stock_pool_path)
    cache_inputs = _decision_cache_inputs_from_run_artifacts(
        run_plan,
        signal_audit=signal_audit,
        stock_pool_path=stock_pool_path,
        stock_pool_order_by_symbol=stock_pool_order_by_symbol,
    )
    table = build_strategy_decision_event_table_from_signal_audit(
        signal_audit,
        cache_inputs=cache_inputs,
        stock_pool_order_by_symbol=stock_pool_order_by_symbol,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    decision_table_path = output_dir / "decision_event_table.json"
    decision_table_path.write_text(json.dumps(to_jsonable(table), ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {
        "decision_event_table": table,
        "artifacts": {"decision_event_table_json": str(decision_table_path)},
    }
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


def _load_json_mapping(path_value: str | None, option_name: str, *, context: str = "--run-full-study") -> dict[str, Any]:
    path = _required_path(path_value, option_name, context=context)
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


def _required_path(path_value: str | None, option_name: str, *, context: str = "--run-full-study") -> Path:
    if not path_value:
        raise ValueError(f"{option_name} is required when {context} is set")
    return Path(path_value)


def _stock_pool_file_from_args(args: argparse.Namespace, *, run_plan: dict[str, Any], run_plan_path: Path) -> Path:
    if args.stock_pool_file:
        return Path(args.stock_pool_file)
    data = _mapping(run_plan.get("data"), "run_plan.data")
    stock_pool_value = data.get("stock_pool_file")
    if not stock_pool_value:
        raise ValueError("--stock-pool-file is required when run_plan.data.stock_pool_file is missing")
    stock_pool_path = Path(str(stock_pool_value))
    if stock_pool_path.is_absolute():
        return stock_pool_path
    cwd_candidate = Path.cwd() / stock_pool_path
    if cwd_candidate.exists():
        return cwd_candidate
    return run_plan_path.parent / stock_pool_path


def _read_stock_pool_order_by_symbol(path: Path) -> dict[str, int]:
    if not path.exists():
        raise ValueError(f"stock pool file does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"stock pool file has no header: {path}")
        symbol_field = "ts_code" if "ts_code" in reader.fieldnames else "symbol" if "symbol" in reader.fieldnames else None
        if symbol_field is None:
            raise ValueError(f"stock pool file must contain ts_code or symbol column: {path}")
        order_by_symbol: dict[str, int] = {}
        for index, row in enumerate(reader, start=1):
            symbol = str(row.get(symbol_field) or "").strip()
            if not symbol:
                continue
            order_by_symbol.setdefault(symbol, index)
    if not order_by_symbol:
        raise ValueError(f"stock pool file has no symbols: {path}")
    return order_by_symbol


def _decision_cache_inputs_from_run_artifacts(
    run_plan: dict[str, Any],
    *,
    signal_audit: Any,
    stock_pool_path: Path,
    stock_pool_order_by_symbol: dict[str, int],
) -> dict[str, Any]:
    run = _mapping(run_plan.get("run"), "run_plan.run")
    data = _mapping(run_plan.get("data"), "run_plan.data")
    strategy = _mapping(run_plan.get("strategy"), "run_plan.strategy")
    return {
        "data_snapshot_identity": {
            "run_id": run.get("id"),
            "snapshot_root": data.get("snapshot_root"),
            "provider": data.get("provider"),
            "price_adjustment": data.get("price_adjustment"),
        },
        "stock_pool_identity": {
            "path": str(stock_pool_path),
            "sha256": _file_sha256(stock_pool_path),
            "symbol_count": len(stock_pool_order_by_symbol),
        },
        "strategy_signal_parameters": {
            "template": strategy.get("template"),
            "entry_method": strategy.get("entry_method"),
            "entry_params": strategy.get("entry_params") or {},
            "profit_taking_method": strategy.get("profit_taking_method"),
            "stop_loss_method": strategy.get("stop_loss_method"),
            "add_on_method": strategy.get("add_on_method"),
            "add_on_params": strategy.get("add_on_params") or {},
        },
        "factor_field_set": _factor_field_set_from_signal_audit(signal_audit),
        "date_range": {
            "start": run.get("from_date"),
            "end": run.get("to_date"),
        },
        "event_schema_version": 1,
    }


def _factor_field_set_from_signal_audit(signal_audit: Any) -> list[str]:
    if isinstance(signal_audit, dict) and signal_audit.get("schema") == "attbacktrader.compact_signal_audit.v1":
        raise ValueError("--signal-audit requires full signal_audit; compact signal_audit cannot build decision_event_table")
    if not isinstance(signal_audit, list):
        raise ValueError("--signal-audit must point to a full signal_audit JSON array")
    fields: set[str] = set()
    for row in signal_audit:
        if not isinstance(row, dict):
            raise ValueError("full signal_audit rows must be JSON objects")
        intent_type = str(row.get("intent_type") or "")
        if intent_type not in {"enter", "exit", "exit_profit", "exit_loss", "add_on"}:
            continue
        signal_values = _mapping(row.get("signal_values"), "signal_audit.signal_values")
        attribution = _mapping(signal_values.get("attribution"), "signal_audit.signal_values.attribution")
        for bucket in ("values", "categories", "checks"):
            fields.update(str(key) for key in _mapping(attribution.get(bucket), f"attribution.{bucket}"))
        fields.update(str(key) for key in _mapping(signal_values.get("evidence"), "signal_values.evidence"))
    if not fields:
        raise ValueError("full signal_audit has no actionable decision evidence fields")
    return sorted(fields)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan scored entry allocation tuning")
    parser.add_argument("--mode", choices=("dry-run", "smoke", "standard", "sensitivity"), default="dry-run")
    parser.add_argument("--output-dir", default=str(Path("reports") / "scored-entry-allocation-tuning"))
    parser.add_argument("--build-decision-event-table", action="store_true")
    parser.add_argument("--signal-audit")
    parser.add_argument("--run-plan")
    parser.add_argument("--stock-pool-file")
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
