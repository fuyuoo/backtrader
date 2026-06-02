"""Resample daily OHLCV bars into weekly or monthly bars."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Literal, Sequence, TypeVar

from attbacktrader.data.bars import MarketBar
from attbacktrader.data.indexes import IndexBar


BarT = TypeVar("BarT", MarketBar, IndexBar)
Frequency = Literal["W", "M"]


def resample_daily_bars(bars: Sequence[BarT], *, frequency: Frequency) -> tuple[BarT, ...]:
    if frequency not in {"W", "M"}:
        raise ValueError("frequency must be 'W' or 'M'")

    grouped: dict[tuple[str, tuple[int, int]], list[BarT]] = defaultdict(list)
    for bar in sorted(bars, key=lambda value: (value.symbol, value.trade_date)):
        grouped[(bar.symbol, _period_key(bar.trade_date, frequency))].append(bar)

    resampled = [_aggregate_group(group) for group in grouped.values()]
    return tuple(sorted(resampled, key=lambda value: (value.symbol, value.trade_date)))


def _period_key(trade_date: date, frequency: Frequency) -> tuple[int, int]:
    if frequency == "W":
        iso_year, iso_week, _ = trade_date.isocalendar()
        return iso_year, iso_week
    return trade_date.year, trade_date.month


def _aggregate_group(group: Sequence[BarT]) -> BarT:
    ordered = tuple(sorted(group, key=lambda value: value.trade_date))
    first = ordered[0]
    last = ordered[-1]
    high = max(bar.high for bar in ordered)
    low = min(bar.low for bar in ordered)
    volume = sum(bar.volume for bar in ordered)

    if isinstance(first, IndexBar):
        amount = sum(bar.amount for bar in ordered)
        return IndexBar(
            symbol=first.symbol,
            trade_date=last.trade_date,
            open=first.open,
            high=high,
            low=low,
            close=last.close,
            volume=volume,
            amount=amount,
        )

    return MarketBar(
        symbol=first.symbol,
        trade_date=last.trade_date,
        open=first.open,
        high=high,
        low=low,
        close=last.close,
        volume=volume,
    )
