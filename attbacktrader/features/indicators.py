"""Indicator calculations used by strategy methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class KDJValue:
    k: float
    d: float
    j: float


@dataclass(frozen=True)
class MACDValue:
    line: float
    signal: float
    histogram: float


@dataclass(frozen=True)
class MAValue:
    period: int
    value: float


@dataclass(frozen=True)
class RSIValue:
    period: int
    value: float


@dataclass(frozen=True)
class ATRValue:
    period: int
    value: float


def calculate_sma(values: Sequence[float], *, period: int) -> tuple[MAValue | None, ...]:
    """Calculate a simple moving average without filling warmup values."""

    if period <= 0:
        raise ValueError("period must be positive")

    rolling_sum = 0.0
    averages: list[MAValue | None] = []
    for index, value in enumerate(values):
        rolling_sum += float(value)
        if index >= period:
            rolling_sum -= float(values[index - period])
        if index + 1 < period:
            averages.append(None)
            continue
        averages.append(MAValue(period=period, value=rolling_sum / period))

    return tuple(averages)


def calculate_rsi(closes: Sequence[float], *, period: int = 14) -> tuple[RSIValue | None, ...]:
    """Calculate Wilder RSI without filling values before enough deltas exist."""

    if period <= 0:
        raise ValueError("period must be positive")
    if not closes:
        return ()

    values: list[RSIValue | None] = [None]
    gains: list[float] = []
    losses: list[float] = []
    average_gain: float | None = None
    average_loss: float | None = None

    for index in range(1, len(closes)):
        delta = float(closes[index]) - float(closes[index - 1])
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)

        if index <= period:
            gains.append(gain)
            losses.append(loss)
            if index < period:
                values.append(None)
                continue
            average_gain = sum(gains) / period
            average_loss = sum(losses) / period
        else:
            assert average_gain is not None
            assert average_loss is not None
            average_gain = ((average_gain * (period - 1)) + gain) / period
            average_loss = ((average_loss * (period - 1)) + loss) / period

        values.append(RSIValue(period=period, value=_rsi_from_averages(average_gain, average_loss)))

    return tuple(values)


def calculate_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int = 14,
) -> tuple[ATRValue | None, ...]:
    """Calculate Wilder ATR without filling values before enough bars exist."""

    if period <= 0:
        raise ValueError("period must be positive")
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must have the same length")
    if not closes:
        return ()

    true_ranges: list[float] = []
    values: list[ATRValue | None] = []
    atr_value: float | None = None

    for index, close in enumerate(closes):
        high = float(highs[index])
        low = float(lows[index])
        if index == 0:
            true_range = high - low
        else:
            previous_close = float(closes[index - 1])
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

        if index < period:
            true_ranges.append(true_range)
            if index + 1 < period:
                values.append(None)
                continue
            atr_value = sum(true_ranges) / period
        else:
            assert atr_value is not None
            atr_value = ((atr_value * (period - 1)) + true_range) / period

        values.append(ATRValue(period=period, value=atr_value))

    return tuple(values)


def calculate_kdj(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int = 9,
    initial_k: float = 50.0,
    initial_d: float = 50.0,
) -> tuple[KDJValue, ...]:
    """Calculate KDJ values using the common RSV smoothing formula."""

    if period <= 0:
        raise ValueError("period must be positive")

    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must have the same length")

    k_value = initial_k
    d_value = initial_d
    values: list[KDJValue] = []

    for index, close in enumerate(closes):
        start = max(0, index - period + 1)
        highest_high = max(highs[start : index + 1])
        lowest_low = min(lows[start : index + 1])

        if highest_high == lowest_low:
            rsv = 50.0
        else:
            rsv = (close - lowest_low) / (highest_high - lowest_low) * 100.0

        k_value = (2.0 / 3.0) * k_value + (1.0 / 3.0) * rsv
        d_value = (2.0 / 3.0) * d_value + (1.0 / 3.0) * k_value
        j_value = 3.0 * k_value - 2.0 * d_value
        values.append(KDJValue(k=k_value, d=d_value, j=j_value))

    return tuple(values)


def calculate_macd(
    closes: Sequence[float],
    *,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[MACDValue, ...]:
    """Calculate MACD using EMA(close, fast) - EMA(close, slow)."""

    if not closes:
        return ()
    if fast_period <= 0 or slow_period <= 0 or signal_period <= 0:
        raise ValueError("MACD periods must be positive")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")

    fast_ema = _calculate_ema(closes, period=fast_period)
    slow_ema = _calculate_ema(closes, period=slow_period)
    macd_lines = tuple(fast - slow for fast, slow in zip(fast_ema, slow_ema))
    signal_lines = _calculate_ema(macd_lines, period=signal_period)

    return tuple(
        MACDValue(
            line=line,
            signal=signal,
            histogram=line - signal,
        )
        for line, signal in zip(macd_lines, signal_lines)
    )


def _calculate_ema(values: Sequence[float], *, period: int) -> tuple[float, ...]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return ()

    alpha = 2.0 / (period + 1.0)
    ema = float(values[0])
    ema_values = [ema]
    for value in values[1:]:
        ema = alpha * float(value) + (1.0 - alpha) * ema
        ema_values.append(ema)
    return tuple(ema_values)


def _rsi_from_averages(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        if average_gain == 0:
            return 50.0
        return 100.0

    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))
