from __future__ import annotations

from datetime import date

from attbacktrader.data import DailyBar, IndexBar, TradingCalendar, assess_daily_bar_quality, trading_calendar_from_bars


def test_trading_calendar_detects_missing_sessions_without_weekend_heuristics() -> None:
    calendar = TradingCalendar(
        name="000001.SH",
        sessions=(date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)),
    )
    bars = (
        DailyBar("000001.SZ", date(2024, 1, 2), 10.0, 11.0, 9.0, 10.0, 1000.0),
        DailyBar("000001.SZ", date(2024, 1, 4), 10.0, 11.0, 9.0, 10.0, 1000.0),
    )

    issues = assess_daily_bar_quality(
        bars,
        symbol="000001.SZ",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 7),
        trading_calendar=calendar,
    )

    assert [issue.code for issue in issues] == ["MISSING_TRADING_SESSIONS"]
    assert issues[0].details["missing_examples"] == ["2024-01-03"]
    assert issues[0].details["missing_ranges"] == [
        {"start_date": "2024-01-03", "end_date": "2024-01-03"}
    ]


def test_trading_calendar_can_be_derived_from_index_bars() -> None:
    bars = (
        IndexBar("000001.SH", date(2024, 1, 2), 100.0, 101.0, 99.0, 100.0),
        IndexBar("000001.SH", date(2024, 1, 3), 101.0, 102.0, 100.0, 101.0),
    )

    calendar = trading_calendar_from_bars("000001.SH", bars)

    assert calendar is not None
    assert calendar.sessions_between(start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)) == (
        date(2024, 1, 2),
        date(2024, 1, 3),
    )
