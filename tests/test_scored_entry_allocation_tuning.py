import json
from datetime import date
from pathlib import Path

import pytest

from attbacktrader.cli import scored_entry_allocation_tuning as tuning_cli
from attbacktrader.reports import (
    FIXED_PARAMETER_SCORED_PORTFOLIO_SMOKE_RUN_SCHEMA,
    SCORED_ENTRY_ALLOCATION_TUNING_CONTRACT_SCHEMA,
    SCORED_PORTFOLIO_BASELINE_COMPARISON_SCHEMA,
    STRATEGY_DECISION_EVENT_TABLE_SCHEMA,
    build_scored_entry_allocation_tuning_report,
    build_simulation_cache_identity,
    build_strategy_decision_event_table_from_intents,
    build_stage_b_search_space_from_stage_a,
    build_strategy_decision_cache_identity,
    build_strategy_decision_event_table,
    build_scored_entry_allocation_tuning_contract,
    apply_fitted_score_gate_to_candidates,
    fit_training_score_gate_statistics,
    require_optuna_for_tuning,
    run_fixed_parameter_scored_portfolio_smoke,
    run_scored_portfolio_baseline_comparison,
    score_entry_candidates,
    simulate_scored_portfolio,
    write_fixed_parameter_scored_portfolio_smoke_run,
    write_scored_portfolio_baseline_comparison,
    write_scored_entry_allocation_tuning_contract,
)
from attbacktrader.strategies import TradeIntent, TradeIntentType


def test_scored_entry_allocation_tuning_dry_run_contract_lists_folds_and_defaults(tmp_path: Path) -> None:
    contract = build_scored_entry_allocation_tuning_contract(
        mode="dry-run",
        output_dir=tmp_path / "study",
    )

    assert contract["schema"] == SCORED_ENTRY_ALLOCATION_TUNING_CONTRACT_SCHEMA
    assert contract["mode"] == "dry-run"
    assert contract["optuna_required"] is False
    assert contract["output_dir"] == str(tmp_path / "study")
    assert [fold["test"]["year"] for fold in contract["folds"]] == [2020, 2021, 2022, 2023, 2024]
    assert contract["folds"][0]["train"] == {"start": "2015-01-01", "end": "2019-12-31", "years": [2015, 2016, 2017, 2018, 2019]}
    assert contract["stages"]["stage_a"]["score_gate"] == {
        "minimum_score_z": 0.0,
        "minimum_score_quantile": 0.50,
    }
    assert contract["stages"]["stage_b"]["score_gate"] == {
        "minimum_score_z": 0.75,
        "minimum_score_quantile": 0.70,
    }
    assert contract["stages"]["stage_a"]["standard_trials_per_fold"] == 300
    assert contract["stages"]["stage_b"]["standard_trials_per_fold"] == 300
    assert contract["stages"]["stage_b"]["portfolio_controls"] == {
        "initial_cash": 10_000_000,
        "max_holding_count": 20,
        "max_new_positions_per_day": 3,
        "cash_reserve_ratio": 0.05,
        "industry_max_new_per_day": 1,
    }
    assert "completed trades" not in " ".join(contract["decision_cache"]["stores"])
    assert {"annualized_return", "sharpe_ratio", "benchmark_excess_return", "max_drawdown"} == set(
        contract["objectives"]
    )


