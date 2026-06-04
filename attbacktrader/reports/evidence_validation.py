"""Validate that persisted run evidence is internally consistent."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Sequence

from attbacktrader.data.snapshots import read_daily_bars_parquet
from attbacktrader.engines.ledger import ExecutionAuditEvent
from attbacktrader.reports.diagnostics import ResultDiagnostics, build_result_diagnostics
from attbacktrader.reports.lifecycle import TradeLifecycleReport, build_trade_lifecycle_report
from attbacktrader.reports.trade_review import TradeReviewReport, build_trade_review_report
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.templates import ClosedTrade


IssueSeverity = Literal["error", "warning"]

_ASHARE_BLOCK_REASONS = {
    "SUSPENDED",
    "LIMIT_UP_BUY_BLOCKED",
    "LIMIT_DOWN_SELL_BLOCKED",
    "BOARD_LOT_TOO_SMALL",
    "CASH_NOT_ENOUGH",
    "T_PLUS_ONE_SELL_BLOCKED",
}
_BLOCK_REASON_EXPECTED_SIDE = {
    "LIMIT_UP_BUY_BLOCKED": "buy",
    "CASH_NOT_ENOUGH": "buy",
    "LIMIT_DOWN_SELL_BLOCKED": "sell",
    "T_PLUS_ONE_SELL_BLOCKED": "sell",
}


@dataclass(frozen=True)
class EvidenceValidationIssue:
    severity: IssueSeverity
    code: str
    artifact: str
    message: str
    symbol: str | None = None
    trade_date: date | None = None
    expected: Any = None
    actual: Any = None


@dataclass(frozen=True)
class EvidenceValidationCounts:
    symbol_count: int
    closed_trade_count: int
    open_position_count: int
    signal_intent_count: int
    sizing_decision_count: int
    execution_event_count: int
    completed_order_count: int
    rejected_order_count: int
    equity_point_count: int
    position_snapshot_count: int
    diagnostic_symbol_count: int
    add_on_signal_count: int
    post_exit_observation_count: int
    post_exit_threshold_summary_count: int
    trade_review_trade_count: int
    trade_review_opportunity_count: int
    trade_review_opportunity_cost_summary_count: int
    trade_review_add_on_entry_count: int


@dataclass(frozen=True)
class EvidenceValidationReport:
    status: Literal["ok", "failed"]
    counts: EvidenceValidationCounts
    error_count: int
    warning_count: int
    issues: tuple[EvidenceValidationIssue, ...]


def build_evidence_validation(
    result: Any,
    *,
    tolerance: float = 1e-6,
) -> EvidenceValidationReport:
    """Build a consistency report from an executed run result.

    This validation consumes existing evidence only. It must not fetch data,
    rerun strategy methods, or recalculate indicators.
    """

    diagnostics = build_result_diagnostics(
        symbols=result.symbols,
        closed_trades=result.closed_trades,
        signal_audit=result.signal_audit,
        execution_audit=result.execution_audit,
        open_positions=result.open_positions,
    )
    post_exit_analysis = getattr(result, "post_exit_analysis", None)
    trade_lifecycle = build_trade_lifecycle_report(
        closed_trades=result.closed_trades,
        signal_audit=result.signal_audit,
        execution_audit=result.execution_audit,
    )
    trade_review = _build_trade_review_for_validation(
        result,
        trade_lifecycle=trade_lifecycle,
        post_exit_analysis=post_exit_analysis,
    )
    issues: list[EvidenceValidationIssue] = []

    _validate_signal_sizing(result.signal_audit, issues)
    _validate_trades_match_signals(result.closed_trades, result.signal_audit, issues)
    _validate_execution_matches_signals(result.execution_audit, result.signal_audit, result.closed_trades, issues)
    _validate_diagnostics(result, diagnostics, issues)
    _validate_post_exit(result, post_exit_analysis, issues)
    _validate_trade_review(result, trade_lifecycle, trade_review, issues)
    _validate_equity_and_report(result, issues, tolerance=tolerance)

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    return EvidenceValidationReport(
        status="ok" if error_count == 0 else "failed",
        counts=_counts(result, diagnostics, post_exit_analysis, trade_review),
        error_count=error_count,
        warning_count=warning_count,
        issues=tuple(issues),
    )


def _counts(
    result: Any,
    diagnostics: ResultDiagnostics,
    post_exit_analysis: Any | None,
    trade_review: TradeReviewReport | None,
) -> EvidenceValidationCounts:
    execution_events = tuple(result.execution_audit)
    return EvidenceValidationCounts(
        symbol_count=len(result.symbols),
        closed_trade_count=len(result.closed_trades),
        open_position_count=len(result.open_positions),
        signal_intent_count=len(result.signal_audit),
        sizing_decision_count=sum(1 for intent in result.signal_audit if _sizing_values(intent) is not None),
        execution_event_count=len(execution_events),
        completed_order_count=sum(1 for event in execution_events if event.event_type == "completed"),
        rejected_order_count=sum(1 for event in execution_events if _is_rejected_execution(event)),
        equity_point_count=len(result.equity_curve),
        position_snapshot_count=len(result.position_snapshots),
        diagnostic_symbol_count=len(diagnostics.symbols),
        add_on_signal_count=sum(1 for intent in result.signal_audit if intent.intent_type == TradeIntentType.ADD_ON),
        post_exit_observation_count=len(post_exit_analysis.observations) if post_exit_analysis is not None else 0,
        post_exit_threshold_summary_count=(
            len(getattr(post_exit_analysis, "threshold_summaries", ())) if post_exit_analysis is not None else 0
        ),
        trade_review_trade_count=trade_review.trade_count if trade_review is not None else 0,
        trade_review_opportunity_count=trade_review.opportunity_count if trade_review is not None else 0,
        trade_review_opportunity_cost_summary_count=(
            len(trade_review.opportunity_cost_summaries) if trade_review is not None else 0
        ),
        trade_review_add_on_entry_count=trade_review.add_on_entry_count if trade_review is not None else 0,
    )


def _build_trade_review_for_validation(
    result: Any,
    *,
    trade_lifecycle: TradeLifecycleReport,
    post_exit_analysis: Any | None,
) -> TradeReviewReport | None:
    if post_exit_analysis is None:
        return None
    return build_trade_review_report(
        closed_trades=result.closed_trades,
        signal_audit=result.signal_audit,
        execution_audit=result.execution_audit,
        post_exit_analysis=post_exit_analysis,
        trade_lifecycle=trade_lifecycle,
        bars_by_symbol=_bars_by_symbol_from_result(result),
    )


def _bars_by_symbol_from_result(result: Any) -> dict[str, tuple[Any, ...]]:
    bars_by_symbol: dict[str, tuple[Any, ...]] = {}
    for symbol_result in getattr(result, "symbol_results", ()):
        snapshot_path = getattr(symbol_result, "snapshot_path", None)
        symbol = getattr(symbol_result, "symbol", None)
        if snapshot_path is None or symbol is None or not snapshot_path.exists():
            continue
        bars_by_symbol[str(symbol)] = read_daily_bars_parquet(snapshot_path)
    return bars_by_symbol


def _validate_signal_sizing(
    signal_audit: Sequence[TradeIntent],
    issues: list[EvidenceValidationIssue],
) -> None:
    for intent in signal_audit:
        if intent.intent_type not in {TradeIntentType.ENTER, TradeIntentType.ADD_ON}:
            continue

        sizing = _sizing_values(intent)
        if sizing is None:
            issues.append(
                _issue(
                    "error",
                    "MISSING_SIZING",
                    "signal_audit.json",
                    "entry/add-on intent must carry sizing evidence",
                    symbol=intent.symbol,
                    trade_date=intent.trade_date,
                    expected="signal_values.sizing",
                    actual=None,
                )
            )
            continue

        requested_quantity = sizing.get("requested_quantity")
        if not _is_number(requested_quantity) or float(requested_quantity) < 0:
            issues.append(
                _issue(
                    "error",
                    "INVALID_REQUESTED_QUANTITY",
                    "sizing_audit.json",
                    "sizing requested_quantity must be a non-negative number",
                    symbol=intent.symbol,
                    trade_date=intent.trade_date,
                    expected=">= 0",
                    actual=requested_quantity,
                )
            )

        executable_quantity = sizing.get("business_executable_quantity")
        if _is_number(executable_quantity) and _is_number(requested_quantity):
            if float(executable_quantity) > float(requested_quantity):
                issues.append(
                    _issue(
                        "error",
                        "EXECUTABLE_EXCEEDS_REQUESTED",
                        "sizing_audit.json",
                        "business executable quantity cannot exceed requested quantity",
                        symbol=intent.symbol,
                        trade_date=intent.trade_date,
                        expected=requested_quantity,
                        actual=executable_quantity,
                    )
                )


def _validate_trades_match_signals(
    closed_trades: Sequence[ClosedTrade],
    signal_audit: Sequence[TradeIntent],
    issues: list[EvidenceValidationIssue],
) -> None:
    entry_signals_by_key: dict[tuple[str, date], deque[TradeIntent]] = {}
    exit_signals_by_key: dict[tuple[str, date, str], deque[TradeIntent]] = {}

    for intent in sorted(signal_audit, key=lambda value: (value.trade_date, value.symbol, value.reason_code)):
        if _intent_blocked(intent):
            continue
        if intent.intent_type == TradeIntentType.ENTER:
            entry_signals_by_key.setdefault((intent.symbol, intent.trade_date), deque()).append(intent)
        elif intent.intent_type in {TradeIntentType.EXIT_PROFIT, TradeIntentType.EXIT_LOSS}:
            exit_signals_by_key.setdefault((intent.symbol, intent.trade_date, intent.reason_code), deque()).append(intent)

    for trade in sorted(closed_trades, key=lambda value: (value.entry_date, value.exit_date, value.symbol)):
        entry_key = (trade.symbol, trade.entry_date)
        entry_signals = entry_signals_by_key.get(entry_key)
        if entry_signals:
            entry_signals.popleft()
        else:
            issues.append(
                _issue(
                    "error",
                    "TRADE_WITHOUT_ENTRY_SIGNAL",
                    "trades.json",
                    "closed trade must match a successful entry intent on entry_date",
                    symbol=trade.symbol,
                    trade_date=trade.entry_date,
                    expected="ENTER intent",
                    actual=None,
                )
            )

        exit_key = (trade.symbol, trade.exit_date, trade.exit_reason)
        exit_signals = exit_signals_by_key.get(exit_key)
        if exit_signals:
            exit_signals.popleft()
        else:
            issues.append(
                _issue(
                    "error",
                    "TRADE_WITHOUT_EXIT_SIGNAL",
                    "trades.json",
                    "closed trade must match a successful exit intent on exit_date",
                    symbol=trade.symbol,
                    trade_date=trade.exit_date,
                    expected=trade.exit_reason,
                    actual=None,
                )
            )


def _validate_execution_matches_signals(
    execution_audit: Sequence[ExecutionAuditEvent],
    signal_audit: Sequence[TradeIntent],
    closed_trades: Sequence[ClosedTrade],
    issues: list[EvidenceValidationIssue],
) -> None:
    if not execution_audit:
        _validate_blocked_intents_have_rejections(signal_audit, execution_audit, issues)
        return

    signal_types_by_key: dict[tuple[str, date, str], set[TradeIntentType]] = {}
    signals_by_key: dict[tuple[str, date, str], list[TradeIntent]] = {}
    for intent in signal_audit:
        key = (intent.symbol, intent.trade_date, intent.reason_code)
        signal_types_by_key.setdefault(key, set()).add(intent.intent_type)
        signals_by_key.setdefault(key, []).append(intent)

    closed_trade_exit_counts = Counter((trade.symbol, trade.exit_date, trade.exit_reason) for trade in closed_trades)
    for event in execution_audit:
        signal_key = (event.symbol, event.signal_date, event.reason_code)
        signal_types = signal_types_by_key.get(signal_key, set())
        if not signal_types:
            issues.append(
                _issue(
                    "error",
                    "EXECUTION_WITHOUT_SIGNAL",
                    "execution_audit.json",
                    "execution event must reference an emitted signal intent",
                    symbol=event.symbol,
                    trade_date=event.signal_date,
                    expected="signal_audit match",
                    actual=event.reason_code,
                )
            )
        elif not _side_matches_signal_types(event.side, signal_types):
            issues.append(
                _issue(
                    "error",
                    "EXECUTION_SIDE_SIGNAL_MISMATCH",
                    "execution_audit.json",
                    "execution side must match the referenced signal intent type",
                    symbol=event.symbol,
                    trade_date=event.signal_date,
                    expected=sorted(intent_type.value for intent_type in signal_types),
                    actual=event.side,
                )
            )

        if event.event_type == "completed":
            if event.executed_quantity is None or event.executed_price is None:
                issues.append(
                    _issue(
                        "error",
                        "COMPLETED_EXECUTION_MISSING_FILL",
                        "execution_audit.json",
                        "completed execution event must include executed quantity and price",
                        symbol=event.symbol,
                        trade_date=event.executed_date or event.event_date,
                        expected="executed_quantity and executed_price",
                        actual=None,
                    )
                )

            if event.side == "sell":
                trade_key = (event.symbol, event.executed_date or event.event_date, event.reason_code)
                if closed_trade_exit_counts[trade_key] > 0:
                    closed_trade_exit_counts[trade_key] -= 1
                else:
                    issues.append(
                        _issue(
                            "error",
                            "SELL_EXECUTION_WITHOUT_CLOSED_TRADE",
                            "execution_audit.json",
                            "completed sell execution must close a trade with the same reason code",
                            symbol=event.symbol,
                            trade_date=event.executed_date or event.event_date,
                            expected="closed trade",
                            actual=event.reason_code,
                        )
                    )

        if _is_rejected_execution(event) and not event.blocked_by:
            issues.append(
                _issue(
                    "warning",
                    "REJECTED_EXECUTION_WITHOUT_REASON",
                    "execution_audit.json",
                    "rejected execution should include blocked_by",
                    symbol=event.symbol,
                    trade_date=event.event_date,
                    expected="blocked_by",
                    actual=None,
                )
            )
        if _is_rejected_execution(event):
            _validate_rejected_execution_reason(
                event,
                signals_by_key.get(signal_key, ()),
                issues,
            )

    _validate_blocked_intents_have_rejections(signal_audit, execution_audit, issues)


def _validate_rejected_execution_reason(
    event: ExecutionAuditEvent,
    matching_intents: Sequence[TradeIntent],
    issues: list[EvidenceValidationIssue],
) -> None:
    blocked_reasons = _blocked_reason_set(event.blocked_by)
    if not blocked_reasons:
        return

    if event.executable_quantity != 0:
        issues.append(
            _issue(
                "error",
                "REJECTED_EXECUTION_HAS_EXECUTABLE_QUANTITY",
                "execution_audit.json",
                "rejected execution must have zero executable quantity",
                symbol=event.symbol,
                trade_date=event.event_date,
                expected=0,
                actual=event.executable_quantity,
            )
        )

    for reason in sorted(blocked_reasons & _ASHARE_BLOCK_REASONS):
        expected_side = _BLOCK_REASON_EXPECTED_SIDE.get(reason)
        if expected_side is not None and event.side != expected_side:
            issues.append(
                _issue(
                    "error",
                    "REJECTION_REASON_SIDE_MISMATCH",
                    "execution_audit.json",
                    "A-share rejection reason must match execution side",
                    symbol=event.symbol,
                    trade_date=event.event_date,
                    expected={reason: expected_side},
                    actual=event.side,
                )
            )

    if not matching_intents:
        return

    signal_block_reasons = set()
    for intent in matching_intents:
        signal_block_reasons.update(_blocked_reason_set(intent.blocked_by))
        sizing = _sizing_values(intent)
        if sizing is not None:
            signal_block_reasons.update(_blocked_reason_set(sizing.get("blocked_by")))

    if blocked_reasons & _ASHARE_BLOCK_REASONS and not blocked_reasons <= signal_block_reasons:
        issues.append(
            _issue(
                "error",
                "REJECTED_EXECUTION_SIGNAL_BLOCK_MISMATCH",
                "execution_audit.json",
                "rejected execution blocked_by must match the referenced blocked signal intent",
                symbol=event.symbol,
                trade_date=event.event_date,
                expected=sorted(blocked_reasons),
                actual=sorted(signal_block_reasons),
            )
        )


def _validate_blocked_intents_have_rejections(
    signal_audit: Sequence[TradeIntent],
    execution_audit: Sequence[ExecutionAuditEvent],
    issues: list[EvidenceValidationIssue],
) -> None:
    rejected_reasons_by_key: dict[tuple[str, date, str, str], set[str]] = {}
    for event in execution_audit:
        if not _is_rejected_execution(event):
            continue
        key = (event.symbol, event.signal_date, event.reason_code, event.side)
        rejected_reasons_by_key.setdefault(key, set()).update(_blocked_reason_set(event.blocked_by))

    for intent in signal_audit:
        side = _side_for_intent(intent.intent_type)
        if side is None:
            continue
        blocked_reasons = _blocked_reason_set(intent.blocked_by) & _ASHARE_BLOCK_REASONS
        if not blocked_reasons:
            continue
        key = (intent.symbol, intent.trade_date, intent.reason_code, side)
        rejected_reasons = rejected_reasons_by_key.get(key, set())
        if blocked_reasons <= rejected_reasons:
            continue
        issues.append(
            _issue(
                "error",
                "BLOCKED_INTENT_WITHOUT_REJECTED_EXECUTION",
                "signal_audit.json",
                "A-share blocked intent must have a matching rejected execution event",
                symbol=intent.symbol,
                trade_date=intent.trade_date,
                expected=sorted(blocked_reasons),
                actual=sorted(rejected_reasons),
            )
        )


def _validate_diagnostics(
    result: Any,
    diagnostics: ResultDiagnostics,
    issues: list[EvidenceValidationIssue],
) -> None:
    trades_by_symbol = Counter(trade.symbol for trade in result.closed_trades)
    add_on_by_symbol = Counter(intent.symbol for intent in result.signal_audit if intent.intent_type == TradeIntentType.ADD_ON)
    diagnostics_by_symbol = {diagnostic.symbol: diagnostic for diagnostic in diagnostics.symbols}

    for symbol in sorted(set(result.symbols) | set(trades_by_symbol) | set(add_on_by_symbol)):
        diagnostic = diagnostics_by_symbol.get(symbol)
        if diagnostic is None:
            issues.append(
                _issue(
                    "error",
                    "MISSING_SYMBOL_DIAGNOSTIC",
                    "result_diagnostics.json",
                    "every symbol with evidence must have a diagnostic row",
                    symbol=symbol,
                    expected="symbol diagnostic",
                    actual=None,
                )
            )
            continue

        _expect_equal(
            issues,
            artifact="result_diagnostics.json",
            code="DIAGNOSTIC_TRADE_COUNT_MISMATCH",
            message="symbol closed_trade_count must equal trades.json count",
            symbol=symbol,
            expected=trades_by_symbol[symbol],
            actual=diagnostic.closed_trade_count,
        )
        _expect_equal(
            issues,
            artifact="result_diagnostics.json",
            code="DIAGNOSTIC_ADD_ON_COUNT_MISMATCH",
            message="symbol add_on_signal_count must equal signal_audit ADD_ON count",
            symbol=symbol,
            expected=add_on_by_symbol[symbol],
            actual=diagnostic.add_on_signal_count,
        )

    _expect_equal(
        issues,
        artifact="result_diagnostics.json",
        code="PORTFOLIO_ADD_ON_COUNT_MISMATCH",
        message="portfolio add-on count must equal signal_audit ADD_ON count",
        expected=sum(add_on_by_symbol.values()),
        actual=diagnostics.portfolio_add_on_signal_count,
    )
    _expect_equal(
        issues,
        artifact="result_diagnostics.json",
        code="PORTFOLIO_WIN_SAMPLE_COUNT_MISMATCH",
        message="portfolio winning entry attribution sample count must equal winning closed trades",
        expected=sum(1 for trade in result.closed_trades if trade.return_pct > 0),
        actual=diagnostics.portfolio_winning_entry_summary.sample_count,
    )
    _expect_equal(
        issues,
        artifact="result_diagnostics.json",
        code="PORTFOLIO_LOSS_SAMPLE_COUNT_MISMATCH",
        message="portfolio losing entry attribution sample count must equal losing closed trades",
        expected=sum(1 for trade in result.closed_trades if trade.return_pct < 0),
        actual=diagnostics.portfolio_losing_entry_summary.sample_count,
    )


def _validate_post_exit(
    result: Any,
    post_exit_analysis: Any | None,
    issues: list[EvidenceValidationIssue],
) -> None:
    if post_exit_analysis is None:
        if result.closed_trades:
            issues.append(
                _issue(
                    "warning",
                    "MISSING_POST_EXIT_ANALYSIS",
                    "post_exit_analysis.json",
                    "completed runs should include post-exit analysis",
                    expected="post_exit_analysis",
                    actual=None,
                )
            )
        return

    _expect_equal(
        issues,
        artifact="post_exit_analysis.json",
        code="POST_EXIT_TRADE_COUNT_MISMATCH",
        message="post-exit trade_count must equal closed trade count",
        expected=len(result.closed_trades),
        actual=post_exit_analysis.trade_count,
    )
    _expect_equal(
        issues,
        artifact="post_exit_analysis.json",
        code="POST_EXIT_OBSERVATION_COUNT_MISMATCH",
        message="post-exit observations must include one row per closed trade",
        expected=len(result.closed_trades),
        actual=len(post_exit_analysis.observations),
    )

    configured_thresholds = tuple(getattr(post_exit_analysis, "rebound_thresholds", ()))
    threshold_summaries = tuple(getattr(post_exit_analysis, "threshold_summaries", ()))
    if configured_thresholds and not threshold_summaries:
        issues.append(
            _issue(
                "error",
                "POST_EXIT_THRESHOLD_SUMMARIES_MISSING",
                "post_exit_analysis.json",
                "configured rebound thresholds must have threshold summaries",
                expected=configured_thresholds,
                actual=0,
            )
        )

    threshold_set = set(configured_thresholds)
    for summary in threshold_summaries:
        if summary.threshold not in threshold_set:
            issues.append(
                _issue(
                    "error",
                    "POST_EXIT_THRESHOLD_SUMMARY_UNKNOWN_THRESHOLD",
                    "post_exit_analysis.json",
                    "threshold summary must reference a configured rebound threshold",
                    expected=sorted(threshold_set),
                    actual=summary.threshold,
                )
            )
        if summary.observed_count > summary.sample_count or summary.rebound_count > summary.observed_count:
            issues.append(
                _issue(
                    "error",
                    "POST_EXIT_THRESHOLD_SUMMARY_COUNT_INVALID",
                    "post_exit_analysis.json",
                    "threshold summary counts must be internally consistent",
                    expected="rebound_count <= observed_count <= sample_count",
                    actual={
                        "sample_count": summary.sample_count,
                        "observed_count": summary.observed_count,
                        "rebound_count": summary.rebound_count,
                    },
                )
            )

    for observation in post_exit_analysis.observations:
        if observation.observed_day_count != 0:
            continue
        if (
            observation.primary_window_close_return_pct is not None
            or observation.max_high_return_pct is not None
            or observation.min_low_return_pct is not None
            or observation.sold_too_early is not None
        ):
            issues.append(
                _issue(
                    "error",
                    "POST_EXIT_MISSING_FUTURE_RETURNS_DEFAULTED",
                    "post_exit_analysis.json",
                    "post-exit observations without future bars must keep return fields missing",
                    symbol=observation.symbol,
                    trade_date=observation.exit_date,
                    expected=None,
                    actual={
                        "primary_window_close_return_pct": observation.primary_window_close_return_pct,
                        "max_high_return_pct": observation.max_high_return_pct,
                        "min_low_return_pct": observation.min_low_return_pct,
                        "sold_too_early": observation.sold_too_early,
                    },
                )
            )


def _validate_trade_review(
    result: Any,
    trade_lifecycle: TradeLifecycleReport,
    trade_review: TradeReviewReport | None,
    issues: list[EvidenceValidationIssue],
) -> None:
    if trade_review is None:
        if result.closed_trades:
            issues.append(
                _issue(
                    "warning",
                    "MISSING_TRADE_REVIEW",
                    "trade_review.json",
                    "completed runs should include trade review evidence",
                    expected="trade_review",
                    actual=None,
                )
            )
        return

    _expect_equal(
        issues,
        artifact="trade_review.json",
        code="TRADE_REVIEW_TRADE_COUNT_MISMATCH",
        message="trade review trade_count must equal closed trade count",
        expected=len(result.closed_trades),
        actual=trade_review.trade_count,
    )
    _expect_equal(
        issues,
        artifact="trade_review.json",
        code="TRADE_REVIEW_OPPORTUNITY_COUNT_MISMATCH",
        message="trade review opportunity_count must equal opportunity sample count",
        expected=len(trade_review.opportunities),
        actual=trade_review.opportunity_count,
    )

    expected_add_on_entry_count = sum(
        1
        for lifecycle in trade_lifecycle.lifecycles
        for event in lifecycle.events
        if event.event_type == "add_on"
    )
    _expect_equal(
        issues,
        artifact="trade_review.json",
        code="TRADE_REVIEW_ADD_ON_ENTRY_COUNT_MISMATCH",
        message="trade review add-on entry count must equal successful add-on lifecycle events",
        expected=expected_add_on_entry_count,
        actual=trade_review.add_on_entry_count,
    )
    _expect_equal(
        issues,
        artifact="trade_review.json",
        code="TRADE_REVIEW_ADD_ON_SAMPLE_COUNT_MISMATCH",
        message="trade review add-on samples must equal add-on entry count",
        expected=trade_review.add_on_entry_count,
        actual=len(trade_review.add_on_entry_points),
    )

    _expect_equal(
        issues,
        artifact="trade_review.json",
        code="TRADE_REVIEW_OPPORTUNITY_SUMMARY_COUNT_MISMATCH",
        message="opportunity cost summary sample counts must cover all opportunity samples",
        expected=trade_review.opportunity_count,
        actual=sum(summary.sample_count for summary in trade_review.opportunity_cost_summaries),
    )
    _expect_equal(
        issues,
        artifact="trade_review.json",
        code="TRADE_REVIEW_ADD_ON_SUMMARY_COUNT_MISMATCH",
        message="add-on entry summary sample counts must cover all add-on entry samples",
        expected=trade_review.add_on_entry_count,
        actual=sum(summary.sample_count for summary in trade_review.add_on_entry_summaries),
    )

    for sample in trade_review.opportunities:
        _validate_follow_up_shape(
            sample.follow_up,
            issues,
            artifact="trade_review.json",
            code="TRADE_REVIEW_OPPORTUNITY_FOLLOW_UP_DEFAULTED",
            message="opportunity follow-up without future bars must keep return fields missing",
            symbol=sample.symbol,
            trade_date=sample.trade_date,
        )
    for sample in trade_review.add_on_entry_points:
        _validate_follow_up_shape(
            sample.follow_up,
            issues,
            artifact="trade_review.json",
            code="TRADE_REVIEW_ADD_ON_FOLLOW_UP_DEFAULTED",
            message="add-on follow-up without future bars must keep return fields missing",
            symbol=sample.symbol,
            trade_date=sample.add_on_date,
        )


def _validate_follow_up_shape(
    follow_up: Any,
    issues: list[EvidenceValidationIssue],
    *,
    artifact: str,
    code: str,
    message: str,
    symbol: str | None,
    trade_date: date | None,
) -> None:
    if follow_up is None or follow_up.observed_day_count != 0:
        return
    if (
        follow_up.window_close_return_pct is not None
        or follow_up.max_high_return_pct is not None
        or follow_up.min_low_return_pct is not None
    ):
        issues.append(
            _issue(
                "error",
                code,
                artifact,
                message,
                symbol=symbol,
                trade_date=trade_date,
                expected=None,
                actual={
                    "window_close_return_pct": follow_up.window_close_return_pct,
                    "max_high_return_pct": follow_up.max_high_return_pct,
                    "min_low_return_pct": follow_up.min_low_return_pct,
                },
            )
        )


def _validate_equity_and_report(
    result: Any,
    issues: list[EvidenceValidationIssue],
    *,
    tolerance: float,
) -> None:
    if result.equity_curve:
        last_equity = result.equity_curve[-1]
        _expect_close(
            issues,
            artifact="equity_curve.json",
            code="FINAL_VALUE_MISMATCH",
            message="last equity point total_value must equal result.final_value",
            expected=result.final_value,
            actual=last_equity.total_value,
            tolerance=tolerance,
        )
        _expect_close(
            issues,
            artifact="equity_curve.json",
            code="FINAL_CASH_MISMATCH",
            message="last equity point cash must equal result.final_cash",
            expected=result.final_cash,
            actual=last_equity.cash,
            tolerance=tolerance,
        )
        latest_snapshots = tuple(
            snapshot
            for snapshot in result.position_snapshots
            if snapshot.trade_date == last_equity.trade_date
        )
        _expect_close(
            issues,
            artifact="positions.json",
            code="POSITION_VALUE_MISMATCH",
            message="latest position snapshots must sum to the last equity position_value",
            expected=last_equity.position_value,
            actual=sum(abs(snapshot.market_value) for snapshot in latest_snapshots),
            tolerance=tolerance,
        )
        _expect_equal(
            issues,
            artifact="positions.json",
            code="OPEN_POSITION_COUNT_MISMATCH",
            message="latest position snapshot count must equal open position count",
            expected=len(result.open_positions),
            actual=len(latest_snapshots),
        )

    report = result.report
    if result.final_value is not None:
        _expect_close(
            issues,
            artifact="report.json",
            code="REPORT_FINAL_EQUITY_MISMATCH",
            message="report final_equity must equal result.final_value",
            expected=result.final_value,
            actual=report.returns.final_equity,
            tolerance=tolerance,
        )
    _expect_equal(
        issues,
        artifact="report.json",
        code="REPORT_TRADE_COUNT_MISMATCH",
        message="report trade_count must equal trades.json closed trade count",
        expected=len(result.closed_trades),
        actual=report.trade_quality.trade_count,
    )


def _side_matches_signal_types(side: str, signal_types: set[TradeIntentType]) -> bool:
    if side == "buy":
        return bool(signal_types & {TradeIntentType.ENTER, TradeIntentType.ADD_ON})
    if side == "sell":
        return bool(signal_types & {TradeIntentType.EXIT_PROFIT, TradeIntentType.EXIT_LOSS})
    return False


def _side_for_intent(intent_type: TradeIntentType) -> str | None:
    if intent_type in {TradeIntentType.ENTER, TradeIntentType.ADD_ON}:
        return "buy"
    if intent_type in {TradeIntentType.EXIT_PROFIT, TradeIntentType.EXIT_LOSS}:
        return "sell"
    return None


def _sizing_values(intent: TradeIntent) -> Mapping[str, Any] | None:
    sizing = intent.signal_values.get("sizing")
    if isinstance(sizing, Mapping):
        return sizing
    return None


def _intent_blocked(intent: TradeIntent) -> bool:
    sizing = _sizing_values(intent)
    return bool(intent.blocked_by or (sizing is not None and sizing.get("blocked_by")))


def _is_rejected_execution(event: ExecutionAuditEvent) -> bool:
    return event.event_type == "rejected" or event.status.lower() == "rejected"


def _blocked_reason_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    return {str(value)}


def _expect_equal(
    issues: list[EvidenceValidationIssue],
    *,
    artifact: str,
    code: str,
    message: str,
    expected: Any,
    actual: Any,
    symbol: str | None = None,
    trade_date: date | None = None,
) -> None:
    if expected == actual:
        return
    issues.append(
        _issue(
            "error",
            code,
            artifact,
            message,
            symbol=symbol,
            trade_date=trade_date,
            expected=expected,
            actual=actual,
        )
    )


def _expect_close(
    issues: list[EvidenceValidationIssue],
    *,
    artifact: str,
    code: str,
    message: str,
    expected: float | None,
    actual: float | None,
    tolerance: float,
) -> None:
    if expected is None and actual is None:
        return
    if expected is None or actual is None or abs(float(expected) - float(actual)) > tolerance:
        issues.append(
            _issue(
                "error",
                code,
                artifact,
                message,
                expected=expected,
                actual=actual,
            )
        )


def _issue(
    severity: IssueSeverity,
    code: str,
    artifact: str,
    message: str,
    *,
    symbol: str | None = None,
    trade_date: date | None = None,
    expected: Any = None,
    actual: Any = None,
) -> EvidenceValidationIssue:
    return EvidenceValidationIssue(
        severity=severity,
        code=code,
        artifact=artifact,
        message=message,
        symbol=symbol,
        trade_date=trade_date,
        expected=expected,
        actual=actual,
    )


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
