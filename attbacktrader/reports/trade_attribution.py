"""Post-trade attribution assembled from completed trade lifecycle evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from attbacktrader.reports.lifecycle import TradeLifecycle, TradeLifecycleEvent, TradeLifecycleReport

TRADE_ATTRIBUTION_SCHEMA = "attbacktrader.trade_attribution.v1"


@dataclass(frozen=True)
class TradeAttributionFactor:
    key: str
    value: Any
    value_kind: str
    missing: bool
    source: str


@dataclass(frozen=True)
class TradeAttributionEvent:
    timing: str
    trade_date: date
    method_name: str | None
    reason_code: str | None
    factors: tuple[TradeAttributionFactor, ...]
    missing_factor_keys: tuple[str, ...]


@dataclass(frozen=True)
class TradeAttribution:
    trade_index: int
    symbol: str
    outcome: str
    entry_date: date
    exit_date: date
    exit_reason: str
    return_pct: float
    entry: TradeAttributionEvent
    exit: TradeAttributionEvent
    add_ons: tuple[TradeAttributionEvent, ...]


@dataclass(frozen=True)
class TradeAttributionFactorSummary:
    timing: str
    key: str
    value_kind: str
    sample_count: int
    missing_count: int
    win_count: int
    loss_count: int
    win_rate: float | None
    average_return_pct: float | None
    value_buckets: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class TradeAttributionReport:
    schema: str
    trade_count: int
    entry_event_count: int
    exit_event_count: int
    add_on_event_count: int
    attributions: tuple[TradeAttribution, ...]
    factor_summaries: tuple[TradeAttributionFactorSummary, ...]


def build_trade_attribution_report(
    trade_lifecycle: TradeLifecycleReport,
    *,
    selected_factor_keys: Sequence[str] = (),
) -> TradeAttributionReport:
    """Build trade-level attribution after completed trades have been matched to lifecycle evidence."""

    selected = frozenset(str(key) for key in selected_factor_keys)
    attributions = tuple(
        _trade_attribution(lifecycle, selected_factor_keys=selected)
        for lifecycle in trade_lifecycle.lifecycles
    )
    factor_summaries = _factor_summaries(attributions)
    return TradeAttributionReport(
        schema=TRADE_ATTRIBUTION_SCHEMA,
        trade_count=len(attributions),
        entry_event_count=len(attributions),
        exit_event_count=len(attributions),
        add_on_event_count=sum(len(attribution.add_ons) for attribution in attributions),
        attributions=attributions,
        factor_summaries=factor_summaries,
    )


def render_trade_attribution_markdown_zh(report: TradeAttributionReport, *, limit: int = 80) -> str:
    lines = [
        "# 交易后验归因",
        "",
        "## 概览",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 完成交易 | {report.trade_count} |",
        f"| 入场事件 | {report.entry_event_count} |",
        f"| 出场事件 | {report.exit_event_count} |",
        f"| 加仓事件 | {report.add_on_event_count} |",
        "",
        "## 因子统计",
        "",
        "| timing | 因子 | 样本 | 缺失 | 胜率 | 平均收益 | top values |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for summary in report.factor_summaries[:limit]:
        top_values = "; ".join(
            f"{bucket.get('value')}({bucket.get('count')})"
            for bucket in summary.value_buckets[:5]
        )
        lines.append(
            "| "
            f"{summary.timing} | "
            f"`{summary.key}` | "
            f"{summary.sample_count} | "
            f"{summary.missing_count} | "
            f"{_format_percent(summary.win_rate)} | "
            f"{_format_percent(summary.average_return_pct)} | "
            f"{top_values or '-'} |"
        )

    lines.extend(
        [
            "",
            "## 交易样本",
            "",
            "| # | 股票 | 结果 | 入场 | 出场 | 收益 | 入场因子 | 出场因子 | 加仓次数 |",
            "|---:|---|---|---|---|---:|---|---|---:|",
        ]
    )
    for attribution in report.attributions[:limit]:
        lines.append(
            "| "
            f"{attribution.trade_index} | "
            f"{attribution.symbol} | "
            f"{_outcome_label(attribution.outcome)} | "
            f"{attribution.entry_date.isoformat()} | "
            f"{attribution.exit_date.isoformat()} | "
            f"{_format_percent(attribution.return_pct)} | "
            f"{_format_event_factors(attribution.entry)} | "
            f"{_format_event_factors(attribution.exit)} | "
            f"{len(attribution.add_ons)} |"
        )
    if len(report.attributions) > limit:
        lines.append("")
        lines.append(f"仅展示前 {limit} 条，完整明细见 `trade_attribution.json`。")
    lines.extend(
        [
            "",
            "## 说明",
            "- 该报告从已完成交易的 lifecycle 事件反查 entry/exit/add_on 当日证据，不重新拉取数据。",
            "- 缺失因子显式记录为 missing，不补成 false、0 或中性值。",
            "- 当前第一版来源是 lifecycle event evidence；后续可扩展为直接从 snapshot/indicator artifact lookup。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _trade_attribution(lifecycle: TradeLifecycle, *, selected_factor_keys: frozenset[str]) -> TradeAttribution:
    entry_event = _event_by_type(lifecycle, "entry")
    exit_event = _event_by_type(lifecycle, "exit")
    add_on_events = tuple(event for event in lifecycle.events if event.event_type == "add_on")
    return TradeAttribution(
        trade_index=lifecycle.trade_index,
        symbol=lifecycle.symbol,
        outcome=lifecycle.outcome,
        entry_date=lifecycle.entry_date,
        exit_date=lifecycle.exit_date,
        exit_reason=lifecycle.exit_reason,
        return_pct=lifecycle.return_pct,
        entry=_attribution_event("entry", lifecycle.entry_date, entry_event, selected_factor_keys=selected_factor_keys),
        exit=_attribution_event("exit", lifecycle.exit_date, exit_event, selected_factor_keys=selected_factor_keys),
        add_ons=tuple(
            _attribution_event("add_on", event.trade_date, event, selected_factor_keys=selected_factor_keys)
            for event in add_on_events
        ),
    )


def _attribution_event(
    timing: str,
    trade_date: date,
    event: TradeLifecycleEvent | None,
    *,
    selected_factor_keys: frozenset[str],
) -> TradeAttributionEvent:
    factors = tuple(_event_factors(event or _empty_event(timing, trade_date), selected_factor_keys=selected_factor_keys))
    present_keys = frozenset(factor.key for factor in factors)
    missing_keys = tuple(sorted(selected_factor_keys - present_keys))
    if missing_keys:
        factors = factors + tuple(
            TradeAttributionFactor(
                key=key,
                value=None,
                value_kind="missing",
                missing=True,
                source="missing",
            )
            for key in missing_keys
        )
    return TradeAttributionEvent(
        timing=timing,
        trade_date=trade_date,
        method_name=event.method_name if event is not None else None,
        reason_code=event.reason_code if event is not None else None,
        factors=factors,
        missing_factor_keys=missing_keys,
    )


def _empty_event(timing: str, trade_date: date) -> TradeLifecycleEvent:
    return TradeLifecycleEvent(
        event_type=timing,
        trade_date=trade_date,
        intent_type=None,
        method_name=None,
        reason_code=None,
        blocked_by=None,
        checks={},
        values={},
        categories={},
        sizing_context={},
        executions=(),
    )


def _event_factors(
    event: TradeLifecycleEvent,
    *,
    selected_factor_keys: frozenset[str],
) -> tuple[TradeAttributionFactor, ...]:
    factors: list[TradeAttributionFactor] = []
    for key, value in sorted(event.checks.items()):
        factors.append(_factor(key, value, value_kind="check"))
    for key, value in sorted(event.values.items()):
        factors.append(_factor(key, value, value_kind="value"))
    for key, value in sorted(event.categories.items()):
        factors.append(_factor(key, value, value_kind="category"))
    for key, value in sorted(event.sizing_context.items()):
        factors.append(_factor(f"sizing.{key}", value, value_kind="sizing"))
    if selected_factor_keys:
        factors = [factor for factor in factors if factor.key in selected_factor_keys or factor.key.startswith("sizing.")]
    return tuple(factors)


def _factor(key: str, value: Any, *, value_kind: str) -> TradeAttributionFactor:
    return TradeAttributionFactor(
        key=str(key),
        value=value,
        value_kind=value_kind,
        missing=False,
        source="lifecycle_event_evidence",
    )


def _factor_summaries(attributions: Sequence[TradeAttribution]) -> tuple[TradeAttributionFactorSummary, ...]:
    rows: dict[tuple[str, str], list[tuple[TradeAttribution, TradeAttributionFactor]]] = defaultdict(list)
    for attribution in attributions:
        for event in (attribution.entry, attribution.exit, *attribution.add_ons):
            for factor in event.factors:
                rows[(event.timing, factor.key)].append((attribution, factor))

    summaries = []
    for (timing, key), items in sorted(rows.items()):
        present_items = tuple((trade, factor) for trade, factor in items if not factor.missing)
        returns = [trade.return_pct for trade, _factor_item in present_items]
        win_count = sum(1 for trade, _factor_item in present_items if trade.outcome == "win")
        loss_count = sum(1 for trade, _factor_item in present_items if trade.outcome == "loss")
        value_kind = next((factor.value_kind for _trade, factor in present_items), "missing")
        summaries.append(
            TradeAttributionFactorSummary(
                timing=timing,
                key=key,
                value_kind=value_kind,
                sample_count=len(items),
                missing_count=sum(1 for _trade, factor in items if factor.missing),
                win_count=win_count,
                loss_count=loss_count,
                win_rate=win_count / len(present_items) if present_items else None,
                average_return_pct=sum(returns) / len(returns) if returns else None,
                value_buckets=_value_buckets(present_items),
            )
        )
    return tuple(summaries)


def _value_buckets(items: Sequence[tuple[TradeAttribution, TradeAttributionFactor]]) -> tuple[dict[str, Any], ...]:
    buckets: dict[str, list[TradeAttribution]] = defaultdict(list)
    for attribution, factor in items:
        buckets[_value_label(factor.value)].append(attribution)
    rows = []
    for value, trades in sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0])):
        win_count = sum(1 for trade in trades if trade.outcome == "win")
        returns = [trade.return_pct for trade in trades]
        rows.append(
            {
                "value": value,
                "count": len(trades),
                "win_count": win_count,
                "loss_count": sum(1 for trade in trades if trade.outcome == "loss"),
                "win_rate": win_count / len(trades) if trades else None,
                "average_return_pct": sum(returns) / len(returns) if returns else None,
                "trade_indexes": tuple(trade.trade_index for trade in trades[:50]),
            }
        )
    return tuple(rows)


def _event_by_type(lifecycle: TradeLifecycle, event_type: str) -> TradeLifecycleEvent | None:
    return next((event for event in lifecycle.events if event.event_type == event_type), None)


def _value_label(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return str(value)


def _format_event_factors(event: TradeAttributionEvent) -> str:
    visible = [
        factor
        for factor in event.factors
        if not factor.missing and factor.value_kind in {"check", "category"}
    ]
    if not visible:
        return "-"
    return "; ".join(f"{factor.key}={_value_label(factor.value)}" for factor in visible[:6])


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _outcome_label(outcome: str) -> str:
    return {"win": "盈利", "loss": "亏损", "flat": "持平"}.get(outcome, outcome)
