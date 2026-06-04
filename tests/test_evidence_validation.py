from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from attbacktrader.config import RunPlan
from attbacktrader.data import DailyBar
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.engines import ExecutionAuditEvent
from attbacktrader.reports import build_evidence_validation
from attbacktrader.runners import execute_run_plan
from attbacktrader.strategies import TradeIntent, TradeIntentType


class FakeDailyProvider:
    def __init__(self, bars: tuple[DailyBar, ...]) -> None:
        self.bars = bars

    def fetch_daily_bars(self, *, symbol, start_date, end_date, adjustment):
        return self.bars


def test_evidence_validation_passes_for_consistent_backtrader_run(tmp_path: Path) -> None:
    result = _execute_fixture_run(tmp_path)

    validation = build_evidence_validation(result)

    assert validation.status == "ok"
    assert validation.error_count == 0
    assert validation.counts.closed_trade_count == 2
    assert validation.counts.sizing_decision_count == 2
    assert validation.counts.execution_event_count > 0
    assert validation.counts.post_exit_observation_count == 2
    assert validation.counts.post_exit_threshold_summary_count > 0
    assert validation.counts.trade_review_trade_count == 2
    assert validation.counts.trade_review_opportunity_cost_summary_count >= 0
    assert validation.counts.trade_review_add_on_entry_count == 0


def test_evidence_validation_flags_trade_without_exit_signal(tmp_path: Path) -> None:
    result = _execute_fixture_run(tmp_path)
    broken_result = replace(
        result,
        signal_audit=tuple(
            intent
            for intent in result.signal_audit
            if intent.intent_type not in {TradeIntentType.EXIT_PROFIT, TradeIntentType.EXIT_LOSS}
        ),
    )

    validation = build_evidence_validation(broken_result)

    assert validation.status == "failed"
    assert "TRADE_WITHOUT_EXIT_SIGNAL" in {issue.code for issue in validation.issues}
    assert "EXECUTION_WITHOUT_SIGNAL" in {issue.code for issue in validation.issues}


def test_evidence_validation_flags_entry_without_sizing(tmp_path: Path) -> None:
    result = _execute_fixture_run(tmp_path)
    first_entry = next(intent for intent in result.signal_audit if intent.intent_type == TradeIntentType.ENTER)
    broken_entry = replace(
        first_entry,
        signal_values={
            key: value
            for key, value in first_entry.signal_values.items()
            if key != "sizing"
        },
    )
    broken_result = replace(
        result,
        signal_audit=tuple(
            broken_entry if intent is first_entry else intent
            for intent in result.signal_audit
        ),
    )

    validation = build_evidence_validation(broken_result)

    assert validation.status == "failed"
    assert "MISSING_SIZING" in {issue.code for issue in validation.issues}


def test_evidence_validation_flags_defaulted_missing_post_exit_returns(tmp_path: Path) -> None:
    result = _execute_fixture_run(tmp_path)
    broken_observation = replace(
        result.post_exit_analysis.observations[0],
        observed_day_count=0,
    )
    broken_post_exit = replace(
        result.post_exit_analysis,
        observations=(broken_observation, *result.post_exit_analysis.observations[1:]),
    )
    broken_result = replace(result, post_exit_analysis=broken_post_exit)

    validation = build_evidence_validation(broken_result)

    assert validation.status == "failed"
    assert "POST_EXIT_MISSING_FUTURE_RETURNS_DEFAULTED" in {issue.code for issue in validation.issues}


def test_evidence_validation_accepts_matching_ashare_rejection() -> None:
    trade_date = result_date = date(2024, 1, 2)
    result = _minimal_result(
        signal_audit=(
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                trade_date,
                "entry",
                "ENTRY",
                signal_values={"sizing": {"requested_quantity": 99}},
                blocked_by="BOARD_LOT_TOO_SMALL",
            ),
        ),
        execution_audit=(
            ExecutionAuditEvent(
                event_date=result_date,
                signal_date=trade_date,
                symbol="000001.SZ",
                side="buy",
                event_type="rejected",
                status="rejected",
                reason_code="ENTRY",
                requested_quantity=99,
                executable_quantity=0,
                signal_price=10.0,
                blocked_by="BOARD_LOT_TOO_SMALL",
            ),
        ),
    )

    validation = build_evidence_validation(result)

    assert validation.status == "ok"


