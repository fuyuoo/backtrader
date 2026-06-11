"""Prepare attribution reference snapshots from all-A daily feature rows."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
from attbacktrader.data.providers import TushareProvider, read_tushare_token
from attbacktrader.data.snapshots import (
    DEFAULT_REFERENCE_UNIVERSE,
    apply_industry_memberships_to_frame,
    attribution_reference_snapshot_dir,
    build_attribution_reference_snapshot_from_frame,
    load_or_fetch_industry_memberships_for_symbols,
    write_attribution_reference_snapshot,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    frame = _load_input_frame(Path(args.input)) if args.input is not None else _fetch_provider_frame(args, start_date, end_date)
    snapshot = build_attribution_reference_snapshot_from_frame(
        frame,
        start_date=start_date,
        end_date=end_date,
        reference_universe=args.reference_universe,
        min_reference_count=args.min_reference_count,
    )
    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else attribution_reference_snapshot_dir(
            args.snapshot_root,
            reference_universe=args.reference_universe,
            start_date=start_date,
            end_date=end_date,
        )
    )
    metadata_path, reference_json_path, values_path = write_attribution_reference_snapshot(snapshot, output_dir)
    print(
        json.dumps(
            {
                "schema": snapshot["metadata"]["schema"],
                "reference_universe": args.reference_universe,
                "start_date": args.start_date,
                "end_date": args.end_date,
                "row_count": snapshot["row_count"],
                "exception_count": snapshot["metadata"]["exception_count"],
                "artifacts": {
                    "metadata_path": str(metadata_path),
                    "reference_json_path": str(reference_json_path),
                    "reference_values_parquet_path": str(values_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare attribution reference snapshots")
    parser.add_argument("--input", default=None, help="All-A daily feature CSV/Parquet input")
    parser.add_argument("--provider", choices=["tushare"], default=None, help="Fetch all-A reference input from a provider")
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--snapshot-root", default="data/snapshots")
    parser.add_argument("--reference-universe", default=DEFAULT_REFERENCE_UNIVERSE)
    parser.add_argument("--industry-source", default="SW2021")
    parser.add_argument(
        "--fetch-industry-memberships",
        action="store_true",
        help="With --provider tushare, fetch/cache per-symbol SW industry memberships and merge by effective interval.",
    )
    parser.add_argument(
        "--refresh-industry-memberships",
        action="store_true",
        help="Refresh industry membership snapshots even when cached files exist.",
    )
    parser.add_argument("--min-reference-count", type=int, default=100)
    parser.add_argument("--output-dir", default=None)
    add_tushare_rate_limit_args(parser)
    args = parser.parse_args(argv)
    if args.input is None and args.provider is None:
        parser.error("--input or --provider is required")
    if args.input is not None and args.provider is not None:
        parser.error("--input and --provider are mutually exclusive")
    return args


def _load_input_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"input does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported input extension: {suffix}")


def _fetch_provider_frame(args: argparse.Namespace, start_date: date, end_date: date) -> pd.DataFrame:
    if args.provider != "tushare":
        raise ValueError(f"unsupported provider: {args.provider}")
    provider = TushareProvider(
        read_tushare_token(args.token_file),
        rate_limit=tushare_rate_limit_config_from_args(args),
    )
    frame = provider.fetch_attribution_reference_frame(start_date=start_date, end_date=end_date)
    if not args.fetch_industry_memberships:
        return frame
    symbols = sorted(str(symbol) for symbol in frame["symbol"].dropna().unique())
    memberships = load_or_fetch_industry_memberships_for_symbols(
        symbols,
        snapshot_root=args.snapshot_root,
        provider=provider,
        source=args.industry_source,
        refresh=args.refresh_industry_memberships,
    )
    return apply_industry_memberships_to_frame(frame, memberships)


if __name__ == "__main__":
    raise SystemExit(main())
