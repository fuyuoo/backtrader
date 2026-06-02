from pathlib import Path
from dataclasses import replace

import pytest

from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.strategies import TradeIntentType
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
