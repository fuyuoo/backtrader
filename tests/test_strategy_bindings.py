from __future__ import annotations

import pytest

from attbacktrader.config.models import StrategyConfig
from attbacktrader.features import IndicatorRequirement
from attbacktrader.strategies.bindings import (
    allowed_strategy_component_values,
    bind_strategy_methods,
    build_strategy_template,
    required_indicators_for_strategy_config,
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
        "add_on_method",
        "sizing_rule",
    )
    assert allowed_strategy_component_values("trend_template_v1", "entry_method") == frozenset(
        {
            "baoma_entry",
            "kdj_oversold_entry",
            "macd_bullish_crossover_entry",
            "macd_weekly_bullish_crossover_entry",
            "macd_monthly_bullish_crossover_entry",
            "ma_bullish_trend_entry",
            "ma_macd_bullish_confirmation_entry",
        }
    )
    assert allowed_strategy_component_values("trend_template_v1", "profit_taking_method") == frozenset(
        {
            "baoma_ma25_profit_exit",
            "kdj_overheated_exit",
            "macd_bearish_crossover_exit",
            "macd_weekly_bearish_crossover_exit",
            "macd_monthly_bearish_crossover_exit",
            "rsi_overbought_exit",
            "ma_macd_weakening_exit",
        }
    )
    assert allowed_strategy_component_values("trend_template_v1", "add_on_method") == frozenset(
        {
            "baoma_add_on",
            "none",
            "kdj_oversold_add_on",
        }
    )
    assert methods.entry_method.method_name == "kdj_oversold_entry"
    assert methods.profit_taking_method.method_name == "kdj_overheated_exit"
    assert methods.stop_loss_method.method_name == "fixed_percent_stop"
    assert methods.add_on_method.method_name == "none"
    assert methods.sizing_rule == "equal_weight"
    assert methods.sizing_method.method_name == "equal_weight"
    assert template.entry_method == methods.entry_method
    assert template.profit_taking_method == methods.profit_taking_method
    assert template.stop_loss_method == methods.stop_loss_method
    assert template.add_on_method == methods.add_on_method
    assert template.sizing_method == methods.sizing_method


def test_strategy_binding_rejects_unknown_component_field() -> None:
    with pytest.raises(ValueError, match="unsupported component binding"):
        allowed_strategy_component_values("trend_template_v1", "unknown_method")


def test_strategy_binding_reports_required_indicators_for_selected_methods() -> None:
    assert required_indicators_for_strategy_config(_strategy_config()) == frozenset({IndicatorRequirement("kdj", "D")})
    assert required_indicators_for_strategy_config(
        StrategyConfig(
            template="trend_template_v1",
            entry_method="macd_bullish_crossover_entry",
            profit_taking_method="macd_bearish_crossover_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
        )
    ) == frozenset({IndicatorRequirement("macd", "D")})
    assert required_indicators_for_strategy_config(
        StrategyConfig(
            template="trend_template_v1",
            entry_method="macd_weekly_bullish_crossover_entry",
            profit_taking_method="macd_weekly_bearish_crossover_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
        )
    ) == frozenset({IndicatorRequirement("macd", "W")})
    assert required_indicators_for_strategy_config(
        StrategyConfig(
            template="trend_template_v1",
            entry_method="ma_macd_bullish_confirmation_entry",
            profit_taking_method="ma_macd_weakening_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
        )
    ) == frozenset(
        {
            IndicatorRequirement("macd", "D"),
            IndicatorRequirement("ma20", "D"),
            IndicatorRequirement("ma60", "D"),
        }
    )
    assert required_indicators_for_strategy_config(
        StrategyConfig(
            template="trend_template_v1",
            entry_method="kdj_oversold_entry",
            profit_taking_method="kdj_overheated_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
            sizing_params={"atr_risk_percent": 0.01},
        )
    ) == frozenset({IndicatorRequirement("kdj", "D"), IndicatorRequirement("atr14", "D")})
    assert required_indicators_for_strategy_config(
        StrategyConfig(
            template="trend_template_v1",
            entry_method="macd_bullish_crossover_entry",
            profit_taking_method="macd_bearish_crossover_exit",
            stop_loss_method="fixed_percent_stop",
            add_on_method="kdj_oversold_add_on",
            sizing_rule="equal_weight",
        )
    ) == frozenset({IndicatorRequirement("macd", "D"), IndicatorRequirement("kdj", "D")})
    assert required_indicators_for_strategy_config(
        StrategyConfig(
            template="trend_template_v1",
            entry_method="baoma_entry",
            profit_taking_method="baoma_ma25_profit_exit",
            stop_loss_method="baoma_ma60_stop",
            add_on_method="baoma_add_on",
            sizing_rule="equal_weight",
        )
    ) == frozenset(
        {
            IndicatorRequirement("macd", "D"),
            IndicatorRequirement("ma25", "D"),
            IndicatorRequirement("ma60", "D"),
        }
    )


