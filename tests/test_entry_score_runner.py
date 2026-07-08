from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from attbacktrader.config import RunPlan
from attbacktrader.runners.entry_score import (
    decision_events_from_intents,
    load_entry_score_rows,
    run_entry_score_replay,
)
from attbacktrader.strategies import TradeIntent, TradeIntentType


def test_load_entry_score_rows_maps_configured_columns_and_drops_future_fields(tmp_path: Path) -> None:
    score_path = tmp_path / "scores.parquet"
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "entry_date": "2024-01-05",
                "ew_score": 0.72,
                "fold_id": "2024",
                "exit_price": 12.3,
                "return_pct": 0.12,
            }
        ]
    ).to_parquet(score_path, index=False)

    rows = load_entry_score_rows(
        score_path,
        symbol_column="ts_code",
        trade_date_column="entry_date",
        score_field="entry.score.ew_seed_only_v2",
        source_score_field="ew_score",
    )

    assert rows == [
        {
            "symbol": "000001.SZ",
            "trade_date": "2024-01-05",
            "entry.score.ew_seed_only_v2": 0.72,
            "fold_id": "2024",
        }
    ]


def test_decision_events_from_intents_keeps_entry_and_exit_prices_without_future_evidence() -> None:
    intents = (
        TradeIntent(
            intent_type=TradeIntentType.ENTER,
            symbol="000001.SZ",
            trade_date=date(2024, 1, 5),
            method_name="baoma_entry",
            reason_code="BAOMA_ENTRY_TRIGGERED",
            signal_values={
                "attribution": {
                    "values": {
                        "symbol.close": 10.0,
                        "exit_price": 12.0,
                    },
                    "categories": {"industry.sw_l1.code": "801780.SI"},
                    "checks": {"entry.check": True},
                }
            },
        ),
        TradeIntent(
            intent_type=TradeIntentType.EXIT_LOSS,
            symbol="000001.SZ",
            trade_date=date(2024, 1, 8),
            method_name="baoma_ma60_stop",
            reason_code="BAOMA_MA60_STOP_TRIGGERED",
            signal_values={"current_close": 9.0},
        ),
        TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol="000001.SZ",
            trade_date=date(2024, 1, 9),
            method_name="baoma_entry",
            reason_code="BAOMA_ENTRY_NOT_TRIGGERED",
            signal_values={"close": 11.0},
        ),
    )

    events = decision_events_from_intents(intents, stock_pool_order_by_symbol={"000001.SZ": 7})

    assert [event["intent_type"] for event in events] == ["enter", "exit_loss"]
    assert events[0]["price"] == pytest.approx(10.0)
    assert events[0]["industry"] == "801780.SI"
    assert events[0]["stock_pool_order"] == 7
    assert "exit_price" not in events[0]["evidence"]
    assert events[1]["price"] == pytest.approx(9.0)


def test_run_entry_score_replay_ranks_external_scores_and_blocks_missing_scores(tmp_path: Path) -> None:
    score_path = tmp_path / "scores.parquet"
    pd.DataFrame(
        [
            {"symbol": "000001.SZ", "entry_date": "2024-01-05", "ew_score": 0.25},
            {"symbol": "000002.SZ", "entry_date": "2024-01-05", "ew_score": 0.90},
        ]
    ).to_parquet(score_path, index=False)
    run_plan = _entry_score_run_plan(tmp_path, score_path)
    intents = (
        _enter_intent("000001.SZ", 10.0),
        _enter_intent("000002.SZ", 10.0),
        _enter_intent("000003.SZ", 10.0),
    )

    replay = run_entry_score_replay(run_plan, intents=intents)

    assert replay is not None
    assert replay["precomputed_score_contract"]["enter_event_count"] == 3
    assert replay["precomputed_score_contract"]["matched_enter_score_count"] == 2
    assert replay["precomputed_score_contract"]["missing_enter_score_count"] == 1
    assert [entry["symbol"] for entry in replay["executed_entries"]] == ["000002.SZ", "000001.SZ"]
    assert replay["blocked_entries"][0]["symbol"] == "000003.SZ"
    assert replay["blocked_entries"][0]["blocked_by"] == "SCORE_GATE"
    assert replay["source"]["artifact_path"] == str(score_path)


def test_run_entry_score_replay_can_use_separate_replay_initial_cash(tmp_path: Path) -> None:
    score_path = tmp_path / "scores.parquet"
    pd.DataFrame(
        [
            {"symbol": "000001.SZ", "entry_date": "2024-01-05", "ew_score": 0.90},
            {"symbol": "000002.SZ", "entry_date": "2024-01-05", "ew_score": 0.80},
        ]
    ).to_parquet(score_path, index=False)
    run_plan = _entry_score_run_plan(tmp_path, score_path, replay_initial_cash=20_000)

    replay = run_entry_score_replay(
        run_plan,
        intents=(
            _enter_intent("000001.SZ", 10.0),
            _enter_intent("000002.SZ", 10.0),
        ),
    )

    assert replay is not None
    assert replay["portfolio_controls"]["initial_cash"] == pytest.approx(20_000)
    assert replay["source"]["engine_initial_cash"] == pytest.approx(100_000)
    assert replay["source"]["replay_initial_cash"] == pytest.approx(20_000)


