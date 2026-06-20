"""Trading calendar utilities derived from market sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

from attbacktrader.data.bars import DailyBar
from attbacktrader.data.indexes import IndexBar


@dataclass(frozen=True)
class TradingCalendar:
    name: str
    sessions: tuple[date, ...]

    def __post_init__(self) -> None:
        ordered_sessions = tuple(sorted(set(self.sessions)))
        object.__setattr__(self, "sessions", ordered_sessions)
        if not self.name:
            raise ValueError("calendar name cannot be empty")

    def sessions_between(self, *, start_date: date, end_date: date) -> tuple[date, ...]:
        return tuple(session for session in self.sessions if start_date <= session <= end_date)

    def missing_sessions(
        self,
        available_dates: Iterable[date],
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[date, ...]:
        available = set(available_dates)
        return tuple(session for session in self.sessions_between(start_date=start_date, end_date=end_date) if session not in available)

    def gap_ranges(
        self,
        available_dates: Iterable[date],
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[tuple[date, date], ...]:
        missing = self.missing_sessions(available_dates, start_date=start_date, end_date=end_date)
        if not missing:
            return ()

        ranges: list[tuple[date, date]] = []
        start = missing[0]
        previous = missing[0]
        session_index = {session: index for index, session in enumerate(self.sessions)}

        for current in missing[1:]:
            if session_index[current] == session_index[previous] + 1:
                previous = current
                continue
            ranges.append((start, previous))
            start = current
            previous = current

        ranges.append((start, previous))
        return tuple(ranges)


def trading_calendar_from_bars(
    name: str,
    bars: Sequence[DailyBar | IndexBar],
) -> TradingCalendar | None:
    sessions = tuple(bar.trade_date for bar in bars)
    if not sessions:
        return None
    return TradingCalendar(name=name, sessions=sessions)
