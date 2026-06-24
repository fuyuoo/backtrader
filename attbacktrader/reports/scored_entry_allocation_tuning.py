"""Scored entry allocation tuning contracts and reports."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCORED_ENTRY_ALLOCATION_TUNING_CONTRACT_SCHEMA = "attbacktrader.scored_entry_allocation_tuning_contract.v1"
SCORED_ENTRY_ALLOCATION_TUNING_REPORT_SCHEMA = "attbacktrader.scored_entry_allocation_tuning_report.v1"
FIXED_PARAMETER_SCORED_PORTFOLIO_SMOKE_RUN_SCHEMA = "attbacktrader.fixed_parameter_scored_portfolio_smoke_run.v1"
SCORED_PORTFOLIO_BASELINE_COMPARISON_SCHEMA = "attbacktrader.scored_portfolio_baseline_comparison.v1"
SINGLE_FOLD_STAGE_A_PRE_TUNING_SCHEMA = "attbacktrader.single_fold_stage_a_pre_tuning.v1"
SINGLE_FOLD_STAGE_B_TUNING_SCHEMA = "attbacktrader.single_fold_stage_b_tuning.v1"
FULL_WALK_FORWARD_TUNING_RUN_SCHEMA = "attbacktrader.full_walk_forward_tuning_run.v1"
SCORED_ALLOCATION_REPORT_PACKAGE_SCHEMA = "attbacktrader.scored_allocation_report_package.v1"
STRATEGY_DECISION_EVENT_TABLE_SCHEMA = "attbacktrader.strategy_decision_event_table.v1"

_SUPPORTED_MODES = {"dry-run", "smoke", "standard", "sensitivity"}
_OBJECTIVES = ("annualized_return", "sharpe_ratio", "benchmark_excess_return", "max_drawdown")
_DECISION_CACHE_KEY_FIELDS = (
    "data_snapshot_identity",
    "stock_pool_identity",
    "strategy_signal_parameters",
    "factor_field_set",
    "date_range",
    "event_schema_version",
)
_TRIAL_SPECIFIC_CACHE_FIELDS = {
    "scorer_weights",
    "trial_id",
    "score_gate",
    "score_thresholds",
    "minimum_score_z",
    "minimum_score_quantile",
}
_FORBIDDEN_DECISION_EVENT_FIELDS = {
    "completed_trade_id",
    "completed_trade",
    "closed_trade",
    "cash",
    "position",
    "positions",
    "equity_curve",
    "trial_score",
    "trial_id",
    "selected_buy",
}
_ACTIONABLE_INTENTS = {"enter", "exit", "exit_profit", "exit_loss", "add_on"}
_CORE_PORTFOLIO_METRICS = (
    "cumulative_return",
    "annualized_return",
    "max_drawdown",
    "sharpe_ratio",
    "trade_count",
    "win_rate",
    "profit_loss_ratio",
)
_REPORT_METRIC_KEYS = (
    "cumulative_return",
    "annualized_return",
    "monthly_returns",
    "yearly_returns",
    "benchmark_excess_return",
    "max_drawdown",
    "annualized_volatility",
    "downside_volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "information_ratio",
    "trade_count",
    "win_rate",
    "profit_loss_ratio",
    "profit_factor",
    "average_trade_return",
    "median_trade_return",
    "average_holding_days",
    "average_cash_ratio",
    "average_exposure",
    "turnover",
    "fee_slippage_ratio",
    "single_symbol_maximum_weight",
    "industry_concentration",
)
_STAGE_BASELINE_REGIMES = {
    "stage_a": "broad_high_capacity_unscored_candidate_filling",
    "stage_b": "realistic_constraints_fixed_stock_pool_order",
}
_UNSCORED_BASELINE_SCORE_GATE = {
    "minimum_score_z": -1_000_000.0,
    "minimum_score_quantile": 0.0,
}
_WINDOW_ROLE_FIELDS = ("window", "fold_role", "sample_role", "fold_window")
_TEST_WINDOW_ROLE_VALUES = {"test", "oos", "out_of_sample", "validation"}


def build_scored_entry_allocation_tuning_contract(
    *,
    mode: str = "dry-run",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Describe the scored entry allocation tuning workflow without running it."""

    if mode not in _SUPPORTED_MODES:
        raise ValueError(f"mode must be one of {', '.join(sorted(_SUPPORTED_MODES))}")

    return {
        "schema": SCORED_ENTRY_ALLOCATION_TUNING_CONTRACT_SCHEMA,
        "mode": mode,
        "optuna_required": mode != "dry-run",
        "output_dir": str(output_dir) if output_dir is not None else str(Path("reports") / "scored-entry-allocation-tuning"),
        "folds": build_walk_forward_folds(),
        "stages": {
            "stage_a": {
                "name": "trade_sample_parameter_pre_tuning",
                "standard_trials_per_fold": 300,
                "smoke_trials_per_fold": 10,
                "score_gate": {
                    "minimum_score_z": 0.0,
                    "minimum_score_quantile": 0.50,
                },
                "portfolio_controls": {
                    "initial_cash": 1_000_000_000,
                    "max_holding_count": 800,
                    "max_new_positions_per_day": None,
                    "cash_reserve_ratio": 0.0,
                    "industry_max_new_per_day": None,
                },
                "evidence_use": "pre_tuning_only",
            },
            "stage_b": {
                "name": "scored_portfolio_parameter_tuning",
                "standard_trials_per_fold": 300,
                "smoke_trials_per_fold": 10,
                "score_gate": {
                    "minimum_score_z": 0.75,
                    "minimum_score_quantile": 0.70,
                },
                "portfolio_controls": {
                    "initial_cash": 10_000_000,
                    "max_holding_count": 20,
                    "max_new_positions_per_day": 3,
                    "cash_reserve_ratio": 0.05,
                    "industry_max_new_per_day": 1,
                },
                "evidence_use": "portfolio_validation",
            },
        },
        "trade_count_gates": {
            "train_per_year": 50,
            "test_per_year": 20,
            "full_out_of_sample_total": 120,
        },
        "objectives": list(_OBJECTIVES),
        "secondary_metrics": [
            "cumulative_return",
            "monthly_returns",
            "yearly_returns",
            "annualized_volatility",
            "downside_volatility",
            "maximum_monthly_loss",
            "drawdown_recovery_days",
            "sortino_ratio",
            "calmar_ratio",
            "information_ratio",
            "trade_count",
            "win_rate",
            "profit_loss_ratio",
            "profit_factor",
            "average_trade_return",
            "median_trade_return",
            "average_win_return",
            "average_loss_return",
            "maximum_win_trade",
            "maximum_loss_trade",
            "average_holding_days",
            "average_holding_count",
            "maximum_holding_count",
            "average_cash_ratio",
            "average_exposure",
            "turnover",
            "fee_slippage_ratio",
            "single_symbol_maximum_weight",
            "industry_concentration",
            "funnel_counts",
        ],
        "decision_cache": {
            "stores": [
                "actionable decision intents",
                "decision-time evidence",
                "symbol-date rows",
            ],
            "forbidden": [
                "completed trades",
                "trial-specific scores",
                "cash",
                "positions",
                "equity curves",
                "selected buys",
            ],
            "cache_key_excludes": [
                "scorer_weights",
                "trial_id",
            ],
        },
        "simulation_cache": {
            "cache_key_includes": [
                "signal_cache_identity",
                "fold_id",
                "parameter_hash",
                "portfolio_control_hash",
                "simulator_version",
            ],
        },
        "outputs": [
            "pareto_frontier",
            "balanced_parameters",
            "aggressive_parameters",
            "defensive_parameters",
            "scored_entry_funnel",
        ],
    }


def build_walk_forward_folds(
    *,
    first_train_year: int = 2015,
    last_test_year: int = 2024,
    train_years: int = 5,
) -> list[dict[str, Any]]:
    if train_years <= 0:
        raise ValueError("train_years must be positive")
    first_test_year = first_train_year + train_years
    if last_test_year < first_test_year:
        raise ValueError("last_test_year must be at least first_train_year + train_years")

    folds: list[dict[str, Any]] = []
    for test_year in range(first_test_year, last_test_year + 1):
        train_start = test_year - train_years
        train_end = test_year - 1
        train_year_list = list(range(train_start, train_end + 1))
        folds.append(
            {
                "fold_id": f"train-{train_start}-{train_end}_test-{test_year}",
                "train": {
                    "start": f"{train_start}-01-01",
                    "end": f"{train_end}-12-31",
                    "years": train_year_list,
                },
                "test": {
                    "start": f"{test_year}-01-01",
                    "end": f"{test_year}-12-31",
                    "year": test_year,
                    "years": [test_year],
                },
            }
        )
    return folds


def render_scored_entry_allocation_tuning_contract_markdown(contract: Mapping[str, Any]) -> str:
    stages = _as_mapping(contract.get("stages"))
    stage_a = _as_mapping(stages.get("stage_a"))
    stage_b = _as_mapping(stages.get("stage_b"))
    lines = [
        "# Scored Entry Allocation Tuning Contract",
        "",
        f"- schema: `{contract.get('schema')}`",
        f"- mode: `{contract.get('mode')}`",
        f"- optuna_required: `{contract.get('optuna_required')}`",
        f"- output_dir: `{contract.get('output_dir')}`",
        "",
        "## Walk-Forward Folds",
        "",
        "| fold_id | train | test |",
        "|---|---|---|",
    ]
    for fold in _as_sequence(contract.get("folds")):
        item = _as_mapping(fold)
        train = _as_mapping(item.get("train"))
        test = _as_mapping(item.get("test"))
        lines.append(f"| `{item.get('fold_id')}` | {train.get('start')} to {train.get('end')} | {test.get('start')} to {test.get('end')} |")
    lines.extend(
        [
            "",
            "## Stage Defaults",
            "",
            f"- Stage A score gate: `{_jsonable(stage_a.get('score_gate'))}`",
            f"- Stage B score gate: `{_jsonable(stage_b.get('score_gate'))}`",
            f"- Stage B portfolio controls: `{_jsonable(stage_b.get('portfolio_controls'))}`",
            "",
            "## Evidence Contract",
        ]
    )
    decision_cache = _as_mapping(contract.get("decision_cache"))
    for item in _as_sequence(decision_cache.get("forbidden")):
        lines.append(f"- Must not cache: `{item}`")
    lines.append("")
    return "\n".join(lines)


