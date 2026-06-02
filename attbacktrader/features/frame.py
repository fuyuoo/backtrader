"""Reusable indicator frame for strategy and engine consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from attbacktrader.data import DailyBar
from attbacktrader.features.indicators import KDJValue, calculate_kdj
from attbacktrader.features.snapshots import IndicatorSnapshot


@dataclass(frozen=True)
class IndicatorFrame:
    symbol: str
    kdj_by_date: Mapping[date, KDJValue]

    def kdj_at(self, trade_date: date) -> KDJValue:
        try:
            return self.kdj_by_date[trade_date]
        except KeyError as exc:
            raise KeyError(f"KDJ is missing for {self.symbol} on {trade_date.isoformat()}") from exc


def build_indicator_frame(bars: Sequence[DailyBar]) -> IndicatorFrame:
    if not bars:
        raise ValueError("bars cannot be empty")

    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    symbol = ordered_bars[0].symbol
    if any(bar.symbol != symbol for bar in ordered_bars):
        raise ValueError("build_indicator_frame requires one symbol")

    kdj_values = calculate_kdj(
        [bar.high for bar in ordered_bars],
        [bar.low for bar in ordered_bars],
        [bar.close for bar in ordered_bars],
    )

    return IndicatorFrame(
        symbol=symbol,
        kdj_by_date={bar.trade_date: value for bar, value in zip(ordered_bars, kdj_values)},
    )


def build_indicator_snapshots(bars: Sequence[DailyBar]) -> tuple[IndicatorSnapshot, ...]:
    frame = build_indicator_frame(bars)
    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    return tuple(
        IndicatorSnapshot(
            symbol=bar.symbol,
            trade_date=bar.trade_date,
            kdj_k=frame.kdj_at(bar.trade_date).k,
            kdj_d=frame.kdj_at(bar.trade_date).d,
            kdj_j=frame.kdj_at(bar.trade_date).j,
        )
        for bar in ordered_bars
    )


def indicator_frame_from_snapshots(snapshots: Sequence[IndicatorSnapshot]) -> IndicatorFrame:
    if not snapshots:
        raise ValueError("indicator snapshots cannot be empty")

    ordered_snapshots = tuple(sorted(snapshots, key=lambda snapshot: snapshot.trade_date))
    symbol = ordered_snapshots[0].symbol
    if any(snapshot.symbol != symbol for snapshot in ordered_snapshots):
        raise ValueError("indicator_frame_from_snapshots requires one symbol")

    return IndicatorFrame(
        symbol=symbol,
        kdj_by_date={snapshot.trade_date: snapshot.kdj for snapshot in ordered_snapshots},
    )


def indicator_snapshots_from_frame(
    frame: IndicatorFrame,
    bars: Sequence[DailyBar],
) -> tuple[IndicatorSnapshot, ...]:
    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    return tuple(
        IndicatorSnapshot(
            symbol=bar.symbol,
            trade_date=bar.trade_date,
            kdj_k=frame.kdj_at(bar.trade_date).k,
            kdj_d=frame.kdj_at(bar.trade_date).d,
            kdj_j=frame.kdj_at(bar.trade_date).j,
        )
        for bar in ordered_bars
    )
