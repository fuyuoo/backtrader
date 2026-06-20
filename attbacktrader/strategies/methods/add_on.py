"""Add-on methods for existing positions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from attbacktrader.features import IndicatorRequirement, KDJValue, MarketFeatureRow
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


@dataclass(frozen=True)
class NoAddOn:
    method_name: str = "none"
    required_indicators: ClassVar[frozenset[IndicatorRequirement]] = frozenset()

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        current_quantity: int = 0,
        entry_price: float | None = None,
        current_price: float | None = None,
        add_on_count: int = 0,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="NO_ADD_ON",
        )


@dataclass(frozen=True)
class KdjOversoldAddOn:
    threshold: float = 13.0
    min_profit_percent: float = 0.0
    max_add_on_count: int = 1
    method_name: str = "kdj_oversold_add_on"
    required_indicators: ClassVar[frozenset[IndicatorRequirement]] = frozenset({IndicatorRequirement("kdj", "D")})

    def __post_init__(self) -> None:
        if self.min_profit_percent <= -1:
            raise ValueError("min_profit_percent must be greater than -1")
        if self.max_add_on_count <= 0:
            raise ValueError("max_add_on_count must be positive")

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        current_quantity: int = 0,
        entry_price: float | None = None,
        current_price: float | None = None,
        add_on_count: int = 0,
        kdj: KDJValue | None = None,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        kdj = kdj or _optional_kdj_from_row(row)
        current_quantity = max(0, int(current_quantity))
        add_on_count = max(0, int(add_on_count))
        entry_price_valid = entry_price is not None and entry_price > 0
        current_price_valid = current_price is not None and current_price > 0
        unrealized_return = None
        if entry_price_valid and current_price_valid:
            unrealized_return = float(current_price) / float(entry_price) - 1.0

        kdj_available = kdj is not None
        position_available = current_quantity > 0 and entry_price_valid and current_price_valid
        kdj_below_threshold = bool(kdj_available and kdj.j < self.threshold)
        profitable_enough = bool(unrealized_return is not None and unrealized_return >= self.min_profit_percent)
        add_on_count_available = add_on_count < self.max_add_on_count
        checks = {
            "required_values_available": kdj_available and position_available,
            "kdj_j_below_threshold": kdj_below_threshold,
            "unrealized_return_at_or_above_min": profitable_enough,
            "add_on_count_available": add_on_count_available,
        }
        signal_values = {
            "kdj_k": kdj.k if kdj is not None else None,
            "kdj_d": kdj.d if kdj is not None else None,
            "kdj_j": kdj.j if kdj is not None else None,
            "threshold": self.threshold,
            "current_quantity": current_quantity,
            "entry_price": entry_price,
            "current_price": current_price,
            "unrealized_return": unrealized_return,
            "min_profit_percent": self.min_profit_percent,
            "add_on_count": add_on_count,
            "max_add_on_count": self.max_add_on_count,
            "checks": checks,
            "attribution": entry_attribution_payload(
                checks={
                    "symbol.kdj.j_below_threshold": kdj_below_threshold,
                    "position.unrealized_return_at_or_above_min": profitable_enough,
                    "position.add_on_count_available": add_on_count_available,
                },
                values={
                    "symbol.kdj.k": kdj.k if kdj is not None else None,
                    "symbol.kdj.d": kdj.d if kdj is not None else None,
                    "symbol.kdj.j": kdj.j if kdj is not None else None,
                    "symbol.kdj.threshold": self.threshold,
                    "position.current_quantity": current_quantity,
                    "position.entry_price": entry_price,
                    "position.current_price": current_price,
                    "position.unrealized_return": unrealized_return,
                    "position.min_profit_percent": self.min_profit_percent,
                    "position.add_on_count": add_on_count,
                    "position.max_add_on_count": self.max_add_on_count,
                },
            ),
        }

        if all(checks.values()):
            return TradeIntent(
                intent_type=TradeIntentType.ADD_ON,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="KDJ_OVERSOLD_ADD_ON",
                signal_values=signal_values | {"position_action": "add_on"},
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="KDJ_OVERSOLD_ADD_ON_NOT_TRIGGERED",
            signal_values=signal_values,
        )


def _optional_kdj_from_row(row: MarketFeatureRow | None) -> KDJValue | None:
    if row is None:
        return None
    return row.indicators.kdj
