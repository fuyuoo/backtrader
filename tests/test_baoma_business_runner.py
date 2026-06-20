from __future__ import annotations

from datetime import date, timedelta

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.engines.business import (
    BaomaBusinessRunConfig,
    SecondScaleOutConfirmationRule,
    run_baoma_v1_business,
)
from attbacktrader.features import ATRValue, CCIValue, IndicatorFrame, KDJValue, MACDValue, MAValue
from attbacktrader.strategies import (
    EntryAttributionContext,
    EntryAttributionEvidence,
    EntryAttributionFilterCondition,
    EntryAttributionFilterRule,
    TradeIntentType,
)


SYMBOL = "000001.SZ"


def test_baoma_business_runner_buys_at_open_from_previous_day_entry_signal() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0),
        closes=(10.0, 11.0, 10.0),
        dea_values=(0.0, 0.1, 0.2),
        ma60_values=(9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=_one_lot_config(),
    )

    buy_events = [event for event in result.lifecycle_events if event.side == "buy"]
    assert len(buy_events) == 1
    assert buy_events[0].accepted is True
    assert buy_events[0].trade_date == trade_dates[2]
    assert buy_events[0].price == pytest.approx(10.0)
    assert buy_events[0].executed_quantity == 100
    assert buy_events[0].reason_code == "BAOMA_ENTRY_TRIGGERED"
    entry_intent = next(intent for intent in result.intents if intent.reason_code == "BAOMA_ENTRY_TRIGGERED")
    assert entry_intent.signal_values["sizing"]["rule"] == "baoma_fixed_slice"
    assert entry_intent.signal_values["sizing"]["target_value"] == pytest.approx(1000.0)
    assert entry_intent.signal_values["sizing"]["price"] == pytest.approx(10.0)
    assert entry_intent.signal_values["sizing"]["requested_quantity"] == 100
    assert entry_intent.signal_values["sizing"]["business_executable_quantity"] == 100


def test_baoma_business_runner_add_on_intent_carries_sizing_evidence() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 11.0, 10.0),
        closes=(10.0, 11.0, 10.0, 10.0),
        dea_values=(0.0, 0.1, 0.2, 0.3),
        ma60_values=(9.0, 9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0, 9.0),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=BaomaBusinessRunConfig(
            total_asset_value=2_000.0,
            max_holding_count=1,
            buy_slice_fraction=1.0,
            board_lot_size=100,
        ),
    )

    buy_events = [event for event in result.lifecycle_events if event.side == "buy"]
    assert [(event.trade_date, event.executed_quantity) for event in buy_events] == [
        (trade_dates[2], 100),
        (trade_dates[3], 200),
    ]
    add_on_intent = next(intent for intent in result.intents if intent.reason_code == "BAOMA_ADD_ON_TRIGGERED")
    assert add_on_intent.signal_values["sizing"]["target_value"] == pytest.approx(2000.0)
    assert add_on_intent.signal_values["sizing"]["price"] == pytest.approx(10.0)
    assert add_on_intent.signal_values["sizing"]["requested_quantity"] == 200
    assert add_on_intent.signal_values["sizing"]["business_executable_quantity"] == 200


