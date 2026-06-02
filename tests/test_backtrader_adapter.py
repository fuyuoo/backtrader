from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from attbacktrader.data import TradabilityStatus
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.engines.backtrader import (
    BacktraderAShareSettings,
    BacktraderBrokerSettings,
    run_trend_template_v1_backtrader,
    run_trend_template_v1_portfolio_backtrader,
)
from attbacktrader.features import build_indicator_frame
from attbacktrader.strategies.templates import TrendTemplateV1


def test_backtrader_adapter_matches_business_golden_runner() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))

    business_result = TrendTemplateV1().run_single_symbol(bars)
    indicators = build_indicator_frame(bars)
    engine_result = run_trend_template_v1_backtrader(
        bars,
        initial_cash=1000.0,
        stake=1,
        indicators=indicators,
    )

    assert engine_result.strategy_result.closed_trades == business_result.closed_trades
    assert engine_result.strategy_result.open_position == business_result.open_position
    assert [intent.reason_code for intent in engine_result.strategy_result.intents] == [
        intent.reason_code for intent in business_result.intents
    ]

    expected_cash = 1000.0 - 8.0 + 7.6 - 7.5 + 14.0
    assert engine_result.final_cash == pytest.approx(expected_cash)
    assert engine_result.final_value == pytest.approx(expected_cash)
    assert engine_result.equity_curve[-1].cash == pytest.approx(engine_result.final_cash)
    assert engine_result.equity_curve[-1].total_value == pytest.approx(engine_result.final_value)
    assert engine_result.equity_curve[-1].holding_count == 0
    assert len(engine_result.position_snapshots) == 4


