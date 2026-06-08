from datetime import date

from attbacktrader.reports import (
    TradeLifecycle,
    TradeLifecycleEvent,
    TradeLifecycleIndexes,
    TradeLifecycleReport,
    build_trade_attribution_report,
    render_trade_attribution_markdown_zh,
)


def test_trade_attribution_builds_post_trade_factor_summary_without_defaulting_missing() -> None:
    lifecycle = TradeLifecycleReport(
        trade_count=2,
        indexes=TradeLifecycleIndexes(
            by_symbol=(),
            by_outcome=(),
            by_exit_reason=(),
            by_add_on_count=(),
            by_entry_check_true=(),
            by_entry_check_false=(),
            by_entry_category=(),
            by_rejection_reason=(),
        ),
        lifecycles=(
            _lifecycle(
                trade_index=1,
                outcome="win",
                return_pct=0.12,
                entry_checks={"symbol.ma.price_above_ma60": True, "market.hs300.bullish_trend": True},
                exit_checks={"symbol.ma.price_above_ma25": False},
            ),
            _lifecycle(
                trade_index=2,
                outcome="loss",
                return_pct=-0.05,
                entry_checks={"symbol.ma.price_above_ma60": True},
                exit_checks={"symbol.ma.price_above_ma25": True},
            ),
        ),
    )

    report = build_trade_attribution_report(
        lifecycle,
        selected_factor_keys=("symbol.ma.price_above_ma60", "market.hs300.bullish_trend"),
    )
    markdown = render_trade_attribution_markdown_zh(report)

    assert report.schema == "attbacktrader.trade_attribution.v1"
    assert report.trade_count == 2
    assert report.attributions[1].entry.missing_factor_keys == ("market.hs300.bullish_trend",)
    assert report.attributions[1].entry.factors[-1].missing is True

    ma60_summary = next(
        summary
        for summary in report.factor_summaries
        if summary.timing == "entry" and summary.key == "symbol.ma.price_above_ma60"
    )
    assert ma60_summary.sample_count == 2
    assert ma60_summary.missing_count == 0
    assert ma60_summary.win_rate == 0.5

    hs300_summary = next(
        summary
        for summary in report.factor_summaries
        if summary.timing == "entry" and summary.key == "market.hs300.bullish_trend"
    )
    assert hs300_summary.sample_count == 2
    assert hs300_summary.missing_count == 1
    assert hs300_summary.win_rate == 1.0
    assert "# 交易后验归因" in markdown
    assert "缺失因子显式记录为 missing" in markdown


def _lifecycle(
    *,
    trade_index: int,
    outcome: str,
    return_pct: float,
    entry_checks: dict[str, bool],
    exit_checks: dict[str, bool],
) -> TradeLifecycle:
    return TradeLifecycle(
        trade_index=trade_index,
        symbol=f"00000{trade_index}.SZ",
        outcome=outcome,
        entry_date=date(2024, 1, trade_index),
        exit_date=date(2024, 1, trade_index + 5),
        exit_reason="TEST_EXIT",
        entry_price=10.0,
        exit_price=10.0 * (1 + return_pct),
        return_pct=return_pct,
        events=(
            TradeLifecycleEvent(
                event_type="entry",
                trade_date=date(2024, 1, trade_index),
                intent_type="enter",
                method_name="test_entry",
                reason_code="TEST_ENTRY",
                blocked_by=None,
                checks=entry_checks,
                values={},
                categories={},
                sizing_context={"target_value": 10000.0},
                executions=(),
            ),
            TradeLifecycleEvent(
                event_type="exit",
                trade_date=date(2024, 1, trade_index + 5),
                intent_type="exit_profit" if outcome == "win" else "exit_loss",
                method_name="test_exit",
                reason_code="TEST_EXIT",
                blocked_by=None,
                checks=exit_checks,
                values={},
                categories={},
                sizing_context={},
                executions=(),
            ),
        ),
    )
