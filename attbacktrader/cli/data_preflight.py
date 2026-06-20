"""Run data preflight checks for a YAML run plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
from attbacktrader.config import load_run_plan
from attbacktrader.data.providers import TushareProvider, read_tushare_token
from attbacktrader.reports import to_jsonable
from attbacktrader.runners import (
    render_data_preflight_summary_text,
    run_data_preflight,
    write_data_preflight_report,
)


DEFAULT_5000_POINT_REQUESTS_PER_MINUTE = 450.0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_plan = load_run_plan(args.config)
    provider = None
    if run_plan.data.refresh_snapshots:
        if run_plan.data.provider != "tushare":
            raise SystemExit(f"Unsupported data provider: {run_plan.data.provider}")
        provider = TushareProvider(
            read_tushare_token(args.token_file),
            rate_limit=tushare_rate_limit_config_from_args(args),
        )

    report = run_data_preflight(
        run_plan,
        provider=provider,
        max_symbols=args.max_symbols,
        indicator_alarm_threshold=args.indicator_alarm_threshold,
        progress=(
            None
            if args.json or args.no_progress
            else lambda current, total, symbol, status: _print_progress(current, total, symbol, status)
        ),
    )

    if args.output is not None:
        write_data_preflight_report(report, args.output)

    if args.json:
        print(json.dumps(to_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_data_preflight_summary_text(report))
        if args.output is not None:
            print(f"report_path={args.output}")

    return 1 if args.strict and report.status == "error" else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight data snapshots for a YAML run plan")
    parser.add_argument("--config", required=True, help="Path to run.yaml")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    add_tushare_rate_limit_args(parser)
    parser.set_defaults(tushare_requests_per_minute=DEFAULT_5000_POINT_REQUESTS_PER_MINUTE)
    parser.add_argument("--max-symbols", type=int, default=None, help="Only preflight the first N tradable symbols")
    parser.add_argument("--indicator-alarm-threshold", type=float, default=0.05)
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path")
    parser.add_argument("--json", action="store_true", help="Print full preflight report JSON")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when preflight status is error")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress messages")
    args = parser.parse_args(argv)
    if args.max_symbols is not None and args.max_symbols <= 0:
        parser.error("--max-symbols must be positive")
    if args.indicator_alarm_threshold < 0:
        parser.error("--indicator-alarm-threshold must be non-negative")
    return args


def _print_progress(current: int, total: int, symbol: str, status: str) -> None:
    print(f"preflight {current}/{total} {symbol} {status}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
