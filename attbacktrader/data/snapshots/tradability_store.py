"""Parquet snapshot reader and writer for tradability status records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

from attbacktrader.data import TradabilityStatus
from attbacktrader.data.snapshots.read_cache import SnapshotReadCache, snapshot_path_cache_key


@dataclass(frozen=True)
class TradabilityStatusSnapshotCandidate:
    path: Path
    symbol: str
    start_date: date
    end_date: date
    asset_type: str

    def overlaps(self, *, start_date: date, end_date: date) -> bool:
        return self.start_date <= end_date and self.end_date >= start_date


def tradability_status_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    asset_type: str = "stock",
) -> Path:
    safe_symbol = _safe_symbol(symbol)
    return (
        Path(snapshot_root)
        / "tradability"
        / asset_type
        / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
    )


def discover_tradability_status_snapshot_paths(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    asset_type: str = "stock",
) -> tuple[TradabilityStatusSnapshotCandidate, ...]:
    directory = Path(snapshot_root) / "tradability" / asset_type
    if not directory.exists():
        return ()

    candidates: list[TradabilityStatusSnapshotCandidate] = []
    for path in directory.glob(f"{_safe_symbol(symbol)}_*.parquet"):
        candidate = _candidate_from_snapshot_path(path, symbol=symbol, asset_type=asset_type)
        if candidate is not None and candidate.overlaps(start_date=start_date, end_date=end_date):
            candidates.append(candidate)

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (candidate.start_date, candidate.end_date, candidate.path.name),
        )
    )


def write_tradability_statuses_parquet(statuses: Sequence[TradabilityStatus], path: str | Path) -> Path:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to write tradability Parquet snapshots") from exc

    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "symbol": status.symbol,
                "trade_date": status.trade_date.isoformat(),
                "is_suspended": status.is_suspended,
                "is_limit_up": status.is_limit_up,
                "is_limit_down": status.is_limit_down,
                "close": status.close,
                "up_limit": status.up_limit,
                "down_limit": status.down_limit,
            }
            for status in statuses
        ],
        columns=[
            "symbol",
            "trade_date",
            "is_suspended",
            "is_limit_up",
            "is_limit_down",
            "close",
            "up_limit",
            "down_limit",
        ],
    )
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def read_tradability_statuses_parquet(
    path: str | Path,
    *,
    cache: SnapshotReadCache | None = None,
) -> tuple[TradabilityStatus, ...]:
    if cache is not None:
        return cache.get_or_read(
            snapshot_path_cache_key("tradability_statuses_parquet", path),
            lambda: read_tradability_statuses_parquet(path),
        )

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to read tradability Parquet snapshots") from exc

    frame = pd.read_parquet(Path(path))
    statuses = [
        TradabilityStatus(
            symbol=str(row.symbol),
            trade_date=date.fromisoformat(str(row.trade_date)),
            is_suspended=bool(row.is_suspended),
            is_limit_up=bool(row.is_limit_up),
            is_limit_down=bool(row.is_limit_down),
            close=_optional_float(row.close),
            up_limit=_optional_float(row.up_limit),
            down_limit=_optional_float(row.down_limit),
        )
        for row in frame.itertuples(index=False)
    ]
    return tuple(sorted(statuses, key=lambda status: (status.symbol, status.trade_date)))


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        import pandas as pd
    except ImportError:
        pd = None
    if pd is not None and pd.isna(value):
        return None
    return float(value)


def _candidate_from_snapshot_path(
    path: Path,
    *,
    symbol: str,
    asset_type: str,
) -> TradabilityStatusSnapshotCandidate | None:
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

    return TradabilityStatusSnapshotCandidate(
        path=path,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        asset_type=asset_type,
    )


def _compact_date_to_iso(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"invalid compact date: {value}")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _safe_symbol(symbol: str) -> str:
    return symbol.replace(".", "_")