def test_baoma_business_runner_injects_post_trade_attribution_into_entry_add_on_and_exit() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 10.0, 9.8),
        closes=(10.0, 11.0, 9.5, 10.0, 11.0),
        dea_values=(0.0, 0.1, 0.2, 0.3, 0.4),
        ma60_values=(9.0, 9.0, 9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0, 12.0, 12.0),
    )
    context = _attribution_context_for_dates(trade_dates)

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=BaomaBusinessRunConfig(
            total_asset_value=2_000.0,
            max_holding_count=1,
            buy_slice_fraction=1.0,
            board_lot_size=100,
        ),
        entry_attribution_context=context,
    )

    entry_intent = next(intent for intent in result.intents if intent.reason_code == "BAOMA_ENTRY_TRIGGERED")
    add_on_intent = next(intent for intent in result.intents if intent.reason_code == "BAOMA_ADD_ON_TRIGGERED")
    exit_intent = next(
        intent for intent in result.intents if intent.reason_code == "BAOMA_MA25_PROFIT_EXIT_TRIGGERED"
    )

    assert entry_intent.signal_values["attribution"]["checks"]["market.hs300.bullish_trend"] is True
    assert entry_intent.signal_values["attribution"]["checks"]["symbol.ma.price_above_ma60"] is True
    assert entry_intent.signal_values["attribution"]["checks"]["symbol.macd.dea_recent_waterline"] is True
    assert entry_intent.signal_values["attribution"]["values"]["market.hs300.ma60"] == pytest.approx(3000.0)
    assert entry_intent.signal_values["attribution"]["values"]["symbol.macd.dea_waterline_age_trading_days"] == 0
    assert entry_intent.signal_values["attribution"]["categories"]["market.hs300.trend_state"] == "bullish"
    assert add_on_intent.signal_values["attribution"]["checks"]["market.hs300.bullish_trend"] is True
    assert exit_intent.signal_values["attribution"]["checks"]["market.hs300.bullish_trend"] is True
    assert exit_intent.signal_values["attribution"]["checks"]["position.profit_exit_confirmed_profitable"] is True


def test_baoma_business_runner_applies_entry_attribution_filter_before_buy() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0),
        closes=(10.0, 11.0, 10.0),
        dea_values=(0.0, 0.1, 0.2),
        ma60_values=(9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0),
    )
    evidence = EntryAttributionEvidence(categories={"market.hs300.trend_state": "bullish"})
    context = EntryAttributionContext(
        evidence_by_key={(SYMBOL, trade_date): evidence for trade_date in trade_dates},
        enabled_factor_keys=frozenset({"market.hs300.trend_state"}),
        entry_filter=EntryAttributionFilterRule(
            enabled=True,
            conditions=(
                EntryAttributionFilterCondition(
                    field="market.hs300.trend_state",
                    value="bearish",
                    action="keep",
                ),
            ),
        ),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=_one_lot_config(),
        entry_attribution_context=context,
    )

    filtered_intent = next(intent for intent in result.intents if intent.reason_code == "ENTRY_ATTRIBUTION_FILTERED")

    assert filtered_intent.intent_type == TradeIntentType.AVOID
    assert filtered_intent.blocked_by == "ENTRY_ATTRIBUTION_FILTER"
    assert filtered_intent.signal_values["entry_attribution_filter"]["failed_conditions"] == [
        "market.hs300.trend_state"
    ]
    assert [event for event in result.lifecycle_events if event.side == "buy"] == []


def test_baoma_business_runner_exits_at_close_and_injects_lifecycle_cost_for_ma25_profit_exit() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 10.0, 9.8),
        closes=(10.0, 11.0, 10.0, 10.0, 11.0),
        dea_values=(0.0, 0.1, 0.2, 0.3, 0.4),
        ma60_values=(9.0, 9.0, 9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0, 12.0, 12.0),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=_one_lot_config(),
    )

    execution_summary = [
        (event.side, event.trade_date, event.price, event.reason_code, event.executed_quantity)
        for event in result.lifecycle_events
    ]
    assert execution_summary == [
        ("buy", trade_dates[2], 10.0, "BAOMA_ENTRY_TRIGGERED", 100),
        ("sell", trade_dates[4], 11.0, "BAOMA_MA25_PROFIT_EXIT_TRIGGERED", 100),
    ]

    profit_intent = next(intent for intent in result.intents if intent.reason_code == "BAOMA_MA25_PROFIT_EXIT_TRIGGERED")
    assert profit_intent.signal_values["adjusted_remaining_cost_basis"] == pytest.approx(10.0)
    assert profit_intent.signal_values["checks"]["confirmed_profitable"] is True

    assert len(result.closed_trades) == 1
    closed_trade = result.closed_trades[0]
    assert closed_trade.entry_date == trade_dates[2]
    assert closed_trade.exit_date == trade_dates[4]
    assert closed_trade.entry_price == pytest.approx(10.0)
    assert closed_trade.exit_price == pytest.approx(11.0)
    assert result.open_positions == ()


