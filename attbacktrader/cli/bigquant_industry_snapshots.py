"""Fetch BigQuant industry membership snapshots."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from attbacktrader.data.providers import BigQuantIndustryProvider, BigQuantIndustryQueryWindow
from attbacktrader.data.snapshots import (
    shenwan_classification_snapshot_path,
    stock_industry_membership_snapshot_path,
    write_shenwan_classifications_parquet,
    write_stock_industry_memberships_parquet,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    provider = BigQuantIndustryProvider(
        api_key=api_key,
        config_path=args.config_path,
        window=BigQuantIndustryQueryWindow(start_date=start_date, end_date=end_date),
    )
    snapshot_root = Path(args.snapshot_root)

    classification_count = 0
    classification_path = None
    if not args.skip_classifications:
        classifications = provider.fetch_shenwan_industry_classifications(source=args.source)
        if not classifications:
            raise ValueError(f"no BigQuant industry classifications returned for {args.source}")
        classification_path = shenwan_classification_snapshot_path(snapshot_root, source=args.source)
        write_shenwan_classifications_parquet(classifications, classification_path)
        classification_count = len(classifications)

    symbols = _symbols_from_args(args)
    memberships_by_symbol = {}
    if args.all:
        all_memberships = provider.fetch_all_stock_industry_memberships(source=args.source)
        for membership in all_memberships:
            memberships_by_symbol.setdefault(membership.symbol, []).append(membership)
    else:
        for batch in _batches(symbols, args.batch_size):
            batch_memberships = provider.fetch_stock_industry_memberships_for_symbols(batch, source=args.source)
            memberships_by_symbol.update({symbol: list(items) for symbol, items in batch_memberships.items()})

    written_paths = []
    empty_symbols = []
    for symbol in sorted(memberships_by_symbol):
        memberships = tuple(memberships_by_symbol[symbol])
        if not memberships:
            empty_symbols.append(symbol)
            continue
        path = stock_industry_membership_snapshot_path(snapshot_root, symbol=symbol, source=args.source)
        write_stock_industry_memberships_parquet(memberships, path)
        written_paths.append(path)

    if args.strict and empty_symbols:
        raise ValueError(f"BigQuant returned no memberships for {len(empty_symbols)} symbols: {empty_symbols[:20]}")

    print(
        json.dumps(
            {
                "schema": "attbacktrader.bigquant_industry_snapshots.v1",
                "source": args.source,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "snapshot_root": str(snapshot_root),
                "classification_count": classification_count,
                "classification_path": str(classification_path) if classification_path is not None else None,
                "requested_symbol_count": "all" if args.all else len(symbols),
                "membership_symbol_count": len(memberships_by_symbol),
                "written_membership_snapshot_count": len(written_paths),
                "empty_symbol_count": len(empty_symbols),
                "empty_symbols_sample": empty_symbols[:20],
                "membership_count": sum(len(items) for items in memberships_by_symbol.values()),
                "written_paths_sample": [str(path) for path in written_paths[:20]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch BigQuant industry snapshots")
    parser.add_argument("--snapshot-root", default="data/snapshots")
    parser.add_argument("--source", default="SW2014", choices=["SW2014", "SW2021", "CS"])
    parser.add_argument("--start-date", default="1990-01-01", help="YYYY-MM-DD partition filter start")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="YYYY-MM-DD partition filter end")
    parser.add_argument("--symbol", action="append", default=[], help="Repeatable stock symbol, e.g. 000001.SZ")
    parser.add_argument("--symbol-file", default=None, help="Text/CSV file containing symbols")
    parser.add_argument("--symbols-from-trades", default=None, help="CSV/Parquet trade rows with symbol/ts_code column")
    parser.add_argument("--all", action="store_true", help="Fetch all symbols in the date range")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--config-path", default=None, help="Optional BigQuant config.json path")
    parser.add_argument(
        "--api-key-env",
        default="BIGQUANT_API_KEY",
        help="Environment variable containing AK/SK or token; default BIGQUANT_API_KEY",
    )
    parser.add_argument("--skip-classifications", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail if any requested symbol returns no membership rows")
    args = parser.parse_args(argv)
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if date.fromisoformat(args.end_date) < date.fromisoformat(args.start_date):
        parser.error("--end-date must be on or after --start-date")
    has_symbol_input = bool(args.symbol or args.symbol_file or args.symbols_from_trades)
    if args.all and has_symbol_input:
        parser.error("--all cannot be combined with symbol inputs")
    if not args.all and not has_symbol_input:
        parser.error("--all or at least one symbol input is required")
    return args


def _symbols_from_args(args: argparse.Namespace) -> list[str]:
    if args.all:
        return []
    symbols = [str(symbol).strip() for symbol in args.symbol if str(symbol).strip()]
    if args.symbol_file is not None:
        symbols.extend(_symbols_from_file(Path(args.symbol_file)))
    if args.symbols_from_trades is not None:
        symbols.extend(_symbols_from_table(Path(args.symbols_from_trades)))
    return _dedupe(symbols)


def _symbols_from_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"symbol file does not exist: {path}")
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        return _symbols_from_frame(frame, path=path)
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _symbols_from_table(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"trade rows file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    elif suffix == ".csv":
        frame = pd.read_csv(path)
    else:
        raise ValueError(f"unsupported trade rows extension: {suffix}")
    return _symbols_from_frame(frame, path=path)


def _symbols_from_frame(frame: pd.DataFrame, *, path: Path) -> list[str]:
    for column in ("symbol", "ts_code", "instrument", "code"):
        if column in frame.columns:
            return [str(item).strip() for item in frame[column].dropna().tolist() if str(item).strip()]
    raise ValueError(f"{path} must contain one of: symbol, ts_code, instrument, code")


def _batches(items: list[str], batch_size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