def test_strategy_binding_accepts_parameterized_methods() -> None:
    config = StrategyConfig(
        template="trend_template_v1",
        entry_method="macd_bullish_crossover_entry",
        entry_params={"timeframe": "W"},
        profit_taking_method="rsi_overbought_exit",
        profit_taking_params={"threshold": 65.0},
        stop_loss_method="atr_multiple_stop",
        stop_loss_params={"multiple": 1.5},
        add_on_method="kdj_oversold_add_on",
        add_on_params={"min_profit_percent": 0.02, "max_add_on_count": 2},
        sizing_rule="equal_weight",
        sizing_params={"max_holding_count": 3, "atr_risk_percent": 0.01, "min_order_quantity": 100},
    )

    methods = bind_strategy_methods(config)

    assert methods.entry_method.timeframe == "W"
    assert methods.profit_taking_method.threshold == 65.0
    assert methods.stop_loss_method.multiple == 1.5
    assert methods.add_on_method.min_profit_percent == 0.02
    assert methods.add_on_method.max_add_on_count == 2
    assert methods.sizing_method.max_holding_count == 3
    assert methods.sizing_method.atr_risk_percent == 0.01
    assert methods.sizing_method.min_order_quantity == 100
    assert required_indicators_for_strategy_config(config) == frozenset(
        {
            IndicatorRequirement("macd", "W"),
            IndicatorRequirement("rsi14", "D"),
            IndicatorRequirement("atr14", "D"),
            IndicatorRequirement("kdj", "D"),
        }
    )


def test_strategy_binding_rejects_method_name_parameter_override() -> None:
    with pytest.raises(ValueError, match="method_name"):
        StrategyConfig(
            template="trend_template_v1",
            entry_method="macd_bullish_crossover_entry",
            entry_params={"method_name": "renamed"},
            profit_taking_method="macd_bearish_crossover_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
        )


def test_strategy_binding_rejects_invalid_timeframe_parameter() -> None:
    with pytest.raises(ValueError, match="unsupported indicator timeframe"):
        StrategyConfig(
            template="trend_template_v1",
            entry_method="macd_bullish_crossover_entry",
            entry_params={"timeframe": "Q"},
            profit_taking_method="macd_bearish_crossover_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
        )


def test_strategy_binding_rejects_invalid_sizing_parameter() -> None:
    with pytest.raises(ValueError, match="max_holding_count"):
        StrategyConfig(
            template="trend_template_v1",
            entry_method="kdj_oversold_entry",
            profit_taking_method="kdj_overheated_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
            sizing_params={"max_holding_count": 0},
        )


def test_strategy_binding_rejects_invalid_risk_group_level() -> None:
    with pytest.raises(ValueError, match="risk_group_level"):
        StrategyConfig(
            template="trend_template_v1",
            entry_method="kdj_oversold_entry",
            profit_taking_method="kdj_overheated_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
            sizing_params={"risk_group_level": 4},
        )


def test_strategy_binding_rejects_invalid_min_order_quantity() -> None:
    with pytest.raises(ValueError, match="min_order_quantity"):
        StrategyConfig(
            template="trend_template_v1",
            entry_method="kdj_oversold_entry",
            profit_taking_method="kdj_overheated_exit",
            stop_loss_method="fixed_percent_stop",
            sizing_rule="equal_weight",
            sizing_params={"min_order_quantity": 0},
        )


def _strategy_config() -> StrategyConfig:
    return StrategyConfig(
        template="trend_template_v1",
        entry_method="kdj_oversold_entry",
        profit_taking_method="kdj_overheated_exit",
        stop_loss_method="fixed_percent_stop",
        sizing_rule="equal_weight",
    )
