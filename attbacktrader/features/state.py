"""Rolling indicator state helpers for exact incremental continuation."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from attbacktrader.data import DailyBar
from attbacktrader.features.indicators import ATRValue, KDJValue, MACDValue, RSIValue
from attbacktrader.features.registry import indicator_period, normalize_indicator_names
from attbacktrader.features.snapshots import IndicatorSnapshot


STATEFUL_INDICATOR_NAMES = frozenset({"kdj", "macd", "rsi14", "atr14"})


def indicator_states_from_bars(
    indicator_names: Sequence[str],
    bars: Sequence[DailyBar],
) -> dict[str, dict[str, Any]]:
    """Build rolling states after the last bar for stateful indicators."""

    names = normalize_indicator_names(indicator_names)
    ordered_bars = _ordered_single_symbol_bars(bars)
    if not ordered_bars:
        return {}

    states: dict[str, dict[str, Any]] = {}
    if "kdj" in names:
        states["kdj"] = _kdj_state_from_bars(ordered_bars)
    if "macd" in names:
        states["macd"] = _macd_state_from_bars(ordered_bars)

    for name in names:
        if name.startswith("rsi"):
            state = _rsi_state_from_bars(ordered_bars, period=_required_period(name))
            if state is not None:
                states[name] = state
        if name.startswith("atr"):
            state = _atr_state_from_bars(ordered_bars, period=_required_period(name))
            if state is not None:
                states[name] = state

    return states


def build_indicator_snapshots_from_state(
    bars: Sequence[DailyBar],
    *,
    indicator_names: Sequence[str],
    timeframe: str = "D",
    states: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[IndicatorSnapshot, ...], dict[str, dict[str, Any]]]:
    """Append indicator snapshots from saved rolling states."""

    names = normalize_indicator_names(indicator_names)
    unsupported = tuple(name for name in names if name not in STATEFUL_INDICATOR_NAMES)
    if unsupported:
        raise ValueError(f"stateful append does not support indicators: {', '.join(unsupported)}")

    ordered_bars = _ordered_single_symbol_bars(bars)
    working_states = {
        name: dict(states[name])
        for name in names
    }
    if not ordered_bars:
        return (), working_states

    snapshots: list[IndicatorSnapshot] = []
    for bar in ordered_bars:
        values: dict[str, float] = {}
        if "kdj" in names:
            value, working_states["kdj"] = _advance_kdj_state(bar, working_states["kdj"])
            values.update({"kdj_k": value.k, "kdj_d": value.d, "kdj_j": value.j})
        if "macd" in names:
            value, working_states["macd"] = _advance_macd_state(bar, working_states["macd"])
            values.update(
                {
                    "macd_line": value.line,
                    "macd_signal": value.signal,
                    "macd_histogram": value.histogram,
                }
            )
        for name in names:
            if name.startswith("rsi"):
                period = _required_period(name)
                value, working_states[name] = _advance_rsi_state(bar, working_states[name])
                values[f"rsi{period}"] = value.value
            if name.startswith("atr"):
                period = _required_period(name)
                value, working_states[name] = _advance_atr_state(bar, working_states[name])
                values[f"atr{period}"] = value.value

        snapshots.append(
            IndicatorSnapshot(
                symbol=bar.symbol,
                trade_date=bar.trade_date,
                timeframe=timeframe,
                **values,
            )
        )

    return tuple(snapshots), working_states


def _kdj_state_from_bars(bars: Sequence[DailyBar], *, period: int = 9) -> dict[str, Any]:
    state: dict[str, Any] = {
        "period": period,
        "k": 50.0,
        "d": 50.0,
        "tail_highs": [],
        "tail_lows": [],
    }
    for bar in bars:
        _, state = _advance_kdj_state(bar, state)
    return state


def _advance_kdj_state(bar: DailyBar, state: Mapping[str, Any]) -> tuple[KDJValue, dict[str, Any]]:
    period = int(state.get("period", 9))
    tail_highs = [float(value) for value in state.get("tail_highs", [])]
    tail_lows = [float(value) for value in state.get("tail_lows", [])]
    window_highs = [*tail_highs, float(bar.high)]
    window_lows = [*tail_lows, float(bar.low)]

    highest_high = max(window_highs)
    lowest_low = min(window_lows)
    if highest_high == lowest_low:
        rsv = 50.0
    else:
        rsv = (float(bar.close) - lowest_low) / (highest_high - lowest_low) * 100.0

    k_value = (2.0 / 3.0) * float(state["k"]) + (1.0 / 3.0) * rsv
    d_value = (2.0 / 3.0) * float(state["d"]) + (1.0 / 3.0) * k_value
    value = KDJValue(k=k_value, d=d_value, j=3.0 * k_value - 2.0 * d_value)

    tail_size = max(0, period - 1)
    return value, {
        "period": period,
        "k": k_value,
        "d": d_value,
        "tail_highs": [*tail_highs, float(bar.high)][-tail_size:] if tail_size else [],
        "tail_lows": [*tail_lows, float(bar.low)][-tail_size:] if tail_size else [],
    }


def _macd_state_from_bars(
    bars: Sequence[DailyBar],
    *,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, Any]:
    first_close = float(bars[0].close)
    state: dict[str, Any] = {
        "fast_period": fast_period,
        "slow_period": slow_period,
        "signal_period": signal_period,
        "fast_ema": first_close,
        "slow_ema": first_close,
        "signal_ema": 0.0,
    }
    for bar in bars[1:]:
        _, state = _advance_macd_state(bar, state)
    return state


def _advance_macd_state(bar: DailyBar, state: Mapping[str, Any]) -> tuple[MACDValue, dict[str, Any]]:
    fast_period = int(state.get("fast_period", 12))
    slow_period = int(state.get("slow_period", 26))
    signal_period = int(state.get("signal_period", 9))
    close = float(bar.close)

    fast_ema = _ema_next(float(state["fast_ema"]), close, period=fast_period)
    slow_ema = _ema_next(float(state["slow_ema"]), close, period=slow_period)
    line = fast_ema - slow_ema
    signal = _ema_next(float(state["signal_ema"]), line, period=signal_period)
    value = MACDValue(line=line, signal=signal, histogram=line - signal)
    return value, {
        "fast_period": fast_period,
        "slow_period": slow_period,
        "signal_period": signal_period,
        "fast_ema": fast_ema,
        "slow_ema": slow_ema,
        "signal_ema": signal,
    }


def _rsi_state_from_bars(bars: Sequence[DailyBar], *, period: int) -> dict[str, Any] | None:
    if len(bars) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        delta = float(bars[index].close) - float(bars[index - 1].close)
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    for index in range(period + 1, len(bars)):
        delta = float(bars[index].close) - float(bars[index - 1].close)
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period

    return {
        "period": period,
        "average_gain": average_gain,
        "average_loss": average_loss,
        "previous_close": float(bars[-1].close),
    }


def _advance_rsi_state(bar: DailyBar, state: Mapping[str, Any]) -> tuple[RSIValue, dict[str, Any]]:
    period = int(state["period"])
    delta = float(bar.close) - float(state["previous_close"])
    gain = max(delta, 0.0)
    loss = max(-delta, 0.0)
    average_gain = ((float(state["average_gain"]) * (period - 1)) + gain) / period
    average_loss = ((float(state["average_loss"]) * (period - 1)) + loss) / period
    value = RSIValue(period=period, value=_rsi_from_averages(average_gain, average_loss))
    return value, {
        "period": period,
        "average_gain": average_gain,
        "average_loss": average_loss,
        "previous_close": float(bar.close),
    }


def _atr_state_from_bars(bars: Sequence[DailyBar], *, period: int) -> dict[str, Any] | None:
    if len(bars) < period:
        return None

    true_ranges: list[float] = []
    for index in range(period):
        bar = bars[index]
        if index == 0:
            true_range = float(bar.high) - float(bar.low)
        else:
            previous_close = float(bars[index - 1].close)
            true_range = _true_range(bar, previous_close)
        true_ranges.append(true_range)

    atr_value = sum(true_ranges) / period
    previous_close = float(bars[period - 1].close)

    for bar in bars[period:]:
        true_range = _true_range(bar, previous_close)
        atr_value = ((atr_value * (period - 1)) + true_range) / period
        previous_close = float(bar.close)

    return {
        "period": period,
        "atr": atr_value,
        "previous_close": previous_close,
    }


def _advance_atr_state(bar: DailyBar, state: Mapping[str, Any]) -> tuple[ATRValue, dict[str, Any]]:
    period = int(state["period"])
    true_range = _true_range(bar, float(state["previous_close"]))
    atr_value = ((float(state["atr"]) * (period - 1)) + true_range) / period
    value = ATRValue(period=period, value=atr_value)
    return value, {
        "period": period,
        "atr": atr_value,
        "previous_close": float(bar.close),
    }


def _ema_next(previous: float, value: float, *, period: int) -> float:
    alpha = 2.0 / (period + 1.0)
    return alpha * value + (1.0 - alpha) * previous


def _true_range(bar: DailyBar, previous_close: float) -> float:
    return max(
        float(bar.high) - float(bar.low),
        abs(float(bar.high) - previous_close),
        abs(float(bar.low) - previous_close),
    )


def _rsi_from_averages(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        if average_gain == 0:
            return 50.0
        return 100.0

    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _required_period(name: str) -> int:
    period = indicator_period(name)
    if period is None:
        raise ValueError(f"indicator period is missing for {name}")
    return period


def _ordered_single_symbol_bars(bars: Sequence[DailyBar]) -> tuple[DailyBar, ...]:
    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    if not ordered_bars:
        return ()

    symbol = ordered_bars[0].symbol
    if any(bar.symbol != symbol for bar in ordered_bars):
        raise ValueError("indicator state requires one symbol")
    return ordered_bars
