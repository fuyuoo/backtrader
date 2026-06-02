"""Profit-taking methods for strategy templates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from attbacktrader.features import KDJValue
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


@dataclass(frozen=True)
class KdjOverheatedExit:
    threshold: float = 100.0
    method_name: str = "kdj_overheated_exit"

    def evaluate(self, *, symbol: str, trade_date: date, kdj: KDJValue) -> TradeIntent:
        signal_values = {"kdj_k": kdj.k, "kdj_d": kdj.d, "kdj_j": kdj.j, "threshold": self.threshold}

        if kdj.j > self.threshold:
            return TradeIntent(
                intent_type=TradeIntentType.EXIT_PROFIT,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="KDJ_J_ABOVE_100",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="KDJ_J_NOT_ABOVE_100",
            signal_values=signal_values,
        )