def test_evidence_validation_flags_blocked_intent_without_rejected_execution() -> None:
    trade_date = date(2024, 1, 2)
    result = _minimal_result(
        signal_audit=(
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                trade_date,
                "entry",
                "ENTRY",
                signal_values={"sizing": {"requested_quantity": 99}},
                blocked_by="BOARD_LOT_TOO_SMALL",
            ),
        ),
        execution_audit=(),
    )

    validation = build_evidence_validation(result)

    assert validation.status == "failed"
    assert "BLOCKED_INTENT_WITHOUT_REJECTED_EXECUTION" in {issue.code for issue in validation.issues}


def test_evidence_validation_flags_rejection_reason_mismatch() -> None:
    trade_date = date(2024, 1, 2)
    result = _minimal_result(
        signal_audit=(
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                trade_date,
                "entry",
                "ENTRY",
                signal_values={"sizing": {"requested_quantity": 99}},
                blocked_by="SUSPENDED",
            ),
        ),
        execution_audit=(
            ExecutionAuditEvent(
                event_date=trade_date,
                signal_date=trade_date,
                symbol="000001.SZ",
                side="buy",
                event_type="rejected",
                status="rejected",
                reason_code="ENTRY",
                requested_quantity=99,
                executable_quantity=0,
                signal_price=10.0,
                blocked_by="BOARD_LOT_TOO_SMALL",
            ),
        ),
    )

    validation = build_evidence_validation(result)

    assert validation.status == "failed"
    assert "REJECTED_EXECUTION_SIGNAL_BLOCK_MISMATCH" in {issue.code for issue in validation.issues}


def test_evidence_validation_flags_invalid_rejection_shape() -> None:
    trade_date = date(2024, 1, 2)
    result = _minimal_result(
        signal_audit=(
            TradeIntent(
                TradeIntentType.EXIT_LOSS,
                "000001.SZ",
                trade_date,
                "stop",
                "STOP",
                blocked_by="LIMIT_UP_BUY_BLOCKED",
            ),
        ),
        execution_audit=(
            ExecutionAuditEvent(
                event_date=trade_date,
                signal_date=trade_date,
                symbol="000001.SZ",
                side="sell",
                event_type="rejected",
                status="rejected",
                reason_code="STOP",
                requested_quantity=100,
                executable_quantity=100,
                signal_price=10.0,
                blocked_by="LIMIT_UP_BUY_BLOCKED",
            ),
        ),
    )

    validation = build_evidence_validation(result)
    codes = {issue.code for issue in validation.issues}

    assert validation.status == "failed"
    assert "REJECTED_EXECUTION_HAS_EXECUTABLE_QUANTITY" in codes
    assert "REJECTION_REASON_SIDE_MISMATCH" in codes


def _execute_fixture_run(tmp_path: Path):
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    run_plan = _run_plan(tmp_path / "snapshots")
    return execute_run_plan(run_plan, provider=FakeDailyProvider(bars))


def _minimal_result(*, signal_audit, execution_audit):
    return SimpleNamespace(
        symbols=("000001.SZ",),
        closed_trades=(),
        signal_audit=signal_audit,
        execution_audit=execution_audit,
        open_positions=(),
        equity_curve=(),
        position_snapshots=(),
        final_value=None,
        final_cash=None,
        report=SimpleNamespace(
            returns=SimpleNamespace(final_equity=None),
            trade_quality=SimpleNamespace(trade_count=0),
        ),
    )


def _run_plan(snapshot_root: Path) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "evidence-validation-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-11",
            },
            "data": {
                "snapshot_root": snapshot_root,
                "refresh_snapshots": True,
                "symbols": ["000001.SZ"],
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "kdj_oversold_entry",
                "profit_taking_method": "kdj_overheated_exit",
                "stop_loss_method": "fixed_percent_stop",
                "sizing_rule": "equal_weight",
            },
            "broker": {
                "initial_cash": 1000000,
                "commission_rate": 0.0003,
                "stamp_tax_rate": 0.001,
                "transfer_fee_rate": 0.00001,
                "slippage": {"type": "percent", "value": 0.0005},
            },
            "constraints": {
                "ashare": {
                    "enabled": False,
                },
            },
            "execution": {
                "engine": "backtrader",
                "stake": 1,
            },
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )
