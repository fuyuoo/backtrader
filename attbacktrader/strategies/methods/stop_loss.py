"""Stop-loss methods for strategy templates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from attbacktrader.features import IndicatorRequirement, MarketFeatureRow, atr_indicator_name
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


@dataclass(frozen=True)
class FixedPercentStop:
    loss_percent: float = 0.05
    method_name: str = "fixed_percent_stop"
    required_indicators: ClassVar[frozenset[IndicatorRequirement]] = frozenset()

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
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")

        stop_price = entry_price * (1.0 - self.loss_percent)
        stop_hit = current_price <= stop_price
        signal_values = {
            "entry_price": entry_price,
            "current_price": current_price,
            "loss_percent": self.loss_percent,
            "stop_price": stop_price,
            "checks": {"current_price_at_or_below_stop": stop_hit},
        }

        if stop_hit:
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


@dataclass(frozen=True)
class AtrMultipleStop:
    period: int = 14
    multiple: float = 2.0
    timeframe: str = "D"
    method_name: str = "atr_multiple_stop"

    def __post_init__(self) -> None:
        if self.multiple <= 0:
            raise ValueError("multiple must be positive")
        atr_indicator_name(self.period)
        IndicatorRequirement(atr_indicator_name(self.period), self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset({IndicatorRequirement(atr_indicator_name(self.period), self.timeframe)})

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        entry_price: float,
        current_price: float,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if row is None:
            raise ValueError("ATR stop evaluation requires row")

        try:
            atr = row.indicators.atr_at(self.period, self.timeframe)
        except KeyError:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="ATR_UNAVAILABLE",
                signal_values={
                    "timeframe": self.timeframe,
                    "period": self.period,
                    "multiple": self.multiple,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "checks": {"atr_available": False},
                },
            )

        stop_price = entry_price - (atr.value * self.multiple)
        stop_hit = current_price <= stop_price
        signal_values = {
            "timeframe": self.timeframe,
            "period": self.period,
            "multiple": self.multiple,
            "entry_price": entry_price,
            "current_price": current_price,
            f"atr{self.period}": atr.value,
            "stop_price": stop_price,
            "indicator_date": _optional_indicator_date(
                row,
                atr_indicator_name(self.period),
                timeframe=self.timeframe,
            ),
            "checks": {
                "atr_available": True,
                "current_price_at_or_below_stop": stop_hit,
            },
        }

        if stop_hit:
            return TradeIntent(
                intent_type=TradeIntentType.EXIT_LOSS,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="ATR_MULTIPLE_STOP",
                signal_values=signal_values,
                risk_price=stop_price,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="ATR_MULTIPLE_STOP_NOT_HIT",
            signal_values=signal_values,
            risk_price=stop_price,
        )


def _optional_indicator_date(row: MarketFeatureRow | None, name: str, *, timeframe: str) -> str | None:
    if row is None:
        return None
    try:
        return row.indicators.indicator_date(name, timeframe).isoformat()
    except KeyError:
        return None
