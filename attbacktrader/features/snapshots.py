"""Indicator snapshots and storage helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT
from attbacktrader.features.indicators import KDJValue


@dataclass(frozen=True)
class IndicatorSnapshot:
    symbol: str
    trade_date: date
    kdj_k: float
    kdj_d: float
    kdj_j: float

    @property
    def kdj(self) -> KDJValue:
        return KDJValue(k=self.kdj_k, d=self.kdj_d, j=self.kdj_j)


def indicator_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    adjustment: str = DEFAULT_PRICE_ADJUSTMENT,
    asset_type: str = "stock",
) -> Path:
    safe_symbol = symbol.replace(".", "_")
    if asset_type == "stock":
        return (
            Path(snapshot_root)
            / "indicators"
            / "kdj"
            / adjustment
            / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
        )

    return (
        Path(snapshot_root)
        / "indicators"
        / "kdj"
        / asset_type
        / adjustment
        / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
    )


def write_indicator_snapshots_parquet(snapshots: Sequence[IndicatorSnapshot], path: str | Path) -> Path:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to write indicator snapshots") from exc

    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "symbol": snapshot.symbol,
                "trade_date": snapshot.trade_date.isoformat(),
                "kdj_k": snapshot.kdj_k,
                "kdj_d": snapshot.kdj_d,
                "kdj_j": snapshot.kdj_j,
            }
            for snapshot in snapshots
        ]
    )
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def read_indicator_snapshots_parquet(path: str | Path) -> tuple[IndicatorSnapshot, ...]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to read indicator snapshots") from exc

    frame = pd.read_parquet(Path(path))
    snapshots = [
        IndicatorSnapshot(
            symbol=str(row.symbol),
            trade_date=date.fromisoformat(str(row.trade_date)),
            kdj_k=float(row.kdj_k),
            kdj_d=float(row.kdj_d),
            kdj_j=float(row.kdj_j),
        )
        for row in frame.itertuples(index=False)
    ]
    return tuple(sorted(snapshots, key=lambda snapshot: (snapshot.symbol, snapshot.trade_date)))