def test_baoma_business_runner_blocks_add_on_during_ma25_exit_watch() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 11.0, 9.6),
        closes=(10.0, 11.0, 10.0, 10.0, 9.5),
        dea_values=(0.0, 0.1, 0.2, 0.3, 0.4),
        ma60_values=(9.0, 9.0, 9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0, 12.0, 12.0),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=_one_lot_config(),
    )

    buy_events = [event for event in result.lifecycle_events if event.side == "buy"]
    assert [event.trade_date for event in buy_events] == [trade_dates[2]]

    blocked_add_on = next(
        intent
        for intent in result.intents
        if intent.method_name == "baoma_add_on" and intent.trade_date == trade_dates[4]
    )
    assert blocked_add_on.intent_type == TradeIntentType.ADD_ON
    assert blocked_add_on.reason_code == "BAOMA_ADD_ON_TRIGGERED"
    assert blocked_add_on.blocked_by == "MA25_PROFIT_EXIT_WATCH"


def test_baoma_business_runner_scales_out_one_stage_per_day_and_recomputes_remaining_cost() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 10.0, 10.0),
        closes=(10.0, 11.0, 10.0, 11.0, 11.2),
        dea_values=(0.0, 0.1, 0.2, 0.3, 0.4),
        ma60_values=(9.0, 9.0, 9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0, 9.0, 9.0),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=_three_lot_config(),
    )

    execution_summary = [
        (event.side, event.trade_date, event.price, event.reason_code, event.executed_quantity)
        for event in result.lifecycle_events
    ]
    assert execution_summary == [
        ("buy", trade_dates[2], 10.0, "BAOMA_ENTRY_TRIGGERED", 300),
        ("sell", trade_dates[3], 11.0, "BAOMA_SCALE_OUT_5_PERCENT_TRIGGERED", 100),
        ("sell", trade_dates[4], 11.2, "BAOMA_SCALE_OUT_15_PERCENT_TRIGGERED", 100),
    ]
    scale_out_events = [event for event in result.lifecycle_events if event.reason_code.startswith("BAOMA_SCALE_OUT_")]
    assert [event.position_quantity_after for event in scale_out_events] == [200, 100]
    assert [event.remaining_cost_basis_after for event in scale_out_events] == pytest.approx([9.5, 7.8])

    assert result.closed_trades == ()
    assert len(result.open_positions) == 1
    open_position = result.open_positions[0]
    assert open_position.total_quantity == 100
    assert open_position.adjusted_remaining_cost_basis == pytest.approx(7.8)


def test_baoma_business_runner_full_exit_has_priority_over_scale_out() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 10.0),
        closes=(10.0, 11.0, 10.0, 11.0),
        dea_values=(0.0, 0.1, 0.2, 0.3),
        ma60_values=(9.0, 9.0, 12.0, 12.0),
        ma25_values=(9.0, 9.0, 9.0, 9.0),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=_three_lot_config(),
    )

    sell_events = [event for event in result.lifecycle_events if event.side == "sell"]
    assert len(sell_events) == 1
    assert sell_events[0].trade_date == trade_dates[3]
    assert sell_events[0].reason_code == "BAOMA_MA60_STOP_TRIGGERED"
    assert sell_events[0].executed_quantity == 300
    assert all("SCALE_OUT" not in event.reason_code for event in result.lifecycle_events)


