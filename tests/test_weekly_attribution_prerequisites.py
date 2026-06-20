from datetime import date
from pathlib import Path

import pytest

from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.features import (
    IndicatorRequirement,
    build_indicator_snapshots_for_requirements,
    completed_indicator_before_event,
    indicator_frame_from_snapshots,
)


def test_completed_weekly_indicator_lookup_uses_previous_completed_week() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    snapshots = build_indicator_snapshots_for_requirements(
        bars,
        indicator_requirements=(
            IndicatorRequirement("kdj", "W"),
            IndicatorRequirement("macd", "W"),
        ),
    )
    frame = indicator_frame_from_snapshots(snapshots)

    monday_kdj = completed_indicator_before_event(
        frame,
        name="kdj",
        timeframe="W",
        event_date=date(2024, 1, 8),
    )
    assert monday_kdj.indicator_date == date(2024, 1, 5)
    assert monday_kdj.value == frame.kdj_at(date(2024, 1, 5), timeframe="W")
    with pytest.raises(KeyError, match="indicator is missing"):
        completed_indicator_before_event(
            frame,
            name="macd",
            timeframe="W",
            event_date=date(2024, 1, 5),
        )


def test_completed_weekly_indicator_lookup_does_not_use_same_event_date_week() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    snapshots = build_indicator_snapshots_for_requirements(
        bars,
        indicator_requirements=(IndicatorRequirement("macd", "W"),),
    )
    frame = indicator_frame_from_snapshots(snapshots)

    thursday_macd = completed_indicator_before_event(
        frame,
        name="macd",
        timeframe="W",
        event_date=date(2024, 1, 11),
    )

    assert frame.indicator_date("macd", date(2024, 1, 11), timeframe="W") == date(2024, 1, 11)
    assert thursday_macd.indicator_date == date(2024, 1, 5)
    assert thursday_macd.value == frame.macd_at(date(2024, 1, 5), timeframe="W")


def test_completed_weekly_indicator_lookup_rejects_daily_timeframe() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    snapshots = build_indicator_snapshots_for_requirements(
        bars,
        indicator_requirements=(IndicatorRequirement("macd", "D"),),
    )
    frame = indicator_frame_from_snapshots(snapshots)

    with pytest.raises(ValueError, match="requires W or M"):
        completed_indicator_before_event(
            frame,
            name="macd",
            timeframe="D",
            event_date=date(2024, 1, 8),
        )
