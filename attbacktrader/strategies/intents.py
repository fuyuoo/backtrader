"""Standard trade intent model emitted before sizing and execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class TradeIntentType(str, Enum):
    ENTER = "enter"
    ADD_ON = "add_on"
    EXIT_PROFIT = "exit_profit"
    EXIT_LOSS = "exit_loss"
    HOLD = "hold"
    AVOID = "avoid"


@dataclass(frozen=True)
class TradeIntent:
    intent_type: TradeIntentType
    symbol: str
    trade_date: date
    method_name: str
    reason_code: str
    signal_values: Mapping[str, Any] = field(default_factory=dict)
    target_price: float | None = None
    risk_price: float | None = None
    confidence: float | None = None
    blocked_by: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_values", MappingProxyType(dict(self.signal_values)))