def test_strategy_decision_event_table_cache_identity_excludes_trial_specific_parameters() -> None:
    base_cache_inputs = {
        "data_snapshot_identity": "snapshot-2015-2024-qfq",
        "stock_pool_identity": "csi300-csi500-freeze-20250101",
        "strategy_signal_parameters": {"template": "baoma_v1", "entry": "baoma_entry"},
        "factor_field_set": ["symbol.ma.trend_state", "symbol.macd.energy_zone"],
        "date_range": {"start": "2015-01-01", "end": "2024-12-31"},
        "event_schema_version": 1,
        "scorer_weights": {"symbol.ma.trend_state=bullish": 2.0},
        "trial_id": "stage-b-001",
        "score_gate": {"minimum_score_z": 0.75, "minimum_score_quantile": 0.70},
        "score_thresholds": {"threshold": 1.5},
    }
    changed_trial_inputs = dict(base_cache_inputs)
    changed_trial_inputs["scorer_weights"] = {"symbol.ma.trend_state=bullish": -7.0}
    changed_trial_inputs["trial_id"] = "stage-b-999"
    changed_trial_inputs["score_gate"] = {"minimum_score_z": 9.99, "minimum_score_quantile": 0.99}
    changed_trial_inputs["score_thresholds"] = {"threshold": 99.0}

    identity = build_strategy_decision_cache_identity(base_cache_inputs)
    changed_identity = build_strategy_decision_cache_identity(changed_trial_inputs)

    assert identity == changed_identity
    assert "scorer_weights" not in identity["inputs"]
    assert "trial_id" not in identity["inputs"]
    assert "score_gate" not in identity["inputs"]
    assert "score_thresholds" not in identity["inputs"]
    assert {"scorer_weights", "trial_id", "score_gate", "score_thresholds"} <= set(identity["excluded_fields"])

    table = build_strategy_decision_event_table(
        [
            {
                "symbol": "000001.SZ",
                "trade_date": "2020-01-02",
                "intent_type": "enter",
                "price": 10.0,
                "industry": "bank",
                "stock_pool_order": 1,
                "tradable": True,
                "evidence": {
                    "symbol.ma.trend_state": "bullish",
                    "symbol.macd.energy_zone": "red_bar_expanding",
                },
            }
        ],
        cache_inputs=base_cache_inputs,
    )

    assert table["schema"] == STRATEGY_DECISION_EVENT_TABLE_SCHEMA
    assert table["cache_identity"] == identity
    assert table["event_count"] == 1
    assert table["events"][0]["evidence"]["symbol.ma.trend_state"] == "bullish"

    with pytest.raises(ValueError, match="completed_trade_id"):
        build_strategy_decision_event_table(
            [
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2020-01-02",
                    "intent_type": "enter",
                    "price": 10.0,
                    "completed_trade_id": "T1",
                    "evidence": {},
                }
            ],
            cache_inputs=base_cache_inputs,
        )


def test_strategy_decision_event_table_can_be_built_from_trade_intents_without_result_state() -> None:
    cache_inputs = _decision_cache_inputs()
    intents = [
        TradeIntent(
            intent_type=TradeIntentType.ENTER,
            symbol="000001.SZ",
            trade_date=date(2020, 1, 2),
            method_name="baoma_entry",
            reason_code="BAOMA_ENTRY",
            signal_values={
                "attribution": {
                    "values": {
                        "symbol.ma.trend_state": "bullish",
                        "symbol.macd.energy_zone": "red_bar_expanding",
                    },
                    "categories": {
                        "market.stage": "warm",
                    },
                    "checks": {
                        "close_above_ma60": True,
                    },
                },
                "sizing": {"business_executable_quantity": 100},
            },
        ),
        TradeIntent(
            intent_type=TradeIntentType.EXIT_PROFIT,
            symbol="000001.SZ",
            trade_date=date(2020, 1, 8),
            method_name="baoma_ma25_profit_exit",
            reason_code="MA25_PROFIT_EXIT",
            signal_values={"attribution": {"values": {"exit.ma25_state": "broken"}}},
        ),
        TradeIntent(
            intent_type=TradeIntentType.HOLD,
            symbol="000002.SZ",
            trade_date=date(2020, 1, 2),
            method_name="baoma_entry",
            reason_code="NO_ENTRY",
            signal_values={"attribution": {"values": {"symbol.ma.trend_state": "flat"}}},
        ),
    ]

    table = build_strategy_decision_event_table_from_intents(
        intents,
        cache_inputs=cache_inputs,
        market_context_by_key={
            ("000001.SZ", "2020-01-02"): {
                "price": 10.0,
                "industry": "bank",
                "stock_pool_order": 1,
                "tradable": True,
            },
            ("000001.SZ", "2020-01-08"): {
                "price": 12.0,
                "industry": "bank",
                "stock_pool_order": 1,
                "tradable": True,
            },
        },
    )

    assert table["schema"] == STRATEGY_DECISION_EVENT_TABLE_SCHEMA
    assert table["event_count"] == 2
    assert [event["intent_type"] for event in table["events"]] == ["enter", "exit_profit"]
    entry = table["events"][0]
    assert entry["price"] == 10.0
    assert entry["evidence"]["symbol.ma.trend_state"] == "bullish"
    assert entry["evidence"]["market.stage"] == "warm"
    assert entry["evidence"]["close_above_ma60"] is True
    assert "business_executable_quantity" not in json.dumps(table["events"], ensure_ascii=False)
    assert "completed_trade" not in json.dumps(table["events"], ensure_ascii=False)

    with pytest.raises(ValueError, match="missing market context"):
        build_strategy_decision_event_table_from_intents(
            [intents[0]],
            cache_inputs=cache_inputs,
            market_context_by_key={},
        )