def write_scored_entry_allocation_tuning_contract(
    contract: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, dict[str, Any]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "scored_entry_allocation_tuning_contract.json"
    markdown_path = output_path / "scored_entry_allocation_tuning_contract.md"
    payload = _jsonable(dict(contract))
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["contract_json"] = str(json_path)
    artifacts["contract_markdown"] = str(markdown_path)
    payload["artifacts"] = artifacts
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_scored_entry_allocation_tuning_contract_markdown(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def build_strategy_decision_cache_identity(cache_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Build the reusable signal cache identity, excluding trial-specific scorer state."""

    inputs = {field: _jsonable(cache_inputs.get(field)) for field in _DECISION_CACHE_KEY_FIELDS}
    missing = [field for field, value in inputs.items() if value is None]
    if missing:
        raise ValueError(f"missing decision cache identity fields: {', '.join(missing)}")
    return {
        "schema": "attbacktrader.strategy_decision_cache_identity.v1",
        "inputs": inputs,
        "excluded_fields": sorted(_TRIAL_SPECIFIC_CACHE_FIELDS),
        "cache_key": _stable_hash(inputs),
    }


def build_strategy_decision_event_table(
    events: Sequence[Mapping[str, Any]],
    *,
    cache_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a reusable decision-event table from actionable intent evidence."""

    normalized = [_normalize_decision_event(event) for event in events]
    normalized.sort(key=lambda event: (str(event["trade_date"]), str(event["symbol"]), str(event["intent_type"])))
    return {
        "schema": STRATEGY_DECISION_EVENT_TABLE_SCHEMA,
        "cache_identity": build_strategy_decision_cache_identity(cache_inputs),
        "event_count": len(normalized),
        "events": normalized,
        "stores": [
            "actionable decision intents",
            "decision-time evidence",
        ],
        "forbidden": sorted(_FORBIDDEN_DECISION_EVENT_FIELDS),
    }


def build_strategy_decision_event_table_from_intents(
    intents: Sequence[Any],
    *,
    cache_inputs: Mapping[str, Any],
    market_context_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a Strategy Decision Event Table from strategy TradeIntent objects."""

    events: list[dict[str, Any]] = []
    for intent in intents:
        intent_type = _intent_type_value(getattr(intent, "intent_type", ""))
        if intent_type not in _ACTIONABLE_INTENTS:
            continue
        context = _market_context_for_intent(intent, market_context_by_key)
        events.append(
            {
                "symbol": str(getattr(intent, "symbol")),
                "trade_date": _date_value(getattr(intent, "trade_date")),
                "intent_type": intent_type,
                "price": context["price"],
                "industry": context.get("industry"),
                "stock_pool_order": context.get("stock_pool_order", 0),
                "tradable": context.get("tradable", True),
                "evidence": _decision_evidence_from_signal_values(
                    _as_mapping(getattr(intent, "signal_values", {}))
                ),
            }
        )
    return build_strategy_decision_event_table(events, cache_inputs=cache_inputs)


def build_strategy_decision_event_table_from_signal_audit(
    signal_audit: Any,
    *,
    cache_inputs: Mapping[str, Any],
    stock_pool_order_by_symbol: Mapping[str, int],
) -> dict[str, Any]:
    """Build a Strategy Decision Event Table from a persisted full signal_audit JSON payload."""

    rows = _full_signal_audit_rows(signal_audit)
    events: list[dict[str, Any]] = []
    for row in rows:
        item = _as_mapping(row)
        intent_type = _intent_type_value(item.get("intent_type", ""))
        if intent_type not in _ACTIONABLE_INTENTS:
            continue
        symbol = str(item.get("symbol") or "")
        trade_date = str(item.get("trade_date") or "")
        if not symbol or not trade_date:
            raise ValueError("signal_audit actionable rows must include symbol and trade_date")
        stock_pool_order = stock_pool_order_by_symbol.get(symbol)
        if stock_pool_order is None:
            raise ValueError(f"missing stock pool order for signal_audit symbol: {symbol}")
        evidence = _decision_evidence_from_signal_values(_as_mapping(item.get("signal_values")))
        events.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "intent_type": intent_type,
                "price": _signal_audit_row_price(item, evidence),
                "industry": evidence.get("industry.sw_l1.code") or evidence.get("industry"),
                "stock_pool_order": stock_pool_order,
                "tradable": item.get("tradable", True),
                "evidence": evidence,
            }
        )
    return build_strategy_decision_event_table(events, cache_inputs=cache_inputs)


def score_entry_candidates(
    events: Sequence[Mapping[str, Any]],
    *,
    scorer_config: Mapping[str, Any],
    training_events: Sequence[Mapping[str, Any]],
    score_gate: Mapping[str, Any],
) -> dict[str, Any]:
    """Score entry candidates and apply training-window z-score/quantile gates."""

    fitted_gate = fit_training_score_gate_statistics(
        training_events,
        scorer_config=scorer_config,
        score_gate=score_gate,
    )
    return apply_fitted_score_gate_to_candidates(
        events,
        scorer_config=scorer_config,
        fitted_score_gate=fitted_gate,
    )


def fit_training_score_gate_statistics(
    training_events: Sequence[Mapping[str, Any]],
    *,
    scorer_config: Mapping[str, Any],
    score_gate: Mapping[str, Any],
) -> dict[str, Any]:
    """Fit score-gate statistics from training-window events only."""

    if not training_events:
        raise ValueError("training_events cannot be empty")
    _assert_no_test_window_threshold_source(training_events)
    training_scores = [_score_event(event, scorer_config)["score"] for event in training_events]
    stats = _score_distribution(training_scores)
    z_floor = _float_required(score_gate, "minimum_score_z")
    quantile = _float_required(score_gate, "minimum_score_quantile")
    if not 0 <= quantile <= 1:
        raise ValueError("minimum_score_quantile must be in [0, 1]")
    quantile_threshold = _quantile(training_scores, quantile)
    z_threshold = stats["mean"] + z_floor * stats["std"]
    threshold = max(z_threshold, quantile_threshold)

    return {
        "minimum_score_z": z_floor,
        "minimum_score_quantile": quantile,
        "mean": stats["mean"],
        "std": stats["std"],
        "z_threshold": z_threshold,
        "quantile_threshold": quantile_threshold,
        "threshold": threshold,
        "derived_from": "training_window",
        "source_event_count": len(training_events),
        "source_window": "training",
    }


def apply_fitted_score_gate_to_candidates(
    events: Sequence[Mapping[str, Any]],
    *,
    scorer_config: Mapping[str, Any],
    fitted_score_gate: Mapping[str, Any],
) -> dict[str, Any]:
    """Score candidate events using pre-fitted training-window score-gate statistics."""

    threshold = _float_required(fitted_score_gate, "threshold")
    rows: list[dict[str, Any]] = []
    for event in events:
        scored = _score_event(event, scorer_config)
        rows.append(
            {
                **_candidate_public_fields(event),
                "score": scored["score"],
                "score_gate_passed": scored["score"] >= threshold,
                "contributions": scored["contributions"],
            }
        )
    rows.sort(key=lambda row: (-float(row["score"]), str(row["trade_date"]), int(row["stock_pool_order"]), str(row["symbol"])))
    return {
        "score_gate": _jsonable(dict(fitted_score_gate)),
        "rows": rows,
    }


def simulate_scored_portfolio(
    events: Sequence[Mapping[str, Any]],
    *,
    scorer_config: Mapping[str, Any],
    training_events: Sequence[Mapping[str, Any]],
    score_gate: Mapping[str, Any],
    portfolio_controls: Mapping[str, Any],
    unscored_baseline: bool = False,
) -> dict[str, Any]:
    """Run a deterministic scored portfolio simulation from decision events."""

    initial_cash = _positive_float(portfolio_controls, "initial_cash")
    max_holding_count = _positive_int(portfolio_controls, "max_holding_count")
    max_new_positions_per_day = _optional_positive_int(portfolio_controls.get("max_new_positions_per_day"))
    industry_max_new_per_day = _optional_positive_int(portfolio_controls.get("industry_max_new_per_day"))
    cash_reserve_ratio = float(portfolio_controls.get("cash_reserve_ratio", 0.0))
    if not 0 <= cash_reserve_ratio < 1:
        raise ValueError("cash_reserve_ratio must be in [0, 1)")
    board_lot_size = int(portfolio_controls.get("board_lot_size") or 100)
    if board_lot_size <= 0:
        raise ValueError("board_lot_size must be positive")

    normalized_events = [_normalize_decision_event(event) for event in events]
    scored = score_entry_candidates(
        [event for event in normalized_events if event["intent_type"] == "enter"],
        scorer_config=scorer_config,
        training_events=[event for event in training_events if str(event.get("intent_type")) == "enter"],
        score_gate=score_gate,
    )
    scores_by_key = {
        (row["symbol"], row["trade_date"]): row
        for row in scored["rows"]
    }
    return _simulate_scored_portfolio_from_normalized(
        normalized_events=normalized_events,
        scores_by_key=scores_by_key,
        scored_gate=scored["score_gate"],
        portfolio_controls=portfolio_controls,
        initial_cash=initial_cash,
        max_holding_count=max_holding_count,
        max_new_positions_per_day=max_new_positions_per_day,
        industry_max_new_per_day=industry_max_new_per_day,
        cash_reserve_ratio=cash_reserve_ratio,
        board_lot_size=board_lot_size,
        unscored_baseline=unscored_baseline,
    )


def run_fixed_parameter_scored_portfolio_smoke(
    decision_event_table: Mapping[str, Any],
    *,
    fold_id: str,
    scorer_config: Mapping[str, Any],
    score_gate: Mapping[str, Any],
    portfolio_controls: Mapping[str, Any],
    training_events: Sequence[Mapping[str, Any]] | None = None,
    simulator_version: str = "scored_portfolio_simulator.v1",
    unscored_baseline: bool = False,
    stage: str | None = None,
) -> dict[str, Any]:
    """Run the fixed-parameter smoke path from a cached decision-event table."""

    if decision_event_table.get("schema") != STRATEGY_DECISION_EVENT_TABLE_SCHEMA:
        raise ValueError("decision_event_table must use the Strategy Decision Event Table schema")
    cache_identity = _as_mapping(decision_event_table.get("cache_identity"))
    signal_cache_key = cache_identity.get("cache_key")
    if not signal_cache_key:
        raise ValueError("decision_event_table.cache_identity.cache_key is required")

    events = [_normalize_decision_event(event) for event in _as_sequence(decision_event_table.get("events"))]
    if not events:
        raise ValueError("decision_event_table.events cannot be empty for smoke simulation")
    training = list(training_events) if training_events is not None else events
    simulation = simulate_scored_portfolio(
        events,
        scorer_config=scorer_config,
        training_events=training,
        score_gate=score_gate,
        portfolio_controls=portfolio_controls,
        unscored_baseline=unscored_baseline,
    )
    parameters = {
        "scorer_config": _jsonable(dict(scorer_config)),
        "score_gate": _jsonable(dict(score_gate)),
        "unscored_baseline": unscored_baseline,
    }
    simulation_cache_identity = build_simulation_cache_identity(
        signal_cache_identity=str(signal_cache_key),
        fold_id=fold_id,
        parameters=parameters,
        portfolio_controls=portfolio_controls,
        simulator_version=simulator_version,
    )
    return {
        "schema": FIXED_PARAMETER_SCORED_PORTFOLIO_SMOKE_RUN_SCHEMA,
        "fold_id": fold_id,
        "stage": stage,
        "result_type": "unscored_baseline" if unscored_baseline else "scored",
        "decision_cache_identity": _jsonable(dict(cache_identity)),
        "simulation_cache_identity": simulation_cache_identity,
        "fixed_parameters": parameters,
        "portfolio_controls": _jsonable(dict(portfolio_controls)),
        "selected_entries": _jsonable(simulation["executed_entries"]),
        "cash_movements": _jsonable(simulation["cash_movements"]),
        "position_snapshots": _jsonable(simulation["position_snapshots"]),
        "equity_curve": _jsonable(simulation["equity_curve"]),
        "blocked_entries": _jsonable(simulation["blocked_entries"]),
        "closed_trades": _jsonable(simulation["closed_trades"]),
        "funnel": _jsonable(simulation["funnel"]),
        "core_metrics": _core_portfolio_metrics(_as_mapping(simulation["metrics"])),
        "metrics": _jsonable(simulation["metrics"]),
        "simulation": _jsonable(simulation),
    }


def run_scored_portfolio_baseline_comparison(
    decision_event_table: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    fold_id: str,
    scorer_config: Mapping[str, Any],
    training_events: Sequence[Mapping[str, Any]] | None = None,
    score_gate_by_stage: Mapping[str, Mapping[str, Any]] | None = None,
    portfolio_controls_by_stage: Mapping[str, Mapping[str, Any]] | None = None,
    simulator_version: str = "scored_portfolio_simulator.v1",
) -> dict[str, Any]:
    """Run Stage A/B scored smoke results and matching unscored baselines."""

    stage_results: dict[str, Any] = {}
    for stage in ("stage_a", "stage_b"):
        default_score_gate, default_controls = _stage_score_gate_and_controls(contract, stage)
        score_gate = _stage_override_or_default(score_gate_by_stage, stage, default_score_gate)
        portfolio_controls = _stage_override_or_default(portfolio_controls_by_stage, stage, default_controls)
        scored = run_fixed_parameter_scored_portfolio_smoke(
            decision_event_table,
            fold_id=fold_id,
            scorer_config=scorer_config,
            score_gate=score_gate,
            portfolio_controls=portfolio_controls,
            training_events=training_events,
            simulator_version=simulator_version,
            unscored_baseline=False,
            stage=stage,
        )
        baseline = run_fixed_parameter_scored_portfolio_smoke(
            decision_event_table,
            fold_id=fold_id,
            scorer_config=scorer_config,
            score_gate=_UNSCORED_BASELINE_SCORE_GATE,
            portfolio_controls=portfolio_controls,
            training_events=training_events,
            simulator_version=simulator_version,
            unscored_baseline=True,
            stage=stage,
        )
        stage_results[stage] = {
            "stage": stage,
            "constraint_regime": _STAGE_BASELINE_REGIMES[stage],
            "portfolio_controls": _jsonable(dict(portfolio_controls)),
            "score_gate": _jsonable(dict(score_gate)),
            "baseline_score_gate": dict(_UNSCORED_BASELINE_SCORE_GATE),
            "scored": scored,
            "unscored_baseline": baseline,
            "core_metric_delta_vs_baseline": _core_metric_delta(
                _as_mapping(scored["core_metrics"]),
                _as_mapping(baseline["core_metrics"]),
            ),
        }

    return {
        "schema": SCORED_PORTFOLIO_BASELINE_COMPARISON_SCHEMA,
        "fold_id": fold_id,
        "core_metric_keys": list(_CORE_PORTFOLIO_METRICS),
        "stages": stage_results,
    }


def run_single_fold_stage_a_pre_tuning(
    decision_event_table: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    fold: Mapping[str, Any],
    trial_parameter_sets: Sequence[Mapping[str, Any]],
    weight_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run one-fold Stage A pre-tuning under broad trade-sample constraints."""

    if not trial_parameter_sets:
        raise ValueError("trial_parameter_sets cannot be empty")
    fold_id = str(fold.get("fold_id") or "")
    if not fold_id:
        raise ValueError("fold.fold_id is required")
    score_gate, portfolio_controls = _stage_score_gate_and_controls(contract, "stage_a")
    training_events = _decision_events_for_fold_window(decision_event_table, fold, window="train")
    if not training_events:
        raise ValueError(f"fold {fold_id} has no training decision events")

    trials: list[dict[str, Any]] = []
    for index, trial_parameters in enumerate(trial_parameter_sets, start=1):
        item = _as_mapping(trial_parameters)
        trial_id = str(item.get("trial_id") or f"stage-a-{index:03d}")
        scorer_config = _trial_scorer_config(item)
        simulation = simulate_scored_portfolio(
            training_events,
            scorer_config=scorer_config,
            training_events=training_events,
            score_gate=score_gate,
            portfolio_controls=portfolio_controls,
        )
        weights = _flatten_scorer_weights(scorer_config)
        metrics = dict(_as_mapping(simulation.get("metrics")))
        metrics["funnel_counts"] = _jsonable(simulation.get("funnel") or {})
        objectives = {key: metrics.get(key, 0.0) for key in _OBJECTIVES}
        trials.append(
            {
                "trial_id": trial_id,
                "fold_id": fold_id,
                "stage": "stage_a",
                "parameters": {
                    "weights": weights,
                    "scorer_config": _jsonable(dict(scorer_config)),
                },
                "objectives": _jsonable(objectives),
                "metrics": _jsonable(metrics),
                "funnel": _jsonable(simulation.get("funnel") or {}),
                "selected_entry_count": len(_as_sequence(simulation.get("executed_entries"))),
            }
        )

    inferred_weight_keys = list(weight_keys or _infer_weight_keys(trials))
    if not inferred_weight_keys:
        raise ValueError("Stage A pre-tuning requires at least one scorer weight")
    pareto_frontier = _pareto_frontier(trials)
    balanced_top = _balanced_top_trials(trials)
    elite_by_id = {str(trial["trial_id"]): trial for trial in [*pareto_frontier, *balanced_top]}
    elite_trials = list(elite_by_id.values())
    return {
        "schema": SINGLE_FOLD_STAGE_A_PRE_TUNING_SCHEMA,
        "fold_id": fold_id,
        "stage": "stage_a",
        "evidence_use": "pre_tuning_only",
        "optimizer": {
            "engine": "trial_parameter_sets",
            "optuna_objectives": list(_OBJECTIVES),
            "standard_trials_per_fold": _as_mapping(_as_mapping(contract.get("stages")).get("stage_a")).get("standard_trials_per_fold"),
            "executed_trial_count": len(trials),
        },
        "score_gate": _jsonable(dict(score_gate)),
        "portfolio_controls": _jsonable(dict(portfolio_controls)),
        "objective_keys": list(_OBJECTIVES),
        "trial_count": len(trials),
        "trials": _jsonable(trials),
        "pareto_frontier": _jsonable(pareto_frontier),
        "balanced_top_20_percent": _jsonable(balanced_top),
        "elite_trial_ids": sorted(elite_by_id),
        "elite_trials": _jsonable(elite_trials),
        "direction_stability": _direction_stability(trials, weight_keys=inferred_weight_keys),
        "stage_b_search_space": build_stage_b_search_space_from_stage_a(trials, weight_keys=inferred_weight_keys),
    }


def run_single_fold_stage_b_tuning(
    decision_event_table: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    fold: Mapping[str, Any],
    stage_b_search_space: Mapping[str, Any],
    trial_parameter_sets: Sequence[Mapping[str, Any]],
    minimum_train_trades_per_year: int | None = None,
) -> dict[str, Any]:
    """Run one-fold Stage B scored portfolio tuning under realistic constraints."""

    if not trial_parameter_sets:
        raise ValueError("trial_parameter_sets cannot be empty")
    fold_id = str(fold.get("fold_id") or "")
    if not fold_id:
        raise ValueError("fold.fold_id is required")
    score_gate, portfolio_controls = _stage_score_gate_and_controls(contract, "stage_b")
    training_events = _decision_events_for_fold_window(decision_event_table, fold, window="train")
    if not training_events:
        raise ValueError(f"fold {fold_id} has no training decision events")
    test_events = _decision_events_for_fold_window(decision_event_table, fold, window="test")
    if not test_events:
        raise ValueError(f"fold {fold_id} has no test decision events")
    baseline_simulation = simulate_scored_portfolio(
        training_events,
        scorer_config=_baseline_scorer_config(training_events),
        training_events=training_events,
        score_gate=_UNSCORED_BASELINE_SCORE_GATE,
        portfolio_controls=portfolio_controls,
        unscored_baseline=True,
    )

    trials: list[dict[str, Any]] = []
    for index, trial_parameters in enumerate(trial_parameter_sets, start=1):
        item = _as_mapping(trial_parameters)
        trial_id = str(item.get("trial_id") or f"stage-b-{index:03d}")
        scorer_config = _trial_scorer_config(item)
        weights = _flatten_scorer_weights(scorer_config)
        _assert_trial_within_stage_b_search_space(weights, stage_b_search_space)
        simulation = simulate_scored_portfolio(
            training_events,
            scorer_config=scorer_config,
            training_events=training_events,
            score_gate=score_gate,
            portfolio_controls=portfolio_controls,
        )
        metrics = dict(_as_mapping(simulation.get("metrics")))
        metrics["funnel_counts"] = _jsonable(simulation.get("funnel") or {})
        metrics["core_metric_delta_vs_unscored_baseline"] = _core_metric_delta(
            _core_portfolio_metrics(_as_mapping(metrics)),
            _core_portfolio_metrics(_as_mapping(baseline_simulation.get("metrics"))),
        )
        objectives = {key: metrics.get(key, 0.0) for key in _OBJECTIVES}
        trials.append(
            {
                "trial_id": trial_id,
                "fold_id": fold_id,
                "stage": "stage_b",
                "parameters": {
                    "weights": weights,
                    "scorer_config": _jsonable(dict(scorer_config)),
                },
                "objectives": _jsonable(objectives),
                "metrics": _jsonable(metrics),
                "funnel": _jsonable(simulation.get("funnel") or {}),
                "selected_entry_count": len(_as_sequence(simulation.get("executed_entries"))),
            }
        )

    gate_config = _stage_b_trade_count_gate(
        contract,
        fold,
        minimum_train_trades_per_year=minimum_train_trades_per_year,
    )
    eligible, rejected = _eligible_trials(trials, min_trade_count=gate_config["minimum_train_trade_count"])
    recommendations = _select_recommendations(eligible)
    recommendations["rejected"] = _jsonable(rejected)
    out_of_sample = _evaluate_stage_b_out_of_sample(
        fold=fold,
        training_events=training_events,
        test_events=test_events,
        recommendations=recommendations,
        portfolio_controls=portfolio_controls,
        score_gate=score_gate,
    )
    return {
        "schema": SINGLE_FOLD_STAGE_B_TUNING_SCHEMA,
        "fold_id": fold_id,
        "stage": "stage_b",
        "evidence_use": "portfolio_validation",
        "score_gate": _jsonable(dict(score_gate)),
        "portfolio_controls": _jsonable(dict(portfolio_controls)),
        "stage_b_search_space": _jsonable(dict(stage_b_search_space)),
        "baseline": {
            "result_type": "unscored_baseline",
            "portfolio_controls": _jsonable(dict(portfolio_controls)),
            "metrics": _jsonable(baseline_simulation.get("metrics") or {}),
            "funnel": _jsonable(baseline_simulation.get("funnel") or {}),
            "core_metrics": _core_portfolio_metrics(_as_mapping(baseline_simulation.get("metrics"))),
        },
        "objective_keys": list(_OBJECTIVES),
        "trade_count_gates": gate_config,
        "trial_count": len(trials),
        "eligible_trial_count": len(eligible),
        "rejected_trial_count": len(rejected),
        "trials": _jsonable(trials),
        "eligible_trials": _jsonable(eligible),
        "rejected_trials": _jsonable(rejected),
        "pareto_frontier": _pareto_frontier(eligible),
        "recommendations": recommendations,
        "out_of_sample": out_of_sample,
    }


def _evaluate_stage_b_out_of_sample(
    *,
    fold: Mapping[str, Any],
    training_events: Sequence[Mapping[str, Any]],
    test_events: Sequence[Mapping[str, Any]],
    recommendations: Mapping[str, Any],
    portfolio_controls: Mapping[str, Any],
    score_gate: Mapping[str, Any],
) -> dict[str, Any]:
    test_window = _test_window_boundary(_as_mapping(fold.get("test")))
    baseline_simulation = simulate_scored_portfolio(
        test_events,
        scorer_config=_baseline_scorer_config(training_events),
        training_events=training_events,
        score_gate=_UNSCORED_BASELINE_SCORE_GATE,
        portfolio_controls=portfolio_controls,
        unscored_baseline=True,
    )
    baseline_metrics = _as_mapping(baseline_simulation.get("metrics"))
    baseline_core = _core_portfolio_metrics(baseline_metrics)
    evaluated: dict[str, Any] = {}

    for name in ("balanced", "aggressive", "defensive"):
        recommendation = recommendations.get(name)
        if not recommendation:
            evaluated[name] = None
            continue
        item = _as_mapping(recommendation)
        parameters = _as_mapping(item.get("parameters"))
        scorer_config = _as_mapping(parameters.get("scorer_config"))
        simulation = simulate_scored_portfolio(
            test_events,
            scorer_config=scorer_config,
            training_events=training_events,
            score_gate=score_gate,
            portfolio_controls=portfolio_controls,
        )
        metrics = dict(_as_mapping(simulation.get("metrics")))
        metrics["funnel_counts"] = _jsonable(simulation.get("funnel") or {})
        core_metrics = _core_portfolio_metrics(_as_mapping(metrics))
        metrics["core_metric_delta_vs_unscored_baseline"] = _core_metric_delta(core_metrics, baseline_core)
        evaluated[name] = {
            "trial_id": item.get("trial_id"),
            "parameters": _jsonable(dict(parameters)),
            "test_window": test_window,
            "score_gate": _jsonable(simulation.get("score_gate") or {}),
            "portfolio_controls": _jsonable(simulation.get("portfolio_controls") or {}),
            "metrics": _jsonable(metrics),
            "core_metrics": core_metrics,
            "funnel": _jsonable(simulation.get("funnel") or {}),
            "selected_entry_count": len(_as_sequence(simulation.get("executed_entries"))),
        }

    return {
        "evidence_use": "out_of_sample_portfolio_evaluation",
        "test_window": test_window,
        "baseline": {
            "result_type": "unscored_baseline",
            "portfolio_controls": _jsonable(dict(portfolio_controls)),
            "score_gate": _jsonable(baseline_simulation.get("score_gate") or {}),
            "metrics": _jsonable(baseline_metrics),
            "funnel": _jsonable(baseline_simulation.get("funnel") or {}),
            "core_metrics": baseline_core,
        },
        "recommendations": evaluated,
    }


def run_full_walk_forward_tuning(
    decision_event_table: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    mode: str,
    stage_a_trial_parameter_sets: Sequence[Mapping[str, Any]],
    stage_b_trial_parameter_sets: Sequence[Mapping[str, Any]],
    completed_artifacts: Mapping[str, str] | None = None,
    minimum_train_trades_per_year: int | None = None,
) -> dict[str, Any]:
    """Run or schedule the full 5Y/1Y walk-forward scored allocation flow."""

    if mode not in {"smoke", "standard"}:
        raise ValueError("mode must be smoke or standard")
    cache_identity = _as_mapping(decision_event_table.get("cache_identity"))
    signal_cache_key = str(cache_identity.get("cache_key") or "")
    if not signal_cache_key:
        raise ValueError("decision_event_table.cache_identity.cache_key is required")
    folds = list(_as_sequence(contract.get("folds")))
    stage_a_scheduled = _scheduled_trials(contract, "stage_a", mode)
    stage_b_scheduled = _scheduled_trials(contract, "stage_b", mode)
    completed = _as_mapping(completed_artifacts)
    fold_results: list[dict[str, Any]] = []
    for fold in folds:
        fold_item = _as_mapping(fold)
        fold_id = str(fold_item.get("fold_id") or "")
        artifact_identity = _fold_artifact_identity(
            signal_cache_key=signal_cache_key,
            fold_id=fold_id,
            mode=mode,
            stage_a_scheduled=stage_a_scheduled,
            stage_b_scheduled=stage_b_scheduled,
        )
        test = _as_mapping(fold_item.get("test"))
        if completed.get(fold_id) == artifact_identity:
            fold_results.append(
                {
                    "fold_id": fold_id,
                    "status": "skipped_completed",
                    "artifact_identity": artifact_identity,
                    "decision_cache_key": signal_cache_key,
                    "stage_a": {"status": "skipped_completed", "scheduled_trial_count": stage_a_scheduled},
                    "stage_b": {"status": "skipped_completed", "scheduled_trial_count": stage_b_scheduled},
                    "test_window": _test_window_boundary(test),
                }
            )
            continue

        stage_a_result = run_single_fold_stage_a_pre_tuning(
            decision_event_table,
            contract=contract,
            fold=fold_item,
            trial_parameter_sets=stage_a_trial_parameter_sets,
        )
        stage_b_result = run_single_fold_stage_b_tuning(
            decision_event_table,
            contract=contract,
            fold=fold_item,
            stage_b_search_space=_as_mapping(stage_a_result.get("stage_b_search_space")),
            trial_parameter_sets=stage_b_trial_parameter_sets,
            minimum_train_trades_per_year=minimum_train_trades_per_year,
        )
        fold_results.append(
            {
                "fold_id": fold_id,
                "status": "completed",
                "artifact_identity": artifact_identity,
                "decision_cache_key": signal_cache_key,
                "stage_a": {
                    "status": "completed",
                    "scheduled_trial_count": stage_a_scheduled,
                    "executed_trial_count": stage_a_result["trial_count"],
                    "result": stage_a_result,
                },
                "stage_b": {
                    "status": "completed",
                    "scheduled_trial_count": stage_b_scheduled,
                    "executed_trial_count": stage_b_result["trial_count"],
                    "result": stage_b_result,
                },
                "test_window": _test_window_boundary(test),
            }
        )

    return {
        "schema": FULL_WALK_FORWARD_TUNING_RUN_SCHEMA,
        "mode": mode,
        "fold_count": len(fold_results),
        "test_years": [int(_as_mapping(fold.get("test")).get("year")) for fold in folds],
        "decision_cache_identity": _jsonable(dict(cache_identity)),
        "decision_cache_reuse": {
            "cache_key": signal_cache_key,
            "fold_ids": [fold["fold_id"] for fold in fold_results],
            "same_cache_key_for_all_folds": len({fold["decision_cache_key"] for fold in fold_results}) <= 1,
        },
        "trial_schedule": {
            "stage_a_per_fold": stage_a_scheduled,
            "stage_b_per_fold": stage_b_scheduled,
        },
        "folds": fold_results,
    }


def build_scored_allocation_report_package(run_result: Mapping[str, Any]) -> dict[str, Any]:
    """Build the machine-readable scored allocation report package."""

    if run_result.get("schema") != FULL_WALK_FORWARD_TUNING_RUN_SCHEMA:
        raise ValueError("run_result must use the full walk-forward tuning run schema")
    fold_reports: list[dict[str, Any]] = []
    parameter_sets = {"balanced": [], "aggressive": [], "defensive": []}
    stage_a_pareto: dict[str, Any] = {}
    stage_b_pareto: dict[str, Any] = {}
    stage_b_training_metrics: dict[str, Any] = {}
    baseline_metrics: dict[str, Any] = {}
    stage_b_oos_metrics = {"balanced": {}, "aggressive": {}, "defensive": {}}
    oos_baseline_metrics: dict[str, Any] = {}
    funnel_by_fold: dict[str, Any] = {}
    oos_funnel_by_fold: dict[str, Any] = {}
    yearly_stability: dict[str, Any] = {}
    for fold in _as_sequence(run_result.get("folds")):
        item = _as_mapping(fold)
        fold_id = str(item.get("fold_id"))
        test_window = _as_mapping(item.get("test_window"))
        if item.get("status") != "completed":
            fold_reports.append(
                {
                    "fold_id": fold_id,
                    "status": item.get("status"),
                    "test_window": _jsonable(dict(test_window)),
                }
            )
            continue
        stage_a_result = _as_mapping(_as_mapping(item.get("stage_a")).get("result"))
        stage_b_result = _as_mapping(_as_mapping(item.get("stage_b")).get("result"))
        stage_a_pareto[fold_id] = _jsonable(stage_a_result.get("pareto_frontier") or [])
        stage_b_pareto[fold_id] = _jsonable(stage_b_result.get("pareto_frontier") or [])
        recommendations = _as_mapping(stage_b_result.get("recommendations"))
        for name in ("balanced", "aggressive", "defensive"):
            parameter_sets[name].append(
                {
                    "fold_id": fold_id,
                    "parameters": _jsonable(_as_mapping(_as_mapping(recommendations.get(name)).get("parameters"))),
                    "trial_id": _as_mapping(recommendations.get(name)).get("trial_id"),
                }
            )
        balanced = _as_mapping(recommendations.get("balanced"))
        scored_metrics = _as_mapping(balanced.get("metrics"))
        baseline = _as_mapping(stage_b_result.get("baseline"))
        baseline_metric_values = _as_mapping(baseline.get("metrics"))
        out_of_sample = _as_mapping(stage_b_result.get("out_of_sample"))
        if not out_of_sample:
            raise ValueError(f"fold {fold_id} missing Stage B out_of_sample portfolio evaluation")
        oos_recommendations = _as_mapping(out_of_sample.get("recommendations"))
        oos_baseline = _as_mapping(out_of_sample.get("baseline"))
        if not oos_baseline:
            raise ValueError(f"fold {fold_id} missing Stage B out_of_sample unscored baseline")
        if not _as_mapping(oos_recommendations.get("balanced")):
            raise ValueError(f"fold {fold_id} missing Stage B out_of_sample balanced recommendation")
        oos_baseline_metric_values = _as_mapping(oos_baseline.get("metrics"))
        stage_b_training_metrics[fold_id] = _metric_snapshot(scored_metrics)
        baseline_metrics[fold_id] = _metric_snapshot(baseline_metric_values)
        oos_baseline_metrics[fold_id] = _metric_snapshot(oos_baseline_metric_values)
        for name in ("balanced", "aggressive", "defensive"):
            oos_item = _as_mapping(oos_recommendations.get(name))
            stage_b_oos_metrics[name][fold_id] = _metric_snapshot(_as_mapping(oos_item.get("metrics")))
        funnel_by_fold[fold_id] = _aggregate_funnels(_as_sequence(stage_b_result.get("trials")))
        oos_balanced = _as_mapping(oos_recommendations.get("balanced"))
        oos_funnel_by_fold[fold_id] = _jsonable(_as_mapping(oos_balanced.get("funnel")))
        year = str(test_window.get("year"))
        yearly_stability[year] = {
            "fold_id": fold_id,
            "source": "out_of_sample_balanced",
            "scored": stage_b_oos_metrics["balanced"][fold_id],
            "unscored_baseline": oos_baseline_metrics[fold_id],
        }
        fold_reports.append(
            {
                "fold_id": fold_id,
                "status": "completed",
                "stage_a": {
                    "evidence_use": stage_a_result.get("evidence_use"),
                    "trial_count": stage_a_result.get("trial_count"),
                    "pareto_count": len(_as_sequence(stage_a_result.get("pareto_frontier"))),
                    "elite_trial_ids": _jsonable(stage_a_result.get("elite_trial_ids") or []),
                },
                "stage_b": {
                    "evidence_use": stage_b_result.get("evidence_use"),
                    "trial_count": stage_b_result.get("trial_count"),
                    "eligible_trial_count": stage_b_result.get("eligible_trial_count"),
                    "pareto_count": len(_as_sequence(stage_b_result.get("pareto_frontier"))),
                    "recommendations": {
                        name: _jsonable(_as_mapping(recommendations.get(name)))
                        for name in ("balanced", "aggressive", "defensive")
                    },
                    "baseline": _jsonable(baseline),
                },
                "out_of_sample": {
                    "evidence_use": out_of_sample.get("evidence_use"),
                    "test_window": _jsonable(dict(_as_mapping(out_of_sample.get("test_window")) or test_window)),
                    "evidence_status": "evaluated",
                    "retunes_parameters": False,
                    "refits_score_gate": False,
                    "updates_stage_a_search_space": False,
                    "recommendations": {
                        name: _jsonable(_as_mapping(oos_recommendations.get(name)))
                        for name in ("balanced", "aggressive", "defensive")
                    },
                    "baseline": _jsonable(oos_baseline),
                },
            }
        )

    return {
        "schema": SCORED_ALLOCATION_REPORT_PACKAGE_SCHEMA,
        "mode": run_result.get("mode"),
        "fold_count": run_result.get("fold_count"),
        "metric_keys": list(_REPORT_METRIC_KEYS),
        "warning": "Stage A is pre-tuning evidence only; final conclusions must come from out-of-sample scored portfolio results.",
        "folds": fold_reports,
        "pareto_frontiers": {
            "stage_a": stage_a_pareto,
            "stage_b": stage_b_pareto,
        },
        "recommended_parameter_sets": parameter_sets,
        "metrics": {
            "stage_b_training_scored": stage_b_training_metrics,
            "stage_b_unscored_baseline": baseline_metrics,
            "stage_b_training_unscored_baseline": baseline_metrics,
            "stage_b_oos_scored": stage_b_oos_metrics,
            "stage_b_oos_unscored_baseline": oos_baseline_metrics,
        },
        "stability": {
            "yearly": yearly_stability,
            "market_stage": {
                "status": "not_available_in_current_fixture",
                "missing_reason": "market-stage labels are not present in the deterministic fixture outputs",
            },
        },
        "scored_entry_funnel": {
            "global": _aggregate_funnel_dicts(oos_funnel_by_fold.values()),
            "by_fold": oos_funnel_by_fold,
            "training_by_fold": funnel_by_fold,
            "by_year": {
                str(_as_mapping(fold.get("test_window")).get("year")): oos_funnel_by_fold.get(str(fold.get("fold_id")), {})
                for fold in _as_sequence(run_result.get("folds"))
            },
            "by_market_stage": {
                "status": "not_available_in_current_fixture",
                "missing_reason": "market-stage labels are not present in the deterministic fixture outputs",
            },
            "by_factor_combination_hit_status": {
                "status": "not_available_in_current_fixture",
                "missing_reason": "factor-combination hit labels are not present in the deterministic fixture outputs",
            },
        },
    }


def _format_report_metric(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_scored_allocation_report_package_markdown_zh(package: Mapping[str, Any]) -> str:
    lines = [
        "# Scored Entry Allocation Tuning 报告",
        "",
        "## 关键警告",
        "",
        "- Stage A 只用于预调优和缩小 Stage B 搜索空间，不能当作最终组合收益证据。",
        "- 最终结论必须来自样本外 scored portfolio 结果，并且要和真实约束下的 unscored baseline 对比。",
        "",
        "## 概览",
        "",
        f"- schema: `{package.get('schema')}`",
        f"- mode: `{package.get('mode')}`",
        f"- fold_count: `{package.get('fold_count')}`",
        "",
        "## Stage A 预调优",
        "",
    ]
    for fold in _as_sequence(package.get("folds")):
        item = _as_mapping(fold)
        stage_a = _as_mapping(item.get("stage_a"))
        if stage_a:
            lines.append(
                f"- `{item.get('fold_id')}`: trials={stage_a.get('trial_count')}, "
                f"pareto={stage_a.get('pareto_count')}, elite={len(_as_sequence(stage_a.get('elite_trial_ids')))}"
            )
    lines.extend(["", "## Stage B 训练", ""])
    for fold in _as_sequence(package.get("folds")):
        item = _as_mapping(fold)
        stage_b = _as_mapping(item.get("stage_b"))
        if stage_b:
            recs = _as_mapping(stage_b.get("recommendations"))
            lines.append(
                f"- `{item.get('fold_id')}`: eligible={stage_b.get('eligible_trial_count')}, "
                f"balanced=`{_as_mapping(recs.get('balanced')).get('trial_id')}`, "
                f"aggressive=`{_as_mapping(recs.get('aggressive')).get('trial_id')}`, "
                f"defensive=`{_as_mapping(recs.get('defensive')).get('trial_id')}`"
            )
    lines.extend(["", "## Stage B 样本外组合评估", ""])
    for fold in _as_sequence(package.get("folds")):
        item = _as_mapping(fold)
        oos = _as_mapping(item.get("out_of_sample"))
        test = _as_mapping(oos.get("test_window"))
        if oos:
            recommendations = _as_mapping(oos.get("recommendations"))
            balanced = _as_mapping(recommendations.get("balanced"))
            balanced_core = _as_mapping(balanced.get("core_metrics"))
            baseline = _as_mapping(oos.get("baseline"))
            baseline_core = _as_mapping(baseline.get("core_metrics"))
            lines.append(
                f"- `{item.get('fold_id')}`: test={test.get('start')} to {test.get('end')}, "
                f"status={oos.get('evidence_status')}, retune={oos.get('retunes_parameters')}, "
                f"refit_gate={oos.get('refits_score_gate')}, balanced=`{balanced.get('trial_id')}`, "
                f"ann={_format_report_metric(balanced_core.get('annualized_return'))}, "
                f"sharpe={_format_report_metric(balanced_core.get('sharpe_ratio'))}, "
                f"mdd={_format_report_metric(balanced_core.get('max_drawdown'))}, "
                f"baseline_ann={_format_report_metric(baseline_core.get('annualized_return'))}, "
                f"baseline_sharpe={_format_report_metric(baseline_core.get('sharpe_ratio'))}"
            )
    lines.extend(["", "## 漏斗诊断", ""])
    global_funnel = _as_mapping(_as_mapping(package.get("scored_entry_funnel")).get("global"))
    for key, value in sorted(global_funnel.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 缺失切片说明", ""])
    market_stage = _as_mapping(_as_mapping(package.get("stability")).get("market_stage"))
    lines.append(f"- market-stage stability: {market_stage.get('missing_reason')}")
    factor_slice = _as_mapping(_as_mapping(package.get("scored_entry_funnel")).get("by_factor_combination_hit_status"))
    lines.append(f"- factor/combination funnel slice: {factor_slice.get('missing_reason')}")
    lines.append("")
    return "\n".join(lines)


def write_fixed_parameter_scored_portfolio_smoke_run(
    smoke_run: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, dict[str, Any]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "fixed_parameter_scored_portfolio_smoke_run.json"
    payload = _jsonable(dict(smoke_run))
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["smoke_run_json"] = str(json_path)
    payload["artifacts"] = artifacts
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, payload


def write_scored_portfolio_baseline_comparison(
    comparison: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, dict[str, Any]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "scored_portfolio_baseline_comparison.json"
    payload = _jsonable(dict(comparison))
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["baseline_comparison_json"] = str(json_path)
    payload["artifacts"] = artifacts
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, payload


def write_single_fold_stage_a_pre_tuning(
    stage_a_result: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, dict[str, Any]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "single_fold_stage_a_pre_tuning.json"
    payload = _jsonable(dict(stage_a_result))
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["stage_a_pre_tuning_json"] = str(json_path)
    payload["artifacts"] = artifacts
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, payload


def write_single_fold_stage_b_tuning(
    stage_b_result: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, dict[str, Any]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "single_fold_stage_b_tuning.json"
    payload = _jsonable(dict(stage_b_result))
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["stage_b_tuning_json"] = str(json_path)
    payload["artifacts"] = artifacts
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, payload


def write_full_walk_forward_tuning_run(
    run_result: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, dict[str, Any]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "full_walk_forward_tuning_run.json"
    payload = _jsonable(dict(run_result))
    artifacts = dict(_as_mapping(payload.get("artifacts")))
    artifacts["full_walk_forward_run_json"] = str(json_path)
    payload["artifacts"] = artifacts
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, payload


def write_scored_allocation_report_package(
    package: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[dict[str, Path], dict[str, Any]]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    package_json_path = output_path / "scored_allocation_report_package.json"
    markdown_path = output_path / "scored_allocation_report_package.zh.md"
    pareto_path = output_path / "pareto_frontiers.json"
    parameter_paths = {
        "balanced": output_path / "balanced_parameters.json",
        "aggressive": output_path / "aggressive_parameters.json",
        "defensive": output_path / "defensive_parameters.json",
    }
    payload = _jsonable(dict(package))
    artifacts = {
        "package_json": str(package_json_path),
        "markdown_zh": str(markdown_path),
        "pareto_frontiers_json": str(pareto_path),
        "balanced_parameters_json": str(parameter_paths["balanced"]),
        "aggressive_parameters_json": str(parameter_paths["aggressive"]),
        "defensive_parameters_json": str(parameter_paths["defensive"]),
    }
    payload["artifacts"] = artifacts
    for name, path in parameter_paths.items():
        path.write_text(
            json.dumps(_jsonable(_as_mapping(payload.get("recommended_parameter_sets")).get(name) or []), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    pareto_path.write_text(json.dumps(_jsonable(payload.get("pareto_frontiers") or {}), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_scored_allocation_report_package_markdown_zh(payload), encoding="utf-8")
    package_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    paths = {
        "package_json": package_json_path,
        "markdown_zh": markdown_path,
        "pareto_frontiers_json": pareto_path,
        **{f"{name}_parameters_json": path for name, path in parameter_paths.items()},
    }
    return paths, payload


def _simulate_scored_portfolio_from_normalized(
    *,
    normalized_events: Sequence[Mapping[str, Any]],
    scores_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
    scored_gate: Mapping[str, Any],
    portfolio_controls: Mapping[str, Any],
    initial_cash: float,
    max_holding_count: int,
    max_new_positions_per_day: int | None,
    industry_max_new_per_day: int | None,
    cash_reserve_ratio: float,
    board_lot_size: int,
    unscored_baseline: bool,
) -> dict[str, Any]:
    cash = float(initial_cash)
    positions: dict[str, dict[str, Any]] = {}
    latest_prices: dict[str, float] = {}
    executed_entries: list[dict[str, Any]] = []
    blocked_entries: list[dict[str, Any]] = []
    closed_trades: list[dict[str, Any]] = []
    cash_movements: list[dict[str, Any]] = []
    position_snapshots: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    peak_value = float(initial_cash)
    total_buy_value = 0.0
    funnel = _empty_funnel()

    events_by_date: dict[str, list[Mapping[str, Any]]] = {}
    for event in normalized_events:
        events_by_date.setdefault(str(event["trade_date"]), []).append(event)

    for trade_date in sorted(events_by_date):
        daily_events = events_by_date[trade_date]
        for event in daily_events:
            latest_prices[str(event["symbol"])] = float(event["price"])

        for event in sorted(daily_events, key=lambda item: (item["stock_pool_order"], item["symbol"])):
            if event["intent_type"] == "enter":
                continue
            position = positions.pop(str(event["symbol"]), None)
            if position is None:
                continue
            proceeds = position["quantity"] * float(event["price"])
            cash += proceeds
            cash_movements.append(
                {
                    "trade_date": trade_date,
                    "symbol": event["symbol"],
                    "action": "sell",
                    "amount": proceeds,
                    "cash_after": cash,
                }
            )
            closed_trades.append(
                {
                    "symbol": event["symbol"],
                    "entry_date": position["entry_date"],
                    "exit_date": trade_date,
                    "entry_price": position["entry_price"],
                    "exit_price": float(event["price"]),
                    "quantity": position["quantity"],
                    "return": float(event["price"]) / position["entry_price"] - 1.0
                    if position["entry_price"]
                    else 0.0,
                }
            )

        entry_candidates = [event for event in daily_events if event["intent_type"] == "enter"]
        funnel["raw_entry_candidates"] += len(entry_candidates)
        daily_new_count = 0
        daily_industry_counts: dict[str, int] = {}
        ranked_candidates = sorted(
            entry_candidates,
            key=lambda event: _candidate_order_key(event, scores_by_key, unscored_baseline=unscored_baseline),
        )
        for event in ranked_candidates:
            scored_row = scores_by_key[(str(event["symbol"]), str(event["trade_date"]))]
            if not scored_row["score_gate_passed"]:
                _block_entry(event, scored_row, "SCORE_GATE", blocked_entries, funnel, "score_gate_blocked_candidates")
                continue
            funnel["score_gated_candidates"] += 1

            if event["symbol"] in positions:
                _block_entry(event, scored_row, "ALREADY_HELD", blocked_entries, funnel, "ranking_capacity_blocked_candidates")
                continue
            if len(positions) >= max_holding_count:
                _block_entry(event, scored_row, "MAX_HOLDING_COUNT", blocked_entries, funnel, "holding_cap_blocked_candidates")
                continue
            if max_new_positions_per_day is not None and daily_new_count >= max_new_positions_per_day:
                _block_entry(
                    event,
                    scored_row,
                    "MAX_NEW_POSITIONS_PER_DAY",
                    blocked_entries,
                    funnel,
                    "max_new_position_blocked_candidates",
                )
                continue
            industry = event.get("industry")
            if (
                industry_max_new_per_day is not None
                and industry
                and daily_industry_counts.get(str(industry), 0) >= industry_max_new_per_day
            ):
                _block_entry(
                    event,
                    scored_row,
                    "INDUSTRY_MAX_NEW_PER_DAY",
                    blocked_entries,
                    funnel,
                    "industry_blocked_candidates",
                )
                continue
            if not event.get("tradable", True):
                _block_entry(event, scored_row, "NOT_TRADABLE", blocked_entries, funnel, "tradability_blocked_candidates")
                continue

            total_value = _portfolio_total_value(cash, positions, latest_prices)
            target_value = total_value * (1.0 - cash_reserve_ratio) / max_holding_count
            quantity = _board_lot_quantity(target_value, float(event["price"]), board_lot_size)
            if quantity <= 0:
                _block_entry(event, scored_row, "BOARD_LOT_MIN_ORDER", blocked_entries, funnel, "board_lot_blocked_candidates")
                continue
            cost = quantity * float(event["price"])
            reserve_cash = total_value * cash_reserve_ratio
            if cash - cost < reserve_cash:
                _block_entry(event, scored_row, "INSUFFICIENT_CASH", blocked_entries, funnel, "cash_blocked_candidates")
                continue

            cash -= cost
            total_buy_value += cost
            cash_movements.append(
                {
                    "trade_date": trade_date,
                    "symbol": event["symbol"],
                    "action": "buy",
                    "amount": -cost,
                    "cash_after": cash,
                }
            )
            positions[str(event["symbol"])] = {
                "symbol": event["symbol"],
                "entry_date": trade_date,
                "entry_price": float(event["price"]),
                "quantity": quantity,
                "industry": industry,
            }
            daily_new_count += 1
            if industry:
                daily_industry_counts[str(industry)] = daily_industry_counts.get(str(industry), 0) + 1
            funnel["executed_entries"] += 1
            executed_entries.append(
                {
                    **_jsonable(dict(scored_row)),
                    "quantity": quantity,
                    "cost": cost,
                }
            )

        snapshot = _equity_snapshot(trade_date, cash, positions, latest_prices, peak_value)
        position_snapshots.append(_position_snapshot(trade_date, positions, latest_prices))
        peak_value = max(peak_value, snapshot["total_value"])
        equity_curve.append(snapshot)

    final_value = equity_curve[-1]["total_value"] if equity_curve else cash
    return {
        "schema": "attbacktrader.scored_portfolio_simulation.v1",
        "unscored_baseline": unscored_baseline,
        "portfolio_controls": _jsonable(dict(portfolio_controls)),
        "score_gate": _jsonable(scored_gate),
        "final_cash": cash,
        "final_value": final_value,
        "positions": [
            _jsonable({**position, "market_price": latest_prices.get(symbol, position["entry_price"])})
            for symbol, position in sorted(positions.items())
        ],
        "executed_entries": executed_entries,
        "blocked_entries": blocked_entries,
        "closed_trades": closed_trades,
        "cash_movements": cash_movements,
        "position_snapshots": position_snapshots,
        "equity_curve": equity_curve,
        "funnel": funnel,
        "metrics": _portfolio_metrics(
            initial_cash=initial_cash,
            final_value=final_value,
            equity_curve=equity_curve,
            executed_entries=executed_entries,
            closed_trades=closed_trades,
            total_buy_value=total_buy_value,
            latest_prices=latest_prices,
            positions=positions,
        ),
    }


def build_stage_b_search_space_from_stage_a(
    stage_a_trials: Sequence[Mapping[str, Any]],
    *,
    weight_keys: Sequence[str],
    stable_sign_probability: float = 0.75,
) -> dict[str, Any]:
    """Use Stage A elite trials to narrow Stage B scorer-weight search ranges."""

    if not stage_a_trials:
        raise ValueError("stage_a_trials cannot be empty")
    if not weight_keys:
        raise ValueError("weight_keys cannot be empty")

    elite_trials = _stage_a_elites(stage_a_trials)
    weights: dict[str, dict[str, Any]] = {}
    for key in weight_keys:
        values = [
            _number_or_zero(_as_mapping(_as_mapping(trial.get("parameters")).get("weights")).get(key))
            for trial in elite_trials
        ]
        positive_probability = sum(1 for value in values if value > 0) / len(values)
        negative_probability = sum(1 for value in values if value < 0) / len(values)
        if positive_probability >= stable_sign_probability:
            classification = "stable_positive"
            low, high = _range_with_margin(values)
            low = max(0.0, low)
        elif negative_probability >= stable_sign_probability:
            classification = "stable_negative"
            low, high = _range_with_margin(values)
            high = min(0.0, high)
        else:
            classification = "unstable"
            low, high = -0.5, 0.5
        weights[key] = {
            "classification": classification,
            "low": low,
            "high": high,
            "elite_values": values,
            "positive_probability": positive_probability,
            "negative_probability": negative_probability,
        }

    return {
        "schema": "attbacktrader.stage_b_search_space_from_stage_a.v1",
        "evidence_use": "narrows_stage_b_search_space_only",
        "elite_trial_ids": [str(trial.get("trial_id")) for trial in elite_trials],
        "weights": weights,
    }


def build_scored_entry_allocation_tuning_report(
    *,
    contract: Mapping[str, Any],
    stage_a_trials: Sequence[Mapping[str, Any]],
    stage_b_trials: Sequence[Mapping[str, Any]],
    stage_b_search_space: Mapping[str, Any],
    baselines: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the scored entry allocation tuning report from trial records."""

    normalized_stage_a = [_normalize_trial(trial) for trial in stage_a_trials]
    normalized_stage_b = [_normalize_trial(trial) for trial in stage_b_trials]
    eligible, rejected = _eligible_trials(normalized_stage_b, min_trade_count=20)
    recommendations = _select_recommendations(eligible)
    recommendations["rejected"] = rejected
    return {
        "schema": SCORED_ENTRY_ALLOCATION_TUNING_REPORT_SCHEMA,
        "mode": contract.get("mode"),
        "folds": _jsonable(contract.get("folds") or []),
        "objectives": _jsonable(contract.get("objectives") or list(_OBJECTIVES)),
        "baselines": _jsonable(dict(baselines or {})),
        "stage_a": {
            "evidence_use": "pre_tuning_only",
            "trial_count": len(normalized_stage_a),
            "trials": normalized_stage_a,
            "pareto_frontier": _pareto_frontier(normalized_stage_a),
        },
        "stage_b": {
            "evidence_use": "portfolio_validation",
            "trial_count": len(normalized_stage_b),
            "trials": normalized_stage_b,
            "search_space": _jsonable(dict(stage_b_search_space)),
            "pareto_frontier": _pareto_frontier(eligible),
        },
        "recommendations": recommendations,
    }


def build_simulation_cache_identity(
    *,
    signal_cache_identity: str,
    fold_id: str,
    parameters: Mapping[str, Any],
    portfolio_controls: Mapping[str, Any],
    simulator_version: str,
) -> dict[str, Any]:
    parameter_hash = _stable_hash(parameters)
    portfolio_control_hash = _stable_hash(portfolio_controls)
    inputs = {
        "signal_cache_identity": signal_cache_identity,
        "fold_id": fold_id,
        "parameter_hash": parameter_hash,
        "portfolio_control_hash": portfolio_control_hash,
        "simulator_version": simulator_version,
    }
    return {
        "schema": "attbacktrader.scored_portfolio_simulation_cache_identity.v1",
        "inputs": inputs,
        "cache_key": _stable_hash(inputs),
    }


def _stage_score_gate_and_controls(contract: Mapping[str, Any], stage: str) -> tuple[dict[str, Any], dict[str, Any]]:
    stages = _as_mapping(contract.get("stages"))
    stage_config = _as_mapping(stages.get(stage))
    if not stage_config:
        raise ValueError(f"contract missing stage config: {stage}")
    score_gate = dict(_as_mapping(stage_config.get("score_gate")))
    portfolio_controls = dict(_as_mapping(stage_config.get("portfolio_controls")))
    if not score_gate:
        raise ValueError(f"contract stage missing score_gate: {stage}")
    if not portfolio_controls:
        raise ValueError(f"contract stage missing portfolio_controls: {stage}")
    return score_gate, portfolio_controls


def _scheduled_trials(contract: Mapping[str, Any], stage: str, mode: str) -> int:
    stage_config = _as_mapping(_as_mapping(contract.get("stages")).get(stage))
    key = "smoke_trials_per_fold" if mode == "smoke" else "standard_trials_per_fold"
    value = stage_config.get(key)
    if value is None:
        raise ValueError(f"contract stage missing {key}: {stage}")
    count = int(value)
    if count <= 0:
        raise ValueError(f"{stage}.{key} must be positive")
    return count


def _fold_artifact_identity(
    *,
    signal_cache_key: str,
    fold_id: str,
    mode: str,
    stage_a_scheduled: int,
    stage_b_scheduled: int,
) -> str:
    return _stable_hash(
        {
            "signal_cache_key": signal_cache_key,
            "fold_id": fold_id,
            "mode": mode,
            "stage_a_scheduled": stage_a_scheduled,
            "stage_b_scheduled": stage_b_scheduled,
            "runner_schema": FULL_WALK_FORWARD_TUNING_RUN_SCHEMA,
        }
    )


def _test_window_boundary(test_window: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "start": test_window.get("start"),
        "end": test_window.get("end"),
        "year": test_window.get("year"),
        "evidence_use": "out_of_sample_evaluation_only",
        "retunes_parameters": False,
        "refits_score_gate": False,
        "updates_stage_a_search_space": False,
        "uses_stage_b_recommendations": True,
    }


def _stage_override_or_default(
    overrides: Mapping[str, Mapping[str, Any]] | None,
    stage: str,
    default: Mapping[str, Any],
) -> dict[str, Any]:
    stage_override = _as_mapping(_as_mapping(overrides).get(stage))
    return dict(stage_override) if stage_override else dict(default)


def _decision_events_for_fold_window(
    decision_event_table: Mapping[str, Any],
    fold: Mapping[str, Any],
    *,
    window: str,
) -> list[dict[str, Any]]:
    if decision_event_table.get("schema") != STRATEGY_DECISION_EVENT_TABLE_SCHEMA:
        raise ValueError("decision_event_table must use the Strategy Decision Event Table schema")
    window_config = _as_mapping(fold.get(window))
    start = str(window_config.get("start") or "")
    end = str(window_config.get("end") or "")
    if not start or not end:
        raise ValueError(f"fold.{window}.start and fold.{window}.end are required")
    events = [_normalize_decision_event(event) for event in _as_sequence(decision_event_table.get("events"))]
    return [
        {**event, "window": "training" if window == "train" else window}
        for event in events
        if start <= str(event["trade_date"]) <= end
    ]


def _trial_scorer_config(trial_parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    scorer_config = _as_mapping(trial_parameters.get("scorer_config"))
    if not scorer_config:
        raise ValueError("trial parameter set missing scorer_config")
    if not _as_mapping(scorer_config.get("factor_weights")) and not _as_sequence(scorer_config.get("interaction_weights")):
        raise ValueError("trial scorer_config must define factor_weights or interaction_weights")
    return scorer_config


def _baseline_scorer_config(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields: set[str] = set()
    for event in events:
        fields.update(str(key) for key in _as_mapping(event.get("evidence")))
    return {"factor_weights": {field: {} for field in sorted(fields)}}


def _flatten_scorer_weights(scorer_config: Mapping[str, Any]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for field, bucket_weights in _as_mapping(scorer_config.get("factor_weights")).items():
        for bucket, weight in _as_mapping(bucket_weights).items():
            weights[f"factor:{field}={bucket}"] = _number_or_zero(weight)
    for interaction in _as_sequence(scorer_config.get("interaction_weights")):
        item = _as_mapping(interaction)
        name = item.get("name") or item.get("key")
        if name:
            key = f"interaction:{name}"
        else:
            fields = _as_mapping(item.get("fields"))
            pairs = "&".join(f"{field}={fields[field]}" for field in sorted(fields))
            key = f"interaction:{pairs}"
        weights[key] = _number_or_zero(item.get("weight"))
    return weights


def _infer_weight_keys(trials: Sequence[Mapping[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for trial in trials:
        keys.update(str(key) for key in _as_mapping(_as_mapping(trial.get("parameters")).get("weights")))
    return sorted(keys)


def _assert_trial_within_stage_b_search_space(
    weights: Mapping[str, Any],
    stage_b_search_space: Mapping[str, Any],
) -> None:
    search_weights = _as_mapping(stage_b_search_space.get("weights"))
    if not search_weights:
        raise ValueError("stage_b_search_space.weights cannot be empty")
    violations: list[str] = []
    for key, limits in search_weights.items():
        bounds = _as_mapping(limits)
        if key not in weights:
            violations.append(f"{key}=<missing>")
            continue
        value = _number_or_zero(weights.get(key))
        low = _number_or_none(bounds.get("low"))
        high = _number_or_none(bounds.get("high"))
        if low is None or high is None:
            raise ValueError(f"stage_b_search_space weight missing low/high: {key}")
        if value < low or value > high:
            violations.append(f"{key}={value} outside [{low}, {high}]")
    if violations:
        raise ValueError("trial scorer weights outside Stage B narrowed search space: " + "; ".join(violations))


def _stage_b_trade_count_gate(
    contract: Mapping[str, Any],
    fold: Mapping[str, Any],
    *,
    minimum_train_trades_per_year: int | None,
) -> dict[str, int]:
    gates = _as_mapping(contract.get("trade_count_gates"))
    train_per_year = (
        int(minimum_train_trades_per_year)
        if minimum_train_trades_per_year is not None
        else int(gates.get("train_per_year") or 50)
    )
    if train_per_year < 0:
        raise ValueError("minimum_train_trades_per_year must be non-negative")
    train_years = len(_as_sequence(_as_mapping(fold.get("train")).get("years"))) or 1
    return {
        "train_per_year": train_per_year,
        "train_years": train_years,
        "minimum_train_trade_count": train_per_year * train_years,
        "test_per_year": int(gates.get("test_per_year") or 20),
        "full_out_of_sample_total": int(gates.get("full_out_of_sample_total") or 120),
    }


def _balanced_top_trials(trials: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not trials:
        return []
    top_count = max(1, math.ceil(len(trials) * 0.2))
    return [_jsonable(dict(trial)) for trial in sorted(trials, key=_balanced_score, reverse=True)[:top_count]]


def _direction_stability(
    trials: Sequence[Mapping[str, Any]],
    *,
    weight_keys: Sequence[str],
) -> dict[str, Any]:
    stability: dict[str, Any] = {}
    for key in weight_keys:
        values = [
            _number_or_zero(_as_mapping(_as_mapping(trial.get("parameters")).get("weights")).get(key))
            for trial in trials
        ]
        positive_count = sum(1 for value in values if value > 0)
        negative_count = sum(1 for value in values if value < 0)
        zero_count = sum(1 for value in values if value == 0)
        total = len(values)
        positive_probability = positive_count / total if total else 0.0
        negative_probability = negative_count / total if total else 0.0
        if positive_probability >= 0.75:
            classification = "stable_positive"
        elif negative_probability >= 0.75:
            classification = "stable_negative"
        else:
            classification = "unstable"
        stability[str(key)] = {
            "kind": "interaction" if str(key).startswith("interaction:") else "factor",
            "classification": classification,
            "values": values,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "zero_count": zero_count,
            "positive_probability": positive_probability,
            "negative_probability": negative_probability,
        }
    return stability


def _assert_no_test_window_threshold_source(training_events: Sequence[Mapping[str, Any]]) -> None:
    leaking: list[str] = []
    for event in training_events:
        item = _as_mapping(event)
        for field in _WINDOW_ROLE_FIELDS:
            role = item.get(field)
            if role is not None and str(role).lower() in _TEST_WINDOW_ROLE_VALUES:
                leaking.append(f"{item.get('symbol', '<unknown>')} {item.get('trade_date', '<unknown>')} {field}={role}")
    if leaking:
        raise ValueError(
            "test-window candidates cannot be used to fit score gate thresholds: "
            + "; ".join(leaking)
        )


def _core_portfolio_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in _CORE_PORTFOLIO_METRICS if key not in metrics]
    if missing:
        raise ValueError(f"portfolio metrics missing core fields: {', '.join(missing)}")
    return {key: _jsonable(metrics[key]) for key in _CORE_PORTFOLIO_METRICS}


def _core_metric_delta(scored: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, float]:
    return {
        key: _number_or_zero(scored.get(key)) - _number_or_zero(baseline.get(key))
        for key in _CORE_PORTFOLIO_METRICS
    }


def _metric_snapshot(metrics: Mapping[str, Any]) -> dict[str, Any]:
    values = {key: _jsonable(metrics.get(key)) for key in _REPORT_METRIC_KEYS}
    missing = [key for key in _REPORT_METRIC_KEYS if key not in metrics]
    return {
        "values": values,
        "missing_metric_fields": missing,
    }


def _aggregate_funnels(trials: Sequence[Any]) -> dict[str, int]:
    return _aggregate_funnel_dicts(
        _as_mapping(_as_mapping(trial).get("funnel"))
        for trial in trials
    )


def _aggregate_funnel_dicts(funnels: Any) -> dict[str, int]:
    totals: dict[str, int] = {}
    for funnel in funnels:
        for key, value in _as_mapping(funnel).items():
            totals[str(key)] = totals.get(str(key), 0) + int(value or 0)
    return totals


def require_optuna_for_tuning(*, import_module: Any = importlib.import_module) -> Any:
    try:
        return import_module("optuna")
    except ImportError as exc:
        raise ImportError("Optuna is required for tuning. Install with: pip install -e .[tuning]") from exc


def _normalize_decision_event(event: Mapping[str, Any]) -> dict[str, Any]:
    forbidden = sorted(field for field in _FORBIDDEN_DECISION_EVENT_FIELDS if field in event)
    if forbidden:
        raise ValueError(f"decision event contains forbidden portfolio result fields: {', '.join(forbidden)}")

    required = ("symbol", "trade_date", "intent_type", "price")
    missing = [field for field in required if field not in event]
    if missing:
        raise ValueError(f"decision event missing required fields: {', '.join(missing)}")
    intent_type = str(event["intent_type"])
    if intent_type not in _ACTIONABLE_INTENTS:
        raise ValueError(f"intent_type must be actionable: {intent_type}")

    evidence = _as_mapping(event.get("evidence"))
    return {
        "symbol": str(event["symbol"]),
        "trade_date": str(event["trade_date"]),
        "intent_type": intent_type,
        "price": float(event["price"]),
        "industry": None if event.get("industry") is None else str(event.get("industry")),
        "stock_pool_order": int(event.get("stock_pool_order") or 0),
        "tradable": bool(event.get("tradable", True)),
        "evidence": _jsonable(dict(evidence)),
    }


def _intent_type_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _date_value(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _market_context_for_intent(
    intent: Any,
    market_context_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
) -> Mapping[str, Any]:
    symbol = str(getattr(intent, "symbol"))
    trade_date = _date_value(getattr(intent, "trade_date"))
    context = market_context_by_key.get((symbol, trade_date))
    if context is None:
        raise ValueError(f"missing market context for {symbol} {trade_date}")
    if "price" not in context:
        raise ValueError(f"missing market context price for {symbol} {trade_date}")
    return context


def _full_signal_audit_rows(signal_audit: Any) -> Sequence[Any]:
    if isinstance(signal_audit, Mapping):
        if signal_audit.get("schema") == "attbacktrader.compact_signal_audit.v1":
            raise ValueError("Strategy Decision Event Table requires full signal_audit; compact signal_audit cannot be used")
        raise ValueError("full signal_audit must be a JSON array of intent rows")
    if isinstance(signal_audit, (str, bytes)) or not isinstance(signal_audit, Sequence):
        raise ValueError("full signal_audit must be a JSON array of intent rows")
    invalid_count = sum(1 for row in signal_audit if not isinstance(row, Mapping))
    if invalid_count:
        raise ValueError("full signal_audit rows must be JSON objects")
    return signal_audit


def _decision_evidence_from_signal_values(signal_values: Mapping[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    attribution = _as_mapping(signal_values.get("attribution"))
    for bucket in ("values", "categories", "checks"):
        evidence.update(dict(_as_mapping(attribution.get(bucket))))
    evidence.update(dict(_as_mapping(signal_values.get("evidence"))))
    forbidden = sorted(field for field in _FORBIDDEN_DECISION_EVENT_FIELDS if field in evidence)
    if forbidden:
        raise ValueError(f"decision evidence contains forbidden portfolio result fields: {', '.join(forbidden)}")
    return _jsonable(evidence)


def _signal_audit_row_price(row: Mapping[str, Any], evidence: Mapping[str, Any]) -> Any:
    for value in (row.get("price"), evidence.get("symbol.close"), _as_mapping(row.get("signal_values")).get("close")):
        if value is not None:
            return value
    raise ValueError(
        "signal_audit actionable row missing decision price: "
        f"{row.get('symbol', '<unknown>')} {row.get('trade_date', '<unknown>')}"
    )


def _score_event(event: Mapping[str, Any], scorer_config: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _as_mapping(event.get("evidence"))
    factor_weights = _as_mapping(scorer_config.get("factor_weights"))
    interaction_weights = _as_sequence(scorer_config.get("interaction_weights"))

    score = 0.0
    factor_contributions: dict[str, dict[str, Any]] = {}
    for field, bucket_weights in factor_weights.items():
        weights = _as_mapping(bucket_weights)
        value = evidence.get(str(field))
        if value in weights:
            weight = _number_or_zero(weights[value])
        else:
            weight = _number_or_zero(weights.get(str(value)))
        if weight == 0.0 and value not in weights and str(value) not in weights:
            continue
        score += weight
        factor_contributions[str(field)] = {
            "value": value,
            "weight": weight,
        }

    interaction_contributions: list[dict[str, Any]] = []
    for interaction in interaction_weights:
        item = _as_mapping(interaction)
        fields = _as_mapping(item.get("fields"))
        if fields and all(evidence.get(str(field)) == expected for field, expected in fields.items()):
            weight = _number_or_zero(item.get("weight"))
            score += weight
            interaction_contributions.append(
                {
                    "fields": dict(fields),
                    "weight": weight,
                }
            )

    return {
        "score": score,
        "contributions": {
            "factor_weights": factor_contributions,
            "interaction_weights": interaction_contributions,
        },
    }


def _candidate_public_fields(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(event.get("symbol")),
        "trade_date": str(event.get("trade_date")),
        "intent_type": str(event.get("intent_type")),
        "price": float(event.get("price")),
        "industry": None if event.get("industry") is None else str(event.get("industry")),
        "stock_pool_order": int(event.get("stock_pool_order") or 0),
        "tradable": bool(event.get("tradable", True)),
        "evidence": _jsonable(dict(_as_mapping(event.get("evidence")))),
    }


def _score_distribution(scores: Sequence[float]) -> dict[str, float]:
    values = [float(score) for score in scores]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {"mean": mean, "std": math.sqrt(variance)}


def _quantile(scores: Sequence[float], quantile: float) -> float:
    values = sorted(float(score) for score in scores)
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    fraction = index - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _float_required(mapping: Mapping[str, Any], key: str) -> float:
    if key not in mapping:
        raise ValueError(f"{key} is required")
    number = _number_or_none(mapping.get(key))
    if number is None:
        raise ValueError(f"{key} must be numeric")
    return number


def _number_or_zero(value: Any) -> float:
    number = _number_or_none(value)
    return 0.0 if number is None else number


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    return number if math.isfinite(number) else None


def _positive_float(mapping: Mapping[str, Any], key: str) -> float:
    number = _float_required(mapping, key)
    if number <= 0:
        raise ValueError(f"{key} must be positive")
    return number


def _positive_int(mapping: Mapping[str, Any], key: str) -> int:
    number = int(_positive_float(mapping, key))
    if number != float(mapping[key]):
        raise ValueError(f"{key} must be an integer")
    return number


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    number = _number_or_none(value)
    if number is None or number <= 0 or int(number) != number:
        raise ValueError("optional portfolio integer controls must be positive integers")
    return int(number)


def _empty_funnel() -> dict[str, int]:
    return {
        "raw_entry_candidates": 0,
        "score_gated_candidates": 0,
        "score_gate_blocked_candidates": 0,
        "ranking_capacity_blocked_candidates": 0,
        "holding_cap_blocked_candidates": 0,
        "max_new_position_blocked_candidates": 0,
        "industry_blocked_candidates": 0,
        "cash_blocked_candidates": 0,
        "tradability_blocked_candidates": 0,
        "board_lot_blocked_candidates": 0,
        "executed_entries": 0,
    }


def _candidate_order_key(
    event: Mapping[str, Any],
    scores_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    unscored_baseline: bool,
) -> tuple[Any, ...]:
    scored_row = scores_by_key[(str(event["symbol"]), str(event["trade_date"]))]
    if unscored_baseline:
        return (int(event.get("stock_pool_order") or 0), str(event["symbol"]))
    return (-float(scored_row["score"]), int(event.get("stock_pool_order") or 0), str(event["symbol"]))


def _block_entry(
    event: Mapping[str, Any],
    scored_row: Mapping[str, Any],
    reason: str,
    blocked_entries: list[dict[str, Any]],
    funnel: dict[str, int],
    funnel_key: str,
) -> None:
    funnel[funnel_key] += 1
    blocked_entries.append(
        {
            **_jsonable(dict(scored_row)),
            "blocked_by": reason,
        }
    )


def _board_lot_quantity(target_value: float, price: float, board_lot_size: int) -> int:
    if price <= 0:
        return 0
    raw_quantity = int(target_value / price)
    return raw_quantity - (raw_quantity % board_lot_size)


def _portfolio_total_value(
    cash: float,
    positions: Mapping[str, Mapping[str, Any]],
    latest_prices: Mapping[str, float],
) -> float:
    return cash + sum(
        float(position["quantity"]) * float(latest_prices.get(symbol, position["entry_price"]))
        for symbol, position in positions.items()
    )


def _equity_snapshot(
    trade_date: str,
    cash: float,
    positions: Mapping[str, Mapping[str, Any]],
    latest_prices: Mapping[str, float],
    peak_value: float,
) -> dict[str, Any]:
    position_value = sum(
        float(position["quantity"]) * float(latest_prices.get(symbol, position["entry_price"]))
        for symbol, position in positions.items()
    )
    total_value = cash + position_value
    peak = max(peak_value, total_value)
    return {
        "trade_date": trade_date,
        "cash": cash,
        "position_value": position_value,
        "total_value": total_value,
        "drawdown": (peak - total_value) / peak if peak > 0 else 0.0,
        "holding_count": len(positions),
        "exposure": position_value / total_value if total_value > 0 else 0.0,
        "cash_ratio": cash / total_value if total_value > 0 else 0.0,
    }


def _position_snapshot(
    trade_date: str,
    positions: Mapping[str, Mapping[str, Any]],
    latest_prices: Mapping[str, float],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for symbol, position in sorted(positions.items()):
        market_price = float(latest_prices.get(symbol, position["entry_price"]))
        quantity = int(position["quantity"])
        rows.append(
            {
                "symbol": symbol,
                "entry_date": position["entry_date"],
                "entry_price": position["entry_price"],
                "quantity": quantity,
                "industry": position.get("industry"),
                "market_price": market_price,
                "market_value": quantity * market_price,
            }
        )
    return {
        "trade_date": trade_date,
        "holding_count": len(rows),
        "positions": rows,
    }


def _portfolio_metrics(
    *,
    initial_cash: float,
    final_value: float,
    equity_curve: Sequence[Mapping[str, Any]],
    executed_entries: Sequence[Mapping[str, Any]],
    closed_trades: Sequence[Mapping[str, Any]],
    total_buy_value: float,
    latest_prices: Mapping[str, float],
    positions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    cumulative_return = final_value / initial_cash - 1.0 if initial_cash else 0.0
    returns = _daily_returns(equity_curve)
    volatility = _sample_std(returns)
    downside = _sample_std([value for value in returns if value < 0])
    max_drawdown = max((float(point.get("drawdown") or 0.0) for point in equity_curve), default=0.0)
    average_cash_ratio = _average(float(point.get("cash_ratio") or 0.0) for point in equity_curve)
    average_exposure = _average(float(point.get("exposure") or 0.0) for point in equity_curve)
    average_holding_count = _average(float(point.get("holding_count") or 0.0) for point in equity_curve)
    max_holding_count = max((int(point.get("holding_count") or 0) for point in equity_curve), default=0)
    trade_returns = [float(trade.get("return") or 0.0) for trade in closed_trades]
    open_trade_returns = [
        float(latest_prices.get(symbol, position["entry_price"])) / float(position["entry_price"]) - 1.0
        for symbol, position in positions.items()
        if float(position["entry_price"]) != 0
    ]
    all_trade_returns = trade_returns + open_trade_returns
    wins = [value for value in all_trade_returns if value > 0]
    losses = [value for value in all_trade_returns if value < 0]
    position_values = [
        float(position["quantity"]) * float(latest_prices.get(symbol, position["entry_price"]))
        for symbol, position in positions.items()
    ]
    industry_values: dict[str, float] = {}
    for symbol, position in positions.items():
        industry = str(position.get("industry") or "")
        industry_values[industry] = industry_values.get(industry, 0.0) + float(position["quantity"]) * float(
            latest_prices.get(symbol, position["entry_price"])
        )

    annualized_return = cumulative_return
    sharpe_ratio = (sum(returns) / len(returns) / volatility * math.sqrt(252)) if returns and volatility > 0 else 0.0
    sortino_ratio = (sum(returns) / len(returns) / downside * math.sqrt(252)) if returns and downside > 0 else 0.0
    calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0.0
    return {
        "cumulative_return": cumulative_return,
        "annualized_return": annualized_return,
        "benchmark_excess_return": cumulative_return,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "calmar_ratio": calmar_ratio,
        "information_ratio": 0.0,
        "trade_count": len(executed_entries),
        "closed_trade_count": len(closed_trades),
        "win_rate": len(wins) / len(all_trade_returns) if all_trade_returns else 0.0,
        "profit_loss_ratio": (abs(_average(wins)) / abs(_average(losses))) if wins and losses else 0.0,
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses else 0.0,
        "average_trade_return": _average(all_trade_returns),
        "median_trade_return": _median(all_trade_returns),
        "average_win_return": _average(wins),
        "average_loss_return": _average(losses),
        "maximum_win_trade": max(wins, default=0.0),
        "maximum_loss_trade": min(losses, default=0.0),
        "average_holding_days": 0.0,
        "average_holding_count": average_holding_count,
        "maximum_holding_count": max_holding_count,
        "average_cash_ratio": average_cash_ratio,
        "average_exposure": average_exposure,
        "turnover": total_buy_value / initial_cash if initial_cash else 0.0,
        "fee_slippage_ratio": 0.0,
        "single_symbol_maximum_weight": max(position_values, default=0.0) / final_value if final_value else 0.0,
        "industry_concentration": max(industry_values.values(), default=0.0) / final_value if final_value else 0.0,
    }


def _daily_returns(equity_curve: Sequence[Mapping[str, Any]]) -> list[float]:
    returns: list[float] = []
    previous: float | None = None
    for point in equity_curve:
        total_value = float(point.get("total_value") or 0.0)
        if previous is not None and previous > 0:
            returns.append(total_value / previous - 1.0)
        previous = total_value
    return returns


def _sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _average(values: Any) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return _quantile(values, 0.5)


def _stage_a_elites(stage_a_trials: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [_normalize_trial(trial) for trial in stage_a_trials]
    pareto = _pareto_frontier(normalized)
    top_count = max(1, math.ceil(len(normalized) * 0.2))
    balanced_top = sorted(normalized, key=_balanced_score, reverse=True)[:top_count]
    by_id: dict[str, dict[str, Any]] = {}
    for trial in [*pareto, *balanced_top]:
        by_id[str(trial.get("trial_id"))] = trial
    return list(by_id.values())


def _range_with_margin(values: Sequence[float]) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    span = high - low
    margin = max(abs(span) * 0.2, 0.05)
    return low - margin, high + margin


def _normalize_trial(trial: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict(_as_mapping(trial.get("metrics")))
    metrics.setdefault("annualized_return", 0.0)
    metrics.setdefault("sharpe_ratio", 0.0)
    metrics.setdefault("benchmark_excess_return", 0.0)
    metrics.setdefault("max_drawdown", 0.0)
    metrics.setdefault("calmar_ratio", 0.0)
    metrics.setdefault("sortino_ratio", 0.0)
    metrics.setdefault("trade_count", 0)
    metrics.setdefault("turnover", 0.0)
    metrics.setdefault("yearly_stability", 0.0)
    metrics.setdefault("funnel_counts", {})
    return {
        "trial_id": str(trial.get("trial_id")),
        "fold_id": trial.get("fold_id"),
        "stage": trial.get("stage"),
        "parameters": _jsonable(dict(_as_mapping(trial.get("parameters")))),
        "metrics": _jsonable(metrics),
        "funnel": _jsonable(trial.get("funnel") or metrics.get("funnel_counts") or {}),
    }


def _eligible_trials(trials: Sequence[Mapping[str, Any]], *, min_trade_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for trial in trials:
        item = dict(trial)
        metrics = _as_mapping(item.get("metrics"))
        if int(metrics.get("trade_count") or 0) < min_trade_count:
            item["rejection_reason"] = "below_minimum_trade_count"
            rejected.append(item)
        else:
            eligible.append(item)
    return eligible, rejected


def _select_recommendations(eligible_trials: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not eligible_trials:
        return {"balanced": None, "aggressive": None, "defensive": None}
    positive_excess = [
        trial
        for trial in eligible_trials
        if _metric(trial, "benchmark_excess_return") > 0 and _metric(trial, "annualized_return") > 0
    ]
    candidates = positive_excess or list(eligible_trials)
    return {
        "balanced": _jsonable(max(candidates, key=_balanced_score)),
        "aggressive": _jsonable(max(candidates, key=lambda trial: (_metric(trial, "annualized_return"), _metric(trial, "benchmark_excess_return")))),
        "defensive": _jsonable(max(candidates, key=lambda trial: (-_metric(trial, "max_drawdown"), _metric(trial, "calmar_ratio"), _metric(trial, "annualized_return")))),
    }


def _pareto_frontier(trials: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    frontier: list[dict[str, Any]] = []
    for trial in trials:
        if any(_dominates(other, trial) for other in trials if other is not trial):
            continue
        frontier.append(_jsonable(dict(trial)))
    frontier.sort(key=lambda trial: str(trial.get("trial_id")))
    return frontier


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_values = (
        _metric(left, "annualized_return"),
        _metric(left, "sharpe_ratio"),
        _metric(left, "benchmark_excess_return"),
        -_metric(left, "max_drawdown"),
    )
    right_values = (
        _metric(right, "annualized_return"),
        _metric(right, "sharpe_ratio"),
        _metric(right, "benchmark_excess_return"),
        -_metric(right, "max_drawdown"),
    )
    return all(left_value >= right_value for left_value, right_value in zip(left_values, right_values)) and any(
        left_value > right_value for left_value, right_value in zip(left_values, right_values)
    )


def _balanced_score(trial: Mapping[str, Any]) -> float:
    return (
        _metric(trial, "annualized_return")
        + _metric(trial, "benchmark_excess_return")
        + _metric(trial, "sharpe_ratio")
        + _metric(trial, "calmar_ratio")
        + _metric(trial, "yearly_stability")
        - _metric(trial, "max_drawdown")
        - abs(_metric(trial, "turnover") - 1.0) * 0.1
    )


def _metric(trial: Mapping[str, Any], key: str) -> float:
    return _number_or_zero(_as_mapping(trial.get("metrics")).get(key))


def _stable_hash(value: Any) -> str:
    payload = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()
