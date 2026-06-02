"""Component bindings for code-backed strategy templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from attbacktrader.strategies.methods import FixedPercentStop, KdjOverheatedExit, KdjOversoldEntry
from attbacktrader.strategies.templates import TrendTemplateV1


@dataclass(frozen=True)
class BoundStrategyMethods:
    entry_method: KdjOversoldEntry
    profit_taking_method: KdjOverheatedExit
    stop_loss_method: FixedPercentStop
    sizing_rule: str


_STRATEGY_COMPONENT_BINDINGS: dict[str, dict[str, set[str]]] = {
    "trend_template_v1": {
        "entry_method": {"kdj_oversold_entry"},
        "profit_taking_method": {"kdj_overheated_exit"},
        "stop_loss_method": {"fixed_percent_stop"},
        "sizing_rule": {"equal_weight"},
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
            entry_method=KdjOversoldEntry(),
            profit_taking_method=KdjOverheatedExit(),
            stop_loss_method=FixedPercentStop(loss_percent=0.05),
            sizing_rule=strategy_config.sizing_rule,
        )

    raise ValueError(f"unsupported strategy template: {strategy_config.template!r}")


def build_strategy_template(strategy_config: Any) -> TrendTemplateV1:
    methods = bind_strategy_methods(strategy_config)
    if strategy_config.template == "trend_template_v1":
        return TrendTemplateV1(
            entry_method=methods.entry_method,
            profit_taking_method=methods.profit_taking_method,
            stop_loss_method=methods.stop_loss_method,
        )

    raise ValueError(f"unsupported strategy template: {strategy_config.template!r}")


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