def test_score_entry_candidates_uses_bucket_weights_interactions_and_training_gate() -> None:
    scorer_config = {
        "factor_weights": {
            "symbol.ma.trend_state": {"bullish": 2.0, "flat": 0.0},
            "symbol.macd.energy_zone": {"green_bar_or_zero": -1.0, "red_bar_expanding": 0.0},
        },
        "interaction_weights": [
            {
                "fields": {
                    "symbol.ma.trend_state": "bullish",
                    "symbol.macd.energy_zone": "red_bar_expanding",
                },
                "weight": 1.5,
            },
            {
                "fields": {
                    "symbol.ma.trend_state": "bullish",
                    "symbol.macd.energy_zone": "green_bar_or_zero",
                },
                "weight": -2.0,
            },
        ],
    }
    events = [
        _entry_event(
            "000001.SZ",
            trend="bullish",
            macd="red_bar_expanding",
            raw_momentum=999.0,
        ),
        _entry_event(
            "000002.SZ",
            trend="bullish",
            macd="green_bar_or_zero",
            raw_momentum=-999.0,
        ),
        _entry_event(
            "000003.SZ",
            trend="flat",
            macd="red_bar_expanding",
            raw_momentum=9999.0,
        ),
    ]

    scored = score_entry_candidates(
        events,
        scorer_config=scorer_config,
        training_events=events,
        score_gate={"minimum_score_z": 0.0, "minimum_score_quantile": 0.50},
    )

    rows_by_symbol = {row["symbol"]: row for row in scored["rows"]}
    assert rows_by_symbol["000001.SZ"]["score"] == pytest.approx(3.5)
    assert rows_by_symbol["000001.SZ"]["score_gate_passed"] is True
    assert rows_by_symbol["000002.SZ"]["score"] == pytest.approx(-1.0)
    assert rows_by_symbol["000002.SZ"]["score_gate_passed"] is False
    assert rows_by_symbol["000003.SZ"]["score"] == pytest.approx(0.0)
    assert rows_by_symbol["000003.SZ"]["score_gate_passed"] is False
    assert "raw_momentum" not in rows_by_symbol["000001.SZ"]["contributions"]["factor_weights"]
    assert scored["score_gate"]["derived_from"] == "training_window"


def test_score_gate_statistics_are_fitted_from_training_window_and_reused_for_test_candidates() -> None:
    scorer_config = {"factor_weights": {"rank_bucket": {"weak": 0.0, "mid": 2.0, "strong": 4.0}}}
    training_events = [
        _rank_event("000001.SZ", rank_bucket="weak", industry="bank", stock_pool_order=1, window="training"),
        _rank_event("000002.SZ", rank_bucket="mid", industry="bank", stock_pool_order=2, window="training"),
        _rank_event("000003.SZ", rank_bucket="strong", industry="bank", stock_pool_order=3, window="training"),
    ]
    test_events = [
        _rank_event("000004.SZ", rank_bucket="weak", industry="tech", stock_pool_order=1, trade_date="2020-02-03", window="test"),
        _rank_event("000005.SZ", rank_bucket="strong", industry="tech", stock_pool_order=2, trade_date="2020-02-03", window="test"),
    ]

    fitted_gate = fit_training_score_gate_statistics(
        training_events,
        scorer_config=scorer_config,
        score_gate={"minimum_score_z": 0.75, "minimum_score_quantile": 0.70},
    )
    scored = apply_fitted_score_gate_to_candidates(
        test_events,
        scorer_config=scorer_config,
        fitted_score_gate=fitted_gate,
    )

    assert fitted_gate["source_window"] == "training"
    assert fitted_gate["source_event_count"] == 3
    assert fitted_gate["mean"] == pytest.approx(2.0)
    assert fitted_gate["std"] == pytest.approx((8 / 3) ** 0.5)
    assert fitted_gate["quantile_threshold"] == pytest.approx(2.8)
    assert fitted_gate["z_threshold"] == pytest.approx(2.0 + 0.75 * ((8 / 3) ** 0.5))
    assert scored["score_gate"] == fitted_gate
    assert {row["symbol"]: row["score_gate_passed"] for row in scored["rows"]} == {
        "000004.SZ": False,
        "000005.SZ": True,
    }

    with pytest.raises(ValueError, match="test-window candidates cannot be used to fit score gate thresholds"):
        fit_training_score_gate_statistics(
            test_events,
            scorer_config=scorer_config,
            score_gate={"minimum_score_z": 0.75, "minimum_score_quantile": 0.70},
        )


