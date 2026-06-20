"""Generate fixed stock pool CSV files."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
from attbacktrader.data import (
    fixed_stock_pool_members_from_index_constituents,
    latest_index_constituents,
    write_fixed_stock_pool_csv,
)
from attbacktrader.data.providers import TushareProvider, read_tushare_token


DEFAULT_BAOMA_INDEX_SPECS = ("000300.SH=HS300", "000905.SH=CSI500")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    freeze_date = date.fromisoformat(args.freeze_date)
    start_date = freeze_date - timedelta(days=args.lookback_days)
    index_specs = args.index
    provider = TushareProvider(
        read_tushare_token(args.token_file),
        rate_limit=tushare_rate_limit_config_from_args(args),
    )
    stock_names = provider.fetch_stock_names()

    constituents_by_label = {}
    snapshot_dates = {}
    for index_code, label in index_specs:
        raw_constituents = provider.fetch_index_constituents(
            index_symbol=index_code,
            start_date=start_date,
            end_date=freeze_date,
        )
        snapshot_date, constituents = latest_index_constituents(raw_constituents)
        constituents_by_label[label] = constituents
        snapshot_dates[label] = snapshot_date.isoformat()

    members = fixed_stock_pool_members_from_index_constituents(
        constituents_by_label,
        stock_names=stock_names,
        freeze_date=freeze_date,
    )
    output_path = write_fixed_stock_pool_csv(args.output, members)
    payload = {
        "schema": "attbacktrader.stock_pool_generation.v1",
        "output": str(output_path),
        "freeze_date": freeze_date.isoformat(),
        "lookback_days": args.lookback_days,
        "index_count": len(index_specs),
        "source_indexes": [
            {"index_code": index_code, "label": label, "snapshot_date": snapshot_dates[label]}
            for index_code, label in index_specs
        ],
        "member_count": len(members),
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "\n".join(
                (
                    f"输出文件: {output_path}",
                    f"冻结日期: {freeze_date.isoformat()}",
                    f"成分股数量: {len(members)}",
                    "来源指数: "
                    + ", ".join(
                        f"{item['label']}({item['index_code']} @ {item['snapshot_date']})"
                        for item in payload["source_indexes"]
                    ),
                )
            )
        )
    return 0


def _parse_index_spec(raw_value: str) -> tuple[str, str]:
    if "=" not in raw_value:
        raise argparse.ArgumentTypeError("index spec must be INDEX_CODE=LABEL")
    index_code, label = (part.strip() for part in raw_value.split("=", 1))
    if not index_code or not label:
        raise argparse.ArgumentTypeError("index spec must be INDEX_CODE=LABEL")
    return index_code, label


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a fixed stock pool CSV from index constituents")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    add_tushare_rate_limit_args(parser)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-date", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=500)
    parser.add_argument("--index", action="append", type=_parse_index_spec, default=None)
    parser.add_argument("--json", action="store_true", help="Print generation summary as JSON")
    args = parser.parse_args(argv)
    if args.lookback_days <= 0:
        parser.error("--lookback-days must be positive")
    if args.index is None:
        args.index = tuple(_parse_index_spec(spec) for spec in DEFAULT_BAOMA_INDEX_SPECS)
    else:
        args.index = tuple(args.index)
    return args


if __name__ == "__main__":
    raise SystemExit(main())
