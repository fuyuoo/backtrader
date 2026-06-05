"""Business-level sizing rules consumed by engine adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping

from attbacktrader.features import IndicatorRequirement, MarketFeatureRow, SUPPORTED_ATR_PERIODS


@dataclass(frozen=True)
class SizingDecision:
    method_name: str
    symbol: str
    trade_date: date
    requested_quantity: int
    target_value: float | None = None
    available_cash: float | None = None
    cash_reserve: float | None = None
    max_position_value: float | None = None
    max_total_exposure_value: float | None = None
    max_risk_group_exposure_value: float | None = None
    turnover_budget_value: float | None = None
    risk_budget_value: float | None = None
    risk_per_share: float | None = None
    blocked_by: str | None = None
    reason_code: str = "SIZING_ACCEPTED"
    signal_values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_values", MappingProxyType(dict(self.signal_values)))


@dataclass(frozen=True)
class EqualWeightSizing:
    """Default entry sizing with optional portfolio, exposure, turnover, and ATR-risk caps."""

    method_name: str = "equal_weight"
    max_holding_count: int | None = None
    max_position_percent: float | None = None
    max_total_exposure_percent: float | None = None
    max_risk_group_exposure_percent: float | None = None
    cash_reserve_percent: float = 0.0
    max_turnover_percent: float | None = None
    rebalance_min_interval_days: int | None = None
    risk_group_level: int = 1
    atr_risk_percent: float | None = None
    atr_multiple: float = 2.0
    atr_period: int = 14
    atr_timeframe: str = "D"
    min_order_quantity: int | None = None

    def __post_init__(self) -> None:
        if self.max_holding_count is not None and self.max_holding_count <= 0:
            raise ValueError("max_holding_count must be positive")
        if self.min_order_quantity is not None and self.min_order_quantity <= 0:
            raise ValueError("min_order_quantity must be positive")
        _validate_percent(self.max_position_percent, "max_position_percent")
        _validate_percent(self.max_total_exposure_percent, "max_total_exposure_percent")
        _validate_percent(self.max_risk_group_exposure_percent, "max_risk_group_exposure_percent")
        if not 0 <= self.cash_reserve_percent < 1:
            raise ValueError("cash_reserve_percent must be between 0 and 1")
        _validate_percent(self.max_turnover_percent, "max_turnover_percent")
        _validate_percent(self.atr_risk_percent, "atr_risk_percent")
        if self.rebalance_min_interval_days is not None and self.rebalance_min_interval_days < 0:
            raise ValueError("rebalance_min_interval_days must be non-negative")
        if self.risk_group_level not in {1, 2, 3}:
            raise ValueError("risk_group_level must be 1, 2, or 3")
        if self.atr_multiple <= 0:
            raise ValueError("atr_multiple must be positive")
        if self.atr_period <= 0:
            raise ValueError("atr_period must be positive")
        if self.atr_period not in SUPPORTED_ATR_PERIODS:
            raise ValueError(f"unsupported ATR period: {self.atr_period}")
        if self.atr_timeframe not in {"D", "W", "M"}:
            raise ValueError("atr_timeframe must be D, W, or M")

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        if self.atr_risk_percent is None:
            return frozenset()
        return frozenset({IndicatorRequirement(f"atr{self.atr_period}", self.atr_timeframe)})

    def size_entry(
        self,
        *,
        symbol: str,
        trade_date: date,
        price: float,
        cash: float,
        total_value: float,
        current_quantity: int = 0,
        current_holding_count: int = 0,
        fallback_quantity: int = 0,
        row: MarketFeatureRow | None = None,
        current_exposure_value: float = 0.0,
        current_risk_group_exposure_value: float = 0.0,
        current_turnover_value: float = 0.0,
        last_rebalance_date: date | None = None,
        risk_group: str | None = None,
    ) -> SizingDecision:
        if price <= 0:
            raise ValueError("price must be positive")
        if total_value <= 0:
            raise ValueError("total_value must be positive")

        fallback_quantity = max(0, int(fallback_quantity))
        current_quantity = max(0, int(current_quantity))
        current_holding_count = max(0, int(current_holding_count))
        current_exposure_value = max(0.0, float(current_exposure_value))
        current_risk_group_exposure_value = max(0.0, float(current_risk_group_exposure_value))
        current_turnover_value = max(0.0, float(current_turnover_value))

        if not self._has_active_caps:
            return self._decision(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=fallback_quantity,
                price=price,
                cash=cash,
                total_value=total_value,
                fallback_quantity=fallback_quantity,
                current_holding_count=current_holding_count,
                current_exposure_value=current_exposure_value,
                current_risk_group_exposure_value=current_risk_group_exposure_value,
                current_turnover_value=current_turnover_value,
                risk_group=risk_group,
            )

        blocked_interval = self._rebalance_interval_blocked(trade_date, last_rebalance_date)
        if blocked_interval is not None:
            return self._blocked_decision(
                symbol=symbol,
                trade_date=trade_date,
                price=price,
                cash=cash,
                total_value=total_value,
                fallback_quantity=fallback_quantity,
                current_holding_count=current_holding_count,
                blocked_by="REBALANCE_INTERVAL",
                current_exposure_value=current_exposure_value,
                current_risk_group_exposure_value=current_risk_group_exposure_value,
                current_turnover_value=current_turnover_value,
                risk_group=risk_group,
                extra_signal_values=blocked_interval,
            )

        if (
            self.max_holding_count is not None
            and current_quantity == 0
            and current_holding_count >= self.max_holding_count
        ):
            return self._blocked_decision(
                symbol=symbol,
                trade_date=trade_date,
                price=price,
                cash=cash,
                total_value=total_value,
                fallback_quantity=fallback_quantity,
                current_holding_count=current_holding_count,
                blocked_by="MAX_HOLDING_COUNT",
                current_exposure_value=current_exposure_value,
                current_risk_group_exposure_value=current_risk_group_exposure_value,
                current_turnover_value=current_turnover_value,
                risk_group=risk_group,
            )

        cash_reserve = total_value * self.cash_reserve_percent
        available_cash = max(0.0, cash - cash_reserve)
        target_value = self._base_target_value(
            price=price,
            total_value=total_value,
            fallback_quantity=fallback_quantity,
        )

        max_position_value = None
        if self.max_position_percent is not None:
            max_position_value = total_value * self.max_position_percent
            target_value = min(target_value, max_position_value)

        current_position_value = current_quantity * price
        incremental_target_value = max(0.0, target_value - current_position_value)
        buy_value = min(incremental_target_value, available_cash)

        max_total_exposure_value = None
        if self.max_total_exposure_percent is not None:
            max_total_exposure_value = total_value * self.max_total_exposure_percent
            buy_value = min(buy_value, max(0.0, max_total_exposure_value - current_exposure_value))

        max_risk_group_exposure_value = None
        if self.max_risk_group_exposure_percent is not None:
            max_risk_group_exposure_value = total_value * self.max_risk_group_exposure_percent
            buy_value = min(
                buy_value,
                max(0.0, max_risk_group_exposure_value - current_risk_group_exposure_value),
            )

        turnover_budget_value = None
        if self.max_turnover_percent is not None:
            turnover_budget_value = total_value * self.max_turnover_percent
            buy_value = min(buy_value, max(0.0, turnover_budget_value - current_turnover_value))

        requested_quantity = int(buy_value / price)
        atr_value = None
        risk_budget_value = None
        risk_per_share = None
        if self.atr_risk_percent is not None:
            atr_value = self._atr_value(row)
            if atr_value is None or atr_value <= 0:
                return self._blocked_decision(
                    symbol=symbol,
                    trade_date=trade_date,
                    price=price,
                    cash=cash,
                    total_value=total_value,
                    fallback_quantity=fallback_quantity,
                    current_holding_count=current_holding_count,
                    cash_reserve=cash_reserve,
                    available_cash=available_cash,
                    target_value=target_value,
                    max_position_value=max_position_value,
                    max_total_exposure_value=max_total_exposure_value,
                    max_risk_group_exposure_value=max_risk_group_exposure_value,
                    turnover_budget_value=turnover_budget_value,
                    blocked_by="ATR_RISK_UNAVAILABLE",
                    extra_signal_values={"atr_value": atr_value},
                    current_exposure_value=current_exposure_value,
                    current_risk_group_exposure_value=current_risk_group_exposure_value,
                    current_turnover_value=current_turnover_value,
                    risk_group=risk_group,
                )

            risk_budget_value = total_value * self.atr_risk_percent
            risk_per_share = atr_value * self.atr_multiple
            requested_quantity = min(requested_quantity, int(risk_budget_value / risk_per_share))

        min_order_values = self._min_order_values(requested_quantity)
        requested_quantity = int(min_order_values["requested_quantity_after_min_order"])

        if requested_quantity <= 0:
            return self._blocked_decision(
                symbol=symbol,
                trade_date=trade_date,
                price=price,
                cash=cash,
                total_value=total_value,
                fallback_quantity=fallback_quantity,
                current_holding_count=current_holding_count,
                cash_reserve=cash_reserve,
                available_cash=available_cash,
                target_value=target_value,
                max_position_value=max_position_value,
                max_total_exposure_value=max_total_exposure_value,
                max_risk_group_exposure_value=max_risk_group_exposure_value,
                turnover_budget_value=turnover_budget_value,
                risk_budget_value=risk_budget_value,
                risk_per_share=risk_per_share,
                blocked_by="SIZING_ZERO_QUANTITY",
                extra_signal_values={"atr_value": atr_value, **min_order_values},
                current_exposure_value=current_exposure_value,
                current_risk_group_exposure_value=current_risk_group_exposure_value,
                current_turnover_value=current_turnover_value,
                risk_group=risk_group,
            )

        return self._decision(
            symbol=symbol,
            trade_date=trade_date,
            requested_quantity=requested_quantity,
            price=price,
            cash=cash,
            total_value=total_value,
            fallback_quantity=fallback_quantity,
            current_holding_count=current_holding_count,
            cash_reserve=cash_reserve,
            available_cash=available_cash,
            target_value=target_value,
            max_position_value=max_position_value,
            max_total_exposure_value=max_total_exposure_value,
            max_risk_group_exposure_value=max_risk_group_exposure_value,
            turnover_budget_value=turnover_budget_value,
            risk_budget_value=risk_budget_value,
            risk_per_share=risk_per_share,
            extra_signal_values={"atr_value": atr_value, **min_order_values},
            current_exposure_value=current_exposure_value,
            current_risk_group_exposure_value=current_risk_group_exposure_value,
            current_turnover_value=current_turnover_value,
            risk_group=risk_group,
        )

    @property
    def _has_active_caps(self) -> bool:
        return (
            self.max_holding_count is not None
            or self.max_position_percent is not None
            or self.max_total_exposure_percent is not None
            or self.max_risk_group_exposure_percent is not None
            or self.cash_reserve_percent > 0
            or self.max_turnover_percent is not None
            or self.rebalance_min_interval_days is not None
            or self.atr_risk_percent is not None
            or self.min_order_quantity is not None
        )

    def _rebalance_interval_blocked(
        self,
        trade_date: date,
        last_rebalance_date: date | None,
    ) -> dict[str, Any] | None:
        if self.rebalance_min_interval_days is None or last_rebalance_date is None:
            return None
        elapsed_days = (trade_date - last_rebalance_date).days
        if elapsed_days >= self.rebalance_min_interval_days:
            return None
        return {
            "last_rebalance_date": last_rebalance_date.isoformat(),
            "elapsed_days": elapsed_days,
        }

    def _base_target_value(self, *, price: float, total_value: float, fallback_quantity: int) -> float:
        if self.max_holding_count is not None:
            return total_value / self.max_holding_count
        return fallback_quantity * price

    def _atr_value(self, row: MarketFeatureRow | None) -> float | None:
        if row is None:
            return None
        try:
            return row.indicators.atr_at(self.atr_period, self.atr_timeframe).value
        except KeyError:
            return None

    def _min_order_values(self, requested_quantity: int) -> dict[str, Any]:
        applied = (
            self.min_order_quantity is not None
            and 0 < requested_quantity < self.min_order_quantity
        )
        return {
            "min_order_quantity": self.min_order_quantity,
            "min_order_quantity_applied": applied,
            "requested_quantity_before_min_order": requested_quantity,
            "requested_quantity_after_min_order": self.min_order_quantity if applied else requested_quantity,
        }

    def _blocked_decision(
        self,
        *,
        symbol: str,
        trade_date: date,
        price: float,
        cash: float,
        total_value: float,
        fallback_quantity: int,
        current_holding_count: int,
        blocked_by: str,
        cash_reserve: float | None = None,
        available_cash: float | None = None,
        target_value: float | None = None,
        max_position_value: float | None = None,
        max_total_exposure_value: float | None = None,
        max_risk_group_exposure_value: float | None = None,
        turnover_budget_value: float | None = None,
        risk_budget_value: float | None = None,
        risk_per_share: float | None = None,
        extra_signal_values: Mapping[str, Any] | None = None,
        current_exposure_value: float = 0.0,
        current_risk_group_exposure_value: float = 0.0,
        current_turnover_value: float = 0.0,
        risk_group: str | None = None,
    ) -> SizingDecision:
        return self._decision(
            symbol=symbol,
            trade_date=trade_date,
            requested_quantity=0,
            price=price,
            cash=cash,
            total_value=total_value,
            fallback_quantity=fallback_quantity,
            current_holding_count=current_holding_count,
            cash_reserve=cash_reserve,
            available_cash=available_cash,
            target_value=target_value,
            max_position_value=max_position_value,
            max_total_exposure_value=max_total_exposure_value,
            max_risk_group_exposure_value=max_risk_group_exposure_value,
            turnover_budget_value=turnover_budget_value,
            risk_budget_value=risk_budget_value,
            risk_per_share=risk_per_share,
            blocked_by=blocked_by,
            reason_code="SIZING_BLOCKED",
            extra_signal_values=extra_signal_values,
            current_exposure_value=current_exposure_value,
            current_risk_group_exposure_value=current_risk_group_exposure_value,
            current_turnover_value=current_turnover_value,
            risk_group=risk_group,
        )

    def _decision(
        self,
        *,
        symbol: str,
        trade_date: date,
        requested_quantity: int,
        price: float,
        cash: float,
        total_value: float,
        fallback_quantity: int,
        current_holding_count: int,
        cash_reserve: float | None = None,
        available_cash: float | None = None,
        target_value: float | None = None,
        max_position_value: float | None = None,
        max_total_exposure_value: float | None = None,
        max_risk_group_exposure_value: float | None = None,
        turnover_budget_value: float | None = None,
        risk_budget_value: float | None = None,
        risk_per_share: float | None = None,
        blocked_by: str | None = None,
        reason_code: str = "SIZING_ACCEPTED",
        extra_signal_values: Mapping[str, Any] | None = None,
        current_exposure_value: float = 0.0,
        current_risk_group_exposure_value: float = 0.0,
        current_turnover_value: float = 0.0,
        risk_group: str | None = None,
    ) -> SizingDecision:
        signal_values = {
            "method_name": self.method_name,
            "fallback_quantity": fallback_quantity,
            "requested_quantity": requested_quantity,
            "price": price,
            "cash": cash,
            "total_value": total_value,
            "current_holding_count": current_holding_count,
            "current_exposure_value": current_exposure_value,
            "current_risk_group_exposure_value": current_risk_group_exposure_value,
            "current_turnover_value": current_turnover_value,
            "risk_group": risk_group,
            "target_value": target_value,
            "available_cash": available_cash,
            "cash_reserve": cash_reserve,
            "max_position_value": max_position_value,
            "max_total_exposure_value": max_total_exposure_value,
            "max_risk_group_exposure_value": max_risk_group_exposure_value,
            "turnover_budget_value": turnover_budget_value,
            "risk_budget_value": risk_budget_value,
            "risk_per_share": risk_per_share,
            "max_holding_count": self.max_holding_count,
            "max_position_percent": self.max_position_percent,
            "max_total_exposure_percent": self.max_total_exposure_percent,
            "max_risk_group_exposure_percent": self.max_risk_group_exposure_percent,
            "cash_reserve_percent": self.cash_reserve_percent,
            "max_turnover_percent": self.max_turnover_percent,
            "rebalance_min_interval_days": self.rebalance_min_interval_days,
            "risk_group_level": self.risk_group_level,
            "atr_risk_percent": self.atr_risk_percent,
            "atr_multiple": self.atr_multiple,
            "atr_period": self.atr_period,
            "atr_timeframe": self.atr_timeframe,
            "min_order_quantity": self.min_order_quantity,
            "blocked_by": blocked_by,
        }
        if extra_signal_values:
            signal_values.update(extra_signal_values)

        return SizingDecision(
            method_name=self.method_name,
            symbol=symbol,
            trade_date=trade_date,
            requested_quantity=max(0, int(requested_quantity)),
            target_value=target_value,
            available_cash=available_cash,
            cash_reserve=cash_reserve,
            max_position_value=max_position_value,
            max_total_exposure_value=max_total_exposure_value,
            max_risk_group_exposure_value=max_risk_group_exposure_value,
            turnover_budget_value=turnover_budget_value,
            risk_budget_value=risk_budget_value,
            risk_per_share=risk_per_share,
            blocked_by=blocked_by,
            reason_code=reason_code,
            signal_values=signal_values,
        )


def _validate_percent(value: float | None, field_name: str) -> None:
    if value is None:
        return
    if not 0 < value <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
