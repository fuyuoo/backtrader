"""CSV snapshot reader used for deterministic local fixtures."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from attbacktrader.data import DailyBar


def read_daily_bars_csv(path: str | Path) -> tuple[DailyBar, ...]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        bars = [_daily_bar_from_row(row) for row in reader]

    return tuple(sorted(bars, key=lambda bar: (bar.symbol, bar.trade_date)))


def _daily_bar_from_row(row: dict[str, str]) -> DailyBar:
    return DailyBar(
        symbol=row["symbol"],
        trade_date=date.fromisoformat(row["trade_date"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume") or 0.0),
    )
