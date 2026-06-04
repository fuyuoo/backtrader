"""Aggregate raw market data with calculated indicator snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from attbacktrader.data import DailyBar
from attbacktrader.features.frame import IndicatorFrame, indicator_frame_from_snapshots
from attbacktrader.features.indicators import ATRValue, KDJValue, MACDValue, MAValue, RSIValue
from attbacktrader.features.registry import IndicatorRequirement, indicator_period, normalize_indicator_requirements
from attbacktrader.features.snapshots import IndicatorSnapshot


@dataclass(frozen=True)
class MarketIndicators:
    symbol: str
    trade_date: date
    frame: IndicatorFrame
    requirements: tuple[IndicatorRequirement, ...]

    @property
    def kdj(self) -> KDJValue:
        return self.kdj_at("D")

    @property
    def kdj_k(self) -> float:
        return self.kdj.k

    @property
    def kdj_d(self) -> float:
        return self.kdj.d

    @property
    def kdj_j(self) -> float:
        return self.kdj.j

    @property
    def macd(self) -> MACDValue:
        return self.macd_at("D")

    def kdj_at(self, timeframe: str = "D") -> KDJValue:
        if timeframe == "D":
            return self.frame.kdj_at(self.trade_date, timeframe=timeframe)
        return self.frame.kdj_at_or_before(self.trade_date, timeframe=timeframe)

    def macd_at(self, timeframe: str = "D") -> MACDValue:
        if timeframe == "D":
            return self.frame.macd_at(self.trade_date, timeframe=timeframe)
        return self.frame.macd_at_or_before(self.trade_date, timeframe=timeframe)

    def ma_at(self, period: int, timeframe: str = "D") -> MAValue:
        if timeframe == "D":
            return self.frame.ma_at(self.trade_date, period=period, timeframe=timeframe)
        return self.frame.ma_at_or_before(self.trade_date, period=period, timeframe=timeframe)

    def rsi_at(self, period: int, timeframe: str = "D") -> RSIValue:
        if timeframe == "D":
            return self.frame.rsi_at(self.trade_date, period=period, timeframe=timeframe)
        return self.frame.rsi_at_or_before(self.trade_date, period=period, timeframe=timeframe)

    def atr_at(self, period: int, timeframe: str = "D") -> ATRValue:
        if timeframe == "D":
            return self.frame.atr_at(self.trade_date, period=period, timeframe=timeframe)
        return self.frame.atr_at_or_before(self.trade_date, period=period, timeframe=timeframe)

    def indicator_date(self, name: str, timeframe: str = "D") -> date:
        return self.frame.indicator_date(name, self.trade_date, timeframe=timeframe)

    def has_required_values(self) -> bool:
        try:
            for requirement in self.requirements:
                if requirement.name == "kdj":
                    self.kdj_at(requirement.timeframe)
                elif requirement.name == "macd":
                    self.macd_at(requirement.timeframe)
                elif requirement.name.startswith("ma"):
                    self.ma_at(_required_period(requirement.name), requirement.timeframe)
                elif requirement.name.startswith("rsi"):
                    self.rsi_at(_required_period(requirement.name), requirement.timeframe)
                elif requirement.name.startswith("atr"):
                    self.atr_at(_required_period(requirement.name), requirement.timeframe)
                else:
                    raise ValueError(f"unsupported indicator: {requirement.name}")
        except KeyError:
            return False
        return True


@dataclass(frozen=True)
class MarketFeatureRow:
    symbol: str
    trade_date: date
    bar: DailyBar
    indicators: MarketIndicators


def join_bars_with_indicators(
    bars: Sequence[DailyBar],
    indicator_snapshots: Sequence[IndicatorSnapshot],
    *,
    indicator_requirements: Sequence[IndicatorRequirement | tuple[str, str] | str] | None = None,
) -> tuple[MarketFeatureRow, ...]:
    requirements = normalize_indicator_requirements(indicator_requirements)
    indicator_frame = indicator_frame_from_snapshots(indicator_snapshots)
    snapshot_keys = {
        (snapshot.symbol, snapshot.timeframe, snapshot.trade_date)
        for snapshot in indicator_snapshots
    }
    rows: list[MarketFeatureRow] = []

    for bar in sorted(bars, key=lambda value: (value.symbol, value.trade_date)):
        if indicator_frame.symbol != bar.symbol:
            raise ValueError("indicator frame symbol must match bars")
        indicators = MarketIndicators(
            symbol=bar.symbol,
            trade_date=bar.trade_date,
            frame=indicator_frame,
            requirements=requirements,
        )
        _validate_required_snapshot_rows(indicators, requirements, snapshot_keys=snapshot_keys)

        rows.append(
            MarketFeatureRow(
                symbol=bar.symbol,
                trade_date=bar.trade_date,
                bar=bar,
                indicators=indicators,
            )
        )

    return tuple(rows)


def _validate_required_snapshot_rows(
    indicators: MarketIndicators,
    requirements: tuple[IndicatorRequirement, ...],
    *,
    snapshot_keys: set[tuple[str, str, date]],
) -> None:
    for requirement in requirements:
        if requirement.timeframe != "D":
            continue
        if (indicators.symbol, "D", indicators.trade_date) in snapshot_keys:
            continue
        raise KeyError(
            f"indicator snapshot is missing for {indicators.symbol} on {indicators.trade_date.isoformat()}"
        )


def _required_period(name: str) -> int:
    period = indicator_period(name)
    if period is None:
        raise ValueError(f"indicator period is missing for {name}")
    return period
