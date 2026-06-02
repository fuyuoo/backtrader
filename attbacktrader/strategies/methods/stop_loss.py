"""Stop-loss methods for strategy templates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


@dataclass(frozen=True)
class FixedPercentStop:
    loss_percent: float = 0.05
    method_name: str = "fixed_percent_stop"

    def __post_init__(self) -> None:
        if not 0 < self.loss_percent < 1:
            raise ValueError("loss_percent must be greater than 0 and less than 1")

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        entry_price: float,
        current_price: float,
    ) -> TradeIntent:
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")

        stop_price = entry_price * (1.0 - self.loss_percent)
        signal_values = {
            "entry_price": entry_price,
            "current_price": current_price,
            "loss_percent": self.loss_percent,
            "stop_price": stop_price,
        }

        if current_price <= stop_price:
            return TradeIntent(
                intent_type=TradeIntentType.EXIT_LOSS,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="FIXED_5_PERCENT_STOP",
                signal_values=signal_values,
                risk_price=stop_price,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="FIXED_5_PERCENT_STOP_NOT_HIT",
            signal_values=signal_values,
            risk_price=stop_price,
        )
