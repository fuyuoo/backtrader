from datetime import date, timedelta

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.engines import ExecutionAuditEvent
from attbacktrader.reports import (
    build_post_exit_analysis,
    build_trade_review_report,
    render_trade_review_markdown_zh,
)
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies.templates import ClosedTrade


def test_trade_review_combines_lifecycle_post_exit_and_opportunity_blocks() -> None:
    bars = _bars("000001.SZ", closes=(10.0, 11.0, 12.0, 13.0, 15.0, 14.0, 16.0, 17.0, 18.0))
    trades = (
        ClosedTrade("000001.SZ", date(2024, 1, 1), date(2024, 1, 3), 10.0, 12.0, "TAKE_PROFIT"),
        ClosedTrade("000001.SZ", date(2024, 1, 5), date(2024, 1, 6), 15.0, 14.0, "STOP_LOSS"),
    )
    signal_audit = (
        _entry(date(2024, 1, 1), price_above_ma25=True),
        _add_on(date(2024, 1, 2)),
        _exit_profit(date(2024, 1, 3)),
        _entry(date(2024, 1, 5), price_above_ma25=False),
        _exit_loss(date(2024, 1, 6)),
        _entry_filter_block(date(2024, 1, 7)),
        _sizing_block(date(2024, 1, 8)),
        _board_lot_block(date(2024, 1, 9)),
    )
    execution_audit = (
        _execution(date(2024, 1, 1), "buy", "ENTRY", "completed"),
        _execution(date(2024, 1, 2), "buy", "ADD_ON", "completed"),
        _execution(date(2024, 1, 3), "sell", "TAKE_PROFIT", "completed"),
        _execution(date(2024, 1, 5), "buy", "ENTRY", "completed"),
        _execution(date(2024, 1, 6), "sell", "STOP_LOSS", "completed"),
        _execution(date(2024, 1, 9), "buy", "ENTRY", "rejected", blocked_by="BOARD_LOT_TOO_SMALL"),
    )
    post_exit = build_post_exit_analysis(
        closed_trades=trades,
        bars_by_symbol={"000001.SZ": bars},
        signal_audit=signal_audit,
        window_days=(3, 5),
        primary_window_days=3,
        sold_too_early_threshold=0.0,
    )

    report = build_trade_review_report(
        closed_trades=trades,
        signal_audit=signal_audit,
        execution_audit=execution_audit,
        post_exit_analysis=post_exit,
        bars_by_symbol={"000001.SZ": bars},
    )
    markdown = render_trade_review_markdown_zh(report)

    assert report.trade_count == 2
    assert report.sold_too_early_count == 2
    assert report.opportunity_window_days == 5
    assert report.add_on_entry_count == 1
    assert report.add_on_window_days == 5
    assert report.trades[0].add_on_count == 1
    assert report.trades[0].sold_too_early is True
    assert report.trades[0].entry_checks["symbol.ma.price_above_ma25"] is True
    assert report.trades[0].exit_checks["market.hs300.bullish_trend"] is True
    assert report.trades[1].exit_checks["current_price_at_or_below_stop"] is True
    assert report.trades[1].max_high_return_pct == pytest.approx(18.5 / 14.0 - 1.0)

    profile = report.sold_too_early_profiles[0]
    assert profile.sold_too_early_rate == pytest.approx(1.0)
    assert "exit.group=" in profile.profile_key
    stop_loss_profile = report.stop_loss_rebound_profiles[0]
    assert stop_loss_profile.threshold == pytest.approx(0.10)
    assert stop_loss_profile.rebound_count == 1
    assert stop_loss_profile.rebound_rate == pytest.approx(1.0)
    assert {summary.opportunity_group for summary in report.opportunity_summaries} == {
        "entry_filter",
        "execution_rejection",
        "sizing_block",
    }
    entry_filter = next(summary for summary in report.opportunity_summaries if summary.opportunity_group == "entry_filter")
    assert entry_filter.blocked_by == "ENTRY_ATTRIBUTION_FILTER"
    execution_rejection = next(
        summary for summary in report.opportunity_summaries if summary.opportunity_group == "execution_rejection"
    )
    assert execution_rejection.blocked_by == "BOARD_LOT_TOO_SMALL"
    assert next(sample for sample in report.opportunities if sample.opportunity_group == "entry_filter").failed_checks == (
        "market.hs300.bullish_trend",
    )
    sizing_sample = next(sample for sample in report.opportunities if sample.opportunity_group == "sizing_block")
    assert sizing_sample.opportunity_price == pytest.approx(17.0)
    assert sizing_sample.follow_up is not None
    assert sizing_sample.follow_up.observed_day_count == 1
    assert sizing_sample.follow_up.max_high_return_pct == pytest.approx(18.5 / 17.0 - 1.0)
    sizing_cost = next(
        summary for summary in report.opportunity_cost_summaries if summary.opportunity_group == "sizing_block"
    )
    assert sizing_cost.observed_count == 1
    assert sizing_cost.positive_max_high_rate == pytest.approx(1.0)
    add_on_sample = report.add_on_entry_points[0]
    assert add_on_sample.trade_index == 1
    assert add_on_sample.outcome == "win"
    assert add_on_sample.add_on_price == pytest.approx(10.0)
    assert add_on_sample.follow_up.observed_day_count == 5
    assert add_on_sample.follow_up.max_high_return_pct == pytest.approx(16.5 / 10.0 - 1.0)
    assert add_on_sample.follow_up.window_close_return_pct == pytest.approx(16.0 / 10.0 - 1.0)
    add_on_summary = report.add_on_entry_summaries[0]
    assert add_on_summary.sample_count == 1
    assert add_on_summary.positive_max_high_rate == pytest.approx(1.0)
    assert "trade.outcome=win" in add_on_summary.profile_key

    assert "# 交易复盘" in markdown
    assert "## 卖飞归因组合" in markdown
    assert "## 止损后反弹归因" in markdown
    assert "## 机会/拦截归因" in markdown
    assert "## 机会成本分层" in markdown
    assert "## 加仓入场点反查" in markdown
    assert "## 交易复盘明细" in markdown
    assert "## 机会/拦截样本" in markdown
    assert "## 加仓入场点样本" in markdown
    assert "入场归因过滤" in markdown
    assert "不足一手 (BOARD_LOT_TOO_SMALL)" in markdown
    assert "沪深300多头趋势=是" in markdown


