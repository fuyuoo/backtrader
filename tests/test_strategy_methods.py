from datetime import date

import pytest

from attbacktrader.features import KDJValue, calculate_kdj
from attbacktrader.strategies import TradeIntentType
from attbacktrader.strategies.methods import FixedPercentStop, KdjOverheatedExit, KdjOversoldEntry


TRADE_DATE = date(2024, 1, 2)


def test_kdj_constant_prices_stay_neutral() -> None:
    values = calculate_kdj(
        highs=[10.0] * 9,
        lows=[10.0] * 9,
        closes=[10.0] * 9,
    )

    assert len(values) == 9
    assert values[-1].k == pytest.approx(50.0)
    assert values[-1].d == pytest.approx(50.0)
    assert values[-1].j == pytest.approx(50.0)


def test_kdj_entry_triggers_only_when_j_is_below_13() -> None:
    method = KdjOversoldEntry()

    enter_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        kdj=KDJValue(k=12.0, d=12.5, j=12.99),
    )
    assert enter_intent.intent_type == TradeIntentType.ENTER
    assert enter_intent.reason_code == "KDJ_J_BELOW_13"
    assert enter_intent.signal_values["kdj_j"] == 12.99

    hold_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        kdj=KDJValue(k=13.0, d=13.0, j=13.0),
    )
    assert hold_intent.intent_type == TradeIntentType.HOLD
    assert hold_intent.reason_code == "KDJ_J_NOT_BELOW_13"


def test_kdj_exit_triggers_only_when_j_is_above_100() -> None:
    method = KdjOverheatedExit()

    exit_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        kdj=KDJValue(k=95.0, d=90.0, j=100.01),
    )
    assert exit_intent.intent_type == TradeIntentType.EXIT_PROFIT
    assert exit_intent.reason_code == "KDJ_J_ABOVE_100"
    assert exit_intent.signal_values["threshold"] == 100.0

    hold_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        kdj=KDJValue(k=90.0, d=85.0, j=100.0),
    )
    assert hold_intent.intent_type == TradeIntentType.HOLD
    assert hold_intent.reason_code == "KDJ_J_NOT_ABOVE_100"


def test_fixed_percent_stop_triggers_at_5_percent_loss() -> None:
    method = FixedPercentStop(loss_percent=0.05)

    stop_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        entry_price=100.0,
        current_price=95.0,
    )
    assert stop_intent.intent_type == TradeIntentType.EXIT_LOSS
    assert stop_intent.reason_code == "FIXED_5_PERCENT_STOP"
    assert stop_intent.risk_price == 95.0

    hold_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        entry_price=100.0,
        current_price=95.01,
    )
    assert hold_intent.intent_type == TradeIntentType.HOLD
    assert hold_intent.reason_code == "FIXED_5_PERCENT_STOP_NOT_HIT"


def test_fixed_percent_stop_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="loss_percent"):
        FixedPercentStop(loss_percent=1.0)

    with pytest.raises(ValueError, match="entry_price"):
        FixedPercentStop().evaluate(
            symbol="000001.SZ",
            trade_date=TRADE_DATE,
            entry_price=0.0,
            current_price=95.0,
        )
