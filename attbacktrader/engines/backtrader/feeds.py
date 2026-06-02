"""Data-feed helpers for the backtrader adapter."""

from __future__ import annotations

from typing import Sequence

from attbacktrader.data import DailyBar


def daily_bars_to_pandas_frame(bars: Sequence[DailyBar]):
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required by the backtrader adapter") from exc

    ordered_bars = tuple(sorted(bars, key=lambda bar: (bar.symbol, bar.trade_date)))
    return pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp(bar.trade_date),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in ordered_bars
        ]
    )
