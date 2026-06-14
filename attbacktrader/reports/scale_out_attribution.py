"""Post-run attribution for executed scale-out events."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from attbacktrader.engines.business import LifecycleExecutionEvent
from attbacktrader.features import IndicatorSnapshot


def build_scale_out_attribution_report(
    *,
    run_id: str,
    lifecycle_events: Sequence[LifecycleExecutionEvent],
    indicator_snapshots_by_symbol: Mapping[str, Sequence[IndicatorSnapshot]],
    run_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build attribution samples for executed scale-out events."""

    run_config = run_config or {}
    samples = tuple(
        _sample(
            sample_index=index,
            event=event,
            snapshot=_snapshot_for_event(event, indicator_snapshots_by_symbol),
            atr_pair=_atr_pair_label(run_config),
        )
        for index, event in enumerate(_executed_scale_out_events(lifecycle_events), start=1)
    )
    return {
        "schema": "attbacktrader.scale_out_attribution.v1",
        "run_id": run_id,
        "scale_out_mode": _scale_out_mode(run_config),
        "atr_pair": _atr_pair_label(run_config),
        "sample_count": len(samples),
        "samples": samples,
        "summaries": {
            "overall": _summary_row(samples, dimensions={}),
            "by_stage": _group_summary(samples, keys=("scale_out_stage",)),
            "by_stage_kdj_cci_boll": _group_summary(
                samples,
                keys=("scale_out_stage", "kdj_j_bucket", "cci14_bucket", "close_at_or_above_boll_up"),
            ),
            "by_stage_kdj_cci_boll_fine": _group_summary(
                samples,
                keys=(
                    "scale_out_stage",
                    "kdj_j_fine_bucket",
                    "cci14_fine_bucket",
                    "boll_up_distance_bucket",
                ),
            ),
            "by_kdj_j_fine_bucket": _group_summary(samples, keys=("kdj_j_fine_bucket",)),
            "by_cci14_fine_bucket": _group_summary(samples, keys=("cci14_fine_bucket",)),
            "by_boll_up_distance_bucket": _group_summary(samples, keys=("boll_up_distance_bucket",)),
        },
        "missing_counts": {
            "kdj_j": sum(1 for sample in samples if sample["kdj_j"] is None),
            "cci14": sum(1 for sample in samples if sample["cci14"] is None),
            "boll_up20_2": sum(1 for sample in samples if sample["boll_up20_2"] is None),
            "boll_up_distance_pct": sum(1 for sample in samples if sample["boll_up_distance_pct"] is None),
            "scale_out_return_pct_before_execution": sum(
                1 for sample in samples if sample["scale_out_return_pct_before_execution"] is None
            ),
        },
    }


def _executed_scale_out_events(
    lifecycle_events: Sequence[LifecycleExecutionEvent],
) -> tuple[LifecycleExecutionEvent, ...]:
    return tuple(
        event
        for event in sorted(lifecycle_events, key=lambda item: (item.trade_date, item.symbol, item.reason_code))
        if event.side == "sell"
        and event.accepted
        and event.reason_code.startswith("BAOMA_SCALE_OUT_")
        and event.executed_quantity > 0
    )


