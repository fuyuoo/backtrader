from datetime import date

import pytest

from attbacktrader.analysis import summarize_execution_costs
from attbacktrader.engines import ExecutionAuditEvent


def test_summarize_execution_costs_counts_orders_costs_and_rejections() -> None:
    events = (
        ExecutionAuditEvent(
            event_date=date(2024, 1, 2),
            signal_date=date(2024, 1, 2),
            symbol="000001.SZ",
            side="buy",
            event_type="submitted",
            status="submitted",
            reason_code="KDJ_J_BELOW_13",
            requested_quantity=100,
            executable_quantity=100,
            signal_price=10.0,
            order_ref=1,
        ),
        ExecutionAuditEvent(
            event_date=date(2024, 1, 2),
            signal_date=date(2024, 1, 2),
            symbol="000001.SZ",
            side="buy",
            event_type="accepted",
            status="Accepted",
            reason_code="KDJ_J_BELOW_13",
            requested_quantity=100,
            executable_quantity=100,
            signal_price=10.0,
            order_ref=1,
        ),
        ExecutionAuditEvent(
            event_date=date(2024, 1, 2),
            signal_date=date(2024, 1, 2),
            symbol="000001.SZ",
            side="buy",
            event_type="completed",
            status="Completed",
            reason_code="KDJ_J_BELOW_13",
            requested_quantity=100,
            executable_quantity=100,
            signal_price=10.0,
            order_ref=1,
            executed_date=date(2024, 1, 2),
            executed_quantity=100,
            executed_price=10.1,
            commission=1.2,
            slippage=0.1,
        ),
        ExecutionAuditEvent(
            event_date=date(2024, 1, 3),
            signal_date=date(2024, 1, 3),
            symbol="000001.SZ",
            side="buy",
            event_type="rejected",
            status="rejected",
            reason_code="KDJ_J_BELOW_13",
            requested_quantity=100,
            executable_quantity=0,
            signal_price=10.0,
            blocked_by="LIMIT_UP_BUY_BLOCKED",
        ),
    )

    summary = summarize_execution_costs(events)

    assert summary.order_count == 2
    assert summary.submitted_count == 1
    assert summary.accepted_count == 1
    assert summary.completed_count == 1
    assert summary.rejected_count == 1
    assert summary.fill_rate == pytest.approx(1.0)
    assert summary.rejection_rate == pytest.approx(0.5)
    assert summary.total_commission == pytest.approx(1.2)
    assert summary.average_commission == pytest.approx(1.2)
    assert summary.total_slippage_cost == pytest.approx(10.0)
    assert summary.average_slippage_cost == pytest.approx(10.0)
    assert summary.rejections[0].blocked_by == "LIMIT_UP_BUY_BLOCKED"
    assert summary.rejections[0].count == 1
