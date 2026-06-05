"""Parquet snapshot reader and writer for index daily bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

from attbacktrader.data import IndexBar


@dataclass(frozen=True)
class IndexBarsSnapshotCandidate:
    path: Path
    symbol: str
    start_date: date
    end_date: date

    def overlaps(self, *, start_date: date, end_date: date) -> bool:
        return self.start_date <= end_date and self.end_date >= start_date


def index_bars_snapshot_path(snapshot_root: str | Path, *, symbol: str, start_date: date, end_date: date) -> Path:
    safe_symbol = symbol.replace(".", "_")
    return Path(snapshot_root) / "indexes" / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"


def industry_index_bars_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    source: str = "SW2021",
) -> Path:
    safe_symbol = symbol.replace(".", "_")
    return (
        Path(snapshot_root)
        / "industries"
        / "sw"
        / source
        / "index_bars"
        / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
    )


def discover_index_bars_snapshot_paths(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
) -> tuple[IndexBarsSnapshotCandidate, ...]:
    directory = Path(snapshot_root) / "indexes"
    return _discover_index_bar_candidates(
        directory,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


def discover_industry_index_bars_snapshot_paths(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    source: str = "SW2021",
) -> tuple[IndexBarsSnapshotCandidate, ...]:
    directory = Path(snapshot_root) / "industries" / "sw" / source / "index_bars"
    return _discover_index_bar_candidates(
        directory,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


def write_index_bars_parquet(bars: Sequence[IndexBar], path: str | Path) -> Path:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to write index Parquet snapshots") from exc

    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "symbol": bar.symbol,
                "trade_date": bar.trade_date.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "amount": bar.amount,
            }
            for bar in bars
        ],
        columns=["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"],
    )
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def read_index_bars_parquet(path: str | Path) -> tuple[IndexBar, ...]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to read index Parquet snapshots") from exc

    frame = pd.read_parquet(Path(path))
    bars = [
        IndexBar(
            symbol=str(row.symbol),
            trade_date=date.fromisoformat(str(row.trade_date)),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
            amount=float(row.amount),
        )
        for row in frame.itertuples(index=False)
    ]
    return tuple(sorted(bars, key=lambda bar: (bar.symbol, bar.trade_date)))


def _discover_index_bar_candidates(
    directory: Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
) -> tuple[IndexBarsSnapshotCandidate, ...]:
    if not directory.exists():
        return ()

    candidates: list[IndexBarsSnapshotCandidate] = []
    safe_symbol = symbol.replace(".", "_")
    for path in directory.glob(f"{safe_symbol}_*.parquet"):
        candidate = _candidate_from_index_snapshot_path(path, symbol=symbol)
        if candidate is not None and candidate.overlaps(start_date=start_date, end_date=end_date):
            candidates.append(candidate)
    return tuple(sorted(candidates, key=lambda candidate: (candidate.start_date, candidate.end_date, candidate.path.name)))


def _candidate_from_index_snapshot_path(path: Path, *, symbol: str) -> IndexBarsSnapshotCandidate | None:
    safe_symbol = symbol.replace(".", "_")
    parts = path.stem.split("_")
    if len(parts) < 3:
        return None
    symbol_part = "_".join(parts[:-2])
    if symbol_part != safe_symbol:
        return None
    try:
        start_date = date.fromisoformat(f"{parts[-2][0:4]}-{parts[-2][4:6]}-{parts[-2][6:8]}")
        end_date = date.fromisoformat(f"{parts[-1][0:4]}-{parts[-1][4:6]}-{parts[-1][6:8]}")
    except (ValueError, IndexError):
        return None
    return IndexBarsSnapshotCandidate(
        path=path,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
