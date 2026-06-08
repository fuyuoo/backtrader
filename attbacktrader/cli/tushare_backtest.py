"""Fetch Tushare daily data and run the first strategy template."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT
from attbacktrader.data.providers import TushareProvider, read_tushare_token
from attbacktrader.data.snapshots import daily_bars_snapshot_path, write_daily_bars_parquet
from attbacktrader.engines.backtrader import run_trend_template_v1_backtrader
from attbacktrader.features import (
    build_indicator_snapshots,
    indicator_frame_from_snapshots,
    indicator_snapshot_path,
    write_indicator_snapshots_parquet,
)
from attbacktrader.reports import build_report_from_trend_result
from attbacktrader.strategies.templates import TrendTemplateV1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start_date = _parse_cli_date(args.start_date)
    end_date = _parse_cli_date(args.end_date)

    token = read_tushare_token(args.token_file)
    provider = TushareProvider(token, rate_limit=tushare_rate_limit_config_from_args(args))
    bars = provider.fetch_daily_bars(
        symbol=args.symbol,
        start_date=start_date,
        end_date=end_date,
        adjustment=args.adjustment,
    )

    if not bars:
        raise SystemExit(f"No Tushare daily bars returned for {args.symbol} from {args.start_date} to {args.end_date}")

    snapshot_path = daily_bars_snapshot_path(
        args.snapshot_root,
        symbol=args.symbol,
        start_date=start_date,
        end_date=end_date,
        adjustment=args.adjustment,
    )
    write_daily_bars_parquet(bars, snapshot_path)
    indicator_snapshots = build_indicator_snapshots(bars)
    indicator_path = indicator_snapshot_path(
        args.snapshot_root,
        symbol=args.symbol,
        start_date=start_date,
        end_date=end_date,
        adjustment=args.adjustment,
    )
    write_indicator_snapshots_parquet(indicator_snapshots, indicator_path)
    indicator_frame = indicator_frame_from_snapshots(indicator_snapshots)

    if args.engine == "backtrader":
        engine_result = run_trend_template_v1_backtrader(
            bars,
            initial_cash=args.initial_cash,
            stake=args.stake,
            indicators=indicator_frame,
        )
        result = engine_result.strategy_result
        final_cash = engine_result.final_cash
        final_value = engine_result.final_value
    else:
        result = TrendTemplateV1().run_single_symbol(bars, indicators=indicator_frame)
        final_cash = None
        final_value = None

    report = build_report_from_trend_result(result, report_id=args.report_id or f"{args.symbol}-{args.start_date}-{args.end_date}")

    payload = {
        "symbol": args.symbol,
        "engine": args.engine,
        "adjustment": args.adjustment,
        "bar_count": len(bars),
        "snapshot_path": str(snapshot_path),
        "indicator_snapshot_path": str(indicator_path),
        "trade_count": len(result.closed_trades),
        "engine_cash": final_cash,
        "engine_value": final_value,
        "open_position": asdict(result.open_position) if result.open_position else None,
        "closed_trades": [asdict(trade) for trade in result.closed_trades],
        "report": asdict(report),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TrendTemplateV1 using Tushare daily data")
    parser.add_argument("--symbol", required=True, help="Tushare ts_code, for example 000001.SZ")
    parser.add_argument("--start-date", required=True, help="Start date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    add_tushare_rate_limit_args(parser)
    parser.add_argument("--snapshot-root", default="data/snapshots")
    parser.add_argument("--adjustment", choices=["qfq", "hfq"], default=DEFAULT_PRICE_ADJUSTMENT)
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--engine", choices=["business", "backtrader"], default="business")
    parser.add_argument("--initial-cash", type=float, default=1000000.0)
    parser.add_argument("--stake", type=int, default=100)
    return parser.parse_args(argv)


def _parse_cli_date(value: str) -> date:
    if "-" in value:
        return date.fromisoformat(value)
    return datetime.strptime(value, "%Y%m%d").date()


if __name__ == "__main__":
    raise SystemExit(main())
