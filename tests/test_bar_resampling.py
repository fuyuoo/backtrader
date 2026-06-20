from datetime import date

import pytest

from attbacktrader.data import DailyBar, IndexBar, resample_daily_bars


def test_resample_daily_bars_to_weekly_ohlcv() -> None:
    bars = (
        DailyBar("000001.SZ", date(2024, 1, 2), 10.0, 11.0, 9.0, 10.5, 100.0),
        DailyBar("000001.SZ", date(2024, 1, 3), 10.5, 12.0, 10.0, 11.5, 200.0),
        DailyBar("000001.SZ", date(2024, 1, 8), 11.5, 13.0, 11.0, 12.5, 300.0),
    )

    weekly = resample_daily_bars(bars, frequency="W")

    assert weekly == (
        DailyBar("000001.SZ", date(2024, 1, 3), 10.0, 12.0, 9.0, 11.5, 300.0),
        DailyBar("000001.SZ", date(2024, 1, 8), 11.5, 13.0, 11.0, 12.5, 300.0),
    )


def test_resample_index_daily_bars_to_monthly_preserves_amount_sum() -> None:
    bars = (
        IndexBar("000001.SH", date(2024, 1, 2), 100.0, 102.0, 99.0, 101.0, 1000.0, 2000.0),
        IndexBar("000001.SH", date(2024, 1, 31), 101.0, 103.0, 100.0, 102.0, 1500.0, 2500.0),
        IndexBar("000001.SH", date(2024, 2, 1), 102.0, 104.0, 101.0, 103.0, 1200.0, 2200.0),
    )

    monthly = resample_daily_bars(bars, frequency="M")

    assert monthly == (
        IndexBar("000001.SH", date(2024, 1, 31), 100.0, 103.0, 99.0, 102.0, 2500.0, 4500.0),
        IndexBar("000001.SH", date(2024, 2, 1), 102.0, 104.0, 101.0, 103.0, 1200.0, 2200.0),
    )


def test_resample_daily_bars_rejects_unknown_frequency() -> None:
    with pytest.raises(ValueError, match="frequency"):
        resample_daily_bars([], frequency="D")
