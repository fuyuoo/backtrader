from datetime import date

import pytest

from attbacktrader.engines import ExecutionAuditEvent
from attbacktrader.reports import build_result_diagnostics
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.templates import ClosedTrade, Position


def test_build_result_diagnostics_summarizes_symbol_outcomes_and_blocks() -> None:
    diagnostics = build_result_diagnostics(
        symbols=("000001.SZ", "600519.SH"),
        closed_trades=(
            ClosedTrade("000001.SZ", date(2024, 1, 2), date(2024, 1, 5), 10.0, 11.0, "TAKE_PROFIT"),
            ClosedTrade("000001.SZ", date(2024, 1, 8), date(2024, 1, 10), 10.0, 9.0, "STOP_LOSS"),
        ),
        signal_audit=(
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                date(2024, 1, 2),
                "entry",
                "ENTRY",
                signal_values={
                    "kdj_j": 8.0,
                    "checks": {"kdj_j_below_threshold": True},
                    "attribution": entry_attribution_payload(
                        checks={
                            "symbol.kdj.j_below_threshold": True,
                            "symbol.ma.price_above_ma25": True,
                            "market.hs300.bullish_trend": True,
                        },
                        values={
                            "symbol.kdj.j": 8.0,
                            "symbol.ma.ma25": 9.5,
                            "market.hs300.ma20": 3100.0,
                            "market.hs300.ma60": 3000.0,
                        },
                        categories={"sizing.risk_group": "801780.SI"},
                    ),
                    "sizing": {"requested_quantity": 100, "risk_group": "801780.SI"},
                },
            ),
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                date(2024, 1, 3),
                "entry",
                "ENTRY",
                signal_values={"sizing": {"requested_quantity": 0, "blocked_by": "MAX_HOLDING_COUNT"}},
                blocked_by="MAX_HOLDING_COUNT",
            ),
            TradeIntent(
                TradeIntentType.EXIT_PROFIT,
                "000001.SZ",
                date(2024, 1, 5),
                "profit",
                "TAKE_PROFIT",
                signal_values={
                    "kdj_j": 101.0,
                    "checks": {
                        "kdj_j_above_threshold": True,
                        "current_price_at_or_below_stop": False,
                    },
                    "attribution": entry_attribution_payload(
                        checks={
                            "symbol.ma.price_above_ma25": True,
                            "market.hs300.bullish_trend": True,
                        },
                        values={
                            "symbol.ma.ma25": 9.8,
                            "market.hs300.ma20": 3100.0,
                            "market.hs300.ma60": 3000.0,
                        },
                        categories={"market.hs300.trend_state": "bullish"},
                    ),
                },
            ),
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                date(2024, 1, 8),
                "entry",
                "ENTRY",
                signal_values={
                    "attribution": entry_attribution_payload(
                        checks={
                            "symbol.kdj.j_below_threshold": True,
                            "symbol.ma.price_above_ma25": False,
                            "market.hs300.bullish_trend": False,
                        },
                        values={
                            "symbol.kdj.j": 12.0,
                            "symbol.ma.ma25": 10.5,
                            "market.hs300.ma20": 2900.0,
                            "market.hs300.ma60": 3000.0,
                        },
                        categories={"sizing.risk_group": "801780.SI"},
                    ),
                    "sizing": {"requested_quantity": 100, "risk_group": "801780.SI"},
                },
            ),
            TradeIntent(
                TradeIntentType.EXIT_LOSS,
                "000001.SZ",
                date(2024, 1, 10),
                "stop",
                "STOP_LOSS",
                signal_values={
                    "current_price": 9.0,
                    "stop_price": 9.5,
                    "checks": {"current_price_at_or_below_stop": True},
                    "attribution": entry_attribution_payload(
                        checks={
                            "symbol.ma.price_above_ma25": False,
                            "market.hs300.bullish_trend": False,
                        },
                        values={
                            "symbol.ma.ma25": 10.2,
                            "market.hs300.ma20": 2900.0,
                            "market.hs300.ma60": 3000.0,
                        },
                        categories={"market.hs300.trend_state": "bearish"},
                    ),
                },
            ),
            TradeIntent(
                TradeIntentType.ADD_ON,
                "000001.SZ",
                date(2024, 1, 3),
                "kdj_oversold_add_on",
                "KDJ_OVERSOLD_ADD_ON",
                signal_values={
                    "position_action": "add_on",
                    "attribution": entry_attribution_payload(
                        checks={"position.add_on_count_available": True},
                        values={"position.unrealized_return": 0.08},
                    ),
                    "sizing": {"requested_quantity": 100, "risk_group": "801780.SI"},
                },
            ),
            TradeIntent(
                TradeIntentType.ADD_ON,
                "000001.SZ",
                date(2024, 1, 9),
                "kdj_oversold_add_on",
                "KDJ_OVERSOLD_ADD_ON",
                signal_values={
                    "position_action": "add_on",
                    "attribution": entry_attribution_payload(
                        checks={"position.add_on_count_available": True},
                        values={"position.unrealized_return": -0.02},
                    ),
                    "sizing": {"requested_quantity": 100, "risk_group": "801780.SI"},
                },
            ),
            TradeIntent(
                TradeIntentType.ENTER,
                "600519.SH",
                date(2024, 1, 4),
                "entry",
                "ENTRY",
                signal_values={"sizing": {"requested_quantity": 50}},
            ),
        ),
        execution_audit=(
            _completed("000001.SZ", date(2024, 1, 2), "buy", 100, 1000.0, 1.0),
            _completed("000001.SZ", date(2024, 1, 5), "sell", 100, 1100.0, 2.0),
            _completed("000001.SZ", date(2024, 1, 8), "buy", 100, 1000.0, 1.0),
            _completed("000001.SZ", date(2024, 1, 10), "sell", 100, 900.0, 2.0),
            ExecutionAuditEvent(
                event_date=date(2024, 1, 4),
                signal_date=date(2024, 1, 4),
                symbol="600519.SH",
                side="buy",
                event_type="rejected",
                status="rejected",
                reason_code="ENTRY",
                requested_quantity=50,
                executable_quantity=0,
                signal_price=1600.0,
                blocked_by="BOARD_LOT_TOO_SMALL",
            ),
        ),
        open_positions=(Position("600519.SH", date(2024, 1, 4), 1600.0),),
    )

    by_symbol = {diagnostic.symbol: diagnostic for diagnostic in diagnostics.symbols}
    bank = by_symbol["000001.SZ"]
    maotai = by_symbol["600519.SH"]

    assert bank.closed_trade_count == 2
    assert bank.win_count == 1
    assert bank.loss_count == 1
    assert bank.cumulative_return == pytest.approx(-0.01)
    assert bank.realized_pnl == pytest.approx(-6.0)
    assert bank.take_profit_count == 1
    assert bank.stop_loss_count == 1
    assert bank.sizing_accepted_count == 4
    assert bank.sizing_blocked_count == 1
    assert bank.sizing_block_counts[0].reason == "MAX_HOLDING_COUNT"
    assert len(bank.winning_trade_attributions) == 1
    assert bank.winning_trade_attributions[0].entry_date == date(2024, 1, 2)
    assert bank.winning_trade_attributions[0].entry_method_name == "entry"
    assert bank.winning_trade_attributions[0].entry_values["kdj_j"] == 8.0
    assert bank.winning_trade_attributions[0].entry_values["symbol.kdj.j"] == 8.0
    assert bank.winning_trade_attributions[0].entry_checks["kdj_j_below_threshold"] is True
    assert bank.winning_trade_attributions[0].entry_checks["symbol.ma.price_above_ma25"] is True
    assert bank.winning_trade_attributions[0].sizing_context["risk_group"] == "801780.SI"
    assert bank.winning_trade_attributions[0].entry_categories["sizing.risk_group"] == "801780.SI"
    assert bank.losing_trade_attributions[0].entry_checks["symbol.ma.price_above_ma25"] is False
    assert bank.winning_entry_check_counts[0].check == "kdj_j_below_threshold"
    assert bank.winning_entry_value_averages[0].name == "kdj_j"
    assert bank.winning_entry_value_averages[0].average == pytest.approx(8.0)
    ma25_contrast = next(contrast for contrast in bank.entry_contrasts if contrast.key == "symbol.ma.price_above_ma25")
    assert ma25_contrast.factor_type == "check"
    assert ma25_contrast.win_value == pytest.approx(1.0)
    assert ma25_contrast.loss_value == pytest.approx(0.0)
    assert ma25_contrast.difference == pytest.approx(1.0)
    assert ma25_contrast.win_missing_rate == pytest.approx(0.0)
    portfolio_ma25_contrast = next(
        contrast for contrast in diagnostics.portfolio_entry_contrasts if contrast.key == "symbol.ma.price_above_ma25"
    )
    assert portfolio_ma25_contrast.difference == pytest.approx(1.0)
    assert diagnostics.portfolio_winning_entry_summary.sample_count == 1
    assert diagnostics.portfolio_losing_entry_summary.sample_count == 1
    assert bank.winning_trade_exit_attributions[0].exit_method_name == "profit"
    assert bank.winning_trade_exit_attributions[0].exit_checks["kdj_j_above_threshold"] is True
    assert bank.winning_trade_exit_attributions[0].exit_checks["market.hs300.bullish_trend"] is True
    assert bank.winning_trade_exit_attributions[0].exit_categories["market.hs300.trend_state"] == "bullish"
    assert bank.losing_trade_exit_attributions[0].exit_checks["current_price_at_or_below_stop"] is True
    assert bank.losing_trade_exit_attributions[0].exit_checks["symbol.ma.price_above_ma25"] is False
    exit_stop_contrast = next(
        contrast for contrast in bank.exit_contrasts if contrast.key == "current_price_at_or_below_stop"
    )
    assert exit_stop_contrast.win_value == pytest.approx(0.0)
    assert exit_stop_contrast.loss_value == pytest.approx(1.0)
    exit_market_contrast = next(
        contrast for contrast in bank.exit_contrasts if contrast.key == "market.hs300.bullish_trend"
    )
    assert exit_market_contrast.win_value == pytest.approx(1.0)
    assert exit_market_contrast.loss_value == pytest.approx(0.0)
    assert diagnostics.portfolio_exit_contrasts
    assert diagnostics.portfolio_add_on_signal_count == 2
    assert bank.add_on_signal_count == 2
    assert len(bank.winning_trade_add_on_attributions) == 1
    assert len(bank.losing_trade_add_on_attributions) == 1
    assert bank.winning_trade_add_on_attributions[0].entry_date == date(2024, 1, 2)
    assert bank.winning_trade_add_on_attributions[0].add_on_date == date(2024, 1, 3)
    assert bank.losing_trade_add_on_attributions[0].entry_date == date(2024, 1, 8)
    assert bank.losing_trade_add_on_attributions[0].add_on_date == date(2024, 1, 9)
    assert bank.winning_add_on_summary.sample_count == 1
    assert bank.losing_add_on_summary.sample_count == 1
    add_on_return_contrast = next(
        contrast for contrast in bank.add_on_contrasts if contrast.key == "position.unrealized_return"
    )
    assert add_on_return_contrast.factor_type == "value"
    assert add_on_return_contrast.difference == pytest.approx(0.10)
    portfolio_add_on_return_contrast = next(
        contrast
        for contrast in diagnostics.portfolio_add_on_contrasts
        if contrast.key == "position.unrealized_return"
    )
    assert portfolio_add_on_return_contrast.difference == pytest.approx(0.10)
    assert maotai.execution_rejection_count == 1
    assert maotai.execution_rejection_counts[0].reason == "BOARD_LOT_TOO_SMALL"
    assert maotai.has_open_position is True


def _completed(
    symbol: str,
    trade_date: date,
    side: str,
    quantity: int,
    gross_value: float,
    commission: float,
) -> ExecutionAuditEvent:
    return ExecutionAuditEvent(
        event_date=trade_date,
        signal_date=trade_date,
        symbol=symbol,
        side=side,
        event_type="completed",
        status="Completed",
        reason_code="REASON",
        requested_quantity=quantity,
        executable_quantity=quantity,
        signal_price=gross_value / quantity,
        executed_date=trade_date,
        executed_quantity=float(quantity),
        executed_price=gross_value / quantity,
        commission=commission,
        gross_value=gross_value,
    )
