"""Execution audit summaries for standard reports."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from attbacktrader.engines.ledger import ExecutionAuditEvent
from attbacktrader.reports.models import ExecutionCostSummary, ExecutionRejectionSummary


def summarize_execution_costs(events: Sequence[ExecutionAuditEvent]) -> ExecutionCostSummary:
    submitted_count = _count_events(events, "submitted")
    accepted_count = _count_events(events, "accepted")
    completed_events = tuple(event for event in events if event.event_type == "completed")
    failed_count = _count_events(events, "failed")
    rejected_events = tuple(event for event in events if event.event_type == "rejected")

    completed_count = len(completed_events)
    rejected_count = len(rejected_events)
    order_count = submitted_count + rejected_count

    total_commission = sum(event.commission or 0.0 for event in completed_events)
    slippage_costs = [
        (event.slippage or 0.0) * (event.executed_quantity or 0.0)
        for event in completed_events
    ]
    total_slippage_cost = sum(slippage_costs)

    return ExecutionCostSummary(
        order_count=order_count,
        submitted_count=submitted_count,
        accepted_count=accepted_count,
        completed_count=completed_count,
        failed_count=failed_count,
        rejected_count=rejected_count,
        fill_rate=(completed_count / submitted_count) if submitted_count else None,
        rejection_rate=(rejected_count / order_count) if order_count else None,
        total_commission=total_commission,
        average_commission=(total_commission / completed_count) if completed_count else None,
        total_slippage_cost=total_slippage_cost,
        average_slippage_cost=(total_slippage_cost / completed_count) if completed_count else None,
        rejections=_rejection_summaries(rejected_events),
    )


def _count_events(events: Sequence[ExecutionAuditEvent], event_type: str) -> int:
    return sum(1 for event in events if event.event_type == event_type)


def _rejection_summaries(events: Sequence[ExecutionAuditEvent]) -> tuple[ExecutionRejectionSummary, ...]:
    counts = Counter(event.blocked_by or "UNKNOWN" for event in events)
    return tuple(
        ExecutionRejectionSummary(blocked_by=blocked_by, count=count)
        for blocked_by, count in sorted(counts.items())
    )
