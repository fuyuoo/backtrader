"""Market bar records used by the research pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol cannot be empty")

        prices = {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }
        invalid = [name for name, value in prices.items() if value <= 0]
        if invalid:
            raise ValueError(f"daily bar prices must be positive: {invalid}")

        if self.high < self.low:
            raise ValueError("high cannot be lower than low")

        if not self.low <= self.open <= self.high:
            raise ValueError("open must be between low and high")

        if not self.low <= self.close <= self.high:
            raise ValueError("close must be between low and high")


DailyBar = MarketBar