def test_baoma_business_runner_closed_trade_return_includes_scale_out_cashflows() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 10.0, 10.0, 9.0, 9.0),
        closes=(10.0, 11.0, 10.0, 11.0, 11.2, 9.0, 8.8),
        dea_values=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
        ma60_values=(7.0, 7.0, 7.0, 7.0, 7.0, 7.0, 7.0),
        ma25_values=(9.0, 9.0, 9.0, 9.0, 9.0, 10.0, 10.0),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=_three_lot_config(),
    )

    execution_summary = [
        (event.side, event.trade_date, event.price, event.reason_code, event.executed_quantity)
        for event in result.lifecycle_events
    ]
    assert execution_summary == [
        ("buy", trade_dates[2], 10.0, "BAOMA_ENTRY_TRIGGERED", 300),
        ("sell", trade_dates[3], 11.0, "BAOMA_SCALE_OUT_5_PERCENT_TRIGGERED", 100),
        ("sell", trade_dates[4], 11.2, "BAOMA_SCALE_OUT_15_PERCENT_TRIGGERED", 100),
        ("sell", trade_dates[6], 8.8, "BAOMA_MA25_PROFIT_EXIT_TRIGGERED", 100),
    ]

    assert len(result.closed_trades) == 1
    closed_trade = result.closed_trades[0]
    assert closed_trade.entry_price == pytest.approx(10.0)
    assert closed_trade.exit_price == pytest.approx(8.8)
    assert closed_trade.entry_gross_value == pytest.approx(3000.0)
    assert closed_trade.exit_gross_value == pytest.approx(3100.0)
    assert closed_trade.net_pnl == pytest.approx(100.0)
    assert closed_trade.return_pct == pytest.approx(100.0 / 3000.0)
    assert closed_trade.return_pct != pytest.approx(8.8 / 10.0 - 1.0)


def test_baoma_business_runner_supports_atr_based_scale_out() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 10.0, 10.0),
        closes=(10.0, 11.0, 10.0, 10.6, 10.8),
        dea_values=(0.0, 0.1, 0.2, 0.3, 0.4),
        ma60_values=(9.0, 9.0, 9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0, 9.0, 9.0),
        atr_values=(0.5, 0.5, 0.5, 0.5, 0.5),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=BaomaBusinessRunConfig(
            total_asset_value=3_000.0,
            max_holding_count=1,
            buy_slice_fraction=1.0,
            board_lot_size=100,
            scale_out_mode="atr_multiple",
            first_scale_out_atr_multiple=1.0,
            second_scale_out_atr_multiple=2.0,
        ),
    )

    scale_out_events = [event for event in result.lifecycle_events if event.reason_code.startswith("BAOMA_SCALE_OUT_")]

    assert [event.reason_code for event in scale_out_events] == [
        "BAOMA_SCALE_OUT_ATR_FIRST_TRIGGERED",
        "BAOMA_SCALE_OUT_ATR_SECOND_TRIGGERED",
    ]
    assert [event.trade_date for event in scale_out_events] == [trade_dates[3], trade_dates[4]]
    assert [event.entry_signal_date for event in scale_out_events] == [trade_dates[2], trade_dates[2]]
    assert [event.entry_signal_day_atr14 for event in scale_out_events] == pytest.approx([0.5, 0.5])
    assert [event.atr_multiple for event in scale_out_events] == pytest.approx([1.0, 2.0])
    assert [event.scale_out_trigger_price for event in scale_out_events] == pytest.approx([10.5, 10.7])
    assert [event.remaining_cost_basis_before for event in scale_out_events] == pytest.approx([10.0, 9.7])