def test_run_entry_score_replay_can_fail_on_missing_scores(tmp_path: Path) -> None:
    score_path = tmp_path / "scores.parquet"
    pd.DataFrame(
        [{"symbol": "000001.SZ", "entry_date": "2024-01-05", "ew_score": 0.25}]
    ).to_parquet(score_path, index=False)
    run_plan = _entry_score_run_plan(tmp_path, score_path, missing_score_policy="fail")

    with pytest.raises(ValueError, match="missing precomputed scores"):
        run_entry_score_replay(
            run_plan,
            intents=(
                _enter_intent("000001.SZ", 10.0),
                _enter_intent("000002.SZ", 10.0),
            ),
        )


def test_run_entry_score_replay_filters_events_and_scores_to_replay_window(tmp_path: Path) -> None:
    score_path = tmp_path / "scores.parquet"
    pd.DataFrame(
        [
            {"symbol": "000001.SZ", "entry_date": "2012-12-28", "ew_score": 9.0},
            {"symbol": "000001.SZ", "entry_date": "2024-01-05", "ew_score": 0.25},
            {"symbol": "000002.SZ", "entry_date": "2024-01-05", "ew_score": 0.90},
            {"symbol": "000003.SZ", "entry_date": "2026-01-05", "ew_score": 8.0},
        ]
    ).to_parquet(score_path, index=False)
    run_plan = _entry_score_run_plan(
        tmp_path,
        score_path,
        replay_start_date="2024-01-01",
        replay_end_date="2024-12-31",
    )

    replay = run_entry_score_replay(
        run_plan,
        intents=(
            _enter_intent("000001.SZ", 10.0, trade_date=date(2012, 12, 28)),
            _enter_intent("000001.SZ", 10.0, trade_date=date(2024, 1, 5)),
            _enter_intent("000002.SZ", 10.0, trade_date=date(2024, 1, 5)),
            _enter_intent("000003.SZ", 10.0, trade_date=date(2026, 1, 5)),
        ),
    )

    assert replay is not None
    contract = replay["precomputed_score_contract"]
    assert contract["enter_event_count"] == 2
    assert contract["matched_enter_score_count"] == 2
    assert contract["score_keys_not_in_enter_events_count"] == 0
    assert replay["source"]["source_decision_event_count"] == 4
    assert replay["source"]["decision_event_count"] == 2
    assert replay["source"]["replay_start_date"] == "2024-01-01"
    assert replay["source"]["replay_end_date"] == "2024-12-31"


def _enter_intent(symbol: str, price: float, *, trade_date: date = date(2024, 1, 5)) -> TradeIntent:
    return TradeIntent(
        intent_type=TradeIntentType.ENTER,
        symbol=symbol,
        trade_date=trade_date,
        method_name="baoma_entry",
        reason_code="BAOMA_ENTRY_TRIGGERED",
        signal_values={
            "attribution": {
                "values": {"symbol.close": price},
                "categories": {},
                "checks": {"entry.check": True},
            }
        },
    )


def _entry_score_run_plan(
    tmp_path: Path,
    score_path: Path,
    *,
    missing_score_policy: str = "skip",
    replay_start_date: str | None = None,
    replay_end_date: str | None = None,
    replay_initial_cash: int | None = None,
) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "entry-score-runner-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-31",
            },
            "data": {
                "snapshot_root": tmp_path / "snapshots",
                "symbols": ["000001.SZ", "000002.SZ", "000003.SZ"],
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "baoma_entry",
                "profit_taking_method": "baoma_ma25_profit_exit",
                "stop_loss_method": "baoma_ma60_stop",
                "add_on_method": "baoma_add_on",
                "sizing_rule": "equal_weight",
                "sizing_params": {"max_holding_count": 2},
            },
            "constraints": {
                "ashare": {
                    "enabled": True,
                    "board_lot_size": 100,
                },
            },
            "broker": {
                "initial_cash": 100000,
                "commission_rate": 0.0003,
                "stamp_tax_rate": 0.001,
                "transfer_fee_rate": 0.00001,
                "slippage": {"type": "percent", "value": 0.0005},
            },
            "execution": {
                "engine": "baoma_v1_business",
                "entry_score": {
                    "enabled": True,
                    "score_id": "ew_seed_only_v2",
                    "score_field": "entry.score.ew_seed_only_v2",
                    "source_score_field": "ew_score",
                    "artifact_path": score_path,
                    "missing_score_policy": missing_score_policy,
                    "replay_start_date": replay_start_date,
                    "replay_end_date": replay_end_date,
                    "replay_initial_cash": replay_initial_cash,
                    "max_holding_count": 2,
                    "max_new_positions_per_day": 2,
                    "cash_reserve_ratio": 0.0,
                    "industry_max_new_per_day": None,
                },
            },
            "analysis": {
                "industry_attribution": {"enabled": False},
                "market_regime": {"enabled": False},
                "scenario_fit": {"enabled": False},
            },
        }
    )
