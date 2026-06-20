"""Indicator alignment helpers for post-trade attribution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from attbacktrader.features.frame import IndicatorFrame
from attbacktrader.features.indicators import KDJValue, MACDValue


CompletedIndicatorName = Literal["kdj", "macd"]


@dataclass(frozen=True)
class CompletedIndicatorEvidence:
    name: CompletedIndicatorName
    timeframe: str
    event_date: date
    indicator_date: date
    value: KDJValue | MACDValue


def completed_indicator_before_event(
    frame: IndicatorFrame,
    *,
    name: CompletedIndicatorName,
    timeframe: str,
    event_date: date,
) -> CompletedIndicatorEvidence:
    """Return the latest completed higher-timeframe indicator before an event date.

    Attribution must not use an in-progress weekly/monthly bar for an event on
    the same date, so the lookup is strictly before ``event_date``.
    """

    if timeframe == "D":
        raise ValueError("completed higher-timeframe lookup requires W or M")
    if timeframe not in {"W", "M"}:
        raise ValueError("timeframe must be W or M")

    lookup_date = event_date - timedelta(days=1)
    indicator_date = frame.indicator_date(name, lookup_date, timeframe=timeframe)
    if name == "kdj":
        value = frame.kdj_at(indicator_date, timeframe=timeframe)
    elif name == "macd":
        value = frame.macd_at(indicator_date, timeframe=timeframe)
    else:
        raise ValueError(f"unsupported completed indicator: {name}")
    return CompletedIndicatorEvidence(
        name=name,
        timeframe=timeframe,
        event_date=event_date,
        indicator_date=indicator_date,
        value=value,
    )