def test_baoma_business_runner_blocks_second_atr_scale_out_until_confirmation_passes() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 10.0, 10.0, 10.0),
        closes=(10.0, 11.0, 10.0, 10.6, 10.8, 11.1),
        dea_values=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5),
        ma60_values=(9.0, 9.0, 9.0, 9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0, 9.0, 9.0, 9.0),
        atr_values=(0.5, 0.5, 0.5, 0.5, 0.5, 0.5),
        boll_up_values=(10.7, 10.7, 10.7, 10.7, 10.7, 10.7),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=BaomaBusinessRunConfig(
            total_asset_value=3_000.0,
            max_holding_count=1,
            buy_slice_fraction=1.0,
            board_lot_size=100,
            scale_out_mode="atr_multiple",
            first_scale_out_atr_multiple=1.0,
            second_scale_out_atr_multiple=2.0,
            second_scale_out_confirmation=SecondScaleOutConfirmationRule(
                enabled=True,
                mode="boll_up_distance",
                min_boll_up_distance=0.03,
            ),
        ),
    )

    scale_out_events = [event for event in result.lifecycle_events if event.reason_code.startswith("BAOMA_SCALE_OUT_")]
    blocked_intents = [
        intent for intent in result.intents if intent.reason_code == "ATR_SCALE_OUT_SECOND_CONFIRMATION_BLOCKED"
    ]

    assert [event.reason_code for event in scale_out_events] == [
        "BAOMA_SCALE_OUT_ATR_FIRST_TRIGGERED",
        "BAOMA_SCALE_OUT_ATR_SECOND_TRIGGERED",
    ]
    assert [event.trade_date for event in scale_out_events] == [trade_dates[3], trade_dates[5]]
    assert len(blocked_intents) == 1
    assert blocked_intents[0].trade_date == trade_dates[4]
    assert blocked_intents[0].blocked_by == "SECOND_SCALE_OUT_CONFIRMATION"
    assert blocked_intents[0].signal_values["confirmation_mode"] == "boll_up_distance"
    assert blocked_intents[0].signal_values["confirmation_block_reason"] == "BOLL_UP_DISTANCE_BELOW_MIN"
    assert blocked_intents[0].signal_values["boll_up_distance_pct"] == pytest.approx(10.8 / 10.7 - 1.0)
    assert blocked_intents[0].signal_values["checks"]["boll_up_distance_at_or_above_min"] is False

    second_event = scale_out_events[1]
    assert second_event.confirmation_required is True
    assert second_event.confirmation_passed is True
    assert second_event.confirmation_mode == "boll_up_distance"
    assert second_event.confirmation_block_reason is None
    assert second_event.boll_up20_2 == pytest.approx(10.7)
    assert second_event.boll_up_distance_pct == pytest.approx(11.1 / 10.7 - 1.0)


def test_baoma_business_runner_records_missing_atr_for_atr_scale_out() -> None:
    bars, frame, trade_dates = _baoma_fixture(
        opens=(10.0, 12.0, 10.0, 10.0),
        closes=(10.0, 11.0, 10.0, 12.0),
        dea_values=(0.0, 0.1, 0.2, 0.3),
        ma60_values=(9.0, 9.0, 9.0, 9.0),
        ma25_values=(9.0, 9.0, 9.0, 9.0),
    )

    result = run_baoma_v1_business(
        {SYMBOL: bars},
        indicators_by_symbol={SYMBOL: frame},
        config=BaomaBusinessRunConfig(
            total_asset_value=3_000.0,
            max_holding_count=1,
            buy_slice_fraction=1.0,
            board_lot_size=100,
            scale_out_mode="atr_multiple",
            first_scale_out_atr_multiple=1.0,
            second_scale_out_atr_multiple=2.0,
        ),
    )

    missing_intents = [intent for intent in result.intents if intent.reason_code == "ATR_SCALE_OUT_ATR14_UNAVAILABLE"]
    scale_out_events = [event for event in result.lifecycle_events if event.reason_code.startswith("BAOMA_SCALE_OUT_")]

    assert len(missing_intents) == 1
    assert missing_intents[0].trade_date == trade_dates[3]
    assert missing_intents[0].signal_values["entry_signal_date"] == trade_dates[2].isoformat()
    assert missing_intents[0].signal_values["checks"]["entry_signal_day_atr14_available"] is False
    assert scale_out_events == []


def _one_lot_config() -> BaomaBusinessRunConfig:
    return BaomaBusinessRunConfig(
        total_asset_value=1_000.0,
        max_holding_count=1,
        buy_slice_fraction=1.0,
        board_lot_size=100,
    )


def _three_lot_config() -> BaomaBusinessRunConfig:
    return BaomaBusinessRunConfig(
        total_asset_value=3_000.0,
        max_holding_count=1,
        buy_slice_fraction=1.0,
        board_lot_size=100,
    )


