"""Tradability status records for order-constraint checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TradabilityStatus:
    symbol: str
    trade_date: date
    is_suspended: bool = False
    is_limit_up: bool = False
    is_limit_down: bool = False
    close: float | None = None
    up_limit: float | None = None
    down_limit: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol cannot be empty")

        prices = {
            "close": self.close,
            "up_limit": self.up_limit,
            "down_limit": self.down_limit,
        }
        invalid = [name for name, value in prices.items() if value is not None and value <= 0]
        if invalid:
            raise ValueError(f"tradability prices must be positive: {invalid}")