def _sample(
    *,
    sample_index: int,
    event: LifecycleExecutionEvent,
    snapshot: IndicatorSnapshot | None,
    atr_pair: str | None,
) -> dict[str, Any]:
    before_quantity = _position_quantity_before(event)
    before_cost_value = _remaining_cost_value_before(event)
    before_cost_basis = _remaining_cost_basis_before(event, before_quantity=before_quantity, before_cost_value=before_cost_value)
    return_pct = _scale_out_return_pct(event.price, before_cost_basis)
    gross_pnl = _scale_out_gross_pnl(event, before_cost_basis=before_cost_basis)
    kdj_j = snapshot.kdj_j if snapshot is not None else None
    cci14 = snapshot.cci14 if snapshot is not None else None
    boll_up20_2 = snapshot.boll_up20_2 if snapshot is not None else None
    boll_up_distance_pct = _boll_up_distance_pct(event.price, boll_up20_2)

    return {
        "sample_index": sample_index,
        "symbol": event.symbol,
        "scale_out_date": event.trade_date,
        "scale_out_stage": _stage_label(event),
        "reason_code": event.reason_code,
        "scale_out_mode": event.scale_out_mode,
        "atr_pair": atr_pair,
        "atr_multiple": event.atr_multiple,
        "entry_signal_date": event.entry_signal_date,
        "entry_signal_day_atr14": event.entry_signal_day_atr14,
        "scale_out_trigger_price": event.scale_out_trigger_price,
        "confirmation_required": event.confirmation_required,
        "confirmation_passed": event.confirmation_passed,
        "confirmation_mode": event.confirmation_mode,
        "confirmation_block_reason": event.confirmation_block_reason,
        "adjusted_remaining_cost_basis_before": before_cost_basis,
        "remaining_cost_value_before": before_cost_value,
        "position_quantity_before": before_quantity,
        "sell_price": event.price,
        "executed_quantity": event.executed_quantity,
        "scale_out_return_pct_before_execution": return_pct,
        "scale_out_gross_pnl_before_execution": gross_pnl,
        "kdj_j": kdj_j,
        "confirmation_kdj_j": event.kdj_j,
        "kdj_j_bucket": _kdj_j_bucket(kdj_j),
        "kdj_j_fine_bucket": _kdj_j_fine_bucket(kdj_j),
        "cci14": cci14,
        "confirmation_cci14": event.cci14,
        "cci14_bucket": _cci_bucket(cci14),
        "cci14_fine_bucket": _cci_fine_bucket(cci14),
        "boll_up20_2": boll_up20_2,
        "confirmation_boll_up20_2": event.boll_up20_2,
        "close_at_or_above_boll_up": event.price >= boll_up20_2 if boll_up20_2 is not None else None,
        "boll_up_distance_pct": boll_up_distance_pct,
        "confirmation_boll_up_distance_pct": event.boll_up_distance_pct,
        "boll_up_distance_bucket": _boll_up_distance_bucket(boll_up_distance_pct),
        "indicator_snapshot_available": snapshot is not None,
    }


def _snapshot_for_event(
    event: LifecycleExecutionEvent,
    indicator_snapshots_by_symbol: Mapping[str, Sequence[IndicatorSnapshot]],
) -> IndicatorSnapshot | None:
    snapshots = indicator_snapshots_by_symbol.get(event.symbol, ())
    return next(
        (
            snapshot
            for snapshot in snapshots
            if snapshot.timeframe == "D" and snapshot.trade_date == event.trade_date
        ),
        None,
    )


def _position_quantity_before(event: LifecycleExecutionEvent) -> int | None:
    if event.position_quantity_before is not None:
        return event.position_quantity_before
    if event.position_quantity_after is None:
        return None
    return int(event.position_quantity_after) + int(event.executed_quantity)


def _remaining_cost_value_before(event: LifecycleExecutionEvent) -> float | None:
    if event.remaining_cost_value_before is not None:
        return event.remaining_cost_value_before
    if event.remaining_cost_value_after is None:
        return None
    return float(event.remaining_cost_value_after) + (float(event.executed_quantity) * float(event.price))


def _remaining_cost_basis_before(
    event: LifecycleExecutionEvent,
    *,
    before_quantity: int | None,
    before_cost_value: float | None,
) -> float | None:
    if event.remaining_cost_basis_before is not None:
        return event.remaining_cost_basis_before
    if before_quantity is None or before_quantity <= 0 or before_cost_value is None:
        return None
    return before_cost_value / before_quantity


def _scale_out_return_pct(sell_price: float, before_cost_basis: float | None) -> float | None:
    if before_cost_basis is None or before_cost_basis <= 0:
        return None
    return float(sell_price) / before_cost_basis - 1.0


def _scale_out_gross_pnl(
    event: LifecycleExecutionEvent,
    *,
    before_cost_basis: float | None,
) -> float | None:
    if before_cost_basis is None:
        return None
    if before_cost_basis <= 0:
        return float(event.executed_quantity) * float(event.price)
    return float(event.executed_quantity) * (float(event.price) - before_cost_basis)


def _boll_up_distance_pct(sell_price: float, boll_up20_2: float | None) -> float | None:
    if boll_up20_2 is None or boll_up20_2 <= 0:
        return None
    return float(sell_price) / float(boll_up20_2) - 1.0


