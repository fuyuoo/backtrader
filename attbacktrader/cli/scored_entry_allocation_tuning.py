"""CLI for scored entry allocation tuning planning and reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_scored_entry_allocation_tuning_contract,
    render_scored_entry_allocation_tuning_contract_markdown,
    require_optuna_for_tuning,
    write_scored_entry_allocation_tuning_contract,
)
from attbacktrader.reports.writer import to_jsonable


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.mode != "dry-run":
        require_optuna_for_tuning()

    output_dir = Path(args.output_dir)
    contract = build_scored_entry_allocation_tuning_contract(mode=args.mode, output_dir=output_dir)
    _, _, payload = write_scored_entry_allocation_tuning_contract(contract, output_dir=output_dir)

    if args.print_markdown:
        print(render_scored_entry_allocation_tuning_contract_markdown(payload))
    else:
        print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan scored entry allocation tuning")
    parser.add_argument("--mode", choices=("dry-run", "smoke", "standard", "sensitivity"), default="dry-run")
    parser.add_argument("--output-dir", default=str(Path("reports") / "scored-entry-allocation-tuning"))
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
