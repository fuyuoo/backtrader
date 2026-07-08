"""Backtest-only entry-score replay adapter for runner results."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from attbacktrader.config import RunPlan
from attbacktrader.reports.scored_entry_allocation_tuning import simulate_precomputed_score_portfolio
from attbacktrader.strategies import TradeIntent, TradeIntentType


_FUTURE_SCORE_ARTIFACT_FIELDS = {
    "exit_date",
    "exit_price",
    "return_pct",
    "realized_return_pct",
    "net_pnl",
    "is_win",
    "holding_days",
    "exit_reason",
}
_ALLOWED_SCORE_METADATA_FIELDS = {
    "fold_id",
    "train_start_year",
    "train_end_year",
    "test_year",
    "seed_v2_candidate_score",
}
_ACTIONABLE_REPLAY_INTENTS = {
    TradeIntentType.ENTER.value,
    TradeIntentType.EXIT_PROFIT.value,
    TradeIntentType.EXIT_LOSS.value,
}


def run_entry_score_replay(
    run_plan: RunPlan,
    *,
    intents: Sequence[TradeIntent],
) -> dict[str, Any] | None:
    config = run_plan.execution.entry_score
    if not config.enabled:
        return None
    if config.scope != "backtest_only":
        raise ValueError("execution.entry_score.scope must be backtest_only")
    if run_plan.execution.engine != "baoma_v1_business":
        raise ValueError("execution.entry_score.enabled requires execution.engine='baoma_v1_business'")
    if config.score_id is None or config.score_field is None or config.artifact_path is None:
        raise ValueError("execution.entry_score requires score_id, score_field, and artifact_path when enabled")

    score_rows = load_entry_score_rows(
        config.artifact_path,
        symbol_column=config.key.symbol,
        trade_date_column=config.key.trade_date,
        score_field=config.score_field,
        source_score_field=config.source_score_field or config.score_field,
    )
    score_rows = _filter_rows_by_replay_window(
        score_rows,
        start_date=_date_label(config.replay_start_date) if config.replay_start_date is not None else None,
        end_date=_date_label(config.replay_end_date) if config.replay_end_date is not None else None,
    )
    stock_pool_order_by_symbol = {
        series.symbol: index
        for index, series in enumerate(run_plan.data.resolved_tradable_series, start=1)
    }
    source_events = decision_events_from_intents(
        intents,
        stock_pool_order_by_symbol=stock_pool_order_by_symbol,
    )
    events = _filter_rows_by_replay_window(
        source_events,
        start_date=_date_label(config.replay_start_date) if config.replay_start_date is not None else None,
        end_date=_date_label(config.replay_end_date) if config.replay_end_date is not None else None,
    )
    max_holding_count = config.max_holding_count or _configured_max_holding_count(run_plan)
    replay_initial_cash = config.replay_initial_cash or run_plan.broker.initial_cash
    portfolio_controls = {
        "initial_cash": replay_initial_cash,
        "max_holding_count": max_holding_count,
        "max_new_positions_per_day": config.max_new_positions_per_day,
        "cash_reserve_ratio": config.cash_reserve_ratio,
        "industry_max_new_per_day": config.industry_max_new_per_day,
        "board_lot_size": run_plan.constraints.ashare.board_lot_size,
        "allow_same_day_exit_cash_reuse": config.allow_same_day_exit_cash_reuse,
        "prefer_unheld_industries": config.prefer_unheld_industries,
    }
    replay = simulate_precomputed_score_portfolio(
        events,
        score_rows=score_rows,
        score_field=config.score_field,
        score_id=config.score_id,
        portfolio_controls=portfolio_controls,
        missing_score_policy=config.missing_score_policy,
        score_gate={"derived_from": "runner_entry_score_config"},
    )
    replay["source"] = {
        "scope": config.scope,
        "artifact_path": str(config.artifact_path),
        "source_score_field": config.source_score_field or config.score_field,
        "replay_start_date": _date_label(config.replay_start_date) if config.replay_start_date is not None else None,
        "replay_end_date": _date_label(config.replay_end_date) if config.replay_end_date is not None else None,
        "engine_initial_cash": float(run_plan.broker.initial_cash),
        "replay_initial_cash": float(replay_initial_cash),
        "source_decision_event_count": len(source_events),
        "decision_event_count": len(events),
    }
    return replay


def load_entry_score_rows(
    artifact_path: str | Path,
    *,
    symbol_column: str,
    trade_date_column: str,
    score_field: str,
    source_score_field: str,
) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError("Entry score artifacts require pandas and pyarrow to be installed.") from exc

    frame = pd.read_parquet(artifact_path)
    required_columns = {symbol_column, trade_date_column, source_score_field}
    missing_columns = sorted(required_columns - set(frame.columns))
    if missing_columns:
        raise ValueError(f"entry score artifact missing columns: {', '.join(missing_columns)}")

    rows: list[dict[str, Any]] = []
    metadata_fields = sorted(_ALLOWED_SCORE_METADATA_FIELDS & set(frame.columns))
    for item in frame.to_dict("records"):
        row = {
            "symbol": str(item[symbol_column]),
            "trade_date": _date_label(item[trade_date_column]),
            score_field: item[source_score_field],
        }
        for field in metadata_fields:
            row[field] = item.get(field)
        rows.append(row)
    return rows


def decision_events_from_intents(
    intents: Sequence[TradeIntent],
    *,
    stock_pool_order_by_symbol: Mapping[str, int],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for intent in intents:
        intent_type = _intent_type_value(intent.intent_type)
        if intent_type not in _ACTIONABLE_REPLAY_INTENTS:
            continue
        signal_values = _as_mapping(intent.signal_values)
        evidence = _decision_evidence(signal_values)
        events.append(
            {
                "symbol": intent.symbol,
                "trade_date": _date_label(intent.trade_date),
                "intent_type": intent_type,
                "price": _decision_price(intent, signal_values, evidence),
                "industry": evidence.get("industry.sw_l1.code") or evidence.get("industry"),
                "stock_pool_order": int(stock_pool_order_by_symbol.get(intent.symbol) or 0),
                "tradable": True,
                "evidence": evidence,
            }
        )
    events.sort(key=lambda item: (str(item["trade_date"]), str(item["symbol"]), str(item["intent_type"])))
    return events


def _configured_max_holding_count(run_plan: RunPlan) -> int:
    sizing_params = dict(run_plan.strategy.sizing_params or {})
    value = sizing_params.get("max_holding_count")
    if value is None:
        return 200
    return int(value)


def _filter_rows_by_replay_window(
    rows: Sequence[Mapping[str, Any]],
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    if start_date is None and end_date is None:
        return [dict(row) for row in rows]
    filtered: list[dict[str, Any]] = []
    for row in rows:
        trade_date = str(row.get("trade_date") or "")
        if start_date is not None and trade_date < start_date:
            continue
        if end_date is not None and trade_date > end_date:
            continue
        filtered.append(dict(row))
    return filtered


def _decision_evidence(signal_values: Mapping[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    attribution = _as_mapping(signal_values.get("attribution"))
    for bucket in ("values", "categories", "checks"):
        evidence.update(dict(_as_mapping(attribution.get(bucket))))
    evidence.update(dict(_as_mapping(signal_values.get("evidence"))))
    for field in _FUTURE_SCORE_ARTIFACT_FIELDS:
        evidence.pop(field, None)
    return json.loads(json.dumps(evidence, ensure_ascii=False, default=str))


def _decision_price(intent: TradeIntent, signal_values: Mapping[str, Any], evidence: Mapping[str, Any]) -> float:
    for value in (
        evidence.get("symbol.close"),
        evidence.get("symbol.close.current"),
        signal_values.get("close"),
        signal_values.get("current_close"),
        intent.target_price,
    ):
        number = _number_or_none(value)
        if number is not None:
            return number
    raise ValueError(f"missing decision price for {intent.symbol} {intent.trade_date}")


def _intent_type_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _date_label(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
