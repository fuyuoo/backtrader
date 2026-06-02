from __future__ import annotations

import pytest

from attbacktrader.config.models import StrategyConfig
from attbacktrader.strategies.bindings import (
    allowed_strategy_component_values,
    bind_strategy_methods,
    build_strategy_template,
    strategy_component_binding_fields,
)


def test_strategy_binding_builds_trend_template_methods() -> None:
    config = _strategy_config()

    methods = bind_strategy_methods(config)
    template = build_strategy_template(config)

    assert strategy_component_binding_fields("trend_template_v1") == (
        "entry_method",
        "profit_taking_method",
        "stop_loss_method",
        "sizing_rule",
    )
    assert allowed_strategy_component_values("trend_template_v1", "entry_method") == frozenset({"kdj_oversold_entry"})
    assert methods.entry_method.method_name == "kdj_oversold_entry"
    assert methods.profit_taking_method.method_name == "kdj_overheated_exit"
    assert methods.stop_loss_method.method_name == "fixed_percent_stop"
    assert methods.sizing_rule == "equal_weight"
    assert template.entry_method == methods.entry_method
    assert template.profit_taking_method == methods.profit_taking_method
    assert template.stop_loss_method == methods.stop_loss_method


def test_strategy_binding_rejects_unknown_component_field() -> None:
    with pytest.raises(ValueError, match="unsupported component binding"):
        allowed_strategy_component_values("trend_template_v1", "unknown_method")


def _strategy_config() -> StrategyConfig:
    return StrategyConfig(
        template="trend_template_v1",
        entry_method="kdj_oversold_entry",
        profit_taking_method="kdj_overheated_exit",
        stop_loss_method="fixed_percent_stop",
        sizing_rule="equal_weight",
    )
