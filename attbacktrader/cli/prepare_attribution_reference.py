"""Prepare attribution reference snapshots from all-A daily feature rows."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from attbacktrader.data.snapshots import (
    DEFAULT_REFERENCE_UNIVERSE,
    attribution_reference_snapshot_dir,
    build_attribution_reference_snapshot_from_frame,
    write_attribution_reference_snapshot,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if args.input is None:
        raise ValueError("--input is required in this offline preparation version")

    frame = _load_input_frame(Path(args.input))
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
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--snapshot-root", default="data/snapshots")
    parser.add_argument("--reference-universe", default=DEFAULT_REFERENCE_UNIVERSE)
    parser.add_argument("--min-reference-count", type=int, default=100)
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args(argv)


def _load_input_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"input does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported input extension: {suffix}")


if __name__ == "__main__":
    raise SystemExit(main())
