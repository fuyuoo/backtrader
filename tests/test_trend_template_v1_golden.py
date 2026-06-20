from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.strategies import TradeIntentType
from attbacktrader.strategies.methods import (
    MacdBearishCrossoverExit,
    MacdBullishCrossoverEntry,
    MovingAverageMacdBullishConfirmationEntry,
    MovingAverageMacdWeakeningExit,
)
from attbacktrader.strategies.templates import TrendTemplateV1


def test_single_stock_kdj_golden_backtest() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))

    result = TrendTemplateV1().run_single_symbol(bars)

    assert result.open_position is None
    assert len(result.closed_trades) == 2

    stop_trade, profit_trade = result.closed_trades
    assert stop_trade.entry_date.isoformat() == "2024-01-03"
    assert stop_trade.exit_date.isoformat() == "2024-01-04"
    assert stop_trade.entry_price == 8.0
    assert stop_trade.exit_price == 7.6
    assert stop_trade.exit_reason == "FIXED_5_PERCENT_STOP"
    assert stop_trade.return_pct == pytest.approx(-0.05)

    assert profit_trade.entry_date.isoformat() == "2024-01-05"
    assert profit_trade.exit_date.isoformat() == "2024-01-10"
    assert profit_trade.entry_price == 7.5
    assert profit_trade.exit_price == 14.0
    assert profit_trade.exit_reason == "KDJ_J_ABOVE_100"
    assert profit_trade.return_pct == pytest.approx(14.0 / 7.5 - 1.0)

    intent_types = [intent.intent_type for intent in result.intents]
    reason_codes = [intent.reason_code for intent in result.intents]

    assert intent_types.count(TradeIntentType.ENTER) == 2
    assert intent_types.count(TradeIntentType.EXIT_LOSS) == 1
    assert intent_types.count(TradeIntentType.EXIT_PROFIT) == 1
    assert "KDJ_J_BELOW_13" in reason_codes
    assert "FIXED_5_PERCENT_STOP" in reason_codes
    assert "KDJ_J_ABOVE_100" in reason_codes


def test_portfolio_kdj_golden_backtest_combines_symbols() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    second_symbol_bars = tuple(replace(bar, symbol="000002.SZ") for bar in bars)

    result = TrendTemplateV1().run_portfolio(
        {
            "000001.SZ": bars,
            "000002.SZ": second_symbol_bars,
        }
    )

    assert len(result.open_positions) == 0
    assert len(result.closed_trades) == 4
    assert {trade.symbol for trade in result.closed_trades} == {"000001.SZ", "000002.SZ"}
    assert result.closed_trades[0].exit_reason == "FIXED_5_PERCENT_STOP"
    assert result.closed_trades[-1].exit_reason == "KDJ_J_ABOVE_100"


def test_single_stock_macd_methods_can_drive_template_flow() -> None:
    result = TrendTemplateV1(
        entry_method=MacdBullishCrossoverEntry(),
        profit_taking_method=MacdBearishCrossoverExit(),
    ).run_single_symbol(_macd_fixture_bars("000001.SZ"))

    reason_codes = [intent.reason_code for intent in result.intents]

    assert result.open_position is None
    assert len(result.closed_trades) == 1
    assert "MACD_BULLISH_CROSSOVER" in reason_codes
    assert result.closed_trades[0].exit_reason == "MACD_BEARISH_CROSSOVER"


def test_single_stock_ma_macd_combo_golden_intent_sequence() -> None:
    result = TrendTemplateV1(
        entry_method=MovingAverageMacdBullishConfirmationEntry(),
        profit_taking_method=MovingAverageMacdWeakeningExit(),
    ).run_single_symbol(_ma_macd_combo_fixture_bars("000001.SZ"))

    reason_codes = [intent.reason_code for intent in result.intents]
    trigger_intents = tuple(intent for intent in result.intents if intent.intent_type != TradeIntentType.HOLD)

    assert result.open_position is None
    assert len(result.closed_trades) == 1
    assert result.closed_trades[0].entry_date == date(2024, 2, 29)
    assert result.closed_trades[0].exit_date == date(2024, 4, 1)
    assert result.closed_trades[0].entry_price == pytest.approx(33.6)
    assert result.closed_trades[0].exit_price == pytest.approx(45.0)
    assert result.closed_trades[0].exit_reason == "MA_MACD_WEAKENING"
    assert [intent.reason_code for intent in trigger_intents] == [
        "MA_MACD_BULLISH_CONFIRMATION",
        "MA_MACD_WEAKENING",
    ]
    assert "MA_MACD_BULLISH_CONFIRMATION_NOT_FOUND" in reason_codes
    assert trigger_intents[0].signal_values["checks"] == {
        "required_values_available": True,
        "price_above_fast_ma": True,
        "fast_ma_above_slow_ma": True,
        "macd_line_above_signal": True,
        "macd_histogram_positive": True,
    }
    assert trigger_intents[1].signal_values["checks"]["macd_bearish_crossover"] is True


def _macd_fixture_bars(symbol: str) -> tuple[DailyBar, ...]:
    closes = (
        [10.0] * 10
        + [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0]
        + [17.0, 16.0, 15.0, 14.0, 13.0, 12.0, 11.0, 10.0]
        + [11.0, 12.0, 13.0, 14.0]
    )
    start_date = date(2024, 1, 2)
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1000,
        )
        for index, close in enumerate(closes)
    )


def _ma_macd_combo_fixture_bars(symbol: str) -> tuple[DailyBar, ...]:
    closes = [10.0 + index * 0.4 for index in range(90)]
    closes.extend([46.0 - index * 1.0 for index in range(35)])
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
