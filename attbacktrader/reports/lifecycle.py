"""Completed trade lifecycle details assembled from persisted run evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from attbacktrader.engines.ledger import ExecutionAuditEvent
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.templates import ClosedTrade


@dataclass(frozen=True)
class TradeLifecycleIndexBucket:
    key: str
    count: int
    trade_indexes: tuple[int, ...]


@dataclass(frozen=True)
class TradeLifecycleIndexes:
    by_symbol: tuple[TradeLifecycleIndexBucket, ...]
    by_outcome: tuple[TradeLifecycleIndexBucket, ...]
    by_exit_reason: tuple[TradeLifecycleIndexBucket, ...]
    by_add_on_count: tuple[TradeLifecycleIndexBucket, ...]
    by_entry_check_true: tuple[TradeLifecycleIndexBucket, ...]
    by_entry_check_false: tuple[TradeLifecycleIndexBucket, ...]
    by_entry_category: tuple[TradeLifecycleIndexBucket, ...]
    by_rejection_reason: tuple[TradeLifecycleIndexBucket, ...]


@dataclass(frozen=True)
class TradeLifecycleExecutionEvent:
    event_date: date
    signal_date: date
    side: str
    event_type: str
    status: str
    reason_code: str
    requested_quantity: int
    executable_quantity: int
    signal_price: float
    order_ref: int | None
    blocked_by: str | None
    executed_date: date | None
    executed_quantity: float | None
    executed_price: float | None
    commission: float | None
    gross_value: float | None
    slippage: float | None
    cash_after: float | None
    value_after: float | None
    position_quantity_after: int | None
    remaining_cost_value_after: float | None
    remaining_cost_basis_after: float | None
    cost_recovered_after: bool | None


@dataclass(frozen=True)
class TradeLifecycleEvent:
    event_type: str
    trade_date: date
    intent_type: str | None
    method_name: str | None
    reason_code: str | None
    blocked_by: str | None
    checks: Mapping[str, bool]
    values: Mapping[str, Any]
    categories: Mapping[str, str]
    sizing_context: Mapping[str, Any]
    executions: tuple[TradeLifecycleExecutionEvent, ...]


@dataclass(frozen=True)
class TradeLifecycle:
    trade_index: int
    symbol: str
    outcome: str
    entry_date: date
    exit_date: date
    exit_reason: str
    entry_price: float
    exit_price: float
    return_pct: float
    events: tuple[TradeLifecycleEvent, ...]
    quantity: int | None = None
    original_entry_price: float | None = None
    remaining_cost_basis_at_exit: float | None = None
    entry_quantity: int | None = None


@dataclass(frozen=True)
class TradeLifecycleReport:
    trade_count: int
    indexes: TradeLifecycleIndexes
    lifecycles: tuple[TradeLifecycle, ...]


def build_trade_lifecycle_report(
    *,
    closed_trades: Sequence[ClosedTrade],
    signal_audit: Sequence[TradeIntent],
    execution_audit: Sequence[ExecutionAuditEvent] = (),
) -> TradeLifecycleReport:
    """Build per-trade entry/add-on/exit timelines from run evidence."""

    lifecycle_trades = tuple(
        sorted(closed_trades, key=lambda trade: (trade.entry_date, trade.exit_date, trade.symbol, trade.exit_reason))
    )
    intents_by_symbol: dict[str, list[TradeIntent]] = defaultdict(list)
    for intent in signal_audit:
        intents_by_symbol[intent.symbol].append(intent)

    executions_by_key: dict[tuple[str, date, str, str], list[ExecutionAuditEvent]] = defaultdict(list)
    executions_by_symbol: dict[str, list[ExecutionAuditEvent]] = defaultdict(list)
    for event in execution_audit:
        executions_by_key[(event.symbol, event.signal_date, event.reason_code, event.side)].append(event)
        executions_by_symbol[event.symbol].append(event)

    lifecycles = tuple(
        _trade_lifecycle(
            index=index,
            trade=trade,
            intents=intents_by_symbol.get(trade.symbol, ()),
            executions_by_key=executions_by_key,
            executions_by_symbol=executions_by_symbol,
        )
        for index, trade in enumerate(lifecycle_trades, start=1)
    )
    return TradeLifecycleReport(
        trade_count=len(lifecycles),
        indexes=_lifecycle_indexes(lifecycles),
        lifecycles=lifecycles,
    )


def render_trade_lifecycle_markdown_zh(report: TradeLifecycleReport, *, limit: int = 50) -> str:
    lines = [
        "# 交易生命周期审阅",
        "",
        f"完成交易数：{report.trade_count}",
        "",
        "## 索引",
        "",
        "| 索引 | 分组 | 数量 | 交易编号 |",
        "|---|---|---:|---|",
    ]
    for index_name, buckets in (
        ("结果", report.indexes.by_outcome),
        ("退出原因", report.indexes.by_exit_reason),
        ("加仓次数", report.indexes.by_add_on_count),
        ("拒因", report.indexes.by_rejection_reason),
    ):
        for bucket in buckets:
            lines.append(
                "| "
                f"{index_name} | "
                f"{bucket.key} | "
                f"{bucket.count} | "
                f"{', '.join(str(index) for index in bucket.trade_indexes[:20])} |"
            )

    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| # | 股票 | 结果 | 入场 | 退出 | 原因 | 收益 | 加仓 | 事件 |",
            "|---:|---|---|---|---|---|---:|---:|---|",
        ]
    )
    for lifecycle in report.lifecycles[:limit]:
        event_labels = [
            f"{event.event_type}:{event.reason_code or '-'}"
            for event in lifecycle.events
        ]
        lines.append(
            "| "
            f"{lifecycle.trade_index} | "
            f"{lifecycle.symbol} | "
            f"{lifecycle.outcome} | "
            f"{lifecycle.entry_date.isoformat()} | "
            f"{lifecycle.exit_date.isoformat()} | "
            f"{lifecycle.exit_reason} | "
            f"{_format_percent(lifecycle.return_pct)} | "
            f"{_add_on_count(lifecycle)} | "
            f"{'; '.join(event_labels)} |"
        )
    if len(report.lifecycles) > limit:
        lines.append("")
        lines.append(f"仅展示前 {limit} 条，完整明细见 `trade_lifecycle.json`。")
    return "\n".join(lines).rstrip() + "\n"


def _trade_lifecycle(
    *,
    index: int,
    trade: ClosedTrade,
    intents: Sequence[TradeIntent],
    executions_by_key: Mapping[tuple[str, date, str, str], Sequence[ExecutionAuditEvent]],
    executions_by_symbol: Mapping[str, Sequence[ExecutionAuditEvent]],
) -> TradeLifecycle:
    entry_intent = _matching_entry_intent(trade, intents)
    exit_intent = _matching_exit_intent(trade, intents)
    add_on_intents = _matching_add_on_intents(trade, intents)

    events: list[TradeLifecycleEvent] = [
        _lifecycle_event(
            event_type="entry",
            trade_date=trade.entry_date,
            intent=entry_intent,
            side="buy",
            executions_by_key=executions_by_key,
        )
    ]
    middle_events = [
        _lifecycle_event(
            event_type="add_on",
            trade_date=add_on_intent.trade_date,
            intent=add_on_intent,
            side="buy",
            executions_by_key=executions_by_key,
        )
        for add_on_intent in add_on_intents
    ]
    middle_events.extend(
        _scale_out_lifecycle_event(execution)
        for execution in _matching_scale_out_executions(trade, executions_by_symbol.get(trade.symbol, ()))
    )
    events.extend(
        sorted(
            middle_events,
            key=lambda event: (event.trade_date, event.event_type, event.reason_code or ""),
        )
    )
    events.append(
        _lifecycle_event(
            event_type="exit",
            trade_date=trade.exit_date,
            intent=exit_intent,
            side="sell",
            executions_by_key=executions_by_key,
        )
    )

    return TradeLifecycle(
        trade_index=index,
        symbol=trade.symbol,
        outcome=_trade_outcome(trade),
        entry_date=trade.entry_date,
        exit_date=trade.exit_date,
        exit_reason=trade.exit_reason,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        return_pct=trade.return_pct,
        quantity=getattr(trade, "quantity", None),
        original_entry_price=getattr(trade, "original_entry_price", None),
        remaining_cost_basis_at_exit=getattr(trade, "remaining_cost_basis_at_exit", None),
        entry_quantity=getattr(trade, "entry_quantity", None),
        events=tuple(events),
    )


def _matching_entry_intent(trade: ClosedTrade, intents: Sequence[TradeIntent]) -> TradeIntent | None:
    candidates = [
        intent
        for intent in sorted(intents, key=lambda value: (value.trade_date, value.reason_code))
        if intent.intent_type == TradeIntentType.ENTER
        and intent.trade_date == trade.entry_date
        and _successful_intent(intent)
    ]
    return candidates[0] if candidates else None


def _matching_exit_intent(trade: ClosedTrade, intents: Sequence[TradeIntent]) -> TradeIntent | None:
    candidates = [
        intent
        for intent in sorted(intents, key=lambda value: (value.trade_date, value.reason_code))
        if intent.intent_type in {TradeIntentType.EXIT_PROFIT, TradeIntentType.EXIT_LOSS}
        and intent.trade_date == trade.exit_date
        and _successful_intent(intent)
    ]
    by_reason = [intent for intent in candidates if intent.reason_code == trade.exit_reason]
    if by_reason:
        return by_reason[0]
    return candidates[0] if candidates else None


def _matching_add_on_intents(trade: ClosedTrade, intents: Sequence[TradeIntent]) -> tuple[TradeIntent, ...]:
    return tuple(
        intent
        for intent in sorted(intents, key=lambda value: (value.trade_date, value.reason_code))
        if intent.intent_type == TradeIntentType.ADD_ON
        and trade.entry_date < intent.trade_date < trade.exit_date
        and _successful_intent(intent)
    )


def _matching_scale_out_executions(
    trade: ClosedTrade,
    executions: Sequence[ExecutionAuditEvent],
) -> tuple[ExecutionAuditEvent, ...]:
    return tuple(
        event
        for event in sorted(executions, key=lambda value: (value.signal_date, value.reason_code))
        if event.side == "sell"
        and event.reason_code.startswith("BAOMA_SCALE_OUT_")
        and event.event_type == "completed"
        and trade.entry_date < event.signal_date < trade.exit_date
    )


def _successful_intent(intent: TradeIntent) -> bool:
    if intent.blocked_by:
        return False
    sizing = intent.signal_values.get("sizing")
    return not (isinstance(sizing, Mapping) and sizing.get("blocked_by"))


def _lifecycle_event(
    *,
    event_type: str,
    trade_date: date,
    intent: TradeIntent | None,
    side: str,
    executions_by_key: Mapping[tuple[str, date, str, str], Sequence[ExecutionAuditEvent]],
) -> TradeLifecycleEvent:
    signal_values = dict(intent.signal_values) if intent is not None else {}
    reason_code = intent.reason_code if intent is not None else None
    executions: tuple[TradeLifecycleExecutionEvent, ...] = ()
    if intent is not None:
        execution_key = (intent.symbol, intent.trade_date, intent.reason_code, side)
        executions = tuple(_execution_event(event) for event in executions_by_key.get(execution_key, ()))

    return TradeLifecycleEvent(
        event_type=event_type,
        trade_date=trade_date,
        intent_type=intent.intent_type.value if intent is not None else None,
        method_name=intent.method_name if intent is not None else None,
        reason_code=reason_code,
        blocked_by=intent.blocked_by if intent is not None else None,
        checks=_checks(signal_values),
        values=_values(signal_values),
        categories=_categories(signal_values),
        sizing_context=_sizing_context(signal_values.get("sizing")),
        executions=executions,
    )


def _scale_out_lifecycle_event(event: ExecutionAuditEvent) -> TradeLifecycleEvent:
    return TradeLifecycleEvent(
        event_type="scale_out",
        trade_date=event.signal_date,
        intent_type=None,
        method_name=None,
        reason_code=event.reason_code,
        blocked_by=event.blocked_by,
        checks={},
        values={
            "executed_quantity": event.executed_quantity,
            "executed_price": event.executed_price,
            "gross_value": event.gross_value,
            "position_quantity_after": event.position_quantity_after,
            "remaining_cost_value_after": event.remaining_cost_value_after,
            "remaining_cost_basis_after": event.remaining_cost_basis_after,
            "cost_recovered_after": event.cost_recovered_after,
        },
        categories={},
        sizing_context={},
        executions=(_execution_event(event),),
    )


def _execution_event(event: ExecutionAuditEvent) -> TradeLifecycleExecutionEvent:
    return TradeLifecycleExecutionEvent(
        event_date=event.event_date,
        signal_date=event.signal_date,
        side=event.side,
        event_type=event.event_type,
        status=event.status,
        reason_code=event.reason_code,
        requested_quantity=event.requested_quantity,
        executable_quantity=event.executable_quantity,
        signal_price=event.signal_price,
        order_ref=event.order_ref,
        blocked_by=event.blocked_by,
        executed_date=event.executed_date,
        executed_quantity=event.executed_quantity,
        executed_price=event.executed_price,
        commission=event.commission,
        gross_value=event.gross_value,
        slippage=event.slippage,
        cash_after=event.cash_after,
        value_after=event.value_after,
        position_quantity_after=event.position_quantity_after,
        remaining_cost_value_after=event.remaining_cost_value_after,
        remaining_cost_basis_after=event.remaining_cost_basis_after,
        cost_recovered_after=event.cost_recovered_after,
    )


def _checks(signal_values: Mapping[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    legacy_checks = signal_values.get("checks")
    if isinstance(legacy_checks, Mapping):
        checks.update({str(key): value for key, value in legacy_checks.items() if isinstance(value, bool)})

    attribution_checks = _attribution_payload(signal_values).get("checks")
    if isinstance(attribution_checks, Mapping):
        checks.update({str(key): value for key, value in attribution_checks.items() if isinstance(value, bool)})
    return checks


def _values(signal_values: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in signal_values.items():
        if key in {"attribution", "checks", "sizing"}:
            continue
        if _is_scalar_json_value(value):
            values[str(key)] = value

    attribution_values = _attribution_payload(signal_values).get("values")
    if isinstance(attribution_values, Mapping):
        values.update(
            {
                str(key): value
                for key, value in attribution_values.items()
                if _is_scalar_json_value(value) and not isinstance(value, bool)
            }
        )
    return values


def _categories(signal_values: Mapping[str, Any]) -> dict[str, str]:
    categories: dict[str, str] = {}
    attribution_categories = _attribution_payload(signal_values).get("categories")
    if isinstance(attribution_categories, Mapping):
        categories.update({str(key): str(value) for key, value in attribution_categories.items() if value is not None})

    sizing = signal_values.get("sizing")
    if isinstance(sizing, Mapping) and sizing.get("risk_group"):
        categories.setdefault("sizing.risk_group", str(sizing["risk_group"]))
    return categories


def _sizing_context(sizing: object) -> dict[str, Any]:
    if not isinstance(sizing, Mapping):
        return {}
    return {str(key): value for key, value in sizing.items() if _is_scalar_json_value(value)}


def _attribution_payload(signal_values: Mapping[str, Any]) -> Mapping[str, Any]:
    attribution = signal_values.get("attribution")
    if not isinstance(attribution, Mapping):
        return {}
    return attribution


def _is_scalar_json_value(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _trade_outcome(trade: ClosedTrade) -> str:
    if trade.return_pct > 0:
        return "win"
    if trade.return_pct < 0:
        return "loss"
    return "flat"


def _lifecycle_indexes(lifecycles: Sequence[TradeLifecycle]) -> TradeLifecycleIndexes:
    by_symbol: dict[str, list[int]] = defaultdict(list)
    by_outcome: dict[str, list[int]] = defaultdict(list)
    by_exit_reason: dict[str, list[int]] = defaultdict(list)
    by_add_on_count: dict[str, list[int]] = defaultdict(list)
    by_entry_check_true: dict[str, list[int]] = defaultdict(list)
    by_entry_check_false: dict[str, list[int]] = defaultdict(list)
    by_entry_category: dict[str, list[int]] = defaultdict(list)
    by_rejection_reason: dict[str, list[int]] = defaultdict(list)

    for lifecycle in lifecycles:
        trade_index = lifecycle.trade_index
        by_symbol[lifecycle.symbol].append(trade_index)
        by_outcome[lifecycle.outcome].append(trade_index)
        by_exit_reason[lifecycle.exit_reason].append(trade_index)
        by_add_on_count[str(_add_on_count(lifecycle))].append(trade_index)

        entry_event = _entry_event(lifecycle)
        if entry_event is not None:
            for key, value in entry_event.checks.items():
                if value:
                    by_entry_check_true[key].append(trade_index)
                else:
                    by_entry_check_false[key].append(trade_index)
            for key, value in entry_event.categories.items():
                by_entry_category[f"{key}={value}"].append(trade_index)

        for event in lifecycle.events:
            for execution in event.executions:
                for reason in _blocked_reasons(execution.blocked_by):
                    by_rejection_reason[reason].append(trade_index)

    return TradeLifecycleIndexes(
        by_symbol=_index_buckets(by_symbol),
        by_outcome=_index_buckets(by_outcome),
        by_exit_reason=_index_buckets(by_exit_reason),
        by_add_on_count=_index_buckets(by_add_on_count, numeric_keys=True),
        by_entry_check_true=_index_buckets(by_entry_check_true),
        by_entry_check_false=_index_buckets(by_entry_check_false),
        by_entry_category=_index_buckets(by_entry_category),
        by_rejection_reason=_index_buckets(by_rejection_reason),
    )


def _add_on_count(lifecycle: TradeLifecycle) -> int:
    return sum(1 for event in lifecycle.events if event.event_type == "add_on")


def _entry_event(lifecycle: TradeLifecycle) -> TradeLifecycleEvent | None:
    return next((event for event in lifecycle.events if event.event_type == "entry"), None)


def _blocked_reasons(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _index_buckets(
    values: Mapping[str, Sequence[int]],
    *,
    numeric_keys: bool = False,
) -> tuple[TradeLifecycleIndexBucket, ...]:
    def sort_key(item: tuple[str, Sequence[int]]) -> tuple[int, int | str]:
        key, trade_indexes = item
        if numeric_keys and key.isdigit():
            return (0, int(key))
        return (1, key)

    return tuple(
        TradeLifecycleIndexBucket(
            key=key,
            count=len(tuple(dict.fromkeys(trade_indexes))),
            trade_indexes=tuple(dict.fromkeys(trade_indexes)),
        )
        for key, trade_indexes in sorted(values.items(), key=sort_key)
    )
