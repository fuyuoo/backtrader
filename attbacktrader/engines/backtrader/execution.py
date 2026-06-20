"""Backtrader broker execution settings for attbacktrader runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import backtrader as bt


@dataclass(frozen=True)
class BacktraderBrokerSettings:
    commission_rate: float = 0.0
    stamp_tax_rate: float = 0.0
    transfer_fee_rate: float = 0.0
    slippage_type: Literal["percent", "fixed"] = "percent"
    slippage_value: float = 0.0

    def __post_init__(self) -> None:
        rates = {
            "commission_rate": self.commission_rate,
            "stamp_tax_rate": self.stamp_tax_rate,
            "transfer_fee_rate": self.transfer_fee_rate,
            "slippage_value": self.slippage_value,
        }
        invalid = [name for name, value in rates.items() if value < 0]
        if invalid:
            raise ValueError(f"broker execution settings cannot be negative: {invalid}")


@dataclass(frozen=True)
class BacktraderAShareSettings:
    enabled: bool = False
    board_lot_size: int = 100
    suspension_enabled: bool = True
    limit_up_down_enabled: bool = True
    t_plus_one_enabled: bool = True

    def __post_init__(self) -> None:
        if self.board_lot_size <= 0:
            raise ValueError("board_lot_size must be positive")


class AShareCommissionInfo(bt.CommInfoBase):
    params = (
        ("commission_rate", 0.0),
        ("stamp_tax_rate", 0.0),
        ("transfer_fee_rate", 0.0),
    )

    def _getcommission(self, size, price, pseudoexec):
        trade_value = abs(size) * price
        fee_rate = self.p.commission_rate + self.p.transfer_fee_rate
        if size < 0:
            fee_rate += self.p.stamp_tax_rate
        return trade_value * fee_rate


def configure_backtrader_broker(
    cerebro: bt.Cerebro,
    *,
    initial_cash: float,
    broker_settings: BacktraderBrokerSettings | None = None,
) -> None:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")

    broker_settings = broker_settings or BacktraderBrokerSettings()
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.set_coc(True)
    cerebro.broker.addcommissioninfo(
        AShareCommissionInfo(
            commission_rate=broker_settings.commission_rate,
            stamp_tax_rate=broker_settings.stamp_tax_rate,
            transfer_fee_rate=broker_settings.transfer_fee_rate,
        )
    )

    if broker_settings.slippage_value <= 0:
        return

    if broker_settings.slippage_type == "percent":
        cerebro.broker.set_slippage_perc(
            broker_settings.slippage_value,
            slip_open=True,
            slip_match=True,
            slip_out=True,
        )
    else:
        cerebro.broker.set_slippage_fixed(
            broker_settings.slippage_value,
            slip_open=True,
            slip_match=True,
            slip_out=True,
        )
