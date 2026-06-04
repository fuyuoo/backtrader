"""Data quality checks for prepared market inputs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from attbacktrader.data.bars import DailyBar
from attbacktrader.data.calendar import TradingCalendar


@dataclass(frozen=True)
class DataQualityIssue:
    scope: str
    code: str
    severity: str
    message: str
    symbol: str | None = None
    trade_date: date | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


def assess_daily_bar_quality(
    bars: Sequence[DailyBar],
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    trading_calendar: TradingCalendar | None = None,
    max_calendar_gap_days: int = 10,
) -> tuple[DataQualityIssue, ...]:
    issues: list[DataQualityIssue] = []

    if not bars:
        return (
            DataQualityIssue(
                scope="daily_bars",
                code="NO_BARS",
                severity="error",
                message=f"no daily bars available for {symbol}",
                symbol=symbol,
            ),
        )

    mismatched_symbols = sorted({bar.symbol for bar in bars if bar.symbol != symbol})
    if mismatched_symbols:
        issues.append(
            DataQualityIssue(
                scope="daily_bars",
                code="SYMBOL_MISMATCH",
                severity="error",
                message=f"daily bars contain symbols other than {symbol}",
                symbol=symbol,
                details={"mismatched_symbols": mismatched_symbols},
            )
        )

    original_dates = [bar.trade_date for bar in bars]
    duplicate_dates = sorted(date_value for date_value, count in Counter(original_dates).items() if count > 1)
    if duplicate_dates:
        issues.append(
            DataQualityIssue(
                scope="daily_bars",
                code="DUPLICATE_DATES",
                severity="warning",
                message=f"daily bars contain duplicate trade dates for {symbol}",
                symbol=symbol,
                details={"trade_dates": [value.isoformat() for value in duplicate_dates]},
            )
        )

    if any(next_date <= current_date for current_date, next_date in zip(original_dates, original_dates[1:])):
        issues.append(
            DataQualityIssue(
                scope="daily_bars",
                code="NON_INCREASING_DATES",
                severity="warning",
                message=f"daily bars are not strictly increasing for {symbol}",
                symbol=symbol,
            )
        )

    ordered_dates = tuple(sorted(set(original_dates)))
    expected_start_date = start_date
    expected_end_date = end_date
    if trading_calendar is not None:
        sessions = trading_calendar.sessions_between(start_date=start_date, end_date=end_date)
        if sessions:
            expected_start_date = sessions[0]
            expected_end_date = sessions[-1]

    if ordered_dates[0] > expected_start_date:
        issues.append(
            DataQualityIssue(
                scope="daily_bars",
                code="MISSING_LEADING_RANGE",
                severity="warning",
                message=f"first available daily bar for {symbol} is after requested start date",
                symbol=symbol,
                trade_date=ordered_dates[0],
                details={
                    "requested_start_date": start_date.isoformat(),
                    "expected_first_session": expected_start_date.isoformat(),
                    "calendar": trading_calendar.name if trading_calendar is not None else None,
                },
            )
        )
    if ordered_dates[-1] < expected_end_date:
        issues.append(
            DataQualityIssue(
                scope="daily_bars",
                code="MISSING_TRAILING_RANGE",
                severity="warning",
                message=f"last available daily bar for {symbol} is before requested end date",
                symbol=symbol,
                trade_date=ordered_dates[-1],
                details={
                    "requested_end_date": end_date.isoformat(),
                    "expected_last_session": expected_end_date.isoformat(),
                    "calendar": trading_calendar.name if trading_calendar is not None else None,
                },
            )
        )

    if trading_calendar is not None:
        missing_sessions = trading_calendar.missing_sessions(
            ordered_dates,
            start_date=start_date,
            end_date=end_date,
        )
        if missing_sessions:
            issues.append(
                DataQualityIssue(
                    scope="daily_bars",
                    code="MISSING_TRADING_SESSIONS",
                    severity="warning",
                    message=f"daily bars are missing trading sessions for {symbol}",
                    symbol=symbol,
                    details={
                        "calendar": trading_calendar.name,
                        "missing_count": len(missing_sessions),
                        "missing_examples": [value.isoformat() for value in missing_sessions[:5]],
                        "missing_ranges": [
                            {
                                "start_date": start.isoformat(),
                                "end_date": end.isoformat(),
                            }
                            for start, end in trading_calendar.gap_ranges(
                                ordered_dates,
                                start_date=start_date,
                                end_date=end_date,
                            )
                        ],
                    },
                )
            )
        return tuple(issues)

    for previous_date, current_date in zip(ordered_dates, ordered_dates[1:]):
        gap_days = (current_date - previous_date).days
        if gap_days > max_calendar_gap_days:
            issues.append(
                DataQualityIssue(
                    scope="daily_bars",
                    code="LARGE_CALENDAR_GAP",
                    severity="warning",
                    message=f"daily bars contain a large calendar gap for {symbol}",
                    symbol=symbol,
                    trade_date=current_date,
                    details={
                        "previous_trade_date": previous_date.isoformat(),
                        "current_trade_date": current_date.isoformat(),
                        "gap_days": gap_days,
                    },
                )
            )

    return tuple(issues)