def test_scored_portfolio_simulation_ranks_candidates_and_records_blockage_funnel() -> None:
    events = [
        _rank_event("000001.SZ", rank_bucket="a", industry="bank", stock_pool_order=1),
        _rank_event("000002.SZ", rank_bucket="b", industry="bank", stock_pool_order=2),
        _rank_event("000003.SZ", rank_bucket="c", industry="tech", stock_pool_order=3),
        _rank_event("000004.SZ", rank_bucket="d", industry="medicine", stock_pool_order=4),
    ]

    result = simulate_scored_portfolio(
        events,
        scorer_config={"factor_weights": {"rank_bucket": {"a": 4.0, "b": 3.0, "c": 2.0, "d": 1.0}}},
        training_events=events,
        score_gate={"minimum_score_z": -10.0, "minimum_score_quantile": 0.0},
        portfolio_controls={
            "initial_cash": 10_000,
            "max_holding_count": 2,
            "max_new_positions_per_day": 3,
            "cash_reserve_ratio": 0.10,
            "industry_max_new_per_day": 1,
            "board_lot_size": 100,
        },
    )

    assert [entry["symbol"] for entry in result["executed_entries"]] == ["000001.SZ", "000003.SZ"]
    assert result["final_cash"] == pytest.approx(2_000)
    assert result["final_value"] == pytest.approx(10_000)
    assert result["metrics"]["trade_count"] == 2
    assert result["metrics"]["turnover"] == pytest.approx(0.8)
    assert result["funnel"]["raw_entry_candidates"] == 4
    assert result["funnel"]["score_gated_candidates"] == 4
    assert result["funnel"]["industry_blocked_candidates"] == 1
    assert result["funnel"]["holding_cap_blocked_candidates"] == 1
    assert result["funnel"]["executed_entries"] == 2
    assert result["blocked_entries"][0]["symbol"] == "000002.SZ"
    assert result["blocked_entries"][0]["blocked_by"] == "INDUSTRY_MAX_NEW_PER_DAY"
    assert result["equity_curve"][-1]["holding_count"] == 2


