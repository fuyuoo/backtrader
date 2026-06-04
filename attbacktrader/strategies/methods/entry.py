"""Entry methods for strategy templates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from attbacktrader.features import (
    IndicatorRequirement,
    KDJValue,
    MACDValue,
    MarketFeatureRow,
    ma_indicator_name,
)
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


@dataclass(frozen=True)
class KdjOversoldEntry:
    threshold: float = 13.0
    method_name: str = "kdj_oversold_entry"
    required_indicators: ClassVar[frozenset[IndicatorRequirement]] = frozenset({IndicatorRequirement("kdj", "D")})

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        kdj: KDJValue | None = None,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        kdj = kdj or _kdj_from_row(row)
        kdj_below_threshold = kdj.j < self.threshold
        signal_values = {
            "kdj_k": kdj.k,
            "kdj_d": kdj.d,
            "kdj_j": kdj.j,
            "threshold": self.threshold,
            "checks": {"kdj_j_below_threshold": kdj_below_threshold},
            "attribution": entry_attribution_payload(
                checks={"symbol.kdj.j_below_threshold": kdj_below_threshold},
                values={
                    "symbol.kdj.k": kdj.k,
                    "symbol.kdj.d": kdj.d,
                    "symbol.kdj.j": kdj.j,
                    "symbol.kdj.threshold": self.threshold,
                },
            ),
        }

        if kdj_below_threshold:
            return TradeIntent(
                intent_type=TradeIntentType.ENTER,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="KDJ_J_BELOW_13",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="KDJ_J_NOT_BELOW_13",
            signal_values=signal_values,
        )


@dataclass(frozen=True)
class MacdBullishCrossoverEntry:
    method_name: str = "macd_bullish_crossover_entry"
    timeframe: str = "D"

    def __post_init__(self) -> None:
        IndicatorRequirement("macd", self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset({IndicatorRequirement("macd", self.timeframe)})

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        macd: MACDValue | None = None,
        previous_macd: MACDValue | None = None,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        macd = macd or _optional_macd_from_row(row, timeframe=self.timeframe)
        previous_macd = previous_macd or _optional_macd_from_row(previous_row, timeframe=self.timeframe)
        if macd is None:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MACD_UNAVAILABLE",
                signal_values={"timeframe": self.timeframe, "checks": {"macd_available": False}},
            )
        signal_values = {
            "macd_line": macd.line,
            "macd_signal": macd.signal,
            "macd_histogram": macd.histogram,
            "timeframe": self.timeframe,
            "indicator_date": _optional_indicator_date(row, "macd", timeframe=self.timeframe),
            "checks": {"macd_available": True, "previous_macd_available": previous_macd is not None},
        }

        if previous_macd is None:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MACD_PREVIOUS_UNAVAILABLE",
                signal_values=signal_values,
            )

        bullish_crossover = previous_macd.line <= previous_macd.signal and macd.line > macd.signal
        signal_values.update(
            {
                "previous_macd_line": previous_macd.line,
                "previous_macd_signal": previous_macd.signal,
                "previous_macd_histogram": previous_macd.histogram,
                "checks": signal_values["checks"] | {"bullish_crossover": bullish_crossover},
            }
        )
        if bullish_crossover:
            return TradeIntent(
                intent_type=TradeIntentType.ENTER,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MACD_BULLISH_CROSSOVER",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="MACD_BULLISH_CROSSOVER_NOT_FOUND",
            signal_values=signal_values,
        )


@dataclass(frozen=True)
class MovingAverageBullishTrendEntry:
    fast_period: int = 20
    slow_period: int = 60
    timeframe: str = "D"
    method_name: str = "ma_bullish_trend_entry"

    def __post_init__(self) -> None:
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")
        ma_indicator_name(self.fast_period)
        ma_indicator_name(self.slow_period)
        IndicatorRequirement(ma_indicator_name(self.fast_period), self.timeframe)
        IndicatorRequirement(ma_indicator_name(self.slow_period), self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset(
            {
                IndicatorRequirement(ma_indicator_name(self.fast_period), self.timeframe),
                IndicatorRequirement(ma_indicator_name(self.slow_period), self.timeframe),
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
        if row is None:
            raise ValueError("MA bullish trend entry evaluation requires row")

        try:
            fast_ma = row.indicators.ma_at(self.fast_period, self.timeframe)
            slow_ma = row.indicators.ma_at(self.slow_period, self.timeframe)
        except KeyError:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MA_TREND_UNAVAILABLE",
                signal_values={
                    "timeframe": self.timeframe,
                    "fast_period": self.fast_period,
                    "slow_period": self.slow_period,
                    "checks": {"ma_values_available": False},
                },
            )

        close = row.bar.close
        price_above_fast_ma = close > fast_ma.value
        fast_ma_above_slow_ma = fast_ma.value > slow_ma.value
        signal_values = {
            "timeframe": self.timeframe,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "close": close,
            f"ma{self.fast_period}": fast_ma.value,
            f"ma{self.slow_period}": slow_ma.value,
            "fast_indicator_date": _optional_indicator_date(
                row,
                ma_indicator_name(self.fast_period),
                timeframe=self.timeframe,
            ),
            "slow_indicator_date": _optional_indicator_date(
                row,
                ma_indicator_name(self.slow_period),
                timeframe=self.timeframe,
            ),
            "checks": {
                "ma_values_available": True,
                "price_above_fast_ma": price_above_fast_ma,
                "fast_ma_above_slow_ma": fast_ma_above_slow_ma,
            },
        }

        if price_above_fast_ma and fast_ma_above_slow_ma:
            return TradeIntent(
                intent_type=TradeIntentType.ENTER,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MA_BULLISH_TREND",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="MA_BULLISH_TREND_NOT_FOUND",
            signal_values=signal_values,
        )


@dataclass(frozen=True)
class MovingAverageMacdBullishConfirmationEntry:
    fast_period: int = 20
    slow_period: int = 60
    timeframe: str = "D"
    method_name: str = "ma_macd_bullish_confirmation_entry"

    def __post_init__(self) -> None:
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")
        ma_indicator_name(self.fast_period)
        ma_indicator_name(self.slow_period)
        IndicatorRequirement("macd", self.timeframe)
        IndicatorRequirement(ma_indicator_name(self.fast_period), self.timeframe)
        IndicatorRequirement(ma_indicator_name(self.slow_period), self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset(
            {
                IndicatorRequirement("macd", self.timeframe),
                IndicatorRequirement(ma_indicator_name(self.fast_period), self.timeframe),
                IndicatorRequirement(ma_indicator_name(self.slow_period), self.timeframe),
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
        if row is None:
            raise ValueError("MA+MACD entry evaluation requires row")

        unavailable_signal_values = {
            "timeframe": self.timeframe,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
        }
        try:
            fast_ma = row.indicators.ma_at(self.fast_period, self.timeframe)
            slow_ma = row.indicators.ma_at(self.slow_period, self.timeframe)
            macd = row.indicators.macd_at(self.timeframe)
        except KeyError:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MA_MACD_CONFIRMATION_UNAVAILABLE",
                signal_values=unavailable_signal_values | {"checks": {"required_values_available": False}},
            )

        close = row.bar.close
        price_above_fast_ma = close > fast_ma.value
        fast_ma_above_slow_ma = fast_ma.value > slow_ma.value
        macd_bullish = macd.line > macd.signal
        macd_histogram_positive = macd.histogram > 0
        signal_values = {
            "timeframe": self.timeframe,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "close": close,
            f"ma{self.fast_period}": fast_ma.value,
            f"ma{self.slow_period}": slow_ma.value,
            "macd_line": macd.line,
            "macd_signal": macd.signal,
            "macd_histogram": macd.histogram,
            "fast_indicator_date": _optional_indicator_date(
                row,
                ma_indicator_name(self.fast_period),
                timeframe=self.timeframe,
            ),
            "slow_indicator_date": _optional_indicator_date(
                row,
                ma_indicator_name(self.slow_period),
                timeframe=self.timeframe,
            ),
            "macd_indicator_date": _optional_indicator_date(row, "macd", timeframe=self.timeframe),
            "checks": {
                "required_values_available": True,
                "price_above_fast_ma": price_above_fast_ma,
                "fast_ma_above_slow_ma": fast_ma_above_slow_ma,
                "macd_line_above_signal": macd_bullish,
                "macd_histogram_positive": macd_histogram_positive,
            },
        }

        if price_above_fast_ma and fast_ma_above_slow_ma and macd_bullish and macd_histogram_positive:
            return TradeIntent(
                intent_type=TradeIntentType.ENTER,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MA_MACD_BULLISH_CONFIRMATION",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="MA_MACD_BULLISH_CONFIRMATION_NOT_FOUND",
            signal_values=signal_values,
        )


def _kdj_from_row(row: MarketFeatureRow | None) -> KDJValue:
    if row is None:
        raise ValueError("KDJ entry evaluation requires kdj or row")
    return row.indicators.kdj


def _optional_macd_from_row(row: MarketFeatureRow | None, *, timeframe: str) -> MACDValue | None:
    if row is None:
        return None
    try:
        return row.indicators.macd_at(timeframe)
    except KeyError:
        return None


def _optional_indicator_date(row: MarketFeatureRow | None, name: str, *, timeframe: str) -> str | None:
    if row is None:
        return None
    try:
        return row.indicators.indicator_date(name, timeframe).isoformat()
    except KeyError:
        return None
