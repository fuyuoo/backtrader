from datetime import date

from attbacktrader.engines import ExecutionAuditEvent
from attbacktrader.reports import build_trade_lifecycle_report
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies.templates import ClosedTrade


def test_trade_lifecycle_report_indexes_completed_trade_timelines() -> None:
    report = build_trade_lifecycle_report(
        closed_trades=(
            ClosedTrade("000001.SZ", date(2024, 1, 2), date(2024, 1, 5), 10.0, 11.0, "TAKE_PROFIT"),
            ClosedTrade("000001.SZ", date(2024, 1, 8), date(2024, 1, 10), 10.0, 9.0, "STOP_LOSS"),
        ),
        signal_audit=(
            _entry(date(2024, 1, 2), price_above_ma25=True, risk_group="801780.SI"),
            _add_on(date(2024, 1, 3)),
            _exit(TradeIntentType.EXIT_PROFIT, date(2024, 1, 5), "TAKE_PROFIT"),
            _entry(date(2024, 1, 8), price_above_ma25=False, risk_group="801780.SI"),
            _exit(TradeIntentType.EXIT_LOSS, date(2024, 1, 10), "STOP_LOSS"),
        ),
        execution_audit=(
            _execution(date(2024, 1, 2), "buy", "ENTRY", "completed"),
            _execution(date(2024, 1, 3), "buy", "ADD_ON", "completed"),
            _execution(date(2024, 1, 5), "sell", "TAKE_PROFIT", "completed"),
            _execution(date(2024, 1, 8), "buy", "ENTRY", "rejected", blocked_by="BOARD_LOT_TOO_SMALL"),
            _execution(date(2024, 1, 8), "buy", "ENTRY", "completed"),
            _execution(date(2024, 1, 10), "sell", "STOP_LOSS", "completed"),
        ),
    )

    assert report.trade_count == 2
    assert _bucket(report.indexes.by_outcome, "win").trade_indexes == (1,)
    assert _bucket(report.indexes.by_outcome, "loss").trade_indexes == (2,)
    assert _bucket(report.indexes.by_add_on_count, "1").trade_indexes == (1,)
    assert _bucket(report.indexes.by_add_on_count, "0").trade_indexes == (2,)
    assert _bucket(report.indexes.by_entry_check_true, "symbol.ma.price_above_ma25").trade_indexes == (1,)
    assert _bucket(report.indexes.by_entry_check_false, "symbol.ma.price_above_ma25").trade_indexes == (2,)
    assert _bucket(report.indexes.by_entry_category, "sizing.risk_group=801780.SI").trade_indexes == (1, 2)
    assert _bucket(report.indexes.by_rejection_reason, "BOARD_LOT_TOO_SMALL").trade_indexes == (2,)


def _entry(trade_date: date, *, price_above_ma25: bool, risk_group: str) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.ENTER,
        "000001.SZ",
        trade_date,
        "entry",
        "ENTRY",
        signal_values={
            "attribution": entry_attribution_payload(
                checks={"symbol.ma.price_above_ma25": price_above_ma25},
                categories={"sizing.risk_group": risk_group},
            ),
            "sizing": {"requested_quantity": 100, "risk_group": risk_group},
        },
    )


def _add_on(trade_date: date) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.ADD_ON,
        "000001.SZ",
        trade_date,
        "add_on",
        "ADD_ON",
        signal_values={"sizing": {"requested_quantity": 100}},
    )


def _exit(intent_type: TradeIntentType, trade_date: date, reason_code: str) -> TradeIntent:
    return TradeIntent(intent_type, "000001.SZ", trade_date, "exit", reason_code)


def _execution(
    trade_date: date,
    side: str,
    reason_code: str,
    event_type: str,
    *,
    blocked_by: str | None = None,
) -> ExecutionAuditEvent:
    return ExecutionAuditEvent(
        event_date=trade_date,
        signal_date=trade_date,
        symbol="000001.SZ",
        side=side,
        event_type=event_type,
        status=event_type,
        reason_code=reason_code,
        requested_quantity=100,
        executable_quantity=0 if event_type == "rejected" else 100,
        signal_price=10.0,
        blocked_by=blocked_by,
        executed_date=trade_date if event_type == "completed" else None,
        executed_quantity=100.0 if event_type == "completed" else None,
        executed_price=10.0 if event_type == "completed" else None,
    )


def _bucket(buckets, key: str):
    return next(bucket for bucket in buckets if bucket.key == key)
