"""Validate strategy method integration against the framework contract."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping

from attbacktrader.config.models import RunPlan, StrategyConfig
from attbacktrader.data import DailyBar
from attbacktrader.features import (
    IndicatorRequirement,
    KDJValue,
    MACDValue,
    build_indicator_snapshots_for_requirements,
    join_bars_with_indicators,
)
from attbacktrader.strategies.bindings import bind_strategy_methods, required_indicators_for_strategy_config
from attbacktrader.strategies.contract import validate_trade_intent_output_contract
from attbacktrader.strategies.intents import TradeIntent


STRATEGY_INTEGRATION_VALIDATION_SCHEMA = "attbacktrader.strategy_integration_validation.v1"


@dataclass(frozen=True)
class StrategyIntegrationValidationIssue:
    component_role: str
    method_name: str | None
    code: str
    message: str
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_role": self.component_role,
            "method_name": self.method_name,
            "code": self.code,
            "message": self.message,
            "field": self.field,
        }


@dataclass(frozen=True)
class StrategyComponentValidation:
    component_role: str
    selected_name: str
    method_name: str | None
    required_indicators: tuple[str, ...]
    output_contract_checked: bool
    output_contract_status: str
    sampled_intent_type: str | None = None
    sampled_reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_role": self.component_role,
            "selected_name": self.selected_name,
            "method_name": self.method_name,
            "required_indicators": list(self.required_indicators),
            "output_contract_checked": self.output_contract_checked,
            "output_contract_status": self.output_contract_status,
            "sampled_intent_type": self.sampled_intent_type,
            "sampled_reason_code": self.sampled_reason_code,
        }


@dataclass(frozen=True)
class StrategyIntegrationValidationResult:
    schema: str
    status: str
    run_id: str | None
    template: str | None
    required_indicators: tuple[str, ...]
    components: tuple[StrategyComponentValidation, ...]
    issues: tuple[StrategyIntegrationValidationIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "run_id": self.run_id,
            "template": self.template,
            "required_indicators": list(self.required_indicators),
            "components": [component.to_dict() for component in self.components],
            "issues": [issue.to_dict() for issue in self.issues],
        }


def validate_run_plan_strategy_integration(run_plan: RunPlan) -> StrategyIntegrationValidationResult:
    return validate_strategy_config_integration(run_plan.strategy, run_id=run_plan.run.id)


def validate_strategy_config_integration(
    strategy_config: StrategyConfig,
    *,
    run_id: str | None = None,
) -> StrategyIntegrationValidationResult:
    methods = bind_strategy_methods(strategy_config)
    required_indicators = tuple(sorted(_format_requirement(item) for item in required_indicators_for_strategy_config(strategy_config)))
    rows = _sample_rows_for_strategy(strategy_config)

    component_specs = (
        ("entry_method", strategy_config.entry_method, methods.entry_method, True),
        ("profit_taking_method", strategy_config.profit_taking_method, methods.profit_taking_method, True),
        ("stop_loss_method", strategy_config.stop_loss_method, methods.stop_loss_method, True),
        ("add_on_method", strategy_config.add_on_method, methods.add_on_method, True),
        ("sizing_rule", strategy_config.sizing_rule, methods.sizing_method, False),
    )

    components: list[StrategyComponentValidation] = []
    issues: list[StrategyIntegrationValidationIssue] = []
    for component_role, selected_name, method, should_check_output in component_specs:
        component, component_issues = _validate_component(
            component_role=component_role,
            selected_name=selected_name,
            method=method,
            rows=rows,
            check_output_contract=should_check_output,
        )
        components.append(component)
        issues.extend(component_issues)

    return StrategyIntegrationValidationResult(
        schema=STRATEGY_INTEGRATION_VALIDATION_SCHEMA,
        status="fail" if issues else "ok",
        run_id=run_id,
        template=strategy_config.template,
        required_indicators=required_indicators,
        components=tuple(components),
        issues=tuple(issues),
    )


def build_strategy_integration_validation_failure(
    *,
    message: str,
    code: str = "load_run_plan_failed",
    run_id: str | None = None,
    template: str | None = None,
) -> StrategyIntegrationValidationResult:
    return StrategyIntegrationValidationResult(
        schema=STRATEGY_INTEGRATION_VALIDATION_SCHEMA,
        status="fail",
        run_id=run_id,
        template=template,
        required_indicators=(),
        components=(),
        issues=(
            StrategyIntegrationValidationIssue(
                component_role="run_plan",
                method_name=None,
                code=code,
                message=message,
            ),
        ),
    )


def render_strategy_integration_validation_text_zh(result: StrategyIntegrationValidationResult) -> str:
    status_zh = "通过" if result.status == "ok" else "失败"
    lines = [
        f"策略接入校验: {status_zh}",
        f"- schema: `{result.schema}`",
        f"- run_id: `{result.run_id or '-'}`",
        f"- template: `{result.template or '-'}`",
        f"- required_indicators: {', '.join(result.required_indicators) if result.required_indicators else '无'}",
        "",
        "组件:",
    ]
    for component in result.components:
        lines.append(
            "- "
            f"{component.component_role}: `{component.selected_name}` -> "
            f"`{component.method_name or '-'}` "
            f"(输出契约: {component.output_contract_status})"
        )
        if component.sampled_reason_code:
            lines.append(f"  sample: {component.sampled_intent_type} / {component.sampled_reason_code}")

    if result.issues:
        lines.extend(["", "问题:"])
        for issue in result.issues:
            field = f" field={issue.field}" if issue.field else ""
            lines.append(
                f"- {issue.component_role} `{issue.method_name or '-'}` "
                f"{issue.code}{field}: {issue.message}"
            )
    return "\n".join(lines)


def _validate_component(
    *,
    component_role: str,
    selected_name: str,
    method: Any,
    rows: tuple[Any, ...],
    check_output_contract: bool,
) -> tuple[StrategyComponentValidation, tuple[StrategyIntegrationValidationIssue, ...]]:
    method_name = getattr(method, "method_name", None)
    requirements = tuple(sorted(_format_requirement(item) for item in getattr(method, "required_indicators", ())))
    issues: list[StrategyIntegrationValidationIssue] = []
    if not isinstance(method_name, str) or not method_name:
        issues.append(
            StrategyIntegrationValidationIssue(
                component_role=component_role,
                method_name=None,
                code="missing_method_name",
                message="strategy component must expose a non-empty method_name",
            )
        )

    sampled_intent: TradeIntent | None = None
    output_status = "not_checked"
    if check_output_contract:
        sampled_intent, output_issues = _sample_and_validate_trade_intent(component_role, method, rows)
        issues.extend(output_issues)
        output_status = "fail" if output_issues else "ok"
    else:
        output_status = "not_trade_intent"

    return (
        StrategyComponentValidation(
            component_role=component_role,
            selected_name=selected_name,
            method_name=method_name if isinstance(method_name, str) else None,
            required_indicators=requirements,
            output_contract_checked=check_output_contract,
            output_contract_status=output_status,
            sampled_intent_type=sampled_intent.intent_type.value if sampled_intent is not None else None,
            sampled_reason_code=sampled_intent.reason_code if sampled_intent is not None else None,
        ),
        tuple(issues),
    )


def _sample_and_validate_trade_intent(
    component_role: str,
    method: Any,
    rows: tuple[Any, ...],
) -> tuple[TradeIntent | None, tuple[StrategyIntegrationValidationIssue, ...]]:
    try:
        intent = method.evaluate(**_sample_evaluate_kwargs(component_role, method, rows))
    except Exception as exc:  # pragma: no cover - exercised through CLI/user-created methods
        return (
            None,
            (
                StrategyIntegrationValidationIssue(
                    component_role=component_role,
                    method_name=getattr(method, "method_name", None),
                    code="sample_evaluation_failed",
                    message=str(exc),
                ),
            ),
        )

    if not isinstance(intent, TradeIntent):
        return (
            None,
            (
                StrategyIntegrationValidationIssue(
                    component_role=component_role,
                    method_name=getattr(method, "method_name", None),
                    code="evaluate_did_not_return_trade_intent",
                    message="evaluate() must return TradeIntent",
                ),
            ),
        )

    issues = tuple(
        StrategyIntegrationValidationIssue(
            component_role=component_role,
            method_name=intent.method_name,
            code=issue.code,
            field=issue.field,
            message=issue.message,
        )
        for issue in validate_trade_intent_output_contract(intent)
    )
    return intent, issues


def _sample_evaluate_kwargs(component_role: str, method: Any, rows: tuple[Any, ...]) -> dict[str, Any]:
    trade_date = rows[-1].trade_date if rows else date(2024, 1, 2)
    base_kwargs: dict[str, Any] = {
        "symbol": "000001.SZ",
        "trade_date": trade_date,
        "row": rows[-1] if rows else None,
        "previous_row": rows[-2] if len(rows) >= 2 else None,
        "kdj": KDJValue(k=12.0, d=12.5, j=12.99),
        "macd": MACDValue(line=0.1, signal=0.0, histogram=0.1),
        "previous_macd": MACDValue(line=-0.1, signal=0.0, histogram=-0.1),
        "entry_price": 20.0,
        "current_price": 19.0,
        "current_quantity": 100,
        "add_on_count": 0,
    }
    if component_role == "profit_taking_method":
        base_kwargs["current_price"] = 25.0
    if component_role == "add_on_method":
        base_kwargs["current_price"] = 21.0

    parameters = inspect.signature(method.evaluate).parameters
    return {key: value for key, value in base_kwargs.items() if key in parameters}


def _sample_rows_for_strategy(strategy_config: StrategyConfig) -> tuple[Any, ...]:
    requirements = tuple(required_indicators_for_strategy_config(strategy_config))
    if not requirements:
        return ()

    bars = _trend_fixture_bars("000001.SZ", count=2200)
    snapshots = build_indicator_snapshots_for_requirements(bars, indicator_requirements=requirements)
    rows = join_bars_with_indicators(bars, snapshots, indicator_requirements=requirements)
    usable_rows = tuple(row for row in rows if row.indicators.has_required_values())
    return usable_rows if len(usable_rows) >= 2 else rows[-2:]


def _trend_fixture_bars(symbol: str, *, count: int) -> tuple[DailyBar, ...]:
    start_date = date(2018, 1, 1)
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=10.0 + index * 0.03,
            high=10.5 + index * 0.03,
            low=9.5 + index * 0.03,
            close=10.0 + index * 0.03,
            volume=1000,
        )
        for index in range(count)
    )


def _format_requirement(requirement: IndicatorRequirement | tuple[str, str] | str) -> str:
    if isinstance(requirement, IndicatorRequirement):
        return f"{requirement.name}:{requirement.timeframe}"
    if isinstance(requirement, tuple):
        return f"{requirement[0]}:{requirement[1]}"
    return f"{requirement}:D"
