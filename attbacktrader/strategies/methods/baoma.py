"""Baoma v1 strategy methods."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from attbacktrader.features import IndicatorRequirement, MarketFeatureRow, ma_indicator_name
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


@dataclass(frozen=True)
class BaomaEntry:
    dea_max_age_trading_days: int = 14
    ma_period: int = 60
    timeframe: str = "D"
    method_name: str = "baoma_entry"

    def __post_init__(self) -> None:
        if self.dea_max_age_trading_days < 0:
            raise ValueError("dea_max_age_trading_days must be non-negative")
        ma_indicator_name(self.ma_period)
        IndicatorRequirement("macd", self.timeframe)
        IndicatorRequirement(ma_indicator_name(self.ma_period), self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset(
            {
                IndicatorRequirement("macd", self.timeframe),
                IndicatorRequirement(ma_indicator_name(self.ma_period), self.timeframe),
            }
        )

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        signal_values = _baoma_entry_signal_values(
            row=row,
            previous_row=previous_row,
            ma_period=self.ma_period,
            timeframe=self.timeframe,
            dea_max_age_trading_days=self.dea_max_age_trading_days,
        )
        checks = signal_values["checks"]

        if not checks["required_values_available"]:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="BAOMA_ENTRY_UNAVAILABLE",
                signal_values=signal_values,
            )

        if (
            checks["price_above_ma60"]
            and checks["dea_recent_waterline"]
            and checks["previous_bearish_candle"]
        ):
            return TradeIntent(
                intent_type=TradeIntentType.ENTER,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="BAOMA_ENTRY_TRIGGERED",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="BAOMA_ENTRY_NOT_TRIGGERED",
            signal_values=signal_values,
        )


@dataclass(frozen=True)
class BaomaAddOn:
    dea_max_age_trading_days: int = 14
    ma_period: int = 60
    max_add_on_count: int = 2
    timeframe: str = "D"
    method_name: str = "baoma_add_on"

    def __post_init__(self) -> None:
        if self.max_add_on_count <= 0:
            raise ValueError("max_add_on_count must be positive")
        if self.dea_max_age_trading_days < 0:
            raise ValueError("dea_max_age_trading_days must be non-negative")
        ma_indicator_name(self.ma_period)
        IndicatorRequirement("macd", self.timeframe)
        IndicatorRequirement(ma_indicator_name(self.ma_period), self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset(
            {
                IndicatorRequirement("macd", self.timeframe),
                IndicatorRequirement(ma_indicator_name(self.ma_period), self.timeframe),
            }
        )

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        current_quantity: int = 0,
        entry_price: float | None = None,
        current_price: float | None = None,
        add_on_count: int = 0,
        ever_profitable: bool = False,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        current_quantity = max(0, int(current_quantity))
        add_on_count = max(0, int(add_on_count))
        signal_values = _baoma_entry_signal_values(
            row=row,
            previous_row=previous_row,
            ma_period=self.ma_period,
            timeframe=self.timeframe,
            dea_max_age_trading_days=self.dea_max_age_trading_days,
        )
        checks = dict(signal_values["checks"])
        checks.update(
            {
                "position_available": current_quantity > 0,
                "add_on_count_available": add_on_count < self.max_add_on_count,
                "ever_profitable_block": bool(ever_profitable),
            }
        )
        signal_values.update(
            {
                "current_quantity": current_quantity,
                "entry_price": entry_price,
                "current_price": current_price,
                "add_on_count": add_on_count,
                "max_add_on_count": self.max_add_on_count,
                "ever_profitable": bool(ever_profitable),
                "checks": checks,
                "attribution": _baoma_attribution_payload(
                    signal_values,
                    extra_checks={
                        "position.available": checks["position_available"],
                        "position.add_on_count_available": checks["add_on_count_available"],
                        "position.ever_profitable_block": checks["ever_profitable_block"],
                    },
                    extra_values={
                        "position.current_quantity": current_quantity,
                        "position.add_on_count": add_on_count,
                        "position.max_add_on_count": self.max_add_on_count,
                    },
                ),
            }
        )

        if not checks["required_values_available"] or not checks["position_available"]:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="BAOMA_ADD_ON_UNAVAILABLE",
                signal_values=signal_values,
            )

        triggered = (
            checks["price_above_ma60"]
            and checks["dea_recent_waterline"]
            and checks["previous_bearish_candle"]
            and checks["add_on_count_available"]
            and not checks["ever_profitable_block"]
        )
        if triggered:
            return TradeIntent(
                intent_type=TradeIntentType.ADD_ON,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="BAOMA_ADD_ON_TRIGGERED",
                signal_values=signal_values | {"position_action": "add_on"},
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="BAOMA_ADD_ON_NOT_TRIGGERED",
            signal_values=signal_values,
        )


@dataclass(frozen=True)
class BaomaMa60Stop:
    ma_period: int = 60
    timeframe: str = "D"
    method_name: str = "baoma_ma60_stop"

    def __post_init__(self) -> None:
        ma_indicator_name(self.ma_period)
        IndicatorRequirement(ma_indicator_name(self.ma_period), self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset({IndicatorRequirement(ma_indicator_name(self.ma_period), self.timeframe)})

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        entry_price: float | None = None,
        current_price: float | None = None,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        signal_values = _ma_exit_signal_values(
            row=row,
            previous_row=previous_row,
            ma_period=self.ma_period,
            timeframe=self.timeframe,
        )
        checks = signal_values["checks"]
        if not checks["required_values_available"]:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="BAOMA_MA60_STOP_UNAVAILABLE",
                signal_values=signal_values,
            )

        if checks["previous_price_below_ma"] and checks["current_price_below_ma"]:
            return TradeIntent(
                intent_type=TradeIntentType.EXIT_LOSS,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="BAOMA_MA60_STOP_TRIGGERED",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="BAOMA_MA60_STOP_NOT_TRIGGERED",
            signal_values=signal_values,
        )


@dataclass(frozen=True)
class BaomaMa25ProfitExit:
    ma_period: int = 25
    timeframe: str = "D"
    method_name: str = "baoma_ma25_profit_exit"

    def __post_init__(self) -> None:
        ma_indicator_name(self.ma_period)
        IndicatorRequirement(ma_indicator_name(self.ma_period), self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset({IndicatorRequirement(ma_indicator_name(self.ma_period), self.timeframe)})

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
        adjusted_remaining_cost_basis: float | None = None,
        cost_recovered: bool = False,
    ) -> TradeIntent:
        signal_values = _ma_exit_signal_values(
            row=row,
            previous_row=previous_row,
            ma_period=self.ma_period,
            timeframe=self.timeframe,
        )
        checks = dict(signal_values["checks"])
        cost_available = bool(cost_recovered) or (
            adjusted_remaining_cost_basis is not None and adjusted_remaining_cost_basis > 0
        )
        confirmed_profitable = bool(cost_recovered)
        if row is not None and adjusted_remaining_cost_basis is not None and adjusted_remaining_cost_basis > 0:
            confirmed_profitable = row.bar.close > adjusted_remaining_cost_basis
        checks.update(
            {
                "remaining_cost_available": cost_available,
                "confirmed_profitable": confirmed_profitable,
            }
        )
        checks["required_values_available"] = checks["required_values_available"] and cost_available
        signal_values.update(
            {
                "adjusted_remaining_cost_basis": adjusted_remaining_cost_basis,
                "cost_recovered": bool(cost_recovered),
                "checks": checks,
            }
        )
        signal_values["attribution"] = _ma_exit_attribution_payload(signal_values)

        if not checks["required_values_available"]:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="BAOMA_MA25_PROFIT_EXIT_UNAVAILABLE",
                signal_values=signal_values,
            )

        if (
            checks["previous_price_below_ma"]
            and checks["current_price_below_ma"]
            and checks["confirmed_profitable"]
        ):
            return TradeIntent(
                intent_type=TradeIntentType.EXIT_PROFIT,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="BAOMA_MA25_PROFIT_EXIT_TRIGGERED",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="BAOMA_MA25_PROFIT_EXIT_NOT_TRIGGERED",
            signal_values=signal_values,
        )


def _baoma_entry_signal_values(
    *,
    row: MarketFeatureRow | None,
    previous_row: MarketFeatureRow | None,
    ma_period: int,
    timeframe: str,
    dea_max_age_trading_days: int,
) -> dict[str, object]:
    values: dict[str, object] = {
        "timeframe": timeframe,
        "ma_period": ma_period,
        "dea_max_age_trading_days": dea_max_age_trading_days,
        "signal_trade_date": previous_row.trade_date.isoformat() if previous_row is not None else None,
        "close": previous_row.bar.close if previous_row is not None else None,
        "open": previous_row.bar.open if previous_row is not None else None,
        "ma60": None,
        "dea": None,
        "dea_waterline_start_date": None,
        "dea_waterline_age_trading_days": None,
    }
    checks = {
        "row_available": row is not None,
        "previous_row_available": previous_row is not None,
        "ma60_available": False,
        "macd_available": False,
        "dea_positive": False,
        "dea_waterline_found": False,
        "dea_recent_waterline": False,
        "price_above_ma60": False,
        "previous_bearish_candle": False,
        "required_values_available": False,
    }

    if row is not None and previous_row is not None:
        try:
            ma = previous_row.indicators.ma_at(ma_period, timeframe)
            values["ma60"] = ma.value
            checks["ma60_available"] = True
            checks["price_above_ma60"] = previous_row.bar.close > ma.value
        except KeyError:
            pass

        waterline = _dea_waterline(previous_row, timeframe=timeframe)
        checks["macd_available"] = waterline["macd_available"]
        checks["dea_positive"] = waterline["dea_positive"]
        checks["dea_waterline_found"] = waterline["dea_waterline_found"]
        values["dea"] = waterline["dea"]
        values["dea_waterline_start_date"] = waterline["dea_waterline_start_date"]
        values["dea_waterline_age_trading_days"] = waterline["dea_waterline_age_trading_days"]
        age = waterline["dea_waterline_age_trading_days"]
        checks["dea_recent_waterline"] = (
            checks["dea_positive"]
            and checks["dea_waterline_found"]
            and age is not None
            and age <= dea_max_age_trading_days
        )
        checks["previous_bearish_candle"] = previous_row.bar.close < previous_row.bar.open

    checks["required_values_available"] = checks["row_available"] and checks["previous_row_available"] and checks["ma60_available"] and checks["macd_available"]
    values["checks"] = checks
    values["attribution"] = _baoma_attribution_payload(values)
    return values


def _dea_waterline(row: MarketFeatureRow, *, timeframe: str) -> dict[str, object]:
    result: dict[str, object] = {
        "macd_available": False,
        "dea": None,
        "dea_positive": False,
        "dea_waterline_found": False,
        "dea_waterline_start_date": None,
        "dea_waterline_age_trading_days": None,
    }
    try:
        current_macd = row.indicators.macd_at(timeframe)
    except KeyError:
        return result

    result["macd_available"] = True
    result["dea"] = current_macd.signal
    result["dea_positive"] = current_macd.signal > 0
    if current_macd.signal <= 0:
        return result

    macd_by_key = row.indicators.frame.macd_by_key
    if macd_by_key is None:
        return result
    available_dates = sorted(
        key[-1]
        for key in macd_by_key
        if key[0] == timeframe and key[-1] <= row.trade_date
    )
    if row.trade_date not in available_dates:
        return result
    current_index = available_dates.index(row.trade_date)
    start_index = None
    for index in range(current_index, -1, -1):
        candidate_date = available_dates[index]
        if macd_by_key[(timeframe, candidate_date)].signal <= 0:
            if index + 1 <= current_index:
                start_index = index + 1
            break
    if start_index is None:
        return result

    start_date = available_dates[start_index]
    result["dea_waterline_found"] = True
    result["dea_waterline_start_date"] = start_date.isoformat()
    result["dea_waterline_age_trading_days"] = current_index - start_index
    return result


def _ma_exit_signal_values(
    *,
    row: MarketFeatureRow | None,
    previous_row: MarketFeatureRow | None,
    ma_period: int,
    timeframe: str,
) -> dict[str, object]:
    values: dict[str, object] = {
        "timeframe": timeframe,
        "ma_period": ma_period,
        "previous_close": previous_row.bar.close if previous_row is not None else None,
        "current_close": row.bar.close if row is not None else None,
        "previous_ma": None,
        "current_ma": None,
    }
    checks = {
        "row_available": row is not None,
        "previous_row_available": previous_row is not None,
        "previous_ma_available": False,
        "current_ma_available": False,
        "previous_price_below_ma": False,
        "current_price_below_ma": False,
        "required_values_available": False,
    }
    if row is not None and previous_row is not None:
        try:
            previous_ma = previous_row.indicators.ma_at(ma_period, timeframe)
            values["previous_ma"] = previous_ma.value
            checks["previous_ma_available"] = True
            checks["previous_price_below_ma"] = previous_row.bar.close < previous_ma.value
        except KeyError:
            pass
        try:
            current_ma = row.indicators.ma_at(ma_period, timeframe)
            values["current_ma"] = current_ma.value
            checks["current_ma_available"] = True
            checks["current_price_below_ma"] = row.bar.close < current_ma.value
        except KeyError:
            pass

    checks["required_values_available"] = (
        checks["row_available"]
        and checks["previous_row_available"]
        and checks["previous_ma_available"]
        and checks["current_ma_available"]
    )
    values["checks"] = checks
    values["attribution"] = _ma_exit_attribution_payload(values)
    return values


def _baoma_attribution_payload(
    signal_values: dict[str, object],
    *,
    extra_checks: dict[str, bool] | None = None,
    extra_values: dict[str, object] | None = None,
) -> dict[str, dict[str, object]]:
    checks = signal_values["checks"]
    return entry_attribution_payload(
        checks={
            "symbol.ma.price_above_ma60": checks["price_above_ma60"],
            "symbol.macd.dea_positive": checks["dea_positive"],
            "symbol.macd.dea_recent_waterline": checks["dea_recent_waterline"],
            "symbol.yesterday_bearish_candle": checks["previous_bearish_candle"],
            **dict(extra_checks or {}),
        },
        values={
            "symbol.close": signal_values["close"],
            "symbol.open": signal_values["open"],
            "symbol.ma.ma60": signal_values["ma60"],
            "symbol.macd.dea": signal_values["dea"],
            "symbol.macd.dea_waterline_age_trading_days": signal_values["dea_waterline_age_trading_days"],
            "symbol.macd.dea_waterline_max_age_days": signal_values["dea_max_age_trading_days"],
            **dict(extra_values or {}),
        },
    )


def _ma_exit_attribution_payload(signal_values: dict[str, object]) -> dict[str, dict[str, object]]:
    checks = signal_values["checks"]
    values = {
        "symbol.close.previous": signal_values["previous_close"],
        "symbol.close.current": signal_values["current_close"],
        "symbol.ma.previous": signal_values["previous_ma"],
        "symbol.ma.current": signal_values["current_ma"],
    }
    if "adjusted_remaining_cost_basis" in signal_values:
        values["position.adjusted_remaining_cost_basis"] = signal_values["adjusted_remaining_cost_basis"]
    return entry_attribution_payload(
        checks={
            "symbol.ma.previous_price_below_ma": checks["previous_price_below_ma"],
            "symbol.ma.current_price_below_ma": checks["current_price_below_ma"],
            "position.profit_exit_confirmed_profitable": checks.get("confirmed_profitable", False),
        },
        values=values,
    )
