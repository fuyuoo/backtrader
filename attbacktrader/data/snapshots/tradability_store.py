"""Parquet snapshot reader and writer for tradability status records."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

from attbacktrader.data import TradabilityStatus


def tradability_status_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    asset_type: str = "stock",
) -> Path:
    safe_symbol = symbol.replace(".", "_")
    return (
        Path(snapshot_root)
        / "tradability"
        / asset_type
        / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
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


def read_tradability_statuses_parquet(path: str | Path) -> tuple[TradabilityStatus, ...]:
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