def _stage_label(event: LifecycleExecutionEvent) -> str:
    stage = (event.scale_out_stage or "").upper()
    reason = event.reason_code.upper()
    if (
        stage in {"FIFTEEN_PERCENT", "SECOND"}
        or "ATR_SECOND" in reason
        or reason.endswith("_15_PERCENT_TRIGGERED")
    ):
        return "second"
    if stage in {"FIVE_PERCENT", "FIRST"} or "ATR_FIRST" in reason or reason.endswith("_5_PERCENT_TRIGGERED"):
        return "first"
    return event.scale_out_stage or "unknown"


def _summary_row(samples: Sequence[Mapping[str, Any]], *, dimensions: Mapping[str, Any]) -> dict[str, Any]:
    return_values = [
        float(sample["scale_out_return_pct_before_execution"])
        for sample in samples
        if sample["scale_out_return_pct_before_execution"] is not None
    ]
    gross_pnls = [
        float(sample["scale_out_gross_pnl_before_execution"])
        for sample in samples
        if sample["scale_out_gross_pnl_before_execution"] is not None
    ]
    return {
        "dimensions": dict(dimensions),
        "sample_count": len(samples),
        "average_scale_out_return_pct_before_execution": (
            sum(return_values) / len(return_values) if return_values else None
        ),
        "total_scale_out_gross_pnl_before_execution": sum(gross_pnls) if gross_pnls else None,
        "boll_up_hit_rate": _rate(
            sample["close_at_or_above_boll_up"] is True
            for sample in samples
            if sample["close_at_or_above_boll_up"] is not None
        ),
    }


def _group_summary(samples: Sequence[Mapping[str, Any]], *, keys: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[tuple(sample.get(key) for key in keys)].append(sample)

    rows = [
        _summary_row(group_samples, dimensions={key: value for key, value in zip(keys, group_key)})
        for group_key, group_samples in grouped.items()
    ]
    return tuple(sorted(rows, key=lambda row: (-int(row["sample_count"]), str(row["dimensions"]))))


def _rate(values) -> float | None:
    items = list(values)
    if not items:
        return None
    return sum(1 for item in items if item) / len(items)


def _kdj_j_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 13:
        return "lt_13"
    if value < 30:
        return "13_30"
    if value < 50:
        return "30_50"
    if value < 80:
        return "50_80"
    return "gte_80"


def _kdj_j_fine_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 80:
        return "lt_80"
    if value < 100:
        return "80_100"
    if value < 120:
        return "100_120"
    return "gte_120"


def _cci_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < -100:
        return "lt_neg100"
    if value < 100:
        return "neg100_100"
    return "gte_100"


def _cci_fine_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 100:
        return "lt_100"
    if value < 150:
        return "100_150"
    if value < 200:
        return "150_200"
    if value < 300:
        return "200_300"
    return "gte_300"


def _boll_up_distance_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < -0.05:
        return "lt_neg_5pct"
    if value < 0:
        return "neg_5_0pct"
    if value < 0.03:
        return "0_3pct"
    if value < 0.07:
        return "3_7pct"
    return "gte_7pct"


def _scale_out_mode(run_config: Mapping[str, Any]) -> str | None:
    baoma = _baoma_config(run_config)
    value = baoma.get("scale_out_mode")
    return str(value) if value is not None else None


def _atr_pair_label(run_config: Mapping[str, Any]) -> str | None:
    baoma = _baoma_config(run_config)
    if baoma.get("scale_out_mode") != "atr_multiple":
        return None
    first = baoma.get("first_scale_out_atr_multiple")
    second = baoma.get("second_scale_out_atr_multiple")
    if first is None or second is None:
        return None
    return f"{float(first):g}_{float(second):g}atr"


def _baoma_config(run_config: Mapping[str, Any]) -> Mapping[str, Any]:
    execution = run_config.get("execution")
    if not isinstance(execution, Mapping):
        return {}
    baoma = execution.get("baoma")
    if isinstance(baoma, Mapping):
        return baoma
    if hasattr(baoma, "model_dump"):
        return baoma.model_dump(mode="json")
    return {}
