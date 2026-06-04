"""Component bindings for code-backed strategy templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from attbacktrader.sizing import EqualWeightSizing
from attbacktrader.strategies.methods import (
    AtrMultipleStop,
    FixedPercentStop,
    KdjOversoldAddOn,
    KdjOverheatedExit,
    KdjOversoldEntry,
    MacdBearishCrossoverExit,
    MacdBullishCrossoverEntry,
    MovingAverageBullishTrendEntry,
    MovingAverageMacdBullishConfirmationEntry,
    MovingAverageMacdWeakeningExit,
    NoAddOn,
    RsiOverboughtExit,
    required_indicator_requirements,
)
from attbacktrader.strategies.templates import TrendTemplateV1


@dataclass(frozen=True)
class BoundStrategyMethods:
    entry_method: Any
    profit_taking_method: Any
    stop_loss_method: Any
    add_on_method: Any
    sizing_rule: str
    sizing_method: Any


_ENTRY_METHODS = {
    "kdj_oversold_entry": KdjOversoldEntry,
    "macd_bullish_crossover_entry": MacdBullishCrossoverEntry,
    "macd_weekly_bullish_crossover_entry": lambda **params: MacdBullishCrossoverEntry(
        method_name="macd_weekly_bullish_crossover_entry",
        timeframe="W",
        **params,
    ),
    "macd_monthly_bullish_crossover_entry": lambda **params: MacdBullishCrossoverEntry(
        method_name="macd_monthly_bullish_crossover_entry",
        timeframe="M",
        **params,
    ),
    "ma_bullish_trend_entry": MovingAverageBullishTrendEntry,
    "ma_macd_bullish_confirmation_entry": MovingAverageMacdBullishConfirmationEntry,
}
_PROFIT_TAKING_METHODS = {
    "kdj_overheated_exit": KdjOverheatedExit,
    "macd_bearish_crossover_exit": MacdBearishCrossoverExit,
    "macd_weekly_bearish_crossover_exit": lambda **params: MacdBearishCrossoverExit(
        method_name="macd_weekly_bearish_crossover_exit",
        timeframe="W",
        **params,
    ),
    "macd_monthly_bearish_crossover_exit": lambda **params: MacdBearishCrossoverExit(
        method_name="macd_monthly_bearish_crossover_exit",
        timeframe="M",
        **params,
    ),
    "rsi_overbought_exit": RsiOverboughtExit,
    "ma_macd_weakening_exit": MovingAverageMacdWeakeningExit,
}
_STOP_LOSS_METHODS = {
    "fixed_percent_stop": lambda **params: FixedPercentStop(**({"loss_percent": 0.05} | params)),
    "atr_multiple_stop": AtrMultipleStop,
}
_ADD_ON_METHODS = {
    "none": NoAddOn,
    "kdj_oversold_add_on": KdjOversoldAddOn,
}
_SIZING_RULES = {
    "equal_weight": EqualWeightSizing,
}

_STRATEGY_COMPONENT_BINDINGS: dict[str, dict[str, set[str]]] = {
    "trend_template_v1": {
        "entry_method": set(_ENTRY_METHODS),
        "profit_taking_method": set(_PROFIT_TAKING_METHODS),
        "stop_loss_method": set(_STOP_LOSS_METHODS),
        "add_on_method": set(_ADD_ON_METHODS),
        "sizing_rule": set(_SIZING_RULES),
    }
}


def strategy_component_binding_fields(template: str) -> tuple[str, ...]:
    try:
        return tuple(_STRATEGY_COMPONENT_BINDINGS[template])
    except KeyError as exc:
        raise ValueError(f"unsupported strategy template: {template!r}") from exc


def allowed_strategy_component_values(template: str, field_name: str) -> frozenset[str]:
    try:
        values = _STRATEGY_COMPONENT_BINDINGS[template][field_name]
    except KeyError as exc:
        raise ValueError(f"unsupported component binding {field_name!r} for template {template!r}") from exc

    return frozenset(values)


def bind_strategy_methods(strategy_config: Any) -> BoundStrategyMethods:
    if strategy_config.template == "trend_template_v1":
        _validate_selected_components(strategy_config)
        return BoundStrategyMethods(
            entry_method=_build_component(
                _ENTRY_METHODS,
                strategy_config.entry_method,
                _component_params(strategy_config, "entry_method"),
            ),
            profit_taking_method=_build_component(
                _PROFIT_TAKING_METHODS,
                strategy_config.profit_taking_method,
                _component_params(strategy_config, "profit_taking_method"),
            ),
            stop_loss_method=_build_component(
                _STOP_LOSS_METHODS,
                strategy_config.stop_loss_method,
                _component_params(strategy_config, "stop_loss_method"),
            ),
            add_on_method=_build_component(
                _ADD_ON_METHODS,
                strategy_config.add_on_method,
                _component_params(strategy_config, "add_on_method"),
            ),
            sizing_rule=strategy_config.sizing_rule,
            sizing_method=_build_component(
                _SIZING_RULES,
                strategy_config.sizing_rule,
                _component_params(strategy_config, "sizing_rule"),
            ),
        )

    raise ValueError(f"unsupported strategy template: {strategy_config.template!r}")


def build_strategy_template(strategy_config: Any) -> TrendTemplateV1:
    methods = bind_strategy_methods(strategy_config)
    if strategy_config.template == "trend_template_v1":
        return TrendTemplateV1(
            entry_method=methods.entry_method,
            profit_taking_method=methods.profit_taking_method,
            stop_loss_method=methods.stop_loss_method,
            add_on_method=methods.add_on_method,
            sizing_method=methods.sizing_method,
        )

    raise ValueError(f"unsupported strategy template: {strategy_config.template!r}")


def required_indicators_for_strategy_config(strategy_config: Any):
    methods = bind_strategy_methods(strategy_config)
    return required_indicator_requirements(
        methods.entry_method,
        methods.profit_taking_method,
        methods.stop_loss_method,
        methods.add_on_method,
        methods.sizing_method,
    )


def validate_strategy_component_params(
    template: str,
    field_name: str,
    component_name: str,
    params: dict[str, Any] | None,
) -> None:
    if not params:
        return

    if "method_name" in params:
        raise ValueError(f"strategy.{_params_field_name(field_name)} cannot override method_name")

    if template != "trend_template_v1":
        raise ValueError(f"unsupported strategy template: {template!r}")
    if field_name == "entry_method":
        registry = _ENTRY_METHODS
    elif field_name == "profit_taking_method":
        registry = _PROFIT_TAKING_METHODS
    elif field_name == "stop_loss_method":
        registry = _STOP_LOSS_METHODS
    elif field_name == "add_on_method":
        registry = _ADD_ON_METHODS
    elif field_name == "sizing_rule":
        registry = _SIZING_RULES
    else:
        raise ValueError(f"unsupported component binding {field_name!r} for template {template!r}")

    _build_component(registry, component_name, params)


def _validate_selected_components(strategy_config: Any) -> None:
    for field_name in strategy_component_binding_fields(strategy_config.template):
        selected = getattr(strategy_config, field_name)
        allowed_values = allowed_strategy_component_values(strategy_config.template, field_name)
        if selected not in allowed_values:
            allowed = ", ".join(sorted(allowed_values))
            raise ValueError(
                f"strategy.{field_name}={selected!r} is not bound to "
                f"template {strategy_config.template!r}; allowed values: {allowed}"
            )
        validate_strategy_component_params(
            strategy_config.template,
            field_name,
            selected,
            _component_params(strategy_config, field_name),
        )


def _build_component(registry: dict[str, Any], component_name: str, params: dict[str, Any] | None):
    constructor = registry[component_name]
    clean_params = dict(params or {})
    if "method_name" in clean_params:
        raise ValueError("method_name cannot be configured")
    try:
        return constructor(**clean_params)
    except TypeError as exc:
        raise ValueError(f"invalid parameters for {component_name}: {clean_params}") from exc


def _component_params(strategy_config: Any, field_name: str) -> dict[str, Any]:
    return dict(getattr(strategy_config, _params_field_name(field_name), {}) or {})


def _params_field_name(field_name: str) -> str:
    return {
        "entry_method": "entry_params",
        "profit_taking_method": "profit_taking_params",
        "stop_loss_method": "stop_loss_params",
        "add_on_method": "add_on_params",
        "sizing_rule": "sizing_params",
    }.get(field_name, f"{field_name}_params")
