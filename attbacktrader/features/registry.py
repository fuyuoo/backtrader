"""Indicator registry helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


DEFAULT_INDICATOR_NAMES = ("kdj",)
SUPPORTED_INDICATOR_NAMES = frozenset(
    {"kdj", "macd", "ma20", "ma25", "ma60", "rsi14", "atr14", "cci14", "boll_up20_2"}
)
SUPPORTED_INDICATOR_TIMEFRAMES = frozenset({"D", "W", "M"})
SUPPORTED_MA_PERIODS = frozenset({20, 25, 60})
SUPPORTED_RSI_PERIODS = frozenset({14})
SUPPORTED_ATR_PERIODS = frozenset({14})
SUPPORTED_CCI_PERIODS = frozenset({14})
SUPPORTED_BOLL_UP_SPECS = frozenset({(20, 2.0)})


@dataclass(frozen=True, order=True)
class IndicatorRequirement:
    name: str
    timeframe: str = "D"

    def __post_init__(self) -> None:
        if self.name not in SUPPORTED_INDICATOR_NAMES:
            raise ValueError(f"unsupported indicator: {self.name}")
        if self.timeframe not in SUPPORTED_INDICATOR_TIMEFRAMES:
            raise ValueError(f"unsupported indicator timeframe: {self.timeframe}")


@dataclass(frozen=True, order=True)
class IndicatorSpec:
    name: str
    warmup_bars: int
    recompute_lookback_bars: int
    params: tuple[tuple[str, Any], ...] = ()
    version: str = "v1"
    requires_state: bool = False

    @property
    def params_mapping(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self.params))


def normalize_indicator_names(indicator_names: Iterable[str] | None = None) -> tuple[str, ...]:
    names = tuple(dict.fromkeys(indicator_names or DEFAULT_INDICATOR_NAMES))
    if not names:
        names = DEFAULT_INDICATOR_NAMES

    unsupported = sorted(set(names) - SUPPORTED_INDICATOR_NAMES)
    if unsupported:
        raise ValueError(f"unsupported indicators: {', '.join(unsupported)}")

    return tuple(sorted(names))


def normalize_indicator_requirements(
    indicator_requirements: Iterable[IndicatorRequirement | tuple[str, str] | str] | None = None,
) -> tuple[IndicatorRequirement, ...]:
    raw_requirements = tuple(indicator_requirements or (IndicatorRequirement(name) for name in DEFAULT_INDICATOR_NAMES))
    requirements: list[IndicatorRequirement] = []

    for requirement in raw_requirements:
        if isinstance(requirement, IndicatorRequirement):
            normalized = requirement
        elif isinstance(requirement, str):
            normalized = IndicatorRequirement(requirement)
        else:
            name, timeframe = requirement
            normalized = IndicatorRequirement(name=name, timeframe=timeframe)
        requirements.append(normalized)

    if not requirements:
        requirements = [IndicatorRequirement(name) for name in DEFAULT_INDICATOR_NAMES]

    return tuple(sorted(dict.fromkeys(requirements)))


def indicator_set_name(indicator_names: Iterable[str] | None = None) -> str:
    return "_".join(normalize_indicator_names(indicator_names))


def indicator_names_for_timeframe(
    indicator_requirements: Iterable[IndicatorRequirement],
    *,
    timeframe: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                requirement.name
                for requirement in indicator_requirements
                if requirement.timeframe == timeframe
            }
        )
    )


def indicator_spec(name: str) -> IndicatorSpec:
    if name == "kdj":
        return IndicatorSpec(
            name=name,
            params=(("period", 9), ("initial_k", 50.0), ("initial_d", 50.0)),
            warmup_bars=9,
            recompute_lookback_bars=8,
            requires_state=True,
        )
    if name == "macd":
        return IndicatorSpec(
            name=name,
            params=(("fast_period", 12), ("slow_period", 26), ("signal_period", 9)),
            warmup_bars=34,
            recompute_lookback_bars=33,
            requires_state=True,
        )
    if name.startswith("ma"):
        period = _period_from_name(name, prefix="ma")
        ma_indicator_name(period)
        return IndicatorSpec(
            name=name,
            params=(("period", period),),
            warmup_bars=period,
            recompute_lookback_bars=period - 1,
            requires_state=False,
        )
    if name.startswith("rsi"):
        period = _period_from_name(name, prefix="rsi")
        rsi_indicator_name(period)
        return IndicatorSpec(
            name=name,
            params=(("period", period),),
            warmup_bars=period + 1,
            recompute_lookback_bars=period,
            requires_state=True,
        )
    if name.startswith("atr"):
        period = _period_from_name(name, prefix="atr")
        atr_indicator_name(period)
        return IndicatorSpec(
            name=name,
            params=(("period", period),),
            warmup_bars=period,
            recompute_lookback_bars=period - 1,
            requires_state=True,
        )
    if name.startswith("cci"):
        period = _period_from_name(name, prefix="cci")
        cci_indicator_name(period)
        return IndicatorSpec(
            name=name,
            params=(("period", period), ("constant", 0.015)),
            warmup_bars=period,
            recompute_lookback_bars=period - 1,
            requires_state=False,
        )
    if name.startswith("boll_up"):
        period, devfactor = boll_up_indicator_params(name)
        return IndicatorSpec(
            name=name,
            params=(("period", period), ("devfactor", devfactor), ("line", "upper")),
            warmup_bars=period,
            recompute_lookback_bars=period - 1,
            requires_state=False,
        )
    raise ValueError(f"unsupported indicator: {name}")


def ma_indicator_name(period: int) -> str:
    if period not in SUPPORTED_MA_PERIODS:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_MA_PERIODS))
        raise ValueError(f"unsupported MA period: {period}; supported periods: {supported}")
    return f"ma{period}"


def rsi_indicator_name(period: int) -> str:
    if period not in SUPPORTED_RSI_PERIODS:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_RSI_PERIODS))
        raise ValueError(f"unsupported RSI period: {period}; supported periods: {supported}")
    return f"rsi{period}"


def atr_indicator_name(period: int) -> str:
    if period not in SUPPORTED_ATR_PERIODS:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_ATR_PERIODS))
        raise ValueError(f"unsupported ATR period: {period}; supported periods: {supported}")
    return f"atr{period}"


def cci_indicator_name(period: int) -> str:
    if period not in SUPPORTED_CCI_PERIODS:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_CCI_PERIODS))
        raise ValueError(f"unsupported CCI period: {period}; supported periods: {supported}")
    return f"cci{period}"


def boll_up_indicator_name(period: int, devfactor: float) -> str:
    spec = (period, float(devfactor))
    if spec not in SUPPORTED_BOLL_UP_SPECS:
        supported = ", ".join(f"{item[0]}:{item[1]:g}" for item in sorted(SUPPORTED_BOLL_UP_SPECS))
        raise ValueError(f"unsupported Bollinger upper spec: {period}:{devfactor:g}; supported specs: {supported}")
    return f"boll_up{period}_{devfactor:g}"


def boll_up_indicator_params(name: str) -> tuple[int, float]:
    suffix = name.removeprefix("boll_up")
    period_text, separator, devfactor_text = suffix.partition("_")
    if not name.startswith("boll_up") or not separator or not period_text.isdigit():
        raise ValueError(f"Bollinger upper parameters are missing for {name}")
    period = int(period_text)
    try:
        devfactor = float(devfactor_text)
    except ValueError as exc:
        raise ValueError(f"Bollinger upper devfactor is invalid for {name}") from exc
    boll_up_indicator_name(period, devfactor)
    return period, devfactor


def indicator_period(name: str) -> int | None:
    if name.startswith("boll_up"):
        return boll_up_indicator_params(name)[0]
    for prefix in ("ma", "rsi", "atr", "cci"):
        suffix = name.removeprefix(prefix)
        if name.startswith(prefix) and suffix.isdigit():
            return int(suffix)
    return None


def _period_from_name(name: str, *, prefix: str) -> int:
    suffix = name.removeprefix(prefix)
    if not name.startswith(prefix) or not suffix.isdigit():
        raise ValueError(f"indicator period is missing for {name}")
    return int(suffix)
