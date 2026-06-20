"""Post-exit observations for completed trades."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from attbacktrader.data import DailyBar
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import entry_attribution_declaration_by_key
from attbacktrader.strategies.templates import ClosedTrade

_ATTRIBUTION_DECLARATIONS = entry_attribution_declaration_by_key()


@dataclass(frozen=True)
class PostExitDayObservation:
    day_index: int
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    close_return_pct: float
    high_return_pct: float
    low_return_pct: float


@dataclass(frozen=True)
class PostExitWindowObservation:
    window_days: int
    observed_day_count: int
    complete: bool
    window_close_return_pct: float | None
    max_close_return_pct: float | None
    max_high_return_pct: float | None
    min_low_return_pct: float | None
    sold_too_early: bool | None


@dataclass(frozen=True)
class PostExitTradeObservation:
    trade_index: int
    symbol: str
    outcome: str
    entry_date: date
    exit_date: date
    exit_reason: str
    exit_intent_type: str | None
    exit_method_name: str | None
    exit_group: str
    exit_checks: Mapping[str, bool]
    exit_values: Mapping[str, Any]
    exit_categories: Mapping[str, str]
    exit_price: float
    trade_return_pct: float
    observed_day_count: int
    fifth_day_close_return_pct: float | None
    primary_window_close_return_pct: float | None
    max_close_return_pct: float | None
    max_high_return_pct: float | None
    min_low_return_pct: float | None
    sold_too_early: bool | None
    windows: tuple[PostExitWindowObservation, ...]
    observations: tuple[PostExitDayObservation, ...]


@dataclass(frozen=True)
class PostExitGroupSummary:
    group: str
    sample_count: int
    observed_count: int
    sold_too_early_count: int
    sold_too_early_rate: float | None
    average_max_high_return_pct: float | None
    average_fifth_day_close_return_pct: float | None


@dataclass(frozen=True)
class PostExitWindowGroupSummary:
    window_days: int
    group: str
    sample_count: int
    observed_count: int
    complete_count: int
    sold_too_early_count: int
    sold_too_early_rate: float | None
    average_max_high_return_pct: float | None
    average_window_close_return_pct: float | None


@dataclass(frozen=True)
class PostExitThresholdGroupSummary:
    threshold: float
    group: str
    sample_count: int
    observed_count: int
    rebound_count: int
    rebound_rate: float | None
    average_max_high_return_pct: float | None
    average_window_close_return_pct: float | None


@dataclass(frozen=True)
class PostExitFactorGroupSummary:
    window_days: int
    factor_key: str
    factor_type: str
    factor_value: str
    sample_count: int
    observed_count: int
    sold_too_early_count: int
    sold_too_early_rate: float | None
    average_max_high_return_pct: float | None
    average_window_close_return_pct: float | None


@dataclass(frozen=True)
class PostExitAnalysisReport:
    window_days: int
    configured_window_days: tuple[int, ...]
    sold_too_early_threshold: float
    rebound_thresholds: tuple[float, ...]
    trade_count: int
    summaries: tuple[PostExitGroupSummary, ...]
    window_summaries: tuple[PostExitWindowGroupSummary, ...]
    threshold_summaries: tuple[PostExitThresholdGroupSummary, ...]
    factor_group_summaries: tuple[PostExitFactorGroupSummary, ...]
    observations: tuple[PostExitTradeObservation, ...]


def build_post_exit_analysis(
    *,
    closed_trades: Sequence[ClosedTrade],
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    signal_audit: Sequence[TradeIntent] = (),
    window_days: int | Sequence[int] = 5,
    primary_window_days: int | None = None,
    sold_too_early_threshold: float = 0.0,
    rebound_thresholds: Sequence[float] = (0.0, 0.02, 0.05, 0.10),
) -> PostExitAnalysisReport:
    configured_window_days = _normalize_window_days(window_days)
    primary_window_days = _primary_window_days(configured_window_days, primary_window_days)
    configured_rebound_thresholds = _normalize_rebound_thresholds(rebound_thresholds)

    bars_by_symbol = {
        symbol: tuple(sorted(bars, key=lambda bar: bar.trade_date))
        for symbol, bars in bars_by_symbol.items()
    }
    exit_intents_by_key = _exit_intents_by_key(signal_audit)
    observations = tuple(
        _trade_observation(
            index=index,
            trade=trade,
            bars=bars_by_symbol.get(trade.symbol, ()),
            exit_intents_by_key=exit_intents_by_key,
            window_days=configured_window_days,
            primary_window_days=primary_window_days,
            sold_too_early_threshold=sold_too_early_threshold,
        )
        for index, trade in enumerate(
            sorted(closed_trades, key=lambda value: (value.exit_date, value.symbol, value.exit_reason)),
            start=1,
        )
    )
    return PostExitAnalysisReport(
        window_days=primary_window_days,
        configured_window_days=configured_window_days,
        sold_too_early_threshold=sold_too_early_threshold,
        rebound_thresholds=configured_rebound_thresholds,
        trade_count=len(observations),
        summaries=_summaries(observations),
        window_summaries=_window_summaries(observations, configured_window_days),
        threshold_summaries=_threshold_summaries(observations, configured_rebound_thresholds),
        factor_group_summaries=_factor_group_summaries(observations),
        observations=observations,
    )


def render_post_exit_analysis_markdown_zh(report: PostExitAnalysisReport, *, limit: int = 30) -> str:
    lines = [
        "# 卖出后观察",
        "",
        f"主窗口：卖出后 {report.window_days} 个交易日",
        f"全部窗口：{', '.join(str(window) for window in report.configured_window_days)} 个交易日",
        f"卖飞阈值：{_format_percent(report.sold_too_early_threshold)}",
        f"反弹分层阈值：{', '.join(_format_percent(threshold) for threshold in report.rebound_thresholds)}",
        "",
        "## 主窗口汇总",
        "",
        "| 分组 | 样本 | 有后续数据 | 卖飞/反弹 | 比例 | 平均最高涨幅 | 平均第5日涨幅 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in report.summaries:
        lines.append(
            "| "
            f"{_group_label(summary.group)} | "
            f"{summary.sample_count} | "
            f"{summary.observed_count} | "
            f"{summary.sold_too_early_count} | "
            f"{_format_optional_percent(summary.sold_too_early_rate)} | "
            f"{_format_optional_percent(summary.average_max_high_return_pct)} | "
            f"{_format_optional_percent(summary.average_fifth_day_close_return_pct)} |"
        )

    lines.extend(
        [
            "",
            "## 窗口对比",
            "",
            "| 窗口 | 分组 | 样本 | 有后续数据 | 完整窗口 | 卖飞/反弹 | 比例 | 平均最高涨幅 | 平均窗口收盘涨幅 |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in report.window_summaries:
        lines.append(
            "| "
            f"{summary.window_days} | "
            f"{_group_label(summary.group)} | "
            f"{summary.sample_count} | "
            f"{summary.observed_count} | "
            f"{summary.complete_count} | "
            f"{summary.sold_too_early_count} | "
            f"{_format_optional_percent(summary.sold_too_early_rate)} | "
            f"{_format_optional_percent(summary.average_max_high_return_pct)} | "
            f"{_format_optional_percent(summary.average_window_close_return_pct)} |"
        )

    if report.threshold_summaries:
        lines.extend(
            [
                "",
                "## 反弹阈值分层",
                "",
                "| 阈值 | 分组 | 样本 | 有后续数据 | 达到阈值 | 比例 | 平均最高涨幅 | 平均窗口收盘涨幅 |",
                "|---:|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for summary in report.threshold_summaries:
            lines.append(
                "| "
                f"{_format_percent(summary.threshold)} | "
                f"{_group_label(summary.group)} | "
                f"{summary.sample_count} | "
                f"{summary.observed_count} | "
                f"{summary.rebound_count} | "
                f"{_format_optional_percent(summary.rebound_rate)} | "
                f"{_format_optional_percent(summary.average_max_high_return_pct)} | "
                f"{_format_optional_percent(summary.average_window_close_return_pct)} |"
            )

    primary_factor_summaries = tuple(
        sorted(
            (summary for summary in report.factor_group_summaries if summary.window_days == report.window_days),
            key=_factor_group_summary_sort_key,
        )
    )
    if primary_factor_summaries:
        lines.extend(
            [
                "",
                "## 退出证据分组",
                "",
                "| 因子 | 值 | 样本 | 有后续数据 | 卖飞/反弹 | 比例 | 平均最高涨幅 | 平均窗口收盘涨幅 |",
                "|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for summary in primary_factor_summaries[:limit]:
            lines.append(
                "| "
                f"{_factor_label(summary.factor_key)} | "
                f"{_factor_value_label(summary.factor_key, summary.factor_value)} | "
                f"{summary.sample_count} | "
                f"{summary.observed_count} | "
                f"{summary.sold_too_early_count} | "
                f"{_format_optional_percent(summary.sold_too_early_rate)} | "
                f"{_format_optional_percent(summary.average_max_high_return_pct)} | "
                f"{_format_optional_percent(summary.average_window_close_return_pct)} |"
            )
        if len(primary_factor_summaries) > limit:
            lines.append("")
            lines.append(f"仅展示前 {limit} 个分组，完整分组见 `post_exit_analysis.json`。")

    sold_too_early_items = _sold_too_early_items(report)
    if sold_too_early_items:
        lines.extend(
            [
                "",
                "## 卖飞样本 Top",
                "",
                "| # | 股票 | 退出日 | 类型 | 原因 | 退出证据 | 交易收益 | 最高涨幅 | 窗口收盘涨幅 | 第5日涨幅 | 后续天数 |",
                "|---:|---|---|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for item in sold_too_early_items[:limit]:
            lines.append(
                "| "
                f"{item.trade_index} | "
                f"{item.symbol} | "
                f"{item.exit_date.isoformat()} | "
                f"{_group_label(item.exit_group)} | "
                f"{item.exit_reason} | "
                f"{_format_exit_checks(item.exit_checks)} | "
                f"{_format_percent(item.trade_return_pct)} | "
                f"{_format_optional_percent(item.max_high_return_pct)} | "
                f"{_format_optional_percent(item.primary_window_close_return_pct)} | "
                f"{_format_optional_percent(item.fifth_day_close_return_pct)} | "
                f"{item.observed_day_count} |"
            )
        if len(sold_too_early_items) > limit:
            lines.append("")
            lines.append(f"仅展示前 {limit} 条卖飞样本，完整明细见 `post_exit_analysis.json`。")

    lines.extend(
        [
            "",
            "## 交易明细",
            "",
            "| # | 股票 | 退出日 | 类型 | 原因 | 退出证据 | 交易收益 | 最高涨幅 | 第5日涨幅 | 卖飞 | 后续天数 |",
            "|---:|---|---|---|---|---|---:|---:|---:|---|---:|",
        ]
    )
    for item in report.observations[:limit]:
        lines.append(
            "| "
            f"{item.trade_index} | "
            f"{item.symbol} | "
            f"{item.exit_date.isoformat()} | "
            f"{_group_label(item.exit_group)} | "
            f"{item.exit_reason} | "
            f"{_format_exit_checks(item.exit_checks)} | "
            f"{_format_percent(item.trade_return_pct)} | "
            f"{_format_optional_percent(item.max_high_return_pct)} | "
            f"{_format_optional_percent(item.fifth_day_close_return_pct)} | "
            f"{_format_bool(item.sold_too_early)} | "
            f"{item.observed_day_count} |"
        )
    if len(report.observations) > limit:
        lines.append("")
        lines.append(f"仅展示前 {limit} 条，完整明细见 `post_exit_analysis.json`。")
    return "\n".join(lines).rstrip() + "\n"


def _trade_observation(
    *,
    index: int,
    trade: ClosedTrade,
    bars: Sequence[DailyBar],
    exit_intents_by_key: Mapping[tuple[str, date, str], deque[TradeIntent]],
    window_days: tuple[int, ...],
    primary_window_days: int,
    sold_too_early_threshold: float,
) -> PostExitTradeObservation:
    future_bars = tuple(bar for bar in bars if bar.trade_date > trade.exit_date)[:max(window_days)]
    day_observations = tuple(
        _day_observation(day_index=day_index, bar=bar, exit_price=trade.exit_price)
        for day_index, bar in enumerate(future_bars, start=1)
    )
    close_returns = tuple(day.close_return_pct for day in day_observations)
    window_observations = tuple(
        _window_observation(
            window_days=window,
            day_observations=day_observations,
            sold_too_early_threshold=sold_too_early_threshold,
        )
        for window in window_days
    )
    primary_window = _window_for(window_observations, primary_window_days)
    exit_intent = _matching_exit_intent(trade, exit_intents_by_key)
    exit_intent_type = exit_intent.intent_type.value if exit_intent is not None else None
    exit_checks, exit_values, exit_categories = _exit_evidence(exit_intent)

    return PostExitTradeObservation(
        trade_index=index,
        symbol=trade.symbol,
        outcome=_trade_outcome(trade),
        entry_date=trade.entry_date,
        exit_date=trade.exit_date,
        exit_reason=trade.exit_reason,
        exit_intent_type=exit_intent_type,
        exit_method_name=exit_intent.method_name if exit_intent is not None else None,
        exit_group=_exit_group(exit_intent),
        exit_checks=exit_checks,
        exit_values=exit_values,
        exit_categories=exit_categories,
        exit_price=trade.exit_price,
        trade_return_pct=trade.return_pct,
        observed_day_count=primary_window.observed_day_count,
        fifth_day_close_return_pct=close_returns[4] if len(close_returns) >= 5 else None,
        primary_window_close_return_pct=primary_window.window_close_return_pct,
        max_close_return_pct=primary_window.max_close_return_pct,
        max_high_return_pct=primary_window.max_high_return_pct,
        min_low_return_pct=primary_window.min_low_return_pct,
        sold_too_early=primary_window.sold_too_early,
        windows=window_observations,
        observations=day_observations,
    )


def _day_observation(*, day_index: int, bar: DailyBar, exit_price: float) -> PostExitDayObservation:
    return PostExitDayObservation(
        day_index=day_index,
        trade_date=bar.trade_date,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        close_return_pct=bar.close / exit_price - 1.0,
        high_return_pct=bar.high / exit_price - 1.0,
        low_return_pct=bar.low / exit_price - 1.0,
    )


def _window_observation(
    *,
    window_days: int,
    day_observations: Sequence[PostExitDayObservation],
    sold_too_early_threshold: float,
) -> PostExitWindowObservation:
    window = tuple(day_observations[:window_days])
    close_returns = tuple(day.close_return_pct for day in window)
    high_returns = tuple(day.high_return_pct for day in window)
    low_returns = tuple(day.low_return_pct for day in window)
    max_high_return = max(high_returns) if high_returns else None

    return PostExitWindowObservation(
        window_days=window_days,
        observed_day_count=len(window),
        complete=len(window) >= window_days,
        window_close_return_pct=close_returns[window_days - 1] if len(close_returns) >= window_days else None,
        max_close_return_pct=max(close_returns) if close_returns else None,
        max_high_return_pct=max_high_return,
        min_low_return_pct=min(low_returns) if low_returns else None,
        sold_too_early=(max_high_return > sold_too_early_threshold) if max_high_return is not None else None,
    )


def _window_for(
    windows: Sequence[PostExitWindowObservation],
    window_days: int,
) -> PostExitWindowObservation:
    for window in windows:
        if window.window_days == window_days:
            return window
    raise ValueError(f"missing post-exit window: {window_days}")


def _normalize_window_days(window_days: int | Sequence[int]) -> tuple[int, ...]:
    if isinstance(window_days, int):
        windows = (window_days,)
    else:
        windows = tuple(int(window) for window in window_days)
    if not windows:
        raise ValueError("post-exit window_days must not be empty")
    if any(window <= 0 for window in windows):
        raise ValueError("post-exit window_days must be positive")
    if len(set(windows)) != len(windows):
        raise ValueError("post-exit window_days cannot contain duplicates")
    return tuple(sorted(windows))


def _normalize_rebound_thresholds(thresholds: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(threshold) for threshold in thresholds)
    if not values:
        raise ValueError("post-exit rebound_thresholds must not be empty")
    if any(threshold < 0 for threshold in values):
        raise ValueError("post-exit rebound_thresholds must be non-negative")
    if len(set(values)) != len(values):
        raise ValueError("post-exit rebound_thresholds cannot contain duplicates")
    return tuple(sorted(values))


def _primary_window_days(windows: Sequence[int], primary_window_days: int | None) -> int:
    if primary_window_days is None:
        return 5 if 5 in windows else windows[0]
    if primary_window_days not in windows:
        raise ValueError("post-exit primary_window_days must be included in window_days")
    return primary_window_days


def _exit_intents_by_key(signal_audit: Sequence[TradeIntent]) -> dict[tuple[str, date, str], deque[TradeIntent]]:
    result: dict[tuple[str, date, str], deque[TradeIntent]] = defaultdict(deque)
    for intent in sorted(signal_audit, key=lambda value: (value.trade_date, value.symbol, value.reason_code)):
        if intent.intent_type not in {TradeIntentType.EXIT_PROFIT, TradeIntentType.EXIT_LOSS}:
            continue
        if intent.blocked_by:
            continue
        result[(intent.symbol, intent.trade_date, intent.reason_code)].append(intent)
    return result


def _exit_evidence(intent: TradeIntent | None) -> tuple[dict[str, bool], dict[str, Any], dict[str, str]]:
    if intent is None:
        return {}, {}, {}

    signal_values = intent.signal_values
    checks = _bool_mapping(signal_values.get("checks"))
    values = _numeric_mapping(signal_values, excluded_keys={"checks", "attribution", "sizing"})
    categories: dict[str, str] = {}
    attribution = signal_values.get("attribution")
    if isinstance(attribution, Mapping):
        checks.update(_bool_mapping(attribution.get("checks")))
        values.update(_numeric_mapping(attribution.get("values"), excluded_keys=set()))
        categories.update(_string_mapping(attribution.get("categories")))

    return checks, values, categories


def _bool_mapping(value: object) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, bool)
    }


def _numeric_mapping(value: object, *, excluded_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text in excluded_keys or isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            result[key_text] = float(item)
    return result


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if item is not None
    }


def _matching_exit_intent(
    trade: ClosedTrade,
    exit_intents_by_key: Mapping[tuple[str, date, str], deque[TradeIntent]],
) -> TradeIntent | None:
    intents = exit_intents_by_key.get((trade.symbol, trade.exit_date, trade.exit_reason))
    if intents:
        return intents.popleft()
    return None


def _exit_group(intent: TradeIntent | None) -> str:
    if intent is None:
        return "other"
    if intent.intent_type == TradeIntentType.EXIT_PROFIT:
        return "take_profit"
    if intent.intent_type == TradeIntentType.EXIT_LOSS:
        return "stop_loss"
    return "other"


def _trade_outcome(trade: ClosedTrade) -> str:
    if trade.return_pct > 0:
        return "win"
    if trade.return_pct < 0:
        return "loss"
    return "flat"


def _summaries(observations: Sequence[PostExitTradeObservation]) -> tuple[PostExitGroupSummary, ...]:
    groups = ("all", "take_profit", "stop_loss", "other")
    by_group: dict[str, list[PostExitTradeObservation]] = {group: [] for group in groups}
    for observation in observations:
        by_group["all"].append(observation)
        by_group.setdefault(observation.exit_group, []).append(observation)

    return tuple(
        _summary(group, tuple(items))
        for group, items in by_group.items()
        if items or group == "all"
    )


def _window_summaries(
    observations: Sequence[PostExitTradeObservation],
    window_days: Sequence[int],
) -> tuple[PostExitWindowGroupSummary, ...]:
    summaries: list[PostExitWindowGroupSummary] = []
    for window in window_days:
        by_group: dict[str, list[PostExitWindowObservation]] = {
            "all": [],
            "take_profit": [],
            "stop_loss": [],
            "other": [],
        }
        for observation in observations:
            window_observation = _window_for(observation.windows, window)
            by_group["all"].append(window_observation)
            by_group.setdefault(observation.exit_group, []).append(window_observation)
        summaries.extend(
            _window_summary(window, group, tuple(items))
            for group, items in by_group.items()
            if items or group == "all"
        )
    return tuple(summaries)


def _threshold_summaries(
    observations: Sequence[PostExitTradeObservation],
    thresholds: Sequence[float],
) -> tuple[PostExitThresholdGroupSummary, ...]:
    groups = ("all", "take_profit", "stop_loss", "other")
    summaries: list[PostExitThresholdGroupSummary] = []
    for threshold in thresholds:
        by_group: dict[str, list[PostExitTradeObservation]] = {group: [] for group in groups}
        for observation in observations:
            by_group["all"].append(observation)
            by_group.setdefault(observation.exit_group, []).append(observation)
        summaries.extend(
            _threshold_summary(threshold, group, tuple(items))
            for group, items in by_group.items()
            if items or group == "all"
        )
    return tuple(summaries)


def _threshold_summary(
    threshold: float,
    group: str,
    observations: Sequence[PostExitTradeObservation],
) -> PostExitThresholdGroupSummary:
    observed = tuple(item for item in observations if item.observed_day_count > 0)
    rebound_count = sum(
        1
        for item in observed
        if item.max_high_return_pct is not None and item.max_high_return_pct > threshold
    )
    max_high_values = tuple(item.max_high_return_pct for item in observed if item.max_high_return_pct is not None)
    window_close_values = tuple(
        item.primary_window_close_return_pct
        for item in observed
        if item.primary_window_close_return_pct is not None
    )
    return PostExitThresholdGroupSummary(
        threshold=threshold,
        group=group,
        sample_count=len(observations),
        observed_count=len(observed),
        rebound_count=rebound_count,
        rebound_rate=(rebound_count / len(observed)) if observed else None,
        average_max_high_return_pct=(sum(max_high_values) / len(max_high_values)) if max_high_values else None,
        average_window_close_return_pct=(
            sum(window_close_values) / len(window_close_values)
        ) if window_close_values else None,
    )


def _window_summary(
    window_days: int,
    group: str,
    observations: Sequence[PostExitWindowObservation],
) -> PostExitWindowGroupSummary:
    observed = tuple(item for item in observations if item.observed_day_count > 0)
    sold_too_early_count = sum(1 for item in observed if item.sold_too_early is True)
    max_high_values = tuple(item.max_high_return_pct for item in observed if item.max_high_return_pct is not None)
    window_close_values = tuple(
        item.window_close_return_pct
        for item in observed
        if item.window_close_return_pct is not None
    )
    return PostExitWindowGroupSummary(
        window_days=window_days,
        group=group,
        sample_count=len(observations),
        observed_count=len(observed),
        complete_count=sum(1 for item in observations if item.complete),
        sold_too_early_count=sold_too_early_count,
        sold_too_early_rate=(sold_too_early_count / len(observed)) if observed else None,
        average_max_high_return_pct=(sum(max_high_values) / len(max_high_values)) if max_high_values else None,
        average_window_close_return_pct=(
            sum(window_close_values) / len(window_close_values)
        ) if window_close_values else None,
    )


def _factor_group_summaries(
    observations: Sequence[PostExitTradeObservation],
) -> tuple[PostExitFactorGroupSummary, ...]:
    buckets: dict[tuple[int, str, str, str], list[PostExitWindowObservation]] = defaultdict(list)
    for observation in observations:
        factors = _factor_values(observation)
        for window in observation.windows:
            for factor_key, factor_type, factor_value in factors:
                buckets[(window.window_days, factor_key, factor_type, factor_value)].append(window)

    return tuple(
        _factor_group_summary(window_days, factor_key, factor_type, factor_value, tuple(items))
        for (window_days, factor_key, factor_type, factor_value), items in sorted(buckets.items())
    )


def _factor_values(observation: PostExitTradeObservation) -> tuple[tuple[str, str, str], ...]:
    factors: list[tuple[str, str, str]] = [
        ("exit.group", "category", observation.exit_group),
        ("trade.outcome", "category", observation.outcome),
    ]
    if observation.exit_method_name is not None:
        factors.append(("exit.method_name", "category", observation.exit_method_name))
    for key, value in sorted(observation.exit_checks.items()):
        factors.append((f"exit.check.{key}", "check", "true" if value else "false"))
    for key, value in sorted(observation.exit_categories.items()):
        factors.append((f"exit.category.{key}", "category", value))
    return tuple(factors)


def _factor_group_summary(
    window_days: int,
    factor_key: str,
    factor_type: str,
    factor_value: str,
    observations: Sequence[PostExitWindowObservation],
) -> PostExitFactorGroupSummary:
    observed = tuple(item for item in observations if item.observed_day_count > 0)
    sold_too_early_count = sum(1 for item in observed if item.sold_too_early is True)
    max_high_values = tuple(item.max_high_return_pct for item in observed if item.max_high_return_pct is not None)
    window_close_values = tuple(
        item.window_close_return_pct
        for item in observed
        if item.window_close_return_pct is not None
    )
    return PostExitFactorGroupSummary(
        window_days=window_days,
        factor_key=factor_key,
        factor_type=factor_type,
        factor_value=factor_value,
        sample_count=len(observations),
        observed_count=len(observed),
        sold_too_early_count=sold_too_early_count,
        sold_too_early_rate=(sold_too_early_count / len(observed)) if observed else None,
        average_max_high_return_pct=(sum(max_high_values) / len(max_high_values)) if max_high_values else None,
        average_window_close_return_pct=(
            sum(window_close_values) / len(window_close_values)
        ) if window_close_values else None,
    )


def _summary(group: str, observations: Sequence[PostExitTradeObservation]) -> PostExitGroupSummary:
    observed = tuple(item for item in observations if item.observed_day_count > 0)
    sold_too_early_count = sum(1 for item in observed if item.sold_too_early is True)
    max_high_values = tuple(item.max_high_return_pct for item in observed if item.max_high_return_pct is not None)
    fifth_day_values = tuple(
        item.fifth_day_close_return_pct
        for item in observed
        if item.fifth_day_close_return_pct is not None
    )
    return PostExitGroupSummary(
        group=group,
        sample_count=len(observations),
        observed_count=len(observed),
        sold_too_early_count=sold_too_early_count,
        sold_too_early_rate=(sold_too_early_count / len(observed)) if observed else None,
        average_max_high_return_pct=(sum(max_high_values) / len(max_high_values)) if max_high_values else None,
        average_fifth_day_close_return_pct=(sum(fifth_day_values) / len(fifth_day_values)) if fifth_day_values else None,
    )


def _factor_group_summary_sort_key(summary: PostExitFactorGroupSummary) -> tuple[float, int, int, int, float, str, str]:
    sold_rate = summary.sold_too_early_rate if summary.sold_too_early_rate is not None else -1.0
    average_high = summary.average_max_high_return_pct if summary.average_max_high_return_pct is not None else -1.0
    return (
        -sold_rate,
        -summary.sold_too_early_count,
        -summary.observed_count,
        -summary.sample_count,
        -average_high,
        summary.factor_key,
        summary.factor_value,
    )


def _sold_too_early_items(report: PostExitAnalysisReport) -> tuple[PostExitTradeObservation, ...]:
    return tuple(
        sorted(
            (item for item in report.observations if item.sold_too_early is True),
            key=_sold_too_early_sort_key,
        )
    )


def _sold_too_early_sort_key(item: PostExitTradeObservation) -> tuple[float, float, float, date, str]:
    max_high = item.max_high_return_pct if item.max_high_return_pct is not None else -1.0
    window_close = item.primary_window_close_return_pct if item.primary_window_close_return_pct is not None else -1.0
    return_pct = item.trade_return_pct
    return (-max_high, -window_close, return_pct, item.exit_date, item.symbol)


def _group_label(group: str) -> str:
    return {
        "all": "全部",
        "take_profit": "止盈",
        "stop_loss": "止损",
        "other": "其他",
    }.get(group, group)


def _factor_label(key: str) -> str:
    if key == "exit.group":
        return "退出类型"
    if key == "trade.outcome":
        return "交易结果"
    if key == "exit.method_name":
        return "退出方法"
    if key.startswith("exit.check."):
        return f"退出检查：{_exit_check_label(key.removeprefix('exit.check.'))}"
    if key.startswith("exit.category."):
        return f"退出分类：{_exit_check_label(key.removeprefix('exit.category.'))}"
    return key


def _exit_check_label(key: str) -> str:
    declaration = _ATTRIBUTION_DECLARATIONS.get(key)
    if declaration is not None:
        return declaration.label_zh
    return {
        "current_price_at_or_below_stop": "当前价触及止损价",
        "kdj_j_above_threshold": "KDJ J 高于阈值",
    }.get(key, key)


def _factor_value_label(key: str, value: str) -> str:
    if key == "exit.group":
        return _group_label(value)
    if key == "trade.outcome":
        return {
            "win": "盈利",
            "loss": "亏损",
            "flat": "持平",
        }.get(value, value)
    if value == "true":
        return "是"
    if value == "false":
        return "否"
    return value


def _format_exit_checks(checks: Mapping[str, bool]) -> str:
    if not checks:
        return "-"
    return "；".join(
        f"{_exit_check_label(key)}={_format_bool(value)}"
        for key, value in sorted(checks.items())[:4]
    )


def _format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_percent(value)


def _format_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return "是" if value else "否"
