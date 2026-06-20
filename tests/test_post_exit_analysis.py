from datetime import date, timedelta

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.reports import build_post_exit_analysis, render_post_exit_analysis_markdown_zh
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.templates import ClosedTrade


def test_post_exit_analysis_marks_take_profit_sold_too_early_and_stop_loss_rebound() -> None:
    bars = _bars(
        "000001.SZ",
        closes=(10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0),
    )
    report = build_post_exit_analysis(
        closed_trades=(
            ClosedTrade("000001.SZ", date(2024, 1, 1), date(2024, 1, 2), 10.0, 11.0, "TAKE_PROFIT"),
            ClosedTrade("000001.SZ", date(2024, 1, 4), date(2024, 1, 5), 13.0, 14.0, "STOP_LOSS"),
        ),
        bars_by_symbol={"000001.SZ": bars},
        signal_audit=(
            TradeIntent(
                TradeIntentType.EXIT_PROFIT,
                "000001.SZ",
                date(2024, 1, 2),
                "profit",
                "TAKE_PROFIT",
                signal_values={
                    "kdj_j": 105.0,
                    "threshold": 100.0,
                    "checks": {"kdj_j_above_threshold": True},
                },
            ),
            TradeIntent(
                TradeIntentType.EXIT_LOSS,
                "000001.SZ",
                date(2024, 1, 5),
                "stop",
                "STOP_LOSS",
                signal_values={
                    "current_price": 14.0,
                    "stop_price": 14.5,
                    "checks": {"current_price_at_or_below_stop": True},
                },
            ),
        ),
        window_days=(3, 5),
        primary_window_days=5,
        sold_too_early_threshold=0.0,
        rebound_thresholds=(0.0, 0.30, 0.40),
    )
    markdown = render_post_exit_analysis_markdown_zh(report)

    take_profit = report.observations[0]
    stop_loss = report.observations[1]
    take_profit_summary = next(summary for summary in report.summaries if summary.group == "take_profit")
    stop_loss_summary = next(summary for summary in report.summaries if summary.group == "stop_loss")
    three_day_take_profit = next(
        summary
        for summary in report.window_summaries
        if summary.window_days == 3 and summary.group == "take_profit"
    )
    exit_check_group = next(
        summary
        for summary in report.factor_group_summaries
        if summary.window_days == 5
        and summary.factor_key == "exit.check.kdj_j_above_threshold"
        and summary.factor_value == "true"
    )
    stop_loss_40pct = next(
        summary
        for summary in report.threshold_summaries
        if summary.threshold == 0.40 and summary.group == "stop_loss"
    )

    assert report.configured_window_days == (3, 5)
    assert report.rebound_thresholds == (0.0, 0.30, 0.40)
    assert take_profit.exit_group == "take_profit"
    assert take_profit.exit_method_name == "profit"
    assert take_profit.exit_checks == {"kdj_j_above_threshold": True}
    assert take_profit.exit_values["kdj_j"] == 105.0
    assert take_profit.observed_day_count == 5
    assert take_profit.fifth_day_close_return_pct == pytest.approx(16.0 / 11.0 - 1.0)
    assert take_profit.windows[0].window_days == 3
    assert take_profit.windows[0].complete is True
    assert take_profit.windows[0].window_close_return_pct == pytest.approx(14.0 / 11.0 - 1.0)
    assert take_profit.max_high_return_pct is not None
    assert take_profit.max_high_return_pct > take_profit.fifth_day_close_return_pct
    assert take_profit.sold_too_early is True
    assert stop_loss.exit_group == "stop_loss"
    assert stop_loss.observed_day_count == 4
    assert stop_loss.fifth_day_close_return_pct is None
    assert stop_loss.sold_too_early is True
    assert take_profit_summary.sold_too_early_rate == pytest.approx(1.0)
    assert stop_loss_summary.sold_too_early_rate == pytest.approx(1.0)
    assert three_day_take_profit.complete_count == 1
    assert stop_loss_40pct.observed_count == 1
    assert stop_loss_40pct.rebound_count == 0
    assert stop_loss_40pct.rebound_rate == pytest.approx(0.0)
    assert exit_check_group.sample_count == 1
    assert exit_check_group.sold_too_early_rate == pytest.approx(1.0)
    assert "卖出后观察" in markdown
    assert "窗口对比" in markdown
    assert "反弹阈值分层" in markdown
    assert "40.00%" in markdown
    assert "退出证据分组" in markdown
    assert "卖飞样本 Top" in markdown
    assert "KDJ J 高于阈值" in markdown
    top_section_index = markdown.index("## 卖飞样本 Top")
    assert markdown.index("| 1 | 000001.SZ | 2024-01-02 |", top_section_index) < markdown.index(
        "| 2 | 000001.SZ | 2024-01-05 |",
        top_section_index,
    )


def test_post_exit_analysis_does_not_default_missing_future_bars() -> None:
    bars = _bars("000001.SZ", closes=(10.0, 9.0))
    report = build_post_exit_analysis(
        closed_trades=(ClosedTrade("000001.SZ", date(2024, 1, 1), date(2024, 1, 2), 10.0, 9.0, "STOP_LOSS"),),
        bars_by_symbol={"000001.SZ": bars},
        signal_audit=(TradeIntent(TradeIntentType.EXIT_LOSS, "000001.SZ", date(2024, 1, 2), "stop", "STOP_LOSS"),),
    )
    item = report.observations[0]

    assert item.observed_day_count == 0
    assert item.fifth_day_close_return_pct is None
    assert item.max_high_return_pct is None
    assert item.sold_too_early is None


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
            volume=1000,
        )
        for index, close in enumerate(closes)
    )
