"""Aggregate raw market data with calculated indicator snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from attbacktrader.data import DailyBar
from attbacktrader.features.snapshots import IndicatorSnapshot


@dataclass(frozen=True)
class MarketFeatureRow:
    symbol: str
    trade_date: date
    bar: DailyBar
    indicators: IndicatorSnapshot


def join_bars_with_indicators(
    bars: Sequence[DailyBar],
    indicator_snapshots: Sequence[IndicatorSnapshot],
) -> tuple[MarketFeatureRow, ...]:
    indicators_by_key = {
        (snapshot.symbol, snapshot.trade_date): snapshot
        for snapshot in indicator_snapshots
    }
    rows: list[MarketFeatureRow] = []

    for bar in sorted(bars, key=lambda value: (value.symbol, value.trade_date)):
        key = (bar.symbol, bar.trade_date)
        try:
            indicators = indicators_by_key[key]
        except KeyError as exc:
            raise KeyError(f"indicator snapshot is missing for {bar.symbol} on {bar.trade_date.isoformat()}") from exc

        rows.append(
            MarketFeatureRow(
                symbol=bar.symbol,
                trade_date=bar.trade_date,
                bar=bar,
                indicators=indicators,
            )
        )

    return tuple(rows)
