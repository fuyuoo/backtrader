from datetime import date

from attbacktrader.features import KDJValue
from attbacktrader.strategies import (
    STRATEGY_OUTPUT_CONTRACT_SCHEMA,
    TradeIntent,
    TradeIntentType,
    build_strategy_output_contract,
    trade_intent_satisfies_output_contract,
    validate_trade_intent_output_contract,
)
from attbacktrader.strategies.methods import KdjOversoldEntry


def test_strategy_output_contract_defines_framework_boundary() -> None:
    contract = build_strategy_output_contract()

    assert contract["schema"] == STRATEGY_OUTPUT_CONTRACT_SCHEMA
    assert contract["baseline_role"]["current_strategy_role"] == "framework_regression_fixture"
    assert contract["trade_intent"]["required_fields"] == [
        "intent_type",
        "symbol",
        "trade_date",
        "method_name",
        "reason_code",
        "signal_values",
    ]
    assert set(contract["trade_intent"]["allowed_intent_types"]) == {
        "enter",
        "add_on",
        "exit_profit",
        "exit_loss",
        "hold",
        "avoid",
    }
    assert "trade_lifecycle.json" in contract["downstream_artifacts"]
    assert "environment_fit.json" in contract["downstream_artifacts"]
    assert any("attribution factors" in rule for rule in contract["non_goals"])


def test_current_kdj_test_strategy_emits_contract_compliant_intents() -> None:
    intent = KdjOversoldEntry().evaluate(
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        kdj=KDJValue(k=12.0, d=12.5, j=12.99),
    )

    assert trade_intent_satisfies_output_contract(intent)


def test_strategy_output_contract_validates_signal_value_shapes() -> None:
    intent = TradeIntent(
        TradeIntentType.ENTER,
        "000001.SZ",
        date(2024, 1, 2),
        "future_entry",
        "FUTURE_ENTRY",
        signal_values={
            "checks": {"not_bool": "yes"},
            "attribution": {
                "checks": {"valid": True},
                "categories": {"market.state": "range"},
            },
        },
    )

    issues = validate_trade_intent_output_contract(intent)

    assert [(issue.field, issue.code) for issue in issues] == [
        ("signal_values.checks.not_bool", "check_not_bool")
    ]
