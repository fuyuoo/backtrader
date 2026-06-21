"""Parquet snapshot reader and writer for daily bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

from attbacktrader.data import DailyBar
from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT
from attbacktrader.data.snapshots.read_cache import SnapshotReadCache, snapshot_path_cache_key


@dataclass(frozen=True)
class DailyBarsSnapshotCandidate:
    path: Path
    symbol: str
    start_date: date
    end_date: date
    asset_type: str
    adjustment: str

    def overlaps(self, *, start_date: date, end_date: date) -> bool:
        return self.start_date <= end_date and self.end_date >= start_date


def daily_bars_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    adjustment: str = DEFAULT_PRICE_ADJUSTMENT,
) -> Path:
    safe_symbol = _safe_symbol(symbol)
    return (
        Path(snapshot_root)
        / "daily_bars"
        / adjustment
        / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
    )


def tradable_bars_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    asset_type: str = "stock",
    adjustment: str = DEFAULT_PRICE_ADJUSTMENT,
) -> Path:
    if asset_type == "stock":
        return daily_bars_snapshot_path(
            snapshot_root,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjustment=adjustment,
        )

    safe_symbol = _safe_symbol(symbol)
    return (
        Path(snapshot_root)
        / "tradable_bars"
        / asset_type
        / adjustment
        / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
    )


def discover_tradable_bars_snapshot_paths(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    asset_type: str = "stock",
    adjustment: str = DEFAULT_PRICE_ADJUSTMENT,
) -> tuple[DailyBarsSnapshotCandidate, ...]:
    directory = _tradable_bars_snapshot_directory(
        snapshot_root,
        asset_type=asset_type,
        adjustment=adjustment,
    )
    if not directory.exists():
        return ()

    candidates: list[DailyBarsSnapshotCandidate] = []
    for path in directory.glob(f"{_safe_symbol(symbol)}_*.parquet"):
        candidate = _candidate_from_snapshot_path(
            path,
            symbol=symbol,
            asset_type=asset_type,
            adjustment=adjustment,
        )
        if candidate is not None and candidate.overlaps(start_date=start_date, end_date=end_date):
            candidates.append(candidate)

    return tuple(sorted(candidates, key=lambda candidate: (candidate.start_date, candidate.end_date, candidate.path.name)))


def write_daily_bars_parquet(bars: Sequence[DailyBar], path: str | Path) -> Path:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to write Parquet snapshots") from exc

    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(
        [
            {
                "trade_date": bar.trade_date.isoformat(),
                "symbol": bar.symbol,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
    )
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def write_merged_daily_bars_parquet(
    existing_bars: Sequence[DailyBar],
    new_bars: Sequence[DailyBar],
    path: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Path:
    return write_daily_bars_parquet(
        merge_daily_bars(
            existing_bars,
            new_bars,
            start_date=start_date,
            end_date=end_date,
        ),
        path,
    )


def merge_daily_bars(
    existing_bars: Sequence[DailyBar],
    new_bars: Sequence[DailyBar],
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[DailyBar, ...]:
    bars_by_key = {
        (bar.symbol, bar.trade_date): bar
        for bar in existing_bars
    }
    for bar in new_bars:
        bars_by_key[(bar.symbol, bar.trade_date)] = bar

    merged = (
        bar
        for bar in bars_by_key.values()
        if (start_date is None or bar.trade_date >= start_date)
        and (end_date is None or bar.trade_date <= end_date)
    )
    return tuple(sorted(merged, key=lambda bar: (bar.symbol, bar.trade_date)))


def read_daily_bars_parquet(path: str | Path, *, cache: SnapshotReadCache | None = None) -> tuple[DailyBar, ...]:
    if cache is not None:
        return cache.get_or_read(
            snapshot_path_cache_key("daily_bars_parquet", path),
            lambda: read_daily_bars_parquet(path),
        )

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to read Parquet snapshots") from exc

    frame = pd.read_parquet(Path(path))
    bars = [
        DailyBar(
            symbol=str(row.symbol),
            trade_date=date.fromisoformat(str(row.trade_date)),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in frame.itertuples(index=False)
    ]

    return tuple(sorted(bars, key=lambda bar: (bar.symbol, bar.trade_date)))


def _tradable_bars_snapshot_directory(
    snapshot_root: str | Path,
    *,
    asset_type: str,
    adjustment: str,
) -> Path:
    if asset_type == "stock":
        return Path(snapshot_root) / "daily_bars" / adjustment
    return Path(snapshot_root) / "tradable_bars" / asset_type / adjustment


def _candidate_from_snapshot_path(
    path: Path,
    *,
    symbol: str,
    asset_type: str,
    adjustment: str,
) -> DailyBarsSnapshotCandidate | None:
    safe_symbol = _safe_symbol(symbol)
    stem = path.stem
    prefix = f"{safe_symbol}_"
    if not stem.startswith(prefix):
        return None

    date_parts = stem.removeprefix(prefix).split("_")
    if len(date_parts) != 2:
        return None

    try:
        start_date = date.fromisoformat(_compact_date_to_iso(date_parts[0]))
        end_date = date.fromisoformat(_compact_date_to_iso(date_parts[1]))
    except ValueError:
        return None

    return DailyBarsSnapshotCandidate(
        path=path,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        asset_type=asset_type,
        adjustment=adjustment,
    )


def _compact_date_to_iso(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"invalid compact date: {value}")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _safe_symbol(symbol: str) -> str:
    return symbol.replace(".", "_")
