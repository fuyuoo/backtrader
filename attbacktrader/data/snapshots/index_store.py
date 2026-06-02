"""Parquet snapshot reader and writer for index daily bars."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

from attbacktrader.data import IndexBar


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
