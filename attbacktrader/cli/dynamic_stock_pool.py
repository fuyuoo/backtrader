"""Generate point-in-time dynamic stock pool artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
from attbacktrader.data import (
    dynamic_stock_pool_entries_from_index_constituents,
    fixed_stock_pool_members_from_dynamic_entries,
    write_dynamic_stock_pool_parquet,
    write_fixed_stock_pool_csv,
)
from attbacktrader.data.providers import TushareProvider, read_tushare_token


DEFAULT_DYNAMIC_BAOMA_INDEX_SPECS = ("399300.SZ=HS300", "000905.SH=CSI500")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise ValueError("--end-date must be on or after --start-date")

    provider = TushareProvider(
        read_tushare_token(args.token_file),
        rate_limit=tushare_rate_limit_config_from_args(args),
    )
    stock_names = provider.fetch_stock_names()
    constituents_by_label = {}
    source_summaries = []
    for index_code, label in args.index:
        constituents = provider.fetch_index_constituents(
            index_symbol=index_code,
            start_date=start_date,
            end_date=end_date,
        )
        if not constituents:
            raise ValueError(
                f"index constituents are empty for {label}({index_code}) "
                f"between {start_date.isoformat()} and {end_date.isoformat()}"
            )
        constituents_by_label[label] = constituents
        source_summaries.append(_source_summary(index_code=index_code, label=label, constituents=constituents))

    entries = dynamic_stock_pool_entries_from_index_constituents(constituents_by_label)
    dynamic_path = write_dynamic_stock_pool_parquet(entries, args.output_parquet)
    members = fixed_stock_pool_members_from_dynamic_entries(
        entries,
        stock_names=stock_names,
        freeze_date=end_date,
    )
    union_path = write_fixed_stock_pool_csv(args.union_output, members)

    payload = {
        "schema": "attbacktrader.dynamic_stock_pool_generation.v1",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "dynamic_stock_pool_file": str(dynamic_path),
        "union_stock_pool_file": str(union_path),
        "source_indexes": source_summaries,
        "dynamic_row_count": len(entries),
        "union_member_count": len(members),
        "as_of_rule": "latest source snapshot date <= signal_trade_date, per source index",
        "no_future_data_contract": "membership is evaluated on the T-1 signal_trade_date, not the T buy date",
    }
    if args.metadata_output is not None:
        args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "\n".join(
                (
                    f"动态股票池 Parquet: {dynamic_path}",
                    f"历史并集股票池 CSV: {union_path}",
                    f"日期范围: {start_date.isoformat()} ~ {end_date.isoformat()}",
                    f"动态行数: {len(entries)}",
                    f"并集股票数: {len(members)}",
                    "来源指数: "
                    + ", ".join(
                        f"{item['label']}({item['index_code']}, {item['snapshot_count']} snapshots, "
                        f"{item['first_snapshot_date']}~{item['latest_snapshot_date']})"
                        for item in source_summaries
                    ),
                )
            )
        )
    return 0


def _source_summary(*, index_code: str, label: str, constituents) -> dict[str, object]:
    snapshot_dates = sorted({constituent.trade_date for constituent in constituents})
    latest_snapshot_date = snapshot_dates[-1]
    counts_by_date = Counter(constituent.trade_date for constituent in constituents)
    return {
        "index_code": index_code,
        "label": label,
        "row_count": len(constituents),
        "snapshot_count": len(snapshot_dates),
        "first_snapshot_date": snapshot_dates[0].isoformat(),
        "latest_snapshot_date": latest_snapshot_date.isoformat(),
        "latest_snapshot_member_count": counts_by_date[latest_snapshot_date],
    }


def _parse_index_spec(raw_value: str) -> tuple[str, str]:
    if "=" not in raw_value:
        raise argparse.ArgumentTypeError("index spec must be INDEX_CODE=LABEL")
    index_code, label = (part.strip() for part in raw_value.split("=", 1))
    if not index_code or not label:
        raise argparse.ArgumentTypeError("index spec must be INDEX_CODE=LABEL")
    return index_code, label


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a point-in-time dynamic stock pool from index constituents")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    add_tushare_rate_limit_args(parser)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-parquet", type=Path, required=True)
    parser.add_argument("--union-output", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--index", action="append", type=_parse_index_spec, default=None)
    parser.add_argument("--json", action="store_true", help="Print generation summary as JSON")
    args = parser.parse_args(argv)
    if args.index is None:
        args.index = tuple(_parse_index_spec(spec) for spec in DEFAULT_DYNAMIC_BAOMA_INDEX_SPECS)
    else:
        args.index = tuple(args.index)
    return args


if __name__ == "__main__":
    raise SystemExit(main())
