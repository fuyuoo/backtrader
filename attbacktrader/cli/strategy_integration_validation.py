"""Validate a run plan's strategy integration without running a backtest."""

from __future__ import annotations

import argparse
import json

from attbacktrader.config import load_run_plan
from attbacktrader.strategies.integration_validation import (
    build_strategy_integration_validation_failure,
    render_strategy_integration_validation_text_zh,
    validate_run_plan_strategy_integration,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        run_plan = load_run_plan(args.config)
        result = validate_run_plan_strategy_integration(run_plan)
    except Exception as exc:
        result = build_strategy_integration_validation_failure(message=str(exc))

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_strategy_integration_validation_text_zh(result))
    return 0 if result.status == "ok" else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate ATTbacktrader strategy integration")
    parser.add_argument("--config", required=True, help="Path to a validated run plan YAML")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
