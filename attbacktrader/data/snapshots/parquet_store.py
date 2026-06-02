"""Parquet snapshot reader and writer for daily bars."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

from attbacktrader.data import DailyBar
from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT


def daily_bars_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    adjustment: str = DEFAULT_PRICE_ADJUSTMENT,
) -> Path:
    safe_symbol = symbol.replace(".", "_")
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

    safe_symbol = symbol.replace(".", "_")
    return (
        Path(snapshot_root)
        / "tradable_bars"
        / asset_type
        / adjustment
        / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
    )


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


def read_daily_bars_parquet(path: str | Path) -> tuple[DailyBar, ...]:
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