def test_backtrader_adapter_rejects_multi_symbol_input() -> None:
    bars = list(read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv")))
    bars.append(
        type(bars[0])(
            symbol="600000.SH",
            trade_date=bars[0].trade_date,
            open=10.0,
            high=10.0,
            low=10.0,
            close=10.0,
            volume=1000.0,
        )
    )

    with pytest.raises(ValueError, match="one symbol"):
        run_trend_template_v1_backtrader(bars, initial_cash=1000.0, stake=1)


def test_backtrader_adapter_applies_commission_and_slippage_settings() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    engine_result = run_trend_template_v1_backtrader(
        bars,
        initial_cash=1000.0,
        stake=1,
        indicators=build_indicator_frame(bars),
        broker_settings=BacktraderBrokerSettings(
            commission_rate=0.01,
            stamp_tax_rate=0.02,
            transfer_fee_rate=0.001,
            slippage_type="percent",
            slippage_value=0.01,
        ),
    )

    assert engine_result.strategy_result.closed_trades[0].entry_price == pytest.approx(8.0 * 1.01)
    assert engine_result.strategy_result.closed_trades[0].exit_price == pytest.approx(7.6 * 0.99)
    first_completed = next(event for event in engine_result.execution_audit if event.event_type == "completed")
    assert first_completed.side == "buy"
    assert first_completed.executed_price == pytest.approx(8.0 * 1.01)
    assert first_completed.commission == pytest.approx((8.0 * 1.01) * 0.011)
    assert first_completed.slippage == pytest.approx(0.08)
    assert {event.event_type for event in engine_result.execution_audit[:3]} == {
        "submitted",
        "accepted",
        "completed",
    }
    expected_cash = (
        1000.0
        - (8.0 * 1.01) * 1.011
        + (7.6 * 0.99) * (1.0 - 0.031)
        - (7.5 * 1.01) * 1.011
        + (14.0 * 0.99) * (1.0 - 0.031)
    )
    assert engine_result.final_cash == pytest.approx(expected_cash)


def test_backtrader_adapter_blocks_orders_below_ashare_board_lot() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    engine_result = run_trend_template_v1_backtrader(
        bars,
        initial_cash=1000.0,
        stake=99,
        indicators=build_indicator_frame(bars),
        ashare_settings=BacktraderAShareSettings(enabled=True, board_lot_size=100),
    )

    assert engine_result.strategy_result.closed_trades == ()
    assert engine_result.final_cash == pytest.approx(1000.0)
    assert {
        intent.blocked_by
        for intent in engine_result.strategy_result.intents
        if intent.blocked_by is not None
    } == {"BOARD_LOT_TOO_SMALL"}
    assert engine_result.execution_audit[0].event_type == "rejected"
    assert engine_result.execution_audit[0].blocked_by == "BOARD_LOT_TOO_SMALL"
    assert engine_result.execution_audit[0].requested_quantity == 99


def test_backtrader_adapter_blocks_limit_up_entry_from_tradability_status() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    engine_result = run_trend_template_v1_backtrader(
        bars,
        initial_cash=1000.0,
        stake=100,
        indicators=build_indicator_frame(bars),
        tradability_statuses=(
            TradabilityStatus(
                symbol="000001.SZ",
                trade_date=date(2024, 1, 3),
                is_limit_up=True,
            ),
        ),
        ashare_settings=BacktraderAShareSettings(enabled=True, board_lot_size=100),
    )

    assert any(intent.blocked_by == "LIMIT_UP_BUY_BLOCKED" for intent in engine_result.strategy_result.intents)
    assert all(trade.entry_date != date(2024, 1, 3) for trade in engine_result.strategy_result.closed_trades)


def test_backtrader_adapter_blocks_limit_down_exit_from_tradability_status() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    engine_result = run_trend_template_v1_backtrader(
        bars,
        initial_cash=1000.0,
        stake=100,
        indicators=build_indicator_frame(bars),
        tradability_statuses=(
            TradabilityStatus(
                symbol="000001.SZ",
                trade_date=date(2024, 1, 4),
                is_limit_down=True,
            ),
        ),
        ashare_settings=BacktraderAShareSettings(enabled=True, board_lot_size=100),
    )

    assert any(intent.blocked_by == "LIMIT_DOWN_SELL_BLOCKED" for intent in engine_result.strategy_result.intents)
    assert all(trade.exit_date != date(2024, 1, 4) for trade in engine_result.strategy_result.closed_trades)


def test_backtrader_adapter_blocks_suspended_entry_from_tradability_status() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    engine_result = run_trend_template_v1_backtrader(
        bars,
        initial_cash=1000.0,
        stake=100,
        indicators=build_indicator_frame(bars),
        tradability_statuses=(
            TradabilityStatus(
                symbol="000001.SZ",
                trade_date=date(2024, 1, 3),
                is_suspended=True,
            ),
        ),
        ashare_settings=BacktraderAShareSettings(enabled=True, board_lot_size=100),
    )

    assert any(intent.blocked_by == "SUSPENDED" for intent in engine_result.strategy_result.intents)


def test_backtrader_portfolio_adapter_runs_multiple_symbols_in_one_broker() -> None:
    first_symbol_bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    second_symbol_bars = tuple(replace(bar, symbol="000002.SZ") for bar in first_symbol_bars)

    engine_result = run_trend_template_v1_portfolio_backtrader(
        {
            "000001.SZ": first_symbol_bars,
            "000002.SZ": second_symbol_bars,
        },
        initial_cash=1000.0,
        stake=1,
        indicators_by_symbol={
            "000001.SZ": build_indicator_frame(first_symbol_bars),
            "000002.SZ": build_indicator_frame(second_symbol_bars),
        },
    )

    assert len(engine_result.strategy_result.closed_trades) == 4
    assert len(engine_result.strategy_result.open_positions) == 0
    assert {trade.symbol for trade in engine_result.strategy_result.closed_trades} == {"000001.SZ", "000002.SZ"}
    assert engine_result.final_cash == pytest.approx(1012.2)
    assert engine_result.final_value == pytest.approx(1012.2)
    assert len(engine_result.equity_curve) == len(first_symbol_bars)
    assert engine_result.equity_curve[-1].cash == pytest.approx(engine_result.final_cash)
    assert engine_result.equity_curve[-1].total_value == pytest.approx(engine_result.final_value)
    assert engine_result.equity_curve[-1].holding_count == 0
    assert max(point.holding_count for point in engine_result.equity_curve) == 2
    assert len(engine_result.position_snapshots) == 8
