"""Strategy output contract shared by strategy methods and downstream reports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .intents import TradeIntent, TradeIntentType


STRATEGY_OUTPUT_CONTRACT_SCHEMA = "attbacktrader.strategy_output_contract.v1"

_REQUIRED_TRADE_INTENT_FIELDS = (
    "intent_type",
    "symbol",
    "trade_date",
    "method_name",
    "reason_code",
    "signal_values",
)

_DOWNSTREAM_ARTIFACTS = (
    "signal_audit.json",
    "sizing_audit.json",
    "execution_audit.json",
    "trade_lifecycle.json",
    "trade_review.json",
    "environment_fit.json",
    "strategy_adaptation_matrix.json",
    "review_packet.<focus>.json",
)


@dataclass(frozen=True)
class StrategyOutputContractIssue:
    field: str
    code: str
    message: str


def build_strategy_output_contract() -> dict[str, Any]:
    """Return the stable strategy output contract consumed by the workbench."""

    return {
        "schema": STRATEGY_OUTPUT_CONTRACT_SCHEMA,
        "purpose": "Keep strategy implementations decoupled from reports, attribution, and AI review.",
        "trade_intent": {
            "required_fields": list(_REQUIRED_TRADE_INTENT_FIELDS),
            "allowed_intent_types": [intent_type.value for intent_type in TradeIntentType],
            "field_rules": {
                "intent_type": "One of enter, add_on, exit_profit, exit_loss, hold, avoid.",
                "symbol": "Non-empty tradable symbol.",
                "trade_date": "Decision date used to join signal, execution, and lifecycle evidence.",
                "method_name": "Stable strategy method identifier, never overridden by user params.",
                "reason_code": "Stable machine-readable reason for triggered or non-triggered decisions.",
                "signal_values": "JSON-safe evidence payload; reports must consume it without recalculation.",
                "target_price": "Optional target price for the order request.",
                "risk_price": "Optional risk or stop price evidence.",
                "confidence": "Optional strategy confidence score.",
                "blocked_by": "Optional upstream block reason when the intent is deliberately suppressed.",
            },
        },
        "signal_values": {
            "top_level_scalars": "Strategy-specific scalar evidence such as kdj_j or ma20.",
            "checks": "Optional mapping of decision check keys to bool values.",
            "attribution": {
                "checks": "Optional mapping of fully-qualified attribution check keys to bool values.",
                "values": "Optional mapping of fully-qualified numeric/string evidence keys to scalar values.",
                "categories": "Optional mapping of fully-qualified grouping keys to category labels.",
            },
            "sizing": "Downstream sizing context may append requested quantity, risk group, and block reason.",
        },
        "trade_lifecycle": {
            "entry": "Matched from successful enter intent by symbol and entry_date.",
            "add_on": "Matched from successful add_on intents inside the holding window.",
            "exit": "Matched from successful exit_profit or exit_loss intent by symbol, exit_date, and exit_reason.",
            "rule": "Lifecycle may index existing evidence, but must not infer missing strategy decisions.",
        },
        "baseline_role": {
            "current_strategy_role": "framework_regression_fixture",
            "rule": "The current KDJ/MA strategy validates the workbench dataflow; it is not a strategy approval.",
        },
        "downstream_artifacts": list(_DOWNSTREAM_ARTIFACTS),
        "non_goals": [
            "Do not encode market-type decisions inside indicator calculation.",
            "Do not treat attribution factors as trading rules.",
            "Do not default-fill missing warmup values or missing evidence.",
            "Do not require reports to know which concrete strategy implementation emitted the intent.",
        ],
    }


def validate_trade_intent_output_contract(intent: TradeIntent) -> tuple[StrategyOutputContractIssue, ...]:
    """Validate the framework-level fields every strategy intent must expose."""

    issues: list[StrategyOutputContractIssue] = []
    if not isinstance(intent.intent_type, TradeIntentType):
        issues.append(
            StrategyOutputContractIssue(
                field="intent_type",
                code="invalid_intent_type",
                message="intent_type must be a TradeIntentType",
            )
        )
    if not intent.symbol:
        issues.append(
            StrategyOutputContractIssue(field="symbol", code="empty_symbol", message="symbol must be non-empty")
        )
    if not intent.method_name:
        issues.append(
            StrategyOutputContractIssue(
                field="method_name",
                code="empty_method_name",
                message="method_name must be non-empty",
            )
        )
    if not intent.reason_code:
        issues.append(
            StrategyOutputContractIssue(
                field="reason_code",
                code="empty_reason_code",
                message="reason_code must be non-empty",
            )
        )
    issues.extend(_signal_values_issues(intent.signal_values))
    if intent.blocked_by is not None and not intent.blocked_by:
        issues.append(
            StrategyOutputContractIssue(
                field="blocked_by",
                code="empty_blocked_by",
                message="blocked_by must be non-empty when present",
            )
        )
    return tuple(issues)


def trade_intent_satisfies_output_contract(intent: TradeIntent) -> bool:
    return not validate_trade_intent_output_contract(intent)


def _signal_values_issues(signal_values: Mapping[str, Any]) -> tuple[StrategyOutputContractIssue, ...]:
    issues: list[StrategyOutputContractIssue] = []
    for key, value in signal_values.items():
        field = f"signal_values.{key}"
        if key == "checks":
            issues.extend(_bool_mapping_issues(field, value))
            continue
        if key == "attribution":
            issues.extend(_attribution_issues(field, value))
            continue
        if key == "sizing":
            issues.extend(_mapping_scalar_issues(field, value))
            continue
        if not _is_scalar_json_value(value):
            issues.append(
                StrategyOutputContractIssue(
                    field=field,
                    code="non_scalar_signal_value",
                    message="top-level signal_values entries must be JSON-safe scalars unless reserved",
                )
            )
    return tuple(issues)


def _attribution_issues(field: str, value: object) -> tuple[StrategyOutputContractIssue, ...]:
    if not isinstance(value, Mapping):
        return (
            StrategyOutputContractIssue(
                field=field,
                code="attribution_not_mapping",
                message="attribution must be a mapping",
            ),
        )
    issues: list[StrategyOutputContractIssue] = []
    if "checks" in value:
        issues.extend(_bool_mapping_issues(f"{field}.checks", value["checks"]))
    if "values" in value:
        issues.extend(_mapping_scalar_issues(f"{field}.values", value["values"]))
    if "categories" in value:
        issues.extend(_category_mapping_issues(f"{field}.categories", value["categories"]))
    return tuple(issues)


def _bool_mapping_issues(field: str, value: object) -> tuple[StrategyOutputContractIssue, ...]:
    if not isinstance(value, Mapping):
        return (
            StrategyOutputContractIssue(field=field, code="checks_not_mapping", message="checks must be a mapping"),
        )
    return tuple(
        StrategyOutputContractIssue(
            field=f"{field}.{key}",
            code="check_not_bool",
            message="check values must be bool",
        )
        for key, item in value.items()
        if not isinstance(key, str) or not isinstance(item, bool)
    )


def _mapping_scalar_issues(field: str, value: object) -> tuple[StrategyOutputContractIssue, ...]:
    if not isinstance(value, Mapping):
        return (
            StrategyOutputContractIssue(field=field, code="values_not_mapping", message="values must be a mapping"),
        )
    return tuple(
        StrategyOutputContractIssue(
            field=f"{field}.{key}",
            code="value_not_scalar",
            message="values must be JSON-safe scalars",
        )
        for key, item in value.items()
        if not isinstance(key, str) or not _is_scalar_json_value(item)
    )


def _category_mapping_issues(field: str, value: object) -> tuple[StrategyOutputContractIssue, ...]:
    if not isinstance(value, Mapping):
        return (
            StrategyOutputContractIssue(
                field=field,
                code="categories_not_mapping",
                message="categories must be a mapping",
            ),
        )
    return tuple(
        StrategyOutputContractIssue(
            field=f"{field}.{key}",
            code="category_not_scalar",
            message="category values must be string, number, or bool labels",
        )
        for key, item in value.items()
        if not isinstance(key, str) or not isinstance(item, (str, int, float, bool))
    )


def _is_scalar_json_value(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))