def test_fixed_parameter_scored_portfolio_smoke_run_consumes_decision_cache(tmp_path: Path) -> None:
    table = build_strategy_decision_event_table(
        [
            _rank_event("000001.SZ", rank_bucket="top", industry="bank", stock_pool_order=1),
            _rank_event("000002.SZ", rank_bucket="top", industry="tech", stock_pool_order=2),
            _rank_event("000003.SZ", rank_bucket="top", industry="medicine", stock_pool_order=3),
            _rank_event("000004.SZ", rank_bucket="low", industry="retail", stock_pool_order=4),
            _rank_event("000005.SZ", rank_bucket="top", industry="energy", stock_pool_order=1, trade_date="2020-01-03"),
            _rank_event("000006.SZ", rank_bucket="top", industry="auto", stock_pool_order=2, trade_date="2020-01-03"),
            {
                "symbol": "000002.SZ",
                "trade_date": "2020-01-04",
                "intent_type": "exit_profit",
                "price": 10.0,
                "industry": "tech",
                "stock_pool_order": 0,
                "tradable": True,
                "evidence": {"exit": "profit"},
            },
            _rank_event("000001.SZ", rank_bucket="top", industry="bank", stock_pool_order=1, trade_date="2020-01-04", price=50.0),
            _rank_event(
                "000007.SZ",
                rank_bucket="top",
                industry="utility",
                stock_pool_order=2,
                trade_date="2020-01-04",
                tradable=False,
            ),
            _rank_event("000008.SZ", rank_bucket="top", industry="broker", stock_pool_order=3, trade_date="2020-01-04"),
        ],
        cache_inputs=_decision_cache_inputs(),
    )

    smoke_run = run_fixed_parameter_scored_portfolio_smoke(
        table,
        fold_id="train-2015-2019_test-2020",
        scorer_config={"factor_weights": {"rank_bucket": {"top": 5.0, "low": -5.0}}},
        score_gate={"minimum_score_z": 0.0, "minimum_score_quantile": 0.50},
        portfolio_controls={
            "initial_cash": 10_000,
            "max_holding_count": 3,
            "max_new_positions_per_day": 2,
            "cash_reserve_ratio": 0.10,
            "board_lot_size": 100,
        },
    )

    assert smoke_run["schema"] == FIXED_PARAMETER_SCORED_PORTFOLIO_SMOKE_RUN_SCHEMA
    assert smoke_run["decision_cache_identity"] == table["cache_identity"]
    assert smoke_run["simulation_cache_identity"]["inputs"]["fold_id"] == "train-2015-2019_test-2020"
    assert [entry["symbol"] for entry in smoke_run["selected_entries"]] == [
        "000001.SZ",
        "000002.SZ",
        "000005.SZ",
    ]
    assert [entry["cost"] for entry in smoke_run["selected_entries"]] == [3_000.0, 3_000.0, 3_000.0]
    assert [movement["action"] for movement in smoke_run["cash_movements"]] == ["buy", "buy", "buy", "sell"]
    assert smoke_run["cash_movements"][-1] == {
        "trade_date": "2020-01-04",
        "symbol": "000002.SZ",
        "action": "sell",
        "amount": 3_000.0,
        "cash_after": 4_000.0,
    }
    assert smoke_run["equity_curve"][-1]["total_value"] == pytest.approx(22_000)
    assert smoke_run["position_snapshots"][-1]["holding_count"] == 2
    assert {position["symbol"] for position in smoke_run["position_snapshots"][-1]["positions"]} == {
        "000001.SZ",
        "000005.SZ",
    }
    assert smoke_run["funnel"]["raw_entry_candidates"] == 9
    assert smoke_run["funnel"]["score_gate_blocked_candidates"] == 1
    assert smoke_run["funnel"]["max_new_position_blocked_candidates"] == 1
    assert smoke_run["funnel"]["holding_cap_blocked_candidates"] == 1
    assert smoke_run["funnel"]["tradability_blocked_candidates"] == 1
    assert smoke_run["funnel"]["cash_blocked_candidates"] == 1
    assert smoke_run["funnel"]["executed_entries"] == 3
    assert [(entry["symbol"], entry["blocked_by"]) for entry in smoke_run["blocked_entries"]] == [
        ("000003.SZ", "MAX_NEW_POSITIONS_PER_DAY"),
        ("000004.SZ", "SCORE_GATE"),
        ("000006.SZ", "MAX_HOLDING_COUNT"),
        ("000001.SZ", "ALREADY_HELD"),
        ("000007.SZ", "NOT_TRADABLE"),
        ("000008.SZ", "INSUFFICIENT_CASH"),
    ]

    json_path, payload = write_fixed_parameter_scored_portfolio_smoke_run(smoke_run, output_dir=tmp_path)

    assert json_path.exists()
    assert payload["artifacts"]["smoke_run_json"] == str(json_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema"] == FIXED_PARAMETER_SCORED_PORTFOLIO_SMOKE_RUN_SCHEMA


def test_scored_portfolio_baseline_comparison_uses_stage_constraints_and_fixed_stock_pool_order(tmp_path: Path) -> None:
    table = build_strategy_decision_event_table(
        [
            _rank_event("000002.SZ", rank_bucket="low", industry="bank", stock_pool_order=1),
            _rank_event("000001.SZ", rank_bucket="top", industry="tech", stock_pool_order=2),
            _rank_event("000003.SZ", rank_bucket="mid", industry="medicine", stock_pool_order=3),
            _rank_event("000004.SZ", rank_bucket="top", industry="energy", stock_pool_order=4),
            _exit_event("000001.SZ", trade_date="2020-01-03", price=12.0, industry="tech"),
            _exit_event("000002.SZ", trade_date="2020-01-03", price=9.0, industry="bank"),
            _exit_event("000003.SZ", trade_date="2020-01-03", price=11.0, industry="medicine"),
            _exit_event("000004.SZ", trade_date="2020-01-03", price=14.0, industry="energy"),
        ],
        cache_inputs=_decision_cache_inputs(),
    )
    contract = build_scored_entry_allocation_tuning_contract(mode="dry-run")

    comparison = run_scored_portfolio_baseline_comparison(
        table,
        contract=contract,
        fold_id="train-2015-2019_test-2020",
        scorer_config={"factor_weights": {"rank_bucket": {"top": 10.0, "mid": 2.0, "low": -1.0}}},
        score_gate_by_stage={
            "stage_a": {"minimum_score_z": -10.0, "minimum_score_quantile": 0.0},
            "stage_b": {"minimum_score_z": -10.0, "minimum_score_quantile": 0.0},
        },
    )

    assert comparison["schema"] == SCORED_PORTFOLIO_BASELINE_COMPARISON_SCHEMA
    assert comparison["core_metric_keys"] == [
        "cumulative_return",
        "annualized_return",
        "max_drawdown",
        "sharpe_ratio",
        "trade_count",
        "win_rate",
        "profit_loss_ratio",
    ]
    stage_a = comparison["stages"]["stage_a"]
    assert stage_a["constraint_regime"] == "broad_high_capacity_unscored_candidate_filling"
    assert stage_a["unscored_baseline"]["stage"] == "stage_a"
    assert stage_a["unscored_baseline"]["result_type"] == "unscored_baseline"
    assert stage_a["unscored_baseline"]["portfolio_controls"]["max_holding_count"] == 800
    assert [entry["symbol"] for entry in stage_a["unscored_baseline"]["selected_entries"]] == [
        "000002.SZ",
        "000001.SZ",
        "000003.SZ",
        "000004.SZ",
    ]

    stage_b = comparison["stages"]["stage_b"]
    assert stage_b["constraint_regime"] == "realistic_constraints_fixed_stock_pool_order"
    assert stage_b["scored"]["stage"] == "stage_b"
    assert stage_b["scored"]["result_type"] == "scored"
    assert stage_b["portfolio_controls"]["max_holding_count"] == 20
    assert stage_b["portfolio_controls"]["max_new_positions_per_day"] == 3
    assert [entry["symbol"] for entry in stage_b["scored"]["selected_entries"]] == [
        "000001.SZ",
        "000004.SZ",
        "000003.SZ",
    ]
    assert [entry["symbol"] for entry in stage_b["unscored_baseline"]["selected_entries"]] == [
        "000002.SZ",
        "000001.SZ",
        "000003.SZ",
    ]
    assert stage_b["baseline_score_gate"] == {
        "minimum_score_z": -1_000_000.0,
        "minimum_score_quantile": 0.0,
    }
    assert stage_b["unscored_baseline"]["core_metrics"]["trade_count"] == 3
    assert "profit_loss_ratio" in stage_b["core_metric_delta_vs_baseline"]

    json_path, payload = write_scored_portfolio_baseline_comparison(comparison, output_dir=tmp_path)

    assert json_path.exists()
    assert payload["artifacts"]["baseline_comparison_json"] == str(json_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema"] == SCORED_PORTFOLIO_BASELINE_COMPARISON_SCHEMA


def test_fixed_parameter_smoke_run_exposes_core_metrics_for_deterministic_trade() -> None:
    table = build_strategy_decision_event_table(
        [
            _rank_event("000001.SZ", rank_bucket="top", industry="bank", stock_pool_order=1, trade_date="2020-01-02", price=10.0),
            _exit_event("000001.SZ", trade_date="2020-01-03", price=12.0, industry="bank"),
        ],
        cache_inputs=_decision_cache_inputs(),
    )

    smoke_run = run_fixed_parameter_scored_portfolio_smoke(
        table,
        fold_id="train-2015-2019_test-2020",
        stage="stage_b",
        scorer_config={"factor_weights": {"rank_bucket": {"top": 1.0}}},
        score_gate={"minimum_score_z": -10.0, "minimum_score_quantile": 0.0},
        portfolio_controls={
            "initial_cash": 10_000,
            "max_holding_count": 1,
            "cash_reserve_ratio": 0.0,
            "board_lot_size": 100,
        },
    )

    assert smoke_run["stage"] == "stage_b"
    assert smoke_run["result_type"] == "scored"
    assert smoke_run["core_metrics"] == {
        "cumulative_return": pytest.approx(0.2),
        "annualized_return": pytest.approx(0.2),
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "trade_count": 1,
        "win_rate": 1.0,
        "profit_loss_ratio": 0.0,
    }


def test_stage_a_narrows_stage_b_ranges_and_report_selects_recommendations() -> None:
    stage_a_trials = [
        _trial("a1", annualized_return=0.20, sharpe_ratio=1.4, excess=0.10, max_drawdown=0.12, weights={"f1": 1.0, "f2": -0.8, "f3": -0.2}),
        _trial("a2", annualized_return=0.18, sharpe_ratio=1.2, excess=0.08, max_drawdown=0.10, weights={"f1": 1.2, "f2": -1.1, "f3": 0.1}),
        _trial("a3", annualized_return=0.06, sharpe_ratio=0.3, excess=-0.02, max_drawdown=0.20, weights={"f1": -0.4, "f2": 0.5, "f3": 0.2}),
    ]

    search_space = build_stage_b_search_space_from_stage_a(stage_a_trials, weight_keys=["f1", "f2", "f3"])

    assert search_space["weights"]["f1"]["classification"] == "stable_positive"
    assert search_space["weights"]["f1"]["low"] > 0
    assert search_space["weights"]["f2"]["classification"] == "stable_negative"
    assert search_space["weights"]["f2"]["high"] < 0
    assert search_space["weights"]["f3"]["classification"] == "unstable"
    assert search_space["evidence_use"] == "narrows_stage_b_search_space_only"

    stage_b_trials = [
        _trial("balanced", annualized_return=0.16, sharpe_ratio=1.5, excess=0.08, max_drawdown=0.08, trade_count=80, turnover=0.9),
        _trial("aggressive", annualized_return=0.25, sharpe_ratio=1.0, excess=0.14, max_drawdown=0.18, trade_count=90, turnover=1.4),
        _trial("defensive", annualized_return=0.09, sharpe_ratio=1.1, excess=0.04, max_drawdown=0.04, trade_count=70, turnover=0.5),
        _trial("too-few", annualized_return=0.50, sharpe_ratio=4.0, excess=0.40, max_drawdown=0.02, trade_count=3, turnover=0.1),
    ]
    report = build_scored_entry_allocation_tuning_report(
        contract=build_scored_entry_allocation_tuning_contract(mode="dry-run"),
        stage_a_trials=stage_a_trials,
        stage_b_trials=stage_b_trials,
        stage_b_search_space=search_space,
        baselines={"stage_b_unscored": _trial("baseline", annualized_return=0.05, sharpe_ratio=0.6, excess=0.0, max_drawdown=0.10)},
    )

    assert report["stage_a"]["evidence_use"] == "pre_tuning_only"
    assert report["stage_b"]["search_space"]["weights"]["f1"]["classification"] == "stable_positive"
    assert {trial["trial_id"] for trial in report["stage_b"]["pareto_frontier"]} >= {"balanced", "aggressive", "defensive"}
    assert report["recommendations"]["balanced"]["trial_id"] == "balanced"
    assert report["recommendations"]["aggressive"]["trial_id"] == "aggressive"
    assert report["recommendations"]["defensive"]["trial_id"] == "defensive"
    assert report["recommendations"]["rejected"][0]["trial_id"] == "too-few"
    assert "funnel_counts" in report["stage_b"]["trials"][0]["metrics"]


def test_simulation_cache_identity_and_optuna_gate_are_explicit() -> None:
    identity = build_simulation_cache_identity(
        signal_cache_identity="signal-cache-abc",
        fold_id="train-2015-2019_test-2020",
        parameters={"f1": 1.0},
        portfolio_controls={"max_holding_count": 20},
        simulator_version="v1",
    )
    changed = build_simulation_cache_identity(
        signal_cache_identity="signal-cache-abc",
        fold_id="train-2015-2019_test-2020",
        parameters={"f1": 2.0},
        portfolio_controls={"max_holding_count": 20},
        simulator_version="v1",
    )

    assert identity["cache_key"] != changed["cache_key"]
    assert set(identity["inputs"]) == {
        "signal_cache_identity",
        "fold_id",
        "parameter_hash",
        "portfolio_control_hash",
        "simulator_version",
    }

    def missing_import(name: str):
        raise ModuleNotFoundError(name)

    with pytest.raises(ImportError, match=r"pip install -e \.\[tuning\]"):
        require_optuna_for_tuning(import_module=missing_import)


def test_scored_entry_allocation_tuning_contract_writer_and_cli_dry_run(tmp_path: Path, capsys) -> None:
    contract = build_scored_entry_allocation_tuning_contract(mode="dry-run", output_dir=tmp_path / "contract")

    json_path, markdown_path, payload = write_scored_entry_allocation_tuning_contract(
        contract,
        output_dir=tmp_path / "contract",
    )

    assert json_path.exists()
    assert markdown_path.exists()
    assert payload["schema"] == SCORED_ENTRY_ALLOCATION_TUNING_CONTRACT_SCHEMA
    assert "Scored Entry Allocation Tuning" in markdown_path.read_text(encoding="utf-8")

    exit_code = tuning_cli.main(["--mode", "dry-run", "--output-dir", str(tmp_path / "cli-contract")])
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["mode"] == "dry-run"
    assert stdout["optuna_required"] is False
    assert (tmp_path / "cli-contract" / "scored_entry_allocation_tuning_contract.json").exists()


def _entry_event(
    symbol: str,
    *,
    trend: str,
    macd: str,
    raw_momentum: float,
    trade_date: str = "2020-01-02",
    price: float = 10.0,
    industry: str = "bank",
    stock_pool_order: int = 1,
    tradable: bool = True,
) -> dict:
    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "intent_type": "enter",
        "price": price,
        "industry": industry,
        "stock_pool_order": stock_pool_order,
        "tradable": tradable,
        "evidence": {
            "symbol.ma.trend_state": trend,
            "symbol.macd.energy_zone": macd,
            "raw_momentum": raw_momentum,
        },
    }


def _decision_cache_inputs() -> dict:
    return {
        "data_snapshot_identity": "snapshot-2015-2024-qfq",
        "stock_pool_identity": "csi300-csi500-freeze-20250101",
        "strategy_signal_parameters": {"template": "baoma_v1", "entry": "baoma_entry"},
        "factor_field_set": ["symbol.ma.trend_state", "symbol.macd.energy_zone", "market.stage"],
        "date_range": {"start": "2015-01-01", "end": "2024-12-31"},
        "event_schema_version": 1,
    }


def _rank_event(
    symbol: str,
    *,
    rank_bucket: str,
    industry: str,
    stock_pool_order: int,
    trade_date: str = "2020-01-02",
    price: float = 10.0,
    tradable: bool = True,
    window: str | None = None,
) -> dict:
    event = {
        "symbol": symbol,
        "trade_date": trade_date,
        "intent_type": "enter",
        "price": price,
        "industry": industry,
        "stock_pool_order": stock_pool_order,
        "tradable": tradable,
        "evidence": {"rank_bucket": rank_bucket},
    }
    if window is not None:
        event["window"] = window
    return event


def _exit_event(
    symbol: str,
    *,
    trade_date: str,
    price: float,
    industry: str,
) -> dict:
    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "intent_type": "exit_profit",
        "price": price,
        "industry": industry,
        "stock_pool_order": 0,
        "tradable": True,
        "evidence": {"exit": "profit"},
    }


def _trial(
    trial_id: str,
    *,
    annualized_return: float,
    sharpe_ratio: float,
    excess: float,
    max_drawdown: float,
    trade_count: int = 60,
    turnover: float = 1.0,
    weights: dict | None = None,
) -> dict:
    return {
        "trial_id": trial_id,
        "parameters": {"weights": weights or {"f1": 1.0}},
        "metrics": {
            "annualized_return": annualized_return,
            "sharpe_ratio": sharpe_ratio,
            "benchmark_excess_return": excess,
            "max_drawdown": max_drawdown,
            "calmar_ratio": annualized_return / max_drawdown if max_drawdown else 0.0,
            "sortino_ratio": sharpe_ratio,
            "trade_count": trade_count,
            "turnover": turnover,
            "yearly_stability": 0.8,
            "funnel_counts": {"executed_entries": trade_count},
        },
    }