def _entry(trade_date: date, *, price_above_ma25: bool) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.ENTER,
        "000001.SZ",
        trade_date,
        "entry",
        "ENTRY",
        signal_values={
            "attribution": entry_attribution_payload(
                checks={
                    "symbol.ma.price_above_ma25": price_above_ma25,
                    "market.hs300.bullish_trend": price_above_ma25,
                },
            ),
            "sizing": {"requested_quantity": 100},
        },
    )


def _add_on(trade_date: date) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.ADD_ON,
        "000001.SZ",
        trade_date,
        "add_on",
        "ADD_ON",
        signal_values={
            "attribution": entry_attribution_payload(
                checks={
                    "position.unrealized_return_at_or_above_min": True,
                    "position.add_on_count_available": True,
                },
            ),
            "sizing": {"requested_quantity": 100},
        },
    )


def _exit_profit(trade_date: date) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.EXIT_PROFIT,
        "000001.SZ",
        trade_date,
        "profit",
        "TAKE_PROFIT",
        signal_values={
            "checks": {"kdj_j_above_threshold": True},
            "attribution": entry_attribution_payload(
                checks={
                    "symbol.ma.bullish_trend": True,
                    "market.hs300.bullish_trend": True,
                    "industry.kdj.j_below_threshold": False,
                },
            ),
        },
    )


def _exit_loss(trade_date: date) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.EXIT_LOSS,
        "000001.SZ",
        trade_date,
        "stop",
        "STOP_LOSS",
        signal_values={
            "checks": {"current_price_at_or_below_stop": True},
            "attribution": entry_attribution_payload(
                checks={
                    "symbol.ma.bullish_trend": False,
                    "market.hs300.bullish_trend": False,
                    "industry.kdj.j_below_threshold": True,
                },
            ),
        },
    )


def _entry_filter_block(trade_date: date) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.AVOID,
        "000001.SZ",
        trade_date,
        "entry",
        "ENTRY_ATTRIBUTION_FILTERED",
        signal_values={
            "entry_attribution_filter": {
                "failed_checks": ["market.hs300.bullish_trend"],
            },
            "attribution": entry_attribution_payload(
                checks={"market.hs300.bullish_trend": False},
            ),
        },
        blocked_by="ENTRY_ATTRIBUTION_FILTER",
    )


def _sizing_block(trade_date: date) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.ENTER,
        "000001.SZ",
        trade_date,
        "entry",
        "ENTRY",
        signal_values={"sizing": {"requested_quantity": 0, "blocked_by": "MAX_HOLDING_COUNT"}},
        blocked_by="MAX_HOLDING_COUNT",
    )


def _board_lot_block(trade_date: date) -> TradeIntent:
    return TradeIntent(
        TradeIntentType.ENTER,
        "000001.SZ",
        trade_date,
        "entry",
        "ENTRY",
        signal_values={"sizing": {"requested_quantity": 99}},
        blocked_by="BOARD_LOT_TOO_SMALL",
    )


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


def _bars(symbol: str, *, closes: tuple[float, ...]) -> tuple[DailyBar, ...]:
    start_date = date(2024, 1, 1)
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=close,
            high=close + 0.5,
            low=max(0.1, close - 0.5),
            close=close,
            volume=1000.0,
        )
        for index, close in enumerate(closes)
    )
