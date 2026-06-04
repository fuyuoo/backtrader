"""Unified trade review assembled from completed run evidence."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from attbacktrader.data import DailyBar
from attbacktrader.engines.ledger import ExecutionAuditEvent
from attbacktrader.reports.lifecycle import TradeLifecycle, TradeLifecycleReport, build_trade_lifecycle_report
from attbacktrader.reports.post_exit import PostExitAnalysisReport, PostExitTradeObservation
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import entry_attribution_declaration_by_key
from attbacktrader.strategies.templates import ClosedTrade


_ATTRIBUTION_DECLARATIONS = entry_attribution_declaration_by_key()

_REVIEW_CHECK_KEYS = (
    "symbol.ma.price_above_ma25",
    "symbol.ma.price_above_ma60",
    "symbol.ma.bullish_trend",
    "market.hs300.bullish_trend",
    "industry.kdj.j_below_threshold",
    "kdj_j_below_threshold",
    "kdj_j_above_threshold",
    "current_price_at_or_below_stop",
    "position.unrealized_return_at_or_above_min",
    "position.add_on_count_available",
)

_SOLD_TOO_EARLY_PROFILE_CHECK_KEYS = (
    "current_price_at_or_below_stop",
    "kdj_j_above_threshold",
    "symbol.ma.bullish_trend",
    "market.hs300.bullish_trend",
    "industry.kdj.j_below_threshold",
)

_ADD_ON_PROFILE_CHECK_KEYS = (
    "position.unrealized_return_at_or_above_min",
    "position.add_on_count_available",
    "unrealized_return_at_or_above_min",
    "add_on_count_available",
    "symbol.kdj.j_below_threshold",
    "kdj_j_below_threshold",
    "symbol.ma.bullish_trend",
    "market.hs300.bullish_trend",
    "industry.kdj.j_below_threshold",
)


@dataclass(frozen=True)
class TradeReviewTrade:
    trade_index: int
    symbol: str
    outcome: str
    entry_date: date
    exit_date: date
    exit_reason: str
    return_pct: float
    entry_method_name: str | None
    exit_method_name: str | None
    add_on_count: int
    sold_too_early: bool | None
    max_high_return_pct: float | None
    primary_window_close_return_pct: float | None
    entry_checks: Mapping[str, bool]
    exit_checks: Mapping[str, bool]
    add_on_checks: Mapping[str, bool]
    review_flags: tuple[str, ...]


@dataclass(frozen=True)
class SoldTooEarlyProfileSummary:
    profile_key: str
    sample_count: int
    observed_count: int
    sold_too_early_count: int
    sold_too_early_rate: float | None
    average_max_high_return_pct: float | None
    average_trade_return_pct: float | None
    trade_indexes: tuple[int, ...]


@dataclass(frozen=True)
class StopLossReboundProfileSummary:
    profile_key: str
    threshold: float
    sample_count: int
    observed_count: int
    rebound_count: int
    rebound_rate: float | None
    average_max_high_return_pct: float | None
    average_trade_return_pct: float | None
    trade_indexes: tuple[int, ...]


@dataclass(frozen=True)
class TradeReviewOpportunityFollowUp:
    window_days: int
    observed_day_count: int
    complete: bool
    window_close_return_pct: float | None
    max_high_return_pct: float | None
    min_low_return_pct: float | None


@dataclass(frozen=True)
class TradeReviewOpportunitySample:
    sample_index: int
    source: str
    opportunity_group: str
    symbol: str
    trade_date: date
    intent_type: str | None
    method_name: str | None
    reason_code: str
    blocked_by: str | None
    failed_checks: tuple[str, ...]
    checks: Mapping[str, bool]
    opportunity_price: float | None
    follow_up: TradeReviewOpportunityFollowUp | None


@dataclass(frozen=True)
class TradeReviewOpportunitySummary:
    opportunity_group: str
    blocked_by: str
    count: int
    symbols: tuple[str, ...]
    sample_indexes: tuple[int, ...]


@dataclass(frozen=True)
class TradeReviewOpportunityCostSummary:
    opportunity_group: str
    blocked_by: str
    sample_count: int
    observed_count: int
    positive_max_high_count: int
    positive_max_high_rate: float | None
    average_max_high_return_pct: float | None
    average_window_close_return_pct: float | None
    sample_indexes: tuple[int, ...]


@dataclass(frozen=True)
class TradeReviewAddOnEntryPoint:
    sample_index: int
    trade_index: int
    symbol: str
    outcome: str
    trade_return_pct: float
    add_on_date: date
    method_name: str | None
    reason_code: str | None
    checks: Mapping[str, bool]
    categories: Mapping[str, str]
    add_on_price: float | None
    follow_up: TradeReviewOpportunityFollowUp


@dataclass(frozen=True)
class TradeReviewAddOnEntrySummary:
    profile_key: str
    sample_count: int
    observed_count: int
    positive_max_high_count: int
    positive_max_high_rate: float | None
    average_max_high_return_pct: float | None
    average_window_close_return_pct: float | None
    average_trade_return_pct: float | None
    sample_indexes: tuple[int, ...]
    trade_indexes: tuple[int, ...]


@dataclass(frozen=True)
class TradeReviewReport:
    trade_count: int
    sold_too_early_count: int
    opportunity_count: int
    opportunity_window_days: int
    add_on_entry_count: int
    add_on_window_days: int
    sold_too_early_profiles: tuple[SoldTooEarlyProfileSummary, ...]
    stop_loss_rebound_profiles: tuple[StopLossReboundProfileSummary, ...]
    opportunity_summaries: tuple[TradeReviewOpportunitySummary, ...]
    opportunity_cost_summaries: tuple[TradeReviewOpportunityCostSummary, ...]
    add_on_entry_summaries: tuple[TradeReviewAddOnEntrySummary, ...]
    trades: tuple[TradeReviewTrade, ...]
    opportunities: tuple[TradeReviewOpportunitySample, ...]
    add_on_entry_points: tuple[TradeReviewAddOnEntryPoint, ...]


def build_trade_review_report(
    *,
    closed_trades: Sequence[ClosedTrade],
    signal_audit: Sequence[TradeIntent],
    execution_audit: Sequence[ExecutionAuditEvent] = (),
    post_exit_analysis: PostExitAnalysisReport,
    trade_lifecycle: TradeLifecycleReport | None = None,
    bars_by_symbol: Mapping[str, Sequence[DailyBar]] | None = None,
    opportunity_window_days: int = 5,
    add_on_window_days: int | None = None,
) -> TradeReviewReport:
    lifecycle = trade_lifecycle or build_trade_lifecycle_report(
        closed_trades=closed_trades,
        signal_audit=signal_audit,
        execution_audit=execution_audit,
    )
    bars = _sorted_bars_by_symbol(bars_by_symbol or {})
    post_exit_by_key = _post_exit_by_trade_key(post_exit_analysis.observations)
    trades = tuple(
        _review_trade(lifecycle_item, post_exit_by_key.get(_lifecycle_key(lifecycle_item)))
        for lifecycle_item in lifecycle.lifecycles
    )
    opportunities = _opportunities(
        signal_audit,
        execution_audit,
        bars_by_symbol=bars,
        opportunity_window_days=opportunity_window_days,
    )
    add_on_window_days = add_on_window_days or opportunity_window_days
    add_on_entry_points = _add_on_entry_points(
        lifecycle.lifecycles,
        bars_by_symbol=bars,
        window_days=add_on_window_days,
    )
    return TradeReviewReport(
        trade_count=len(trades),
        sold_too_early_count=sum(1 for trade in trades if trade.sold_too_early is True),
        opportunity_count=len(opportunities),
        opportunity_window_days=opportunity_window_days,
        add_on_entry_count=len(add_on_entry_points),
        add_on_window_days=add_on_window_days,
        sold_too_early_profiles=_sold_too_early_profiles(post_exit_analysis.observations),
        stop_loss_rebound_profiles=_stop_loss_rebound_profiles(
            post_exit_analysis.observations,
            post_exit_analysis.rebound_thresholds,
        ),
        opportunity_summaries=_opportunity_summaries(opportunities),
        opportunity_cost_summaries=_opportunity_cost_summaries(opportunities),
        add_on_entry_summaries=_add_on_entry_summaries(add_on_entry_points),
        trades=trades,
        opportunities=opportunities,
        add_on_entry_points=add_on_entry_points,
    )


def render_trade_review_markdown_zh(report: TradeReviewReport, *, limit: int = 50) -> str:
    lines = [
        "# 交易复盘",
        "",
        "## 概览",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 完成交易 | {report.trade_count} |",
        f"| 卖飞样本 | {report.sold_too_early_count} |",
        f"| 机会/拦截样本 | {report.opportunity_count} |",
        f"| 加仓入场点 | {report.add_on_entry_count} |",
        "",
    ]
    if report.sold_too_early_profiles:
        lines.extend(
            [
                "## 卖飞归因组合",
                "",
                "| 组合 | 样本 | 有后续数据 | 卖飞 | 比例 | 平均最高涨幅 | 平均交易收益 | 交易编号 |",
                "|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for summary in report.sold_too_early_profiles[:limit]:
            lines.append(
                "| "
                f"{_profile_label(summary.profile_key)} | "
                f"{summary.sample_count} | "
                f"{summary.observed_count} | "
                f"{summary.sold_too_early_count} | "
                f"{_format_optional_percent(summary.sold_too_early_rate)} | "
                f"{_format_optional_percent(summary.average_max_high_return_pct)} | "
                f"{_format_optional_percent(summary.average_trade_return_pct)} | "
                f"{', '.join(str(index) for index in summary.trade_indexes[:20])} |"
        )
        lines.append("")

    if report.stop_loss_rebound_profiles:
        lines.extend(
            [
                "## 止损后反弹归因",
                "",
                "| 阈值 | 组合 | 样本 | 有后续数据 | 反弹 | 比例 | 平均最高涨幅 | 平均交易收益 | 交易编号 |",
                "|---:|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for summary in report.stop_loss_rebound_profiles[:limit]:
            lines.append(
                "| "
                f"{_format_percent(summary.threshold)} | "
                f"{_profile_label(summary.profile_key)} | "
                f"{summary.sample_count} | "
                f"{summary.observed_count} | "
                f"{summary.rebound_count} | "
                f"{_format_optional_percent(summary.rebound_rate)} | "
                f"{_format_optional_percent(summary.average_max_high_return_pct)} | "
                f"{_format_optional_percent(summary.average_trade_return_pct)} | "
                f"{', '.join(str(index) for index in summary.trade_indexes[:20])} |"
            )
        lines.append("")

    if report.opportunity_summaries:
        lines.extend(
            [
                "## 机会/拦截归因",
                "",
                "| 类型 | 原因 | 次数 | 标的 | 样本编号 |",
                "|---|---|---:|---|---|",
            ]
        )
        for summary in report.opportunity_summaries[:limit]:
            lines.append(
                "| "
                f"{_opportunity_group_label(summary.opportunity_group)} | "
                f"{_block_reason_label(summary.blocked_by)} | "
                f"{summary.count} | "
                f"{', '.join(summary.symbols[:10])} | "
                f"{', '.join(str(index) for index in summary.sample_indexes[:20])} |"
            )
        lines.append("")

    if report.opportunity_cost_summaries:
        lines.extend(
            [
                f"## 机会成本分层（后续 {report.opportunity_window_days} 个交易日）",
                "",
                "| 类型 | 原因 | 样本 | 有后续收益 | 最高涨幅为正 | 比例 | 平均最高涨幅 | 平均窗口收盘涨幅 | 样本编号 |",
                "|---|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for summary in report.opportunity_cost_summaries[:limit]:
            lines.append(
                "| "
                f"{_opportunity_group_label(summary.opportunity_group)} | "
                f"{_block_reason_label(summary.blocked_by)} | "
                f"{summary.sample_count} | "
                f"{summary.observed_count} | "
                f"{summary.positive_max_high_count} | "
                f"{_format_optional_percent(summary.positive_max_high_rate)} | "
                f"{_format_optional_percent(summary.average_max_high_return_pct)} | "
                f"{_format_optional_percent(summary.average_window_close_return_pct)} | "
                f"{', '.join(str(index) for index in summary.sample_indexes[:20])} |"
        )
        lines.append("")

    if report.add_on_entry_summaries:
        lines.extend(
            [
                f"## 加仓入场点反查（后续 {report.add_on_window_days} 个交易日）",
                "",
                "| 组合 | 样本 | 有后续收益 | 最高涨幅为正 | 比例 | 平均最高涨幅 | 平均窗口收盘涨幅 | 平均交易收益 | 样本编号 | 交易编号 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for summary in report.add_on_entry_summaries[:limit]:
            lines.append(
                "| "
                f"{_profile_label(summary.profile_key)} | "
                f"{summary.sample_count} | "
                f"{summary.observed_count} | "
                f"{summary.positive_max_high_count} | "
                f"{_format_optional_percent(summary.positive_max_high_rate)} | "
                f"{_format_optional_percent(summary.average_max_high_return_pct)} | "
                f"{_format_optional_percent(summary.average_window_close_return_pct)} | "
                f"{_format_optional_percent(summary.average_trade_return_pct)} | "
                f"{', '.join(str(index) for index in summary.sample_indexes[:20])} | "
                f"{', '.join(str(index) for index in summary.trade_indexes[:20])} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 交易复盘明细",
            "",
            "| # | 股票 | 结果 | 入场 | 退出 | 原因 | 收益 | 加仓 | 卖飞 | 最高涨幅 | 入场检查 | 出场检查 | 加仓检查 | 标记 |",
            "|---:|---|---|---|---|---|---:|---:|---|---:|---|---|---|---|",
        ]
    )
    for trade in report.trades[:limit]:
        lines.append(
            "| "
            f"{trade.trade_index} | "
            f"{trade.symbol} | "
            f"{_outcome_label(trade.outcome)} | "
            f"{trade.entry_date.isoformat()} | "
            f"{trade.exit_date.isoformat()} | "
            f"{trade.exit_reason} | "
            f"{_format_percent(trade.return_pct)} | "
            f"{trade.add_on_count} | "
            f"{_format_optional_bool(trade.sold_too_early)} | "
            f"{_format_optional_percent(trade.max_high_return_pct)} | "
            f"{_format_checks(trade.entry_checks)} | "
            f"{_format_checks(trade.exit_checks)} | "
            f"{_format_checks(trade.add_on_checks)} | "
            f"{_format_flags(trade.review_flags)} |"
        )
    if len(report.trades) > limit:
        lines.append("")
        lines.append(f"仅展示前 {limit} 条交易，完整明细见 `trade_review.json`。")

    if report.opportunities:
        lines.extend(
            [
                "",
                "## 机会/拦截样本",
                "",
                "| # | 日期 | 股票 | 类型 | 来源 | 原因 | 方法 | 机会价 | 最高涨幅 | 窗口收盘 | 失败检查 | 证据检查 |",
                "|---:|---|---|---|---|---|---|---:|---:|---:|---|---|",
            ]
        )
        for sample in report.opportunities[:limit]:
            follow_up = sample.follow_up
            lines.append(
                "| "
                f"{sample.sample_index} | "
                f"{sample.trade_date.isoformat()} | "
                f"{sample.symbol} | "
                f"{_opportunity_group_label(sample.opportunity_group)} | "
                f"{sample.source} | "
                f"{_block_reason_label(sample.blocked_by or sample.reason_code)} | "
                f"{sample.method_name or '-'} | "
                f"{_format_optional_number(sample.opportunity_price)} | "
                f"{_format_optional_percent(follow_up.max_high_return_pct if follow_up is not None else None)} | "
                f"{_format_optional_percent(follow_up.window_close_return_pct if follow_up is not None else None)} | "
                f"{_format_factor_keys(sample.failed_checks)} | "
                f"{_format_checks(sample.checks)} |"
            )
        if len(report.opportunities) > limit:
            lines.append("")
            lines.append(f"仅展示前 {limit} 条机会/拦截样本，完整明细见 `trade_review.json`。")

    if report.add_on_entry_points:
        lines.extend(
            [
                "",
                "## 加仓入场点样本",
                "",
                "| # | 交易 | 日期 | 股票 | 交易结果 | 方法 | 价格 | 最高涨幅 | 窗口收盘 | 加仓检查 |",
                "|---:|---:|---|---|---|---|---:|---:|---:|---|",
            ]
        )
        for sample in report.add_on_entry_points[:limit]:
            lines.append(
                "| "
                f"{sample.sample_index} | "
                f"{sample.trade_index} | "
                f"{sample.add_on_date.isoformat()} | "
                f"{sample.symbol} | "
                f"{_outcome_label(sample.outcome)} | "
                f"{sample.method_name or '-'} | "
                f"{_format_optional_number(sample.add_on_price)} | "
                f"{_format_optional_percent(sample.follow_up.max_high_return_pct)} | "
                f"{_format_optional_percent(sample.follow_up.window_close_return_pct)} | "
                f"{_format_checks(sample.checks)} |"
            )
        if len(report.add_on_entry_points) > limit:
            lines.append("")
            lines.append(f"仅展示前 {limit} 条加仓入场点样本，完整明细见 `trade_review.json`。")

    return "\n".join(lines).rstrip() + "\n"


def _review_trade(lifecycle: TradeLifecycle, post_exit: PostExitTradeObservation | None) -> TradeReviewTrade:
    entry_event = _event_by_type(lifecycle, "entry")
    exit_event = _event_by_type(lifecycle, "exit")
    add_on_events = tuple(event for event in lifecycle.events if event.event_type == "add_on")
    add_on_checks = _merge_checks(*(event.checks for event in add_on_events))
    review_flags = _review_flags(lifecycle, post_exit, add_on_count=len(add_on_events))
    return TradeReviewTrade(
        trade_index=lifecycle.trade_index,
        symbol=lifecycle.symbol,
        outcome=lifecycle.outcome,
        entry_date=lifecycle.entry_date,
        exit_date=lifecycle.exit_date,
        exit_reason=lifecycle.exit_reason,
        return_pct=lifecycle.return_pct,
        entry_method_name=entry_event.method_name if entry_event is not None else None,
        exit_method_name=exit_event.method_name if exit_event is not None else None,
        add_on_count=len(add_on_events),
        sold_too_early=post_exit.sold_too_early if post_exit is not None else None,
        max_high_return_pct=post_exit.max_high_return_pct if post_exit is not None else None,
        primary_window_close_return_pct=(
            post_exit.primary_window_close_return_pct if post_exit is not None else None
        ),
        entry_checks=_selected_checks(entry_event.checks if entry_event is not None else {}),
        exit_checks=_selected_checks(exit_event.checks if exit_event is not None else {}),
        add_on_checks=_selected_checks(add_on_checks),
        review_flags=review_flags,
    )


def _event_by_type(lifecycle: TradeLifecycle, event_type: str):
    for event in lifecycle.events:
        if event.event_type == event_type:
            return event
    return None


def _review_flags(
    lifecycle: TradeLifecycle,
    post_exit: PostExitTradeObservation | None,
    *,
    add_on_count: int,
) -> tuple[str, ...]:
    flags: list[str] = []
    if lifecycle.return_pct > 0:
        flags.append("win")
    elif lifecycle.return_pct < 0:
        flags.append("loss")
    if add_on_count:
        flags.append("has_add_on")
    if post_exit is not None and post_exit.sold_too_early is True:
        flags.append("sold_too_early")
    if lifecycle.exit_reason:
        flags.append(f"exit_reason:{lifecycle.exit_reason}")
    return tuple(flags)


def _sold_too_early_profiles(
    observations: Sequence[PostExitTradeObservation],
) -> tuple[SoldTooEarlyProfileSummary, ...]:
    buckets: dict[str, list[PostExitTradeObservation]] = defaultdict(list)
    for observation in observations:
        buckets[_sold_profile_key(observation)].append(observation)

    summaries = tuple(_sold_profile_summary(profile_key, items) for profile_key, items in buckets.items())
    return tuple(
        sorted(
            summaries,
            key=lambda item: (
                -(item.sold_too_early_rate if item.sold_too_early_rate is not None else -1.0),
                -item.sold_too_early_count,
                -item.observed_count,
                -item.sample_count,
                -(item.average_max_high_return_pct if item.average_max_high_return_pct is not None else -1.0),
                item.profile_key,
            ),
        )
    )


def _sold_profile_key(observation: PostExitTradeObservation) -> str:
    parts = [
        f"exit.group={observation.exit_group}",
        f"trade.outcome={observation.outcome}",
    ]
    for key in _SOLD_TOO_EARLY_PROFILE_CHECK_KEYS:
        if key in observation.exit_checks:
            parts.append(f"{key}={str(observation.exit_checks[key]).lower()}")
    return "|".join(parts)


def _sold_profile_summary(
    profile_key: str,
    observations: Sequence[PostExitTradeObservation],
) -> SoldTooEarlyProfileSummary:
    observed = tuple(item for item in observations if item.observed_day_count > 0)
    sold_count = sum(1 for item in observed if item.sold_too_early is True)
    max_high_values = tuple(item.max_high_return_pct for item in observed if item.max_high_return_pct is not None)
    trade_returns = tuple(item.trade_return_pct for item in observations)
    return SoldTooEarlyProfileSummary(
        profile_key=profile_key,
        sample_count=len(observations),
        observed_count=len(observed),
        sold_too_early_count=sold_count,
        sold_too_early_rate=(sold_count / len(observed)) if observed else None,
        average_max_high_return_pct=(sum(max_high_values) / len(max_high_values)) if max_high_values else None,
        average_trade_return_pct=(sum(trade_returns) / len(trade_returns)) if trade_returns else None,
        trade_indexes=tuple(item.trade_index for item in observations),
    )


def _stop_loss_rebound_profiles(
    observations: Sequence[PostExitTradeObservation],
    thresholds: Sequence[float],
) -> tuple[StopLossReboundProfileSummary, ...]:
    stop_loss_observations = tuple(item for item in observations if item.exit_group == "stop_loss")
    if not stop_loss_observations:
        return ()

    buckets: dict[str, list[PostExitTradeObservation]] = defaultdict(list)
    for observation in stop_loss_observations:
        buckets[_sold_profile_key(observation)].append(observation)

    summaries = tuple(
        _stop_loss_rebound_profile_summary(profile_key, threshold, tuple(items))
        for profile_key, items in buckets.items()
        for threshold in thresholds
    )
    return tuple(
        sorted(
            summaries,
            key=lambda item: (
                -item.threshold,
                -(item.rebound_rate if item.rebound_rate is not None else -1.0),
                -item.rebound_count,
                -item.observed_count,
                -item.sample_count,
                item.profile_key,
            ),
        )
    )


def _stop_loss_rebound_profile_summary(
    profile_key: str,
    threshold: float,
    observations: Sequence[PostExitTradeObservation],
) -> StopLossReboundProfileSummary:
    observed = tuple(item for item in observations if item.observed_day_count > 0)
    rebound_count = sum(
        1
        for item in observed
        if item.max_high_return_pct is not None and item.max_high_return_pct > threshold
    )
    max_high_values = tuple(item.max_high_return_pct for item in observed if item.max_high_return_pct is not None)
    trade_returns = tuple(item.trade_return_pct for item in observations)
    return StopLossReboundProfileSummary(
        profile_key=profile_key,
        threshold=threshold,
        sample_count=len(observations),
        observed_count=len(observed),
        rebound_count=rebound_count,
        rebound_rate=(rebound_count / len(observed)) if observed else None,
        average_max_high_return_pct=(sum(max_high_values) / len(max_high_values)) if max_high_values else None,
        average_trade_return_pct=(sum(trade_returns) / len(trade_returns)) if trade_returns else None,
        trade_indexes=tuple(item.trade_index for item in observations),
    )


def _opportunities(
    signal_audit: Sequence[TradeIntent],
    execution_audit: Sequence[ExecutionAuditEvent],
    *,
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    opportunity_window_days: int,
) -> tuple[TradeReviewOpportunitySample, ...]:
    samples: list[TradeReviewOpportunitySample] = []
    rejected_keys = {
        (event.symbol, event.signal_date, event.reason_code)
        for event in execution_audit
        if _is_rejected_execution(event)
    }
    intents_by_key = _intents_by_key(signal_audit)

    for event in sorted(execution_audit, key=lambda item: (item.signal_date, item.symbol, item.reason_code)):
        if not _is_rejected_execution(event):
            continue
        intent = _pop_intent(intents_by_key, event.symbol, event.signal_date, event.reason_code)
        samples.append(
            _opportunity_sample(
                sample_index=len(samples) + 1,
                source="execution",
                group="execution_rejection",
                symbol=event.symbol,
                trade_date=event.signal_date,
                intent=intent,
                reason_code=event.reason_code,
                blocked_by=event.blocked_by,
                event_signal_price=event.signal_price,
                bars=bars_by_symbol.get(event.symbol, ()),
                opportunity_window_days=opportunity_window_days,
            )
        )

    for intent in sorted(signal_audit, key=lambda item: (item.trade_date, item.symbol, item.reason_code)):
        key = (intent.symbol, intent.trade_date, intent.reason_code)
        if key in rejected_keys:
            continue
        group = _opportunity_group(intent)
        if group is None:
            continue
        samples.append(
            _opportunity_sample(
                sample_index=len(samples) + 1,
                source="signal",
                group=group,
                symbol=intent.symbol,
                trade_date=intent.trade_date,
                intent=intent,
                reason_code=intent.reason_code,
                blocked_by=_blocked_reason(intent),
                event_signal_price=None,
                bars=bars_by_symbol.get(intent.symbol, ()),
                opportunity_window_days=opportunity_window_days,
            )
        )

    return tuple(samples)


def _opportunity_group(intent: TradeIntent) -> str | None:
    if _is_entry_filter_block(intent):
        return "entry_filter"
    if _sizing_blocked_by(intent) is not None:
        return "sizing_block"
    if intent.blocked_by:
        return "signal_block"
    return None


def _opportunity_sample(
    *,
    sample_index: int,
    source: str,
    group: str,
    symbol: str,
    trade_date: date,
    intent: TradeIntent | None,
    reason_code: str,
    blocked_by: str | None,
    event_signal_price: float | None,
    bars: Sequence[DailyBar],
    opportunity_window_days: int,
) -> TradeReviewOpportunitySample:
    signal_values = intent.signal_values if intent is not None else {}
    sorted_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    opportunity_price = _opportunity_price(
        signal_values=signal_values,
        trade_date=trade_date,
        bars=sorted_bars,
        event_signal_price=event_signal_price,
    )
    return TradeReviewOpportunitySample(
        sample_index=sample_index,
        source=source,
        opportunity_group=group,
        symbol=symbol,
        trade_date=trade_date,
        intent_type=intent.intent_type.value if intent is not None else None,
        method_name=intent.method_name if intent is not None else None,
        reason_code=reason_code,
        blocked_by=blocked_by,
        failed_checks=_failed_checks(signal_values),
        checks=_selected_checks(_checks(signal_values)),
        opportunity_price=opportunity_price,
        follow_up=_opportunity_follow_up(
            trade_date=trade_date,
            bars=sorted_bars,
            price=opportunity_price,
            window_days=opportunity_window_days,
        ),
    )


def _opportunity_summaries(
    samples: Sequence[TradeReviewOpportunitySample],
) -> tuple[TradeReviewOpportunitySummary, ...]:
    buckets: dict[tuple[str, str], list[TradeReviewOpportunitySample]] = defaultdict(list)
    for sample in samples:
        buckets[(sample.opportunity_group, sample.blocked_by or sample.reason_code)].append(sample)

    summaries = tuple(
        TradeReviewOpportunitySummary(
            opportunity_group=group,
            blocked_by=reason,
            count=len(items),
            symbols=tuple(sorted({item.symbol for item in items})),
            sample_indexes=tuple(item.sample_index for item in items),
        )
        for (group, reason), items in buckets.items()
    )
    return tuple(sorted(summaries, key=lambda item: (-item.count, item.opportunity_group, item.blocked_by)))


def _opportunity_cost_summaries(
    samples: Sequence[TradeReviewOpportunitySample],
) -> tuple[TradeReviewOpportunityCostSummary, ...]:
    buckets: dict[tuple[str, str], list[TradeReviewOpportunitySample]] = defaultdict(list)
    for sample in samples:
        buckets[(sample.opportunity_group, sample.blocked_by or sample.reason_code)].append(sample)

    summaries = tuple(
        _opportunity_cost_summary(group, reason, tuple(items))
        for (group, reason), items in buckets.items()
    )
    return tuple(
        sorted(
            summaries,
            key=lambda item: (
                -(item.average_max_high_return_pct if item.average_max_high_return_pct is not None else -1.0),
                -item.observed_count,
                -item.sample_count,
                item.opportunity_group,
                item.blocked_by,
            ),
        )
    )


def _opportunity_cost_summary(
    group: str,
    reason: str,
    samples: Sequence[TradeReviewOpportunitySample],
) -> TradeReviewOpportunityCostSummary:
    observed = tuple(
        sample
        for sample in samples
        if sample.follow_up is not None and sample.follow_up.max_high_return_pct is not None
    )
    max_high_values = tuple(sample.follow_up.max_high_return_pct for sample in observed if sample.follow_up is not None)
    window_close_values = tuple(
        sample.follow_up.window_close_return_pct
        for sample in observed
        if sample.follow_up is not None and sample.follow_up.window_close_return_pct is not None
    )
    positive_max_high_count = sum(
        1
        for sample in observed
        if sample.follow_up is not None and sample.follow_up.max_high_return_pct is not None
        and sample.follow_up.max_high_return_pct > 0
    )
    return TradeReviewOpportunityCostSummary(
        opportunity_group=group,
        blocked_by=reason,
        sample_count=len(samples),
        observed_count=len(observed),
        positive_max_high_count=positive_max_high_count,
        positive_max_high_rate=(positive_max_high_count / len(observed)) if observed else None,
        average_max_high_return_pct=(sum(max_high_values) / len(max_high_values)) if max_high_values else None,
        average_window_close_return_pct=(
            sum(window_close_values) / len(window_close_values)
        ) if window_close_values else None,
        sample_indexes=tuple(sample.sample_index for sample in samples),
    )


def _add_on_entry_points(
    lifecycles: Sequence[TradeLifecycle],
    *,
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    window_days: int,
) -> tuple[TradeReviewAddOnEntryPoint, ...]:
    samples: list[TradeReviewAddOnEntryPoint] = []
    for lifecycle in lifecycles:
        bars = bars_by_symbol.get(lifecycle.symbol, ())
        for event in lifecycle.events:
            if event.event_type != "add_on":
                continue
            add_on_price = _add_on_price(event=event, trade_date=event.trade_date, bars=bars)
            samples.append(
                TradeReviewAddOnEntryPoint(
                    sample_index=len(samples) + 1,
                    trade_index=lifecycle.trade_index,
                    symbol=lifecycle.symbol,
                    outcome=lifecycle.outcome,
                    trade_return_pct=lifecycle.return_pct,
                    add_on_date=event.trade_date,
                    method_name=event.method_name,
                    reason_code=event.reason_code,
                    checks=_selected_checks(event.checks),
                    categories=dict(event.categories),
                    add_on_price=add_on_price,
                    follow_up=_opportunity_follow_up(
                        trade_date=event.trade_date,
                        bars=bars,
                        price=add_on_price,
                        window_days=window_days,
                    ),
                )
            )
    return tuple(samples)


def _add_on_entry_summaries(
    samples: Sequence[TradeReviewAddOnEntryPoint],
) -> tuple[TradeReviewAddOnEntrySummary, ...]:
    buckets: dict[str, list[TradeReviewAddOnEntryPoint]] = defaultdict(list)
    for sample in samples:
        buckets[_add_on_profile_key(sample)].append(sample)

    summaries = tuple(
        _add_on_entry_summary(profile_key, tuple(items))
        for profile_key, items in buckets.items()
    )
    return tuple(
        sorted(
            summaries,
            key=lambda item: (
                -(item.positive_max_high_rate if item.positive_max_high_rate is not None else -1.0),
                -item.positive_max_high_count,
                -item.observed_count,
                -item.sample_count,
                -(item.average_max_high_return_pct if item.average_max_high_return_pct is not None else -1.0),
                item.profile_key,
            ),
        )
    )


def _add_on_profile_key(sample: TradeReviewAddOnEntryPoint) -> str:
    parts = [
        f"trade.outcome={sample.outcome}",
        f"add_on.method_name={sample.method_name or '-'}",
    ]
    for key in _ADD_ON_PROFILE_CHECK_KEYS:
        if key in sample.checks:
            parts.append(f"{key}={str(sample.checks[key]).lower()}")
    return "|".join(parts)


def _add_on_entry_summary(
    profile_key: str,
    samples: Sequence[TradeReviewAddOnEntryPoint],
) -> TradeReviewAddOnEntrySummary:
    observed = tuple(sample for sample in samples if sample.follow_up.max_high_return_pct is not None)
    max_high_values = tuple(sample.follow_up.max_high_return_pct for sample in observed)
    window_close_values = tuple(
        sample.follow_up.window_close_return_pct
        for sample in observed
        if sample.follow_up.window_close_return_pct is not None
    )
    trade_returns = tuple(sample.trade_return_pct for sample in samples)
    positive_max_high_count = sum(
        1
        for sample in observed
        if sample.follow_up.max_high_return_pct is not None and sample.follow_up.max_high_return_pct > 0
    )
    return TradeReviewAddOnEntrySummary(
        profile_key=profile_key,
        sample_count=len(samples),
        observed_count=len(observed),
        positive_max_high_count=positive_max_high_count,
        positive_max_high_rate=(positive_max_high_count / len(observed)) if observed else None,
        average_max_high_return_pct=(sum(max_high_values) / len(max_high_values)) if max_high_values else None,
        average_window_close_return_pct=(
            sum(window_close_values) / len(window_close_values)
        ) if window_close_values else None,
        average_trade_return_pct=(sum(trade_returns) / len(trade_returns)) if trade_returns else None,
        sample_indexes=tuple(sample.sample_index for sample in samples),
        trade_indexes=tuple(dict.fromkeys(sample.trade_index for sample in samples)),
    )


def _add_on_price(
    *,
    event,
    trade_date: date,
    bars: Sequence[DailyBar],
) -> float | None:
    execution_price = next(
        (
            execution.executed_price
            for execution in event.executions
            if execution.executed_price is not None and execution.executed_price > 0
        ),
        None,
    )
    if execution_price is not None:
        return execution_price

    sizing_price = _first_numeric_value(
        event.sizing_context,
        ("price", "signal_price", "current_price", "close"),
    )
    if sizing_price is not None and sizing_price > 0:
        return sizing_price

    value_price = _first_numeric_value(
        event.values,
        ("current_price", "symbol.close", "price", "signal_price", "close"),
    )
    if value_price is not None and value_price > 0:
        return value_price

    bar = _bar_on_date(bars, trade_date)
    if bar is not None and bar.close > 0:
        return bar.close
    return None


def _opportunity_price(
    *,
    signal_values: Mapping[str, Any],
    trade_date: date,
    bars: Sequence[DailyBar],
    event_signal_price: float | None,
) -> float | None:
    if event_signal_price is not None and event_signal_price > 0:
        return event_signal_price

    sizing_values = signal_values.get("sizing")
    if isinstance(sizing_values, Mapping):
        sizing_price = _first_numeric_value(
            sizing_values,
            ("price", "signal_price", "current_price", "close"),
        )
        if sizing_price is not None and sizing_price > 0:
            return sizing_price

    direct_price = _first_numeric_value(signal_values, ("current_price", "price", "signal_price", "close"))
    if direct_price is not None and direct_price > 0:
        return direct_price

    attribution = signal_values.get("attribution")
    if isinstance(attribution, Mapping):
        values = attribution.get("values")
        if isinstance(values, Mapping):
            attribution_price = _first_numeric_value(
                values,
                ("symbol.close", "current_price", "price", "close"),
            )
            if attribution_price is not None and attribution_price > 0:
                return attribution_price

    bar = _bar_on_date(bars, trade_date)
    if bar is not None and bar.close > 0:
        return bar.close
    return None


def _opportunity_follow_up(
    *,
    trade_date: date,
    bars: Sequence[DailyBar],
    price: float | None,
    window_days: int,
) -> TradeReviewOpportunityFollowUp:
    future_bars = tuple(bar for bar in bars if bar.trade_date > trade_date)[:window_days]
    if price is None or price <= 0:
        return TradeReviewOpportunityFollowUp(
            window_days=window_days,
            observed_day_count=len(future_bars),
            complete=len(future_bars) >= window_days,
            window_close_return_pct=None,
            max_high_return_pct=None,
            min_low_return_pct=None,
        )

    close_returns = tuple(bar.close / price - 1.0 for bar in future_bars)
    high_returns = tuple(bar.high / price - 1.0 for bar in future_bars)
    low_returns = tuple(bar.low / price - 1.0 for bar in future_bars)
    return TradeReviewOpportunityFollowUp(
        window_days=window_days,
        observed_day_count=len(future_bars),
        complete=len(future_bars) >= window_days,
        window_close_return_pct=close_returns[window_days - 1] if len(close_returns) >= window_days else None,
        max_high_return_pct=max(high_returns) if high_returns else None,
        min_low_return_pct=min(low_returns) if low_returns else None,
    )


def _first_numeric_value(values: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _bar_on_date(bars: Sequence[DailyBar], trade_date: date) -> DailyBar | None:
    for bar in bars:
        if bar.trade_date == trade_date:
            return bar
    return None


def _sorted_bars_by_symbol(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
) -> dict[str, tuple[DailyBar, ...]]:
    return {
        symbol: tuple(sorted(bars, key=lambda bar: bar.trade_date))
        for symbol, bars in bars_by_symbol.items()
    }


def _intents_by_key(signal_audit: Sequence[TradeIntent]) -> dict[tuple[str, date, str], deque[TradeIntent]]:
    result: dict[tuple[str, date, str], deque[TradeIntent]] = defaultdict(deque)
    for intent in sorted(signal_audit, key=lambda item: (item.trade_date, item.symbol, item.reason_code)):
        result[(intent.symbol, intent.trade_date, intent.reason_code)].append(intent)
    return result


def _pop_intent(
    intents_by_key: dict[tuple[str, date, str], deque[TradeIntent]],
    symbol: str,
    trade_date: date,
    reason_code: str,
) -> TradeIntent | None:
    intents = intents_by_key.get((symbol, trade_date, reason_code))
    if not intents:
        return None
    return intents.popleft()


def _is_rejected_execution(event: ExecutionAuditEvent) -> bool:
    return event.event_type == "rejected" or event.status.lower() == "rejected"


def _is_entry_filter_block(intent: TradeIntent) -> bool:
    return (
        intent.blocked_by == "ENTRY_ATTRIBUTION_FILTER"
        or intent.reason_code == "ENTRY_ATTRIBUTION_FILTERED"
        or isinstance(intent.signal_values.get("entry_attribution_filter"), Mapping)
    )


def _sizing_blocked_by(intent: TradeIntent) -> str | None:
    sizing_values = intent.signal_values.get("sizing")
    if not isinstance(sizing_values, Mapping):
        return None
    blocked_by = sizing_values.get("blocked_by")
    return str(blocked_by) if blocked_by else None


def _blocked_reason(intent: TradeIntent) -> str | None:
    return intent.blocked_by or _sizing_blocked_by(intent)


def _failed_checks(signal_values: Mapping[str, Any]) -> tuple[str, ...]:
    payload = signal_values.get("entry_attribution_filter")
    if not isinstance(payload, Mapping):
        return ()
    failed_checks = payload.get("failed_checks")
    if not isinstance(failed_checks, Sequence) or isinstance(failed_checks, str):
        return ()
    return tuple(str(item) for item in failed_checks)


def _post_exit_by_trade_key(
    observations: Sequence[PostExitTradeObservation],
) -> dict[tuple[str, date, date, str], PostExitTradeObservation]:
    return {
        (item.symbol, item.entry_date, item.exit_date, item.exit_reason): item
        for item in observations
    }


def _lifecycle_key(lifecycle: TradeLifecycle) -> tuple[str, date, date, str]:
    return (lifecycle.symbol, lifecycle.entry_date, lifecycle.exit_date, lifecycle.exit_reason)


def _selected_checks(checks: Mapping[str, bool]) -> dict[str, bool]:
    selected = {key: checks[key] for key in _REVIEW_CHECK_KEYS if key in checks}
    if selected:
        return selected
    return dict(sorted(checks.items())[:6])


def _merge_checks(*checks: Mapping[str, bool]) -> dict[str, bool]:
    merged: dict[str, bool] = {}
    for item in checks:
        merged.update(item)
    return merged


def _checks(signal_values: Mapping[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    legacy_checks = signal_values.get("checks")
    if isinstance(legacy_checks, Mapping):
        checks.update({str(key): value for key, value in legacy_checks.items() if isinstance(value, bool)})
    attribution = signal_values.get("attribution")
    if isinstance(attribution, Mapping):
        attribution_checks = attribution.get("checks")
        if isinstance(attribution_checks, Mapping):
            checks.update(
                {str(key): value for key, value in attribution_checks.items() if isinstance(value, bool)}
            )
    return checks


def _profile_label(profile_key: str) -> str:
    parts = []
    for part in profile_key.split("|"):
        if "=" not in part:
            parts.append(part)
            continue
        key, value = part.split("=", 1)
        parts.append(f"{_factor_label(key)}={_value_label(value)}")
    return "；".join(parts)


def _format_checks(checks: Mapping[str, bool]) -> str:
    if not checks:
        return "-"
    return "；".join(
        f"{_factor_label(key)}={_format_bool(value)}"
        for key, value in sorted(checks.items())[:6]
    )


def _format_factor_keys(keys: Sequence[str]) -> str:
    if not keys:
        return "-"
    return "；".join(_factor_label(key) for key in keys[:6])


def _format_flags(flags: Sequence[str]) -> str:
    if not flags:
        return "-"
    return "；".join(_flag_label(flag) for flag in flags)


def _factor_label(key: str) -> str:
    if key == "exit.group":
        return "退出类型"
    if key == "trade.outcome":
        return "交易结果"
    if key == "add_on.method_name":
        return "加仓方法"
    declaration = _ATTRIBUTION_DECLARATIONS.get(key)
    if declaration is not None:
        return declaration.label_zh
    return {
        "current_price_at_or_below_stop": "当前价触及止损价",
        "kdj_j_above_threshold": "KDJ J 高于阈值",
        "kdj_j_below_threshold": "KDJ J 低于阈值",
        "position.unrealized_return_at_or_above_min": "持仓浮盈达到加仓阈值",
        "position.add_on_count_available": "加仓次数可用",
        "unrealized_return_at_or_above_min": "持仓浮盈达到加仓阈值",
        "add_on_count_available": "加仓次数可用",
    }.get(key, key)


def _value_label(value: str) -> str:
    return {
        "true": "是",
        "false": "否",
        "win": "盈利",
        "loss": "亏损",
        "flat": "持平",
        "take_profit": "止盈",
        "stop_loss": "止损",
        "other": "其他",
    }.get(value, value)


def _opportunity_group_label(group: str) -> str:
    return {
        "entry_filter": "入场过滤",
        "sizing_block": "Sizing 拦截",
        "signal_block": "信号拦截",
        "execution_rejection": "执行拒单",
    }.get(group, group)


def _block_reason_label(reason: str) -> str:
    return {
        "ATR_RISK_UNAVAILABLE": "ATR 风险值不可用",
        "BOARD_LOT_TOO_SMALL": "不足一手 (BOARD_LOT_TOO_SMALL)",
        "CASH_NOT_ENOUGH": "现金不足",
        "ENTRY_ATTRIBUTION_FILTER": "入场归因过滤",
        "LIMIT_DOWN_SELL_BLOCKED": "跌停卖出受限",
        "LIMIT_UP_BUY_BLOCKED": "涨停买入受限",
        "MAX_HOLDING_COUNT": "达到最大持仓数量",
        "REBALANCE_INTERVAL": "再平衡间隔不足",
        "SIZING_ZERO_QUANTITY": "仓位计算为 0",
        "SUSPENDED": "停牌",
        "T_PLUS_ONE_SELL_BLOCKED": "T+1 卖出受限",
    }.get(reason, reason)


def _outcome_label(outcome: str) -> str:
    return {"win": "盈利", "loss": "亏损", "flat": "持平"}.get(outcome, outcome)


def _flag_label(flag: str) -> str:
    if flag.startswith("exit_reason:"):
        return flag.replace("exit_reason:", "退出原因:")
    return {
        "win": "盈利",
        "loss": "亏损",
        "has_add_on": "有加仓",
        "sold_too_early": "卖飞",
    }.get(flag, flag)


def _format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_percent(value)


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return _format_bool(value)


def _format_bool(value: bool) -> str:
    return "是" if value else "否"