def _attribution_context_for_dates(trade_dates: tuple[date, ...]) -> EntryAttributionContext:
    evidence = EntryAttributionEvidence(
        checks={
            "market.hs300.bullish_trend": True,
            "symbol.ma.price_above_ma25": True,
            "symbol.ma.price_above_ma60": True,
        },
        values={
            "market.hs300.close": 3100.0,
            "market.hs300.ma20": 3050.0,
            "market.hs300.ma60": 3000.0,
            "symbol.ma.ma25": 9.0,
            "symbol.ma.ma60": 9.0,
        },
        categories={"market.hs300.trend_state": "bullish"},
    )
    return EntryAttributionContext(
        evidence_by_key={(SYMBOL, trade_date): evidence for trade_date in trade_dates},
        enabled_factor_keys=frozenset(
            {
                "market.hs300.bullish_trend",
                "market.hs300.close",
                "market.hs300.ma20",
                "market.hs300.ma60",
                "market.hs300.trend_state",
                "symbol.ma.price_above_ma25",
                "symbol.ma.price_above_ma60",
                "symbol.ma.ma25",
                "symbol.ma.ma60",
            }
        ),
    )


def _baoma_fixture(
    *,
    opens: tuple[float, ...],
    closes: tuple[float, ...],
    dea_values: tuple[float, ...],
    ma60_values: tuple[float, ...],
    ma25_values: tuple[float, ...],
    atr_values: tuple[float, ...] | None = None,
    kdj_j_values: tuple[float, ...] | None = None,
    cci_values: tuple[float, ...] | None = None,
    boll_up_values: tuple[float, ...] | None = None,
) -> tuple[tuple[DailyBar, ...], IndicatorFrame, tuple[date, ...]]:
    if not (
        len(opens)
        == len(closes)
        == len(dea_values)
        == len(ma60_values)
        == len(ma25_values)
    ):
        raise ValueError("fixture sequences must have the same length")
    if atr_values is not None and len(atr_values) != len(opens):
        raise ValueError("atr_values must have the same length as fixture prices")
    if kdj_j_values is not None and len(kdj_j_values) != len(opens):
        raise ValueError("kdj_j_values must have the same length as fixture prices")
    if cci_values is not None and len(cci_values) != len(opens):
        raise ValueError("cci_values must have the same length as fixture prices")
    if boll_up_values is not None and len(boll_up_values) != len(opens):
        raise ValueError("boll_up_values must have the same length as fixture prices")

    trade_dates = tuple(date(2024, 1, 1) + timedelta(days=index) for index in range(len(opens)))
    bars = tuple(
        DailyBar(
            symbol=SYMBOL,
            trade_date=trade_date,
            open=open_price,
            high=max(open_price, close_price) + 0.5,
            low=max(0.1, min(open_price, close_price) - 0.5),
            close=close_price,
            volume=1000.0,
        )
        for trade_date, open_price, close_price in zip(trade_dates, opens, closes)
    )
    frame = IndicatorFrame(
        symbol=SYMBOL,
        macd_by_key={
            ("D", trade_date): MACDValue(line=dea, signal=dea, histogram=0.0)
            for trade_date, dea in zip(trade_dates, dea_values)
        },
        ma_by_key={
            **{
                ("D", 60, trade_date): MAValue(period=60, value=ma_value)
                for trade_date, ma_value in zip(trade_dates, ma60_values)
            },
            **{
                ("D", 25, trade_date): MAValue(period=25, value=ma_value)
                for trade_date, ma_value in zip(trade_dates, ma25_values)
            },
        },
        atr_by_key=(
            {
                ("D", 14, trade_date): ATRValue(period=14, value=atr_value)
                for trade_date, atr_value in zip(trade_dates, atr_values)
            }
            if atr_values is not None
            else None
        ),
        kdj_by_key=(
            {
                ("D", trade_date): KDJValue(k=50.0, d=50.0, j=kdj_j)
                for trade_date, kdj_j in zip(trade_dates, kdj_j_values)
            }
            if kdj_j_values is not None
            else None
        ),
        cci_by_key=(
            {
                ("D", 14, trade_date): CCIValue(period=14, value=cci_value)
                for trade_date, cci_value in zip(trade_dates, cci_values)
            }
            if cci_values is not None
            else None
        ),
        boll_up_by_key=(
            {
                ("D", 20, 2.0, trade_date): boll_up_value
                for trade_date, boll_up_value in zip(trade_dates, boll_up_values)
            }
            if boll_up_values is not None
            else None
        ),
    )
    return bars, frame, trade_dates
