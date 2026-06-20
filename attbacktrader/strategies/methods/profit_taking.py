"""Profit-taking methods for strategy templates."""

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
    rsi_indicator_name,
)
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


@dataclass(frozen=True)
class KdjOverheatedExit:
    threshold: float = 100.0
    method_name: str = "kdj_overheated_exit"
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
        kdj_above_threshold = kdj.j > self.threshold
        signal_values = {
            "kdj_k": kdj.k,
            "kdj_d": kdj.d,
            "kdj_j": kdj.j,
            "threshold": self.threshold,
            "checks": {"kdj_j_above_threshold": kdj_above_threshold},
        }

        if kdj_above_threshold:
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


@dataclass(frozen=True)
class MacdBearishCrossoverExit:
    method_name: str = "macd_bearish_crossover_exit"
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

        bearish_crossover = previous_macd.line >= previous_macd.signal and macd.line < macd.signal
        signal_values.update(
            {
                "previous_macd_line": previous_macd.line,
                "previous_macd_signal": previous_macd.signal,
                "previous_macd_histogram": previous_macd.histogram,
                "checks": signal_values["checks"] | {"bearish_crossover": bearish_crossover},
            }
        )
        if bearish_crossover:
            return TradeIntent(
                intent_type=TradeIntentType.EXIT_PROFIT,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MACD_BEARISH_CROSSOVER",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="MACD_BEARISH_CROSSOVER_NOT_FOUND",
            signal_values=signal_values,
        )


@dataclass(frozen=True)
class RsiOverboughtExit:
    period: int = 14
    threshold: float = 70.0
    timeframe: str = "D"
    method_name: str = "rsi_overbought_exit"

    def __post_init__(self) -> None:
        if not 0 < self.threshold < 100:
            raise ValueError("threshold must be greater than 0 and less than 100")
        rsi_indicator_name(self.period)
        IndicatorRequirement(rsi_indicator_name(self.period), self.timeframe)

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset({IndicatorRequirement(rsi_indicator_name(self.period), self.timeframe)})

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        if row is None:
            raise ValueError("RSI exit evaluation requires row")

        try:
            rsi = row.indicators.rsi_at(self.period, self.timeframe)
        except KeyError:
            return TradeIntent(
                intent_type=TradeIntentType.HOLD,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="RSI_UNAVAILABLE",
                signal_values={
                    "timeframe": self.timeframe,
                    "period": self.period,
                    "threshold": self.threshold,
                    "checks": {"rsi_available": False},
                },
            )

        rsi_overbought = rsi.value >= self.threshold
        signal_values = {
            "timeframe": self.timeframe,
            "period": self.period,
            "threshold": self.threshold,
            f"rsi{self.period}": rsi.value,
            "indicator_date": _optional_indicator_date(
                row,
                rsi_indicator_name(self.period),
                timeframe=self.timeframe,
            ),
            "checks": {"rsi_available": True, "rsi_at_or_above_threshold": rsi_overbought},
        }

        if rsi_overbought:
            return TradeIntent(
                intent_type=TradeIntentType.EXIT_PROFIT,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="RSI_OVERBOUGHT",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="RSI_NOT_OVERBOUGHT",
            signal_values=signal_values,
        )


@dataclass(frozen=True)
class MovingAverageMacdWeakeningExit:
    fast_period: int = 20
    slow_period: int = 60
    timeframe: str = "D"
    method_name: str = "ma_macd_weakening_exit"

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
            raise ValueError("MA+MACD exit evaluation requires row")

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
                reason_code="MA_MACD_WEAKENING_UNAVAILABLE",
                signal_values=unavailable_signal_values | {"checks": {"required_values_available": False}},
            )

        previous_macd = _optional_macd_from_row(previous_row, timeframe=self.timeframe)
        close = row.bar.close
        price_below_fast_ma = close < fast_ma.value
        fast_ma_below_slow_ma = fast_ma.value < slow_ma.value
        macd_line_below_signal = macd.line < macd.signal
        bearish_crossover = (
            previous_macd is not None
            and previous_macd.line >= previous_macd.signal
            and macd.line < macd.signal
        )
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
                "price_below_fast_ma": price_below_fast_ma,
                "fast_ma_below_slow_ma": fast_ma_below_slow_ma,
                "macd_line_below_signal": macd_line_below_signal,
                "macd_bearish_crossover": bearish_crossover,
            },
        }
        if previous_macd is not None:
            signal_values.update(
                {
                    "previous_macd_line": previous_macd.line,
                    "previous_macd_signal": previous_macd.signal,
                    "previous_macd_histogram": previous_macd.histogram,
                }
            )

        if price_below_fast_ma or fast_ma_below_slow_ma or macd_line_below_signal or bearish_crossover:
            return TradeIntent(
                intent_type=TradeIntentType.EXIT_PROFIT,
                symbol=symbol,
                trade_date=trade_date,
                method_name=self.method_name,
                reason_code="MA_MACD_WEAKENING",
                signal_values=signal_values,
            )

        return TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="MA_MACD_WEAKENING_NOT_FOUND",
            signal_values=signal_values,
        )


def _kdj_from_row(row: MarketFeatureRow | None) -> KDJValue:
    if row is None:
        raise ValueError("KDJ exit evaluation requires kdj or row")
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
