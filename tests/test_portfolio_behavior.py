from datetime import date

import pytest

from attbacktrader.analysis import summarize_portfolio_behavior
from attbacktrader.strategies.templates import ClosedTrade, Position


def test_summarize_portfolio_behavior_groups_trade_contributions_and_cash_ratio() -> None:
    trades = (
        ClosedTrade("000001.SZ", date(2024, 1, 2), date(2024, 1, 3), 10.0, 11.0, "take_profit"),
        ClosedTrade("000001.SZ", date(2024, 1, 4), date(2024, 1, 5), 10.0, 9.5, "stop_loss"),
        ClosedTrade("600519.SH", date(2024, 1, 8), date(2024, 1, 9), 100.0, 110.0, "take_profit"),
    )
    open_positions = (
        Position("000001.SZ", date(2024, 1, 10), 10.5),
        Position("600519.SH", date(2024, 1, 11), 105.0),
    )

    behavior = summarize_portfolio_behavior(
        trades,
        open_positions=open_positions,
        final_cash=250.0,
        final_value=1000.0,
    )

    assert behavior.open_position_count == 2
    assert behavior.open_symbols == ("000001.SZ", "600519.SH")
    assert behavior.closed_symbol_count == 2
    assert behavior.max_symbol_trade_share == pytest.approx(2 / 3)
    assert behavior.cash_ratio == pytest.approx(0.25)
    assert behavior.symbol_contributions[0].symbol == "000001.SZ"
    assert behavior.symbol_contributions[0].trade_count == 2
    assert behavior.symbol_contributions[0].cumulative_return == pytest.approx((1.1 * 0.95) - 1.0)
    assert behavior.symbol_contributions[1].symbol == "600519.SH"
    assert behavior.symbol_contributions[1].cumulative_return == pytest.approx(0.1)


def test_summarize_portfolio_behavior_allows_missing_broker_values() -> None:
    behavior = summarize_portfolio_behavior(())

    assert behavior.open_position_count == 0
    assert behavior.open_symbols == ()
    assert behavior.closed_symbol_count == 0
    assert behavior.max_symbol_trade_share is None
    assert behavior.cash_ratio is None
    assert behavior.symbol_contributions == ()
