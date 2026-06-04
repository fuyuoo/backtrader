"""Result diagnostics assembled from completed run evidence."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from attbacktrader.engines.ledger import ExecutionAuditEvent
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.templates import ClosedTrade, Position


@dataclass(frozen=True)
class ReasonCount:
    reason: str
    count: int


@dataclass(frozen=True)
class EntryCheckCount:
    check: str
    true_count: int
    false_count: int


@dataclass(frozen=True)
class EntryValueAverage:
    name: str
    average: float
    count: int


@dataclass(frozen=True)
class EntryCheckSummary:
    key: str
    sample_count: int
    present_count: int
    missing_count: int
    true_count: int
    false_count: int
    true_rate: float | None
    missing_rate: float | None


@dataclass(frozen=True)
class EntryValueSummary:
    key: str
    sample_count: int
    present_count: int
    missing_count: int
    average: float | None
    minimum: float | None
    maximum: float | None
    missing_rate: float | None


@dataclass(frozen=True)
class EntryCategoryValueCount:
    value: str
    count: int
    rate: float | None


@dataclass(frozen=True)
class EntryCategorySummary:
    key: str
    sample_count: int
    present_count: int
    missing_count: int
    missing_rate: float | None
    values: tuple[EntryCategoryValueCount, ...]


@dataclass(frozen=True)
class EntryAttributionOutcomeSummary:
    outcome: str
    sample_count: int
    checks: tuple[EntryCheckSummary, ...]
    values: tuple[EntryValueSummary, ...]
    categories: tuple[EntryCategorySummary, ...]


@dataclass(frozen=True)
class EntryAttributionContrast:
    factor_type: str
    key: str
    category_value: str | None
    win_value: float | None
    loss_value: float | None
    difference: float | None
    win_present_count: int
    loss_present_count: int
    win_missing_rate: float | None
    loss_missing_rate: float | None
    low_sample: bool


@dataclass(frozen=True)
class TradeEntryAttribution:
    symbol: str
    outcome: str
    entry_date: date
    exit_date: date
    exit_reason: str
    return_pct: float
    entry_method_name: str | None
    entry_reason_code: str | None
    entry_checks: Mapping[str, bool]
    entry_values: Mapping[str, Any]
    entry_categories: Mapping[str, str]
    sizing_context: Mapping[str, Any]


@dataclass(frozen=True)
class TradeExitAttribution:
    symbol: str
    outcome: str
    entry_date: date
    exit_date: date
    exit_reason: str
    return_pct: float
    exit_method_name: str | None
    exit_reason_code: str | None
    exit_checks: Mapping[str, bool]
    exit_values: Mapping[str, Any]
    exit_categories: Mapping[str, str]


@dataclass(frozen=True)
class TradeAddOnAttribution:
    symbol: str
    outcome: str
    entry_date: date
    add_on_date: date
    exit_date: date
    exit_reason: str
    return_pct: float
    add_on_method_name: str | None
    add_on_reason_code: str | None
    add_on_checks: Mapping[str, bool]
    add_on_values: Mapping[str, Any]
    add_on_categories: Mapping[str, str]
    sizing_context: Mapping[str, Any]


@dataclass(frozen=True)
class SymbolResultDiagnostic:
    symbol: str
    closed_trade_count: int
    win_count: int
    loss_count: int
    cumulative_return: float | None
    average_return: float | None
    best_return: float | None
    worst_return: float | None
    realized_pnl: float | None
    take_profit_count: int
    stop_loss_count: int
    other_exit_count: int
    exit_reason_counts: tuple[ReasonCount, ...]
    entry_signal_count: int
    take_profit_signal_count: int
    stop_loss_signal_count: int
    hold_signal_count: int
    avoid_signal_count: int
    execution_rejection_count: int
    execution_rejection_counts: tuple[ReasonCount, ...]
    sizing_accepted_count: int
    sizing_blocked_count: int
    sizing_block_counts: tuple[ReasonCount, ...]
    winning_entry_check_counts: tuple[EntryCheckCount, ...]
    losing_entry_check_counts: tuple[EntryCheckCount, ...]
    winning_entry_value_averages: tuple[EntryValueAverage, ...]
    losing_entry_value_averages: tuple[EntryValueAverage, ...]
    winning_entry_summary: EntryAttributionOutcomeSummary
    losing_entry_summary: EntryAttributionOutcomeSummary
    entry_contrasts: tuple[EntryAttributionContrast, ...]
    winning_exit_summary: EntryAttributionOutcomeSummary
    losing_exit_summary: EntryAttributionOutcomeSummary
    exit_contrasts: tuple[EntryAttributionContrast, ...]
    winning_trade_attributions: tuple[TradeEntryAttribution, ...]
    losing_trade_attributions: tuple[TradeEntryAttribution, ...]
    winning_trade_exit_attributions: tuple[TradeExitAttribution, ...]
    losing_trade_exit_attributions: tuple[TradeExitAttribution, ...]
    winning_add_on_summary: EntryAttributionOutcomeSummary
    losing_add_on_summary: EntryAttributionOutcomeSummary
    add_on_contrasts: tuple[EntryAttributionContrast, ...]
    winning_trade_add_on_attributions: tuple[TradeAddOnAttribution, ...]
    losing_trade_add_on_attributions: tuple[TradeAddOnAttribution, ...]
    add_on_signal_count: int
    has_open_position: bool
    open_position_entry_date: date | None
    open_position_entry_price: float | None


@dataclass(frozen=True)
class ResultDiagnostics:
    symbols: tuple[SymbolResultDiagnostic, ...]
    portfolio_winning_entry_summary: EntryAttributionOutcomeSummary
    portfolio_losing_entry_summary: EntryAttributionOutcomeSummary
    portfolio_entry_contrasts: tuple[EntryAttributionContrast, ...]
    portfolio_winning_exit_summary: EntryAttributionOutcomeSummary
    portfolio_losing_exit_summary: EntryAttributionOutcomeSummary
    portfolio_exit_contrasts: tuple[EntryAttributionContrast, ...]
    portfolio_winning_add_on_summary: EntryAttributionOutcomeSummary
    portfolio_losing_add_on_summary: EntryAttributionOutcomeSummary
    portfolio_add_on_contrasts: tuple[EntryAttributionContrast, ...]
    portfolio_add_on_signal_count: int


def build_result_diagnostics(
    *,
    symbols: Sequence[str],
    closed_trades: Sequence[ClosedTrade],
    signal_audit: Sequence[TradeIntent],
    execution_audit: Sequence[ExecutionAuditEvent] = (),
    open_positions: Sequence[Position] = (),
) -> ResultDiagnostics:
    trades_by_symbol: dict[str, list[ClosedTrade]] = defaultdict(list)
    for trade in closed_trades:
        trades_by_symbol[trade.symbol].append(trade)

    intents_by_symbol: dict[str, list[TradeIntent]] = defaultdict(list)
    for intent in signal_audit:
        intents_by_symbol[intent.symbol].append(intent)

    execution_by_symbol: dict[str, list[ExecutionAuditEvent]] = defaultdict(list)
    for event in execution_audit:
        execution_by_symbol[event.symbol].append(event)

    open_position_by_symbol = {position.symbol: position for position in open_positions}
    realized_pnl_by_symbol = _realized_pnl_by_symbol(execution_audit)
    all_symbols = tuple(sorted(set(symbols) | set(trades_by_symbol) | set(intents_by_symbol) | set(execution_by_symbol)))

    symbol_diagnostics = tuple(
        _symbol_diagnostic(
            symbol=symbol,
            trades=trades_by_symbol.get(symbol, ()),
            intents=intents_by_symbol.get(symbol, ()),
            execution_events=execution_by_symbol.get(symbol, ()),
            open_position=open_position_by_symbol.get(symbol),
            realized_pnl=realized_pnl_by_symbol.get(symbol),
        )
        for symbol in all_symbols
    )
    winning_attributions = tuple(
        attribution
        for diagnostic in symbol_diagnostics
        for attribution in diagnostic.winning_trade_attributions
    )
    losing_attributions = tuple(
        attribution
        for diagnostic in symbol_diagnostics
        for attribution in diagnostic.losing_trade_attributions
    )
    winning_exit_attributions = tuple(
        attribution
        for diagnostic in symbol_diagnostics
        for attribution in diagnostic.winning_trade_exit_attributions
    )
    losing_exit_attributions = tuple(
        attribution
        for diagnostic in symbol_diagnostics
        for attribution in diagnostic.losing_trade_exit_attributions
    )
    winning_add_on_attributions = tuple(
        attribution
        for diagnostic in symbol_diagnostics
        for attribution in diagnostic.winning_trade_add_on_attributions
    )
    losing_add_on_attributions = tuple(
        attribution
        for diagnostic in symbol_diagnostics
        for attribution in diagnostic.losing_trade_add_on_attributions
    )

    return ResultDiagnostics(
        symbols=symbol_diagnostics,
        portfolio_winning_entry_summary=_entry_outcome_summary("win", winning_attributions),
        portfolio_losing_entry_summary=_entry_outcome_summary("loss", losing_attributions),
        portfolio_entry_contrasts=_entry_attribution_contrasts(winning_attributions, losing_attributions),
        portfolio_winning_exit_summary=_entry_outcome_summary("win", winning_exit_attributions),
        portfolio_losing_exit_summary=_entry_outcome_summary("loss", losing_exit_attributions),
        portfolio_exit_contrasts=_entry_attribution_contrasts(winning_exit_attributions, losing_exit_attributions),
        portfolio_winning_add_on_summary=_entry_outcome_summary("win", winning_add_on_attributions),
        portfolio_losing_add_on_summary=_entry_outcome_summary("loss", losing_add_on_attributions),
        portfolio_add_on_contrasts=_entry_attribution_contrasts(winning_add_on_attributions, losing_add_on_attributions),
        portfolio_add_on_signal_count=sum(diagnostic.add_on_signal_count for diagnostic in symbol_diagnostics),
    )


def _symbol_diagnostic(
    *,
    symbol: str,
    trades: Sequence[ClosedTrade],
    intents: Sequence[TradeIntent],
    execution_events: Sequence[ExecutionAuditEvent],
    open_position: Position | None,
    realized_pnl: float | None,
) -> SymbolResultDiagnostic:
    returns = [trade.return_pct for trade in trades]
    cumulative_return = None
    average_return = None
    best_return = None
    worst_return = None
    if returns:
        equity = 1.0
        for value in returns:
            equity *= 1.0 + value
        cumulative_return = equity - 1.0
        average_return = sum(returns) / len(returns)
        best_return = max(returns)
        worst_return = min(returns)

    exit_types = _exit_type_by_reason(intents)
    trade_attributions = _trade_entry_attributions(trades=trades, intents=intents)
    trade_exit_attributions = _trade_exit_attributions(trades=trades, intents=intents)
    trade_add_on_attributions = _trade_add_on_attributions(trades=trades, intents=intents)
    winning_trade_attributions = tuple(attribution for attribution in trade_attributions if attribution.outcome == "win")
    losing_trade_attributions = tuple(attribution for attribution in trade_attributions if attribution.outcome == "loss")
    winning_trade_exit_attributions = tuple(
        attribution for attribution in trade_exit_attributions if attribution.outcome == "win"
    )
    losing_trade_exit_attributions = tuple(
        attribution for attribution in trade_exit_attributions if attribution.outcome == "loss"
    )
    winning_trade_add_on_attributions = tuple(
        attribution for attribution in trade_add_on_attributions if attribution.outcome == "win"
    )
    losing_trade_add_on_attributions = tuple(
        attribution for attribution in trade_add_on_attributions if attribution.outcome == "loss"
    )
    take_profit_count = 0
    stop_loss_count = 0
    exit_reason_counts = Counter(trade.exit_reason for trade in trades)
    for trade in trades:
        exit_type = exit_types.get(trade.exit_reason)
        if exit_type == TradeIntentType.EXIT_PROFIT:
            take_profit_count += 1
        elif exit_type == TradeIntentType.EXIT_LOSS:
            stop_loss_count += 1
        elif trade.return_pct >= 0:
            take_profit_count += 1
        else:
            stop_loss_count += 1
    other_exit_count = max(0, len(trades) - take_profit_count - stop_loss_count)

    intent_type_counts = Counter(intent.intent_type for intent in intents)
    execution_rejection_counts = Counter(
        _execution_rejection_reason(event)
        for event in execution_events
        if _is_rejected_execution(event)
    )
    sizing_accepted_count, sizing_block_counts = _sizing_counts(intents)

    return SymbolResultDiagnostic(
        symbol=symbol,
        closed_trade_count=len(trades),
        win_count=sum(1 for value in returns if value > 0),
        loss_count=sum(1 for value in returns if value < 0),
        cumulative_return=cumulative_return,
        average_return=average_return,
        best_return=best_return,
        worst_return=worst_return,
        realized_pnl=realized_pnl,
        take_profit_count=take_profit_count,
        stop_loss_count=stop_loss_count,
        other_exit_count=other_exit_count,
        exit_reason_counts=_reason_counts(exit_reason_counts),
        entry_signal_count=intent_type_counts[TradeIntentType.ENTER],
        take_profit_signal_count=intent_type_counts[TradeIntentType.EXIT_PROFIT],
        stop_loss_signal_count=intent_type_counts[TradeIntentType.EXIT_LOSS],
        hold_signal_count=intent_type_counts[TradeIntentType.HOLD],
        avoid_signal_count=intent_type_counts[TradeIntentType.AVOID],
        execution_rejection_count=sum(execution_rejection_counts.values()),
        execution_rejection_counts=_reason_counts(execution_rejection_counts),
        sizing_accepted_count=sizing_accepted_count,
        sizing_blocked_count=sum(sizing_block_counts.values()),
        sizing_block_counts=_reason_counts(sizing_block_counts),
        winning_entry_check_counts=_entry_check_counts(winning_trade_attributions),
        losing_entry_check_counts=_entry_check_counts(losing_trade_attributions),
        winning_entry_value_averages=_entry_value_averages(winning_trade_attributions),
        losing_entry_value_averages=_entry_value_averages(losing_trade_attributions),
        winning_entry_summary=_entry_outcome_summary("win", winning_trade_attributions),
        losing_entry_summary=_entry_outcome_summary("loss", losing_trade_attributions),
        entry_contrasts=_entry_attribution_contrasts(winning_trade_attributions, losing_trade_attributions),
        winning_exit_summary=_entry_outcome_summary("win", winning_trade_exit_attributions),
        losing_exit_summary=_entry_outcome_summary("loss", losing_trade_exit_attributions),
        exit_contrasts=_entry_attribution_contrasts(winning_trade_exit_attributions, losing_trade_exit_attributions),
        winning_trade_attributions=winning_trade_attributions,
        losing_trade_attributions=losing_trade_attributions,
        winning_trade_exit_attributions=winning_trade_exit_attributions,
        losing_trade_exit_attributions=losing_trade_exit_attributions,
        winning_add_on_summary=_entry_outcome_summary("win", winning_trade_add_on_attributions),
        losing_add_on_summary=_entry_outcome_summary("loss", losing_trade_add_on_attributions),
        add_on_contrasts=_entry_attribution_contrasts(
            winning_trade_add_on_attributions,
            losing_trade_add_on_attributions,
        ),
        winning_trade_add_on_attributions=winning_trade_add_on_attributions,
        losing_trade_add_on_attributions=losing_trade_add_on_attributions,
        add_on_signal_count=sum(1 for intent in intents if _is_add_on_intent(intent)),
        has_open_position=open_position is not None,
        open_position_entry_date=open_position.entry_date if open_position is not None else None,
        open_position_entry_price=open_position.entry_price if open_position is not None else None,
    )


def _exit_type_by_reason(intents: Sequence[TradeIntent]) -> dict[str, TradeIntentType]:
    exit_types: dict[str, TradeIntentType] = {}
    for intent in intents:
        if intent.intent_type in {TradeIntentType.EXIT_PROFIT, TradeIntentType.EXIT_LOSS}:
            exit_types[intent.reason_code] = intent.intent_type
    return exit_types


def _sizing_counts(intents: Sequence[TradeIntent]) -> tuple[int, Counter[str]]:
    accepted_count = 0
    block_counts: Counter[str] = Counter()

    for intent in intents:
        sizing_values = intent.signal_values.get("sizing")
        if not isinstance(sizing_values, Mapping):
            continue
        blocked_by = intent.blocked_by or sizing_values.get("blocked_by")
        if blocked_by:
            block_counts[str(blocked_by)] += 1
        else:
            accepted_count += 1

    return accepted_count, block_counts


def _trade_entry_attributions(
    *,
    trades: Sequence[ClosedTrade],
    intents: Sequence[TradeIntent],
) -> tuple[TradeEntryAttribution, ...]:
    entry_intents_by_date: dict[date, deque[TradeIntent]] = defaultdict(deque)
    for intent in sorted(intents, key=lambda value: (value.trade_date, value.reason_code)):
        if intent.intent_type != TradeIntentType.ENTER:
            continue
        if intent.blocked_by:
            continue
        sizing_values = intent.signal_values.get("sizing")
        if isinstance(sizing_values, Mapping) and sizing_values.get("blocked_by"):
            continue
        entry_intents_by_date[intent.trade_date].append(intent)

    attributions: list[TradeEntryAttribution] = []
    for trade in sorted(trades, key=lambda value: (value.entry_date, value.exit_date, value.symbol)):
        entry_intent = _pop_entry_intent(entry_intents_by_date, trade.entry_date)
        attributions.append(_trade_entry_attribution(trade, entry_intent))

    return tuple(attributions)


def _pop_entry_intent(entry_intents_by_date: dict[date, deque[TradeIntent]], entry_date: date) -> TradeIntent | None:
    intents = entry_intents_by_date.get(entry_date)
    if not intents:
        return None
    return intents.popleft()


def _trade_entry_attribution(trade: ClosedTrade, entry_intent: TradeIntent | None) -> TradeEntryAttribution:
    signal_values = dict(entry_intent.signal_values) if entry_intent is not None else {}
    sizing_values = signal_values.get("sizing")

    return TradeEntryAttribution(
        symbol=trade.symbol,
        outcome=_trade_outcome(trade),
        entry_date=trade.entry_date,
        exit_date=trade.exit_date,
        exit_reason=trade.exit_reason,
        return_pct=trade.return_pct,
        entry_method_name=entry_intent.method_name if entry_intent is not None else None,
        entry_reason_code=entry_intent.reason_code if entry_intent is not None else None,
        entry_checks=_entry_checks(signal_values),
        entry_values=_entry_values(signal_values),
        entry_categories=_entry_categories(signal_values),
        sizing_context=_sizing_context(sizing_values),
    )


def _trade_exit_attributions(
    *,
    trades: Sequence[ClosedTrade],
    intents: Sequence[TradeIntent],
) -> tuple[TradeExitAttribution, ...]:
    exit_intents = [
        intent
        for intent in sorted(intents, key=lambda value: (value.trade_date, value.reason_code))
        if intent.intent_type in {TradeIntentType.EXIT_PROFIT, TradeIntentType.EXIT_LOSS}
        and not intent.blocked_by
    ]
    used_indexes: set[int] = set()

    attributions: list[TradeExitAttribution] = []
    for trade in sorted(trades, key=lambda value: (value.exit_date, value.symbol, value.exit_reason)):
        exit_intent = _matching_exit_intent(trade, exit_intents, used_indexes)
        attributions.append(_trade_exit_attribution(trade, exit_intent))

    return tuple(attributions)


def _matching_exit_intent(
    trade: ClosedTrade,
    exit_intents: Sequence[TradeIntent],
    used_indexes: set[int],
) -> TradeIntent | None:
    for index, intent in enumerate(exit_intents):
        if index in used_indexes:
            continue
        if intent.trade_date == trade.exit_date and intent.reason_code == trade.exit_reason:
            used_indexes.add(index)
            return intent

    for index, intent in enumerate(exit_intents):
        if index in used_indexes:
            continue
        if intent.trade_date == trade.exit_date:
            used_indexes.add(index)
            return intent

    return None


def _trade_exit_attribution(trade: ClosedTrade, exit_intent: TradeIntent | None) -> TradeExitAttribution:
    signal_values = dict(exit_intent.signal_values) if exit_intent is not None else {}

    return TradeExitAttribution(
        symbol=trade.symbol,
        outcome=_trade_outcome(trade),
        entry_date=trade.entry_date,
        exit_date=trade.exit_date,
        exit_reason=trade.exit_reason,
        return_pct=trade.return_pct,
        exit_method_name=exit_intent.method_name if exit_intent is not None else None,
        exit_reason_code=exit_intent.reason_code if exit_intent is not None else None,
        exit_checks=_entry_checks(signal_values),
        exit_values=_entry_values(signal_values),
        exit_categories=_entry_categories(signal_values),
    )


def _trade_add_on_attributions(
    *,
    trades: Sequence[ClosedTrade],
    intents: Sequence[TradeIntent],
) -> tuple[TradeAddOnAttribution, ...]:
    add_on_intents = [
        intent
        for intent in sorted(intents, key=lambda value: (value.trade_date, value.reason_code))
        if intent.intent_type == TradeIntentType.ADD_ON
        and not intent.blocked_by
        and not _sizing_blocked(intent)
    ]

    attributions: list[TradeAddOnAttribution] = []
    for trade in sorted(trades, key=lambda value: (value.entry_date, value.exit_date, value.symbol)):
        for add_on_intent in _matching_add_on_intents(trade, add_on_intents):
            attributions.append(_trade_add_on_attribution(trade, add_on_intent))

    return tuple(attributions)


def _matching_add_on_intents(
    trade: ClosedTrade,
    add_on_intents: Sequence[TradeIntent],
) -> tuple[TradeIntent, ...]:
    return tuple(
        intent
        for intent in add_on_intents
        if intent.symbol == trade.symbol
        and trade.entry_date < intent.trade_date < trade.exit_date
    )


def _trade_add_on_attribution(trade: ClosedTrade, add_on_intent: TradeIntent) -> TradeAddOnAttribution:
    signal_values = dict(add_on_intent.signal_values)
    sizing_values = signal_values.get("sizing")

    return TradeAddOnAttribution(
        symbol=trade.symbol,
        outcome=_trade_outcome(trade),
        entry_date=trade.entry_date,
        add_on_date=add_on_intent.trade_date,
        exit_date=trade.exit_date,
        exit_reason=trade.exit_reason,
        return_pct=trade.return_pct,
        add_on_method_name=add_on_intent.method_name,
        add_on_reason_code=add_on_intent.reason_code,
        add_on_checks=_entry_checks(signal_values),
        add_on_values=_entry_values(signal_values),
        add_on_categories=_entry_categories(signal_values),
        sizing_context=_sizing_context(sizing_values),
    )


def _trade_outcome(trade: ClosedTrade) -> str:
    if trade.return_pct > 0:
        return "win"
    if trade.return_pct < 0:
        return "loss"
    return "flat"


def _entry_checks(signal_values: Mapping[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    legacy_checks = signal_values.get("checks")
    if isinstance(legacy_checks, Mapping):
        checks.update(
            {
                str(key): value
                for key, value in legacy_checks.items()
                if isinstance(value, bool)
            }
        )

    attribution = _attribution_payload(signal_values)
    attribution_checks = attribution.get("checks")
    if isinstance(attribution_checks, Mapping):
        checks.update(
            {
                str(key): value
                for key, value in attribution_checks.items()
                if isinstance(value, bool)
            }
        )
    return checks


def _entry_values(signal_values: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in signal_values.items():
        if key in {"attribution", "checks", "sizing"}:
            continue
        if _is_scalar_json_value(value):
            values[str(key)] = value

    attribution = _attribution_payload(signal_values)
    attribution_values = attribution.get("values")
    if isinstance(attribution_values, Mapping):
        values.update(
            {
                str(key): value
                for key, value in attribution_values.items()
                if _is_scalar_json_value(value) and not isinstance(value, bool)
            }
        )
    return values


def _entry_categories(signal_values: Mapping[str, Any]) -> dict[str, str]:
    categories: dict[str, str] = {}
    attribution = _attribution_payload(signal_values)
    attribution_categories = attribution.get("categories")
    if isinstance(attribution_categories, Mapping):
        categories.update(
            {
                str(key): str(value)
                for key, value in attribution_categories.items()
                if value is not None
            }
        )

    sizing_values = signal_values.get("sizing")
    if isinstance(sizing_values, Mapping) and sizing_values.get("risk_group"):
        categories.setdefault("sizing.risk_group", str(sizing_values["risk_group"]))
    return categories


def _attribution_payload(signal_values: Mapping[str, Any]) -> Mapping[str, Any]:
    attribution = signal_values.get("attribution")
    if not isinstance(attribution, Mapping):
        return {}
    return attribution


def _sizing_context(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    keys = (
        "requested_quantity",
        "price",
        "target_value",
        "risk_group",
        "atr_value",
        "risk_budget_value",
        "risk_per_share",
        "blocked_by",
    )
    return {
        key: value.get(key)
        for key in keys
        if key in value and _is_scalar_json_value(value.get(key))
    }


def _sizing_blocked(intent: TradeIntent) -> bool:
    sizing_values = intent.signal_values.get("sizing")
    return isinstance(sizing_values, Mapping) and bool(sizing_values.get("blocked_by"))


def _entry_check_counts(attributions: Sequence[TradeEntryAttribution]) -> tuple[EntryCheckCount, ...]:
    checks: dict[str, Counter[bool]] = defaultdict(Counter)
    for attribution in attributions:
        for check, value in attribution.entry_checks.items():
            checks[check][value] += 1

    return tuple(
        EntryCheckCount(
            check=check,
            true_count=counts[True],
            false_count=counts[False],
        )
        for check, counts in sorted(checks.items())
    )


def _entry_value_averages(attributions: Sequence[TradeEntryAttribution]) -> tuple[EntryValueAverage, ...]:
    values_by_name: dict[str, list[float]] = defaultdict(list)
    for attribution in attributions:
        for name, value in attribution.entry_values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            values_by_name[name].append(float(value))

    return tuple(
        EntryValueAverage(
            name=name,
            average=sum(values) / len(values),
            count=len(values),
        )
        for name, values in sorted(values_by_name.items())
        if values
    )


def _entry_outcome_summary(
    outcome: str,
    attributions: Sequence[TradeEntryAttribution],
) -> EntryAttributionOutcomeSummary:
    return EntryAttributionOutcomeSummary(
        outcome=outcome,
        sample_count=len(attributions),
        checks=_entry_check_summaries(attributions),
        values=_entry_value_summaries(attributions),
        categories=_entry_category_summaries(attributions),
    )


def _entry_check_summaries(
    attributions: Sequence[Any],
    *,
    keys: Sequence[str] | None = None,
) -> tuple[EntryCheckSummary, ...]:
    sample_count = len(attributions)
    factor_keys = tuple(sorted(set(keys or ()) | {key for item in attributions for key in _attribution_checks(item)}))
    summaries: list[EntryCheckSummary] = []

    for key in factor_keys:
        values = [
            _attribution_checks(item)[key]
            for item in attributions
            if key in _attribution_checks(item)
        ]
        present_count = len(values)
        true_count = sum(1 for value in values if value)
        false_count = present_count - true_count
        missing_count = sample_count - present_count
        summaries.append(
            EntryCheckSummary(
                key=key,
                sample_count=sample_count,
                present_count=present_count,
                missing_count=missing_count,
                true_count=true_count,
                false_count=false_count,
                true_rate=_safe_rate(true_count, present_count),
                missing_rate=_safe_rate(missing_count, sample_count),
            )
        )

    return tuple(summaries)


def _entry_value_summaries(
    attributions: Sequence[Any],
    *,
    keys: Sequence[str] | None = None,
) -> tuple[EntryValueSummary, ...]:
    sample_count = len(attributions)
    factor_keys = tuple(sorted(set(keys or ()) | {key for item in attributions for key in _attribution_values(item)}))
    summaries: list[EntryValueSummary] = []

    for key in factor_keys:
        values = [
            float(_attribution_values(item)[key])
            for item in attributions
            if key in _attribution_values(item)
            and not isinstance(_attribution_values(item)[key], bool)
            and isinstance(_attribution_values(item)[key], (int, float))
        ]
        present_count = len(values)
        missing_count = sample_count - present_count
        summaries.append(
            EntryValueSummary(
                key=key,
                sample_count=sample_count,
                present_count=present_count,
                missing_count=missing_count,
                average=sum(values) / present_count if present_count else None,
                minimum=min(values) if values else None,
                maximum=max(values) if values else None,
                missing_rate=_safe_rate(missing_count, sample_count),
            )
        )

    return tuple(summary for summary in summaries if summary.present_count > 0)


def _entry_category_summaries(
    attributions: Sequence[Any],
    *,
    keys: Sequence[str] | None = None,
) -> tuple[EntryCategorySummary, ...]:
    sample_count = len(attributions)
    factor_keys = tuple(sorted(set(keys or ()) | {key for item in attributions for key in _attribution_categories(item)}))
    summaries: list[EntryCategorySummary] = []

    for key in factor_keys:
        values = [
            _attribution_categories(item)[key]
            for item in attributions
            if key in _attribution_categories(item)
        ]
        present_count = len(values)
        missing_count = sample_count - present_count
        counts = Counter(values)
        summaries.append(
            EntryCategorySummary(
                key=key,
                sample_count=sample_count,
                present_count=present_count,
                missing_count=missing_count,
                missing_rate=_safe_rate(missing_count, sample_count),
                values=tuple(
                    EntryCategoryValueCount(value=value, count=count, rate=_safe_rate(count, present_count))
                    for value, count in sorted(counts.items())
                ),
            )
        )

    return tuple(summary for summary in summaries if summary.present_count > 0)


def _entry_attribution_contrasts(
    winning_attributions: Sequence[Any],
    losing_attributions: Sequence[Any],
) -> tuple[EntryAttributionContrast, ...]:
    contrasts: list[EntryAttributionContrast] = []

    check_keys = tuple(
        sorted(
            {key for item in winning_attributions for key in _attribution_checks(item)}
            | {key for item in losing_attributions for key in _attribution_checks(item)}
        )
    )
    win_checks = {summary.key: summary for summary in _entry_check_summaries(winning_attributions, keys=check_keys)}
    loss_checks = {summary.key: summary for summary in _entry_check_summaries(losing_attributions, keys=check_keys)}
    for key in check_keys:
        win = win_checks[key]
        loss = loss_checks[key]
        contrasts.append(
            _contrast(
                factor_type="check",
                key=key,
                category_value=None,
                win_value=win.true_rate,
                loss_value=loss.true_rate,
                win_present_count=win.present_count,
                loss_present_count=loss.present_count,
                win_missing_rate=win.missing_rate,
                loss_missing_rate=loss.missing_rate,
            )
        )

    value_keys = tuple(
        sorted(
            {key for item in winning_attributions for key in _attribution_values(item)}
            | {key for item in losing_attributions for key in _attribution_values(item)}
        )
    )
    win_values = {summary.key: summary for summary in _entry_value_summaries(winning_attributions, keys=value_keys)}
    loss_values = {summary.key: summary for summary in _entry_value_summaries(losing_attributions, keys=value_keys)}
    for key in value_keys:
        win = win_values.get(key)
        loss = loss_values.get(key)
        if win is None and loss is None:
            continue
        contrasts.append(
            _contrast(
                factor_type="value",
                key=key,
                category_value=None,
                win_value=win.average if win is not None else None,
                loss_value=loss.average if loss is not None else None,
                win_present_count=win.present_count if win is not None else 0,
                loss_present_count=loss.present_count if loss is not None else 0,
                win_missing_rate=win.missing_rate if win is not None else _safe_rate(len(winning_attributions), len(winning_attributions)),
                loss_missing_rate=loss.missing_rate if loss is not None else _safe_rate(len(losing_attributions), len(losing_attributions)),
            )
        )

    category_keys = tuple(
        sorted(
            {key for item in winning_attributions for key in _attribution_categories(item)}
            | {key for item in losing_attributions for key in _attribution_categories(item)}
        )
    )
    win_categories = {summary.key: summary for summary in _entry_category_summaries(winning_attributions, keys=category_keys)}
    loss_categories = {summary.key: summary for summary in _entry_category_summaries(losing_attributions, keys=category_keys)}
    for key in category_keys:
        win = win_categories.get(key)
        loss = loss_categories.get(key)
        win_category_values = {value.value for value in win.values} if win is not None else set()
        loss_category_values = {value.value for value in loss.values} if loss is not None else set()
        category_values = tuple(sorted(win_category_values | loss_category_values))
        for category_value in category_values:
            win_rate = _category_rate(win, category_value)
            loss_rate = _category_rate(loss, category_value)
            contrasts.append(
                _contrast(
                    factor_type="category",
                    key=key,
                    category_value=category_value,
                    win_value=win_rate,
                    loss_value=loss_rate,
                    win_present_count=win.present_count if win is not None else 0,
                    loss_present_count=loss.present_count if loss is not None else 0,
                    win_missing_rate=win.missing_rate if win is not None else _safe_rate(len(winning_attributions), len(winning_attributions)),
                    loss_missing_rate=loss.missing_rate if loss is not None else _safe_rate(len(losing_attributions), len(losing_attributions)),
                )
            )

    return tuple(sorted(contrasts, key=_contrast_sort_key))


def _contrast(
    *,
    factor_type: str,
    key: str,
    category_value: str | None,
    win_value: float | None,
    loss_value: float | None,
    win_present_count: int,
    loss_present_count: int,
    win_missing_rate: float | None,
    loss_missing_rate: float | None,
) -> EntryAttributionContrast:
    difference = None
    if win_value is not None and loss_value is not None:
        difference = win_value - loss_value
    return EntryAttributionContrast(
        factor_type=factor_type,
        key=key,
        category_value=category_value,
        win_value=win_value,
        loss_value=loss_value,
        difference=difference,
        win_present_count=win_present_count,
        loss_present_count=loss_present_count,
        win_missing_rate=win_missing_rate,
        loss_missing_rate=loss_missing_rate,
        low_sample=win_present_count < 3 or loss_present_count < 3,
    )


def _category_rate(summary: EntryCategorySummary | None, category_value: str) -> float | None:
    if summary is None:
        return None
    for item in summary.values:
        if item.value == category_value:
            return item.rate
    return 0.0 if summary.present_count else None


def _contrast_sort_key(contrast: EntryAttributionContrast) -> tuple[int, float, str, str]:
    difference = contrast.difference
    return (
        1 if difference is None else 0,
        -(abs(difference) if difference is not None else 0.0),
        contrast.key,
        contrast.category_value or "",
    )


def _attribution_checks(attribution: Any) -> Mapping[str, bool]:
    if hasattr(attribution, "entry_checks"):
        return attribution.entry_checks
    if hasattr(attribution, "exit_checks"):
        return attribution.exit_checks
    if hasattr(attribution, "add_on_checks"):
        return attribution.add_on_checks
    return {}


def _attribution_values(attribution: Any) -> Mapping[str, Any]:
    if hasattr(attribution, "entry_values"):
        return attribution.entry_values
    if hasattr(attribution, "exit_values"):
        return attribution.exit_values
    if hasattr(attribution, "add_on_values"):
        return attribution.add_on_values
    return {}


def _attribution_categories(attribution: Any) -> Mapping[str, str]:
    if hasattr(attribution, "entry_categories"):
        return attribution.entry_categories
    if hasattr(attribution, "exit_categories"):
        return attribution.exit_categories
    if hasattr(attribution, "add_on_categories"):
        return attribution.add_on_categories
    return {}


def _is_add_on_intent(intent: TradeIntent) -> bool:
    return intent.intent_type == TradeIntentType.ADD_ON


def _is_rejected_execution(event: ExecutionAuditEvent) -> bool:
    return event.event_type == "rejected" or event.status.lower() == "rejected"


def _execution_rejection_reason(event: ExecutionAuditEvent) -> str:
    return event.blocked_by or event.reason_code or event.status


def _realized_pnl_by_symbol(events: Sequence[ExecutionAuditEvent]) -> dict[str, float]:
    lots_by_symbol: dict[str, deque[dict[str, float]]] = defaultdict(deque)
    pnl_by_symbol: dict[str, float] = defaultdict(float)
    seen_completed_execution_by_symbol: set[str] = set()

    for event in sorted(events, key=lambda value: (value.executed_date or value.event_date, value.symbol, value.side)):
        if event.event_type != "completed" or event.executed_quantity is None or event.gross_value is None:
            continue

        symbol = event.symbol
        seen_completed_execution_by_symbol.add(symbol)
        quantity = abs(float(event.executed_quantity))
        if quantity <= 0:
            continue

        gross_value = abs(float(event.gross_value))
        commission = abs(float(event.commission or 0.0))

        if event.side == "buy":
            lots_by_symbol[symbol].append(
                {
                    "quantity": quantity,
                    "gross_value": gross_value,
                    "commission": commission,
                }
            )
            continue

        if event.side != "sell":
            continue

        remaining_quantity = quantity
        while remaining_quantity > 0 and lots_by_symbol[symbol]:
            lot = lots_by_symbol[symbol][0]
            matched_quantity = min(remaining_quantity, lot["quantity"])
            buy_ratio = matched_quantity / lot["quantity"]
            sell_ratio = matched_quantity / quantity

            buy_gross = lot["gross_value"] * buy_ratio
            buy_commission = lot["commission"] * buy_ratio
            sell_gross = gross_value * sell_ratio
            sell_commission = commission * sell_ratio

            pnl_by_symbol[symbol] += sell_gross - sell_commission - buy_gross - buy_commission

            lot["quantity"] -= matched_quantity
            lot["gross_value"] -= buy_gross
            lot["commission"] -= buy_commission
            remaining_quantity -= matched_quantity
            if lot["quantity"] <= 1e-9:
                lots_by_symbol[symbol].popleft()

    return {
        symbol: pnl_by_symbol.get(symbol, 0.0)
        for symbol in seen_completed_execution_by_symbol
    }


def _reason_counts(counter: Counter[str]) -> tuple[ReasonCount, ...]:
    return tuple(
        ReasonCount(reason=reason, count=count)
        for reason, count in sorted(counter.items())
    )


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _is_scalar_json_value(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))
