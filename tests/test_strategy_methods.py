from datetime import date, timedelta

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.features import (
    IndicatorRequirement,
    IndicatorFrame,
    KDJValue,
    MACDValue,
    MAValue,
    MarketFeatureRow,
    MarketIndicators,
    build_indicator_snapshots_for_requirements,
    calculate_atr,
    calculate_kdj,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    join_bars_with_indicators,
)
from attbacktrader.strategies import TradeIntentType
from attbacktrader.strategies.methods import (
    AtrMultipleStop,
    BaomaAddOn,
    BaomaEntry,
    BaomaMa25ProfitExit,
    BaomaMa60Stop,
    FixedPercentStop,
    KdjOversoldAddOn,
    KdjOverheatedExit,
    KdjOversoldEntry,
    MacdBearishCrossoverExit,
    MacdBullishCrossoverEntry,
    MovingAverageBullishTrendEntry,
    MovingAverageMacdBullishConfirmationEntry,
    MovingAverageMacdWeakeningExit,
    RsiOverboughtExit,
)


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


def test_macd_constant_prices_stay_neutral() -> None:
    values = calculate_macd([10.0] * 30)

    assert len(values) == 30
    assert values[-1].line == pytest.approx(0.0)
    assert values[-1].signal == pytest.approx(0.0)
    assert values[-1].histogram == pytest.approx(0.0)


def test_windowed_indicators_do_not_fill_warmup_values() -> None:
    ma_values = calculate_sma([float(value) for value in range(1, 61)], period=60)
    rsi_values = calculate_rsi([10.0 + value for value in range(15)], period=14)
    atr_values = calculate_atr([11.0] * 14, [9.0] * 14, [10.0] * 14, period=14)

    assert ma_values[58] is None
    assert ma_values[59] is not None
    assert ma_values[59].value == pytest.approx(30.5)
    assert rsi_values[13] is None
    assert rsi_values[14] is not None
    assert rsi_values[14].value == pytest.approx(100.0)
    assert atr_values[12] is None
    assert atr_values[13] is not None
    assert atr_values[13].value == pytest.approx(2.0)


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
    assert enter_intent.signal_values["checks"]["kdj_j_below_threshold"] is True

    hold_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        kdj=KDJValue(k=13.0, d=13.0, j=13.0),
    )
    assert hold_intent.intent_type == TradeIntentType.HOLD
    assert hold_intent.reason_code == "KDJ_J_NOT_BELOW_13"


def test_kdj_add_on_triggers_only_for_profitable_existing_position() -> None:
    method = KdjOversoldAddOn(min_profit_percent=0.05, max_add_on_count=1)

    add_on_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        current_quantity=100,
        entry_price=10.0,
        current_price=10.6,
        add_on_count=0,
        kdj=KDJValue(k=12.0, d=12.5, j=12.99),
    )

    assert add_on_intent.intent_type == TradeIntentType.ADD_ON
    assert add_on_intent.reason_code == "KDJ_OVERSOLD_ADD_ON"
    assert add_on_intent.signal_values["position_action"] == "add_on"
    assert add_on_intent.signal_values["unrealized_return"] == pytest.approx(0.06)
    assert add_on_intent.signal_values["checks"] == {
        "required_values_available": True,
        "kdj_j_below_threshold": True,
        "unrealized_return_at_or_above_min": True,
        "add_on_count_available": True,
    }
    assert add_on_intent.signal_values["attribution"]["checks"]["position.add_on_count_available"] is True

    hold_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        current_quantity=100,
        entry_price=10.0,
        current_price=10.6,
        add_on_count=1,
        kdj=KDJValue(k=12.0, d=12.5, j=12.99),
    )

    assert hold_intent.intent_type == TradeIntentType.HOLD
    assert hold_intent.reason_code == "KDJ_OVERSOLD_ADD_ON_NOT_TRIGGERED"
    assert hold_intent.signal_values["checks"]["add_on_count_available"] is False


def test_macd_entry_triggers_only_on_bullish_crossover() -> None:
    method = MacdBullishCrossoverEntry()

    enter_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        previous_macd=MACDValue(line=-0.1, signal=0.0, histogram=-0.1),
        macd=MACDValue(line=0.1, signal=0.0, histogram=0.1),
    )
    assert enter_intent.intent_type == TradeIntentType.ENTER
    assert enter_intent.reason_code == "MACD_BULLISH_CROSSOVER"
    assert enter_intent.signal_values["previous_macd_line"] == -0.1
    assert enter_intent.signal_values["checks"]["bullish_crossover"] is True

    hold_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        previous_macd=MACDValue(line=0.2, signal=0.0, histogram=0.2),
        macd=MACDValue(line=0.3, signal=0.0, histogram=0.3),
    )
    assert hold_intent.intent_type == TradeIntentType.HOLD
    assert hold_intent.reason_code == "MACD_BULLISH_CROSSOVER_NOT_FOUND"


def test_ma_bullish_trend_entry_is_decision_layer_logic() -> None:
    bars = _trend_fixture_bars("000001.SZ")
    rows = _rows_for_requirements(
        bars,
        (
            IndicatorRequirement("ma20", "D"),
            IndicatorRequirement("ma60", "D"),
        ),
    )
    method = MovingAverageBullishTrendEntry()

    intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert intent.intent_type == TradeIntentType.ENTER
    assert intent.reason_code == "MA_BULLISH_TREND"
    assert intent.signal_values["ma20"] > intent.signal_values["ma60"]
    assert intent.signal_values["fast_indicator_date"] == rows[-1].trade_date.isoformat()
    assert intent.signal_values["checks"]["price_above_fast_ma"] is True


def test_ma_macd_bullish_confirmation_entry_combines_decision_layer_checks() -> None:
    bars = _trend_fixture_bars("000001.SZ")
    rows = _rows_for_requirements(
        bars,
        (
            IndicatorRequirement("ma20", "D"),
            IndicatorRequirement("ma60", "D"),
            IndicatorRequirement("macd", "D"),
        ),
    )
    method = MovingAverageMacdBullishConfirmationEntry()

    intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert intent.intent_type == TradeIntentType.ENTER
    assert intent.reason_code == "MA_MACD_BULLISH_CONFIRMATION"
    assert intent.signal_values["checks"] == {
        "required_values_available": True,
        "price_above_fast_ma": True,
        "fast_ma_above_slow_ma": True,
        "macd_line_above_signal": True,
        "macd_histogram_positive": True,
    }


def test_baoma_entry_uses_previous_day_conditions_and_dea_waterline_age() -> None:
    rows = _baoma_rows(
        closes=(10.0, 11.0, 11.0, 12.0),
        opens=(10.0, 10.5, 12.0, 12.0),
        dea_values=(0.0, 0.1, 0.2, 0.3),
        ma60_values=(9.0, 9.5, 10.0, 10.5),
    )
    method = BaomaEntry()

    intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert intent.intent_type == TradeIntentType.ENTER
    assert intent.reason_code == "BAOMA_ENTRY_TRIGGERED"
    assert intent.signal_values["signal_trade_date"] == rows[-2].trade_date.isoformat()
    assert intent.signal_values["dea_waterline_age_trading_days"] == 1
    assert intent.signal_values["checks"]["price_above_ma60"] is True
    assert intent.signal_values["checks"]["dea_recent_waterline"] is True
    assert intent.signal_values["checks"]["previous_bearish_candle"] is True


def test_baoma_entry_rejects_old_dea_waterline_cycle() -> None:
    rows = _baoma_rows(
        closes=tuple(11.0 for _ in range(18)),
        opens=tuple(12.0 for _ in range(18)),
        dea_values=(0.0,) + tuple(0.1 for _ in range(17)),
        ma60_values=tuple(10.0 for _ in range(18)),
    )
    method = BaomaEntry()

    intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert intent.intent_type == TradeIntentType.HOLD
    assert intent.reason_code == "BAOMA_ENTRY_NOT_TRIGGERED"
    assert intent.signal_values["dea_waterline_age_trading_days"] == 15
    assert intent.signal_values["checks"]["dea_recent_waterline"] is False


def test_baoma_entry_returns_unavailable_without_previous_row() -> None:
    rows = _baoma_rows(
        closes=(10.0, 11.0),
        opens=(10.0, 12.0),
        dea_values=(0.0, 0.1),
        ma60_values=(9.0, 9.0),
    )

    intent = BaomaEntry().evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=None,
    )

    assert intent.intent_type == TradeIntentType.HOLD
    assert intent.reason_code == "BAOMA_ENTRY_UNAVAILABLE"
    assert intent.signal_values["checks"]["required_values_available"] is False


def test_baoma_add_on_reuses_entry_conditions_and_blocks_ever_profitable_position() -> None:
    rows = _baoma_rows(
        closes=(10.0, 11.0, 11.0, 12.0),
        opens=(10.0, 10.5, 12.0, 12.0),
        dea_values=(0.0, 0.1, 0.2, 0.3),
        ma60_values=(9.0, 9.5, 10.0, 10.5),
    )
    method = BaomaAddOn()

    add_on_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        current_quantity=100,
        entry_price=10.0,
        current_price=12.0,
        add_on_count=1,
        ever_profitable=False,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert add_on_intent.intent_type == TradeIntentType.ADD_ON
    assert add_on_intent.reason_code == "BAOMA_ADD_ON_TRIGGERED"
    assert add_on_intent.signal_values["position_action"] == "add_on"

    blocked_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        current_quantity=100,
        entry_price=10.0,
        current_price=12.0,
        add_on_count=1,
        ever_profitable=True,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert blocked_intent.intent_type == TradeIntentType.HOLD
    assert blocked_intent.reason_code == "BAOMA_ADD_ON_NOT_TRIGGERED"
    assert blocked_intent.signal_values["checks"]["ever_profitable_block"] is True


def test_baoma_ma60_stop_requires_previous_break_and_current_confirmation() -> None:
    rows = _baoma_rows(
        closes=(12.0, 9.0, 9.5),
        opens=(12.0, 9.5, 9.8),
        dea_values=(0.0, 0.1, 0.2),
        ma60_values=(10.0, 10.0, 10.0),
    )
    method = BaomaMa60Stop()

    stop_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        entry_price=11.0,
        current_price=9.5,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert stop_intent.intent_type == TradeIntentType.EXIT_LOSS
    assert stop_intent.reason_code == "BAOMA_MA60_STOP_TRIGGERED"
    assert stop_intent.signal_values["checks"]["previous_price_below_ma"] is True
    assert stop_intent.signal_values["checks"]["current_price_below_ma"] is True

    recovered_rows = _baoma_rows(
        closes=(12.0, 9.0, 10.5),
        opens=(12.0, 9.5, 10.6),
        dea_values=(0.0, 0.1, 0.2),
        ma60_values=(10.0, 10.0, 10.0),
    )
    recovered_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=recovered_rows[-1].trade_date,
        entry_price=11.0,
        current_price=10.5,
        row=recovered_rows[-1],
        previous_row=recovered_rows[-2],
    )

    assert recovered_intent.intent_type == TradeIntentType.HOLD
    assert recovered_intent.reason_code == "BAOMA_MA60_STOP_NOT_TRIGGERED"


def test_baoma_ma25_profit_exit_requires_lifecycle_remaining_cost() -> None:
    rows = _baoma_rows(
        closes=(12.0, 9.0, 9.5),
        opens=(12.0, 9.5, 9.8),
        dea_values=(0.0, 0.1, 0.2),
        ma60_values=(10.0, 10.0, 10.0),
        ma25_values=(10.0, 10.0, 10.0),
    )
    method = BaomaMa25ProfitExit()

    unavailable = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert unavailable.intent_type == TradeIntentType.HOLD
    assert unavailable.reason_code == "BAOMA_MA25_PROFIT_EXIT_UNAVAILABLE"
    assert unavailable.signal_values["checks"]["remaining_cost_available"] is False

    exit_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
        adjusted_remaining_cost_basis=8.0,
    )

    assert exit_intent.intent_type == TradeIntentType.EXIT_PROFIT
    assert exit_intent.reason_code == "BAOMA_MA25_PROFIT_EXIT_TRIGGERED"
    assert exit_intent.signal_values["checks"]["confirmed_profitable"] is True

    not_profitable = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
        adjusted_remaining_cost_basis=10.0,
    )

    assert not_profitable.intent_type == TradeIntentType.HOLD
    assert not_profitable.reason_code == "BAOMA_MA25_PROFIT_EXIT_NOT_TRIGGERED"
    assert not_profitable.signal_values["checks"]["confirmed_profitable"] is False


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
    assert exit_intent.signal_values["checks"]["kdj_j_above_threshold"] is True

    hold_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        kdj=KDJValue(k=90.0, d=85.0, j=100.0),
    )
    assert hold_intent.intent_type == TradeIntentType.HOLD
    assert hold_intent.reason_code == "KDJ_J_NOT_ABOVE_100"


def test_macd_exit_triggers_only_on_bearish_crossover() -> None:
    method = MacdBearishCrossoverExit()

    exit_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        previous_macd=MACDValue(line=0.1, signal=0.0, histogram=0.1),
        macd=MACDValue(line=-0.1, signal=0.0, histogram=-0.1),
    )
    assert exit_intent.intent_type == TradeIntentType.EXIT_PROFIT
    assert exit_intent.reason_code == "MACD_BEARISH_CROSSOVER"
    assert exit_intent.signal_values["previous_macd_signal"] == 0.0
    assert exit_intent.signal_values["checks"]["bearish_crossover"] is True

    hold_intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=TRADE_DATE,
        previous_macd=MACDValue(line=-0.2, signal=0.0, histogram=-0.2),
        macd=MACDValue(line=-0.3, signal=0.0, histogram=-0.3),
    )
    assert hold_intent.intent_type == TradeIntentType.HOLD
    assert hold_intent.reason_code == "MACD_BEARISH_CROSSOVER_NOT_FOUND"


def test_rsi_overbought_exit_uses_indicator_value() -> None:
    bars = _trend_fixture_bars("000001.SZ")[:20]
    rows = _rows_for_requirements(bars, (IndicatorRequirement("rsi14", "D"),))
    method = RsiOverboughtExit(threshold=70.0)

    intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert intent.intent_type == TradeIntentType.EXIT_PROFIT
    assert intent.reason_code == "RSI_OVERBOUGHT"
    assert intent.signal_values["rsi14"] == pytest.approx(100.0)
    assert intent.signal_values["checks"]["rsi_at_or_above_threshold"] is True


def test_ma_macd_weakening_exit_combines_decision_layer_checks() -> None:
    bars = _weakening_fixture_bars("000001.SZ")
    rows = _rows_for_requirements(
        bars,
        (
            IndicatorRequirement("ma20", "D"),
            IndicatorRequirement("ma60", "D"),
            IndicatorRequirement("macd", "D"),
        ),
    )
    method = MovingAverageMacdWeakeningExit()

    intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert intent.intent_type == TradeIntentType.EXIT_PROFIT
    assert intent.reason_code == "MA_MACD_WEAKENING"
    assert intent.signal_values["checks"]["required_values_available"] is True
    assert (
        intent.signal_values["checks"]["price_below_fast_ma"]
        or intent.signal_values["checks"]["fast_ma_below_slow_ma"]
        or intent.signal_values["checks"]["macd_line_below_signal"]
    )


def test_atr_multiple_stop_uses_indicator_value() -> None:
    bars = _trend_fixture_bars("000001.SZ")[:20]
    rows = _rows_for_requirements(bars, (IndicatorRequirement("atr14", "D"),))
    method = AtrMultipleStop(multiple=1.0)

    intent = method.evaluate(
        symbol="000001.SZ",
        trade_date=rows[-1].trade_date,
        entry_price=20.0,
        current_price=17.0,
        row=rows[-1],
        previous_row=rows[-2],
    )

    assert intent.intent_type == TradeIntentType.EXIT_LOSS
    assert intent.reason_code == "ATR_MULTIPLE_STOP"
    assert intent.signal_values["atr14"] > 0.0
    assert intent.signal_values["checks"]["current_price_at_or_below_stop"] is True


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
    assert stop_intent.signal_values["checks"]["current_price_at_or_below_stop"] is True

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


def _rows_for_requirements(
    bars: tuple[DailyBar, ...],
    requirements: tuple[IndicatorRequirement, ...],
):
    snapshots = build_indicator_snapshots_for_requirements(bars, indicator_requirements=requirements)
    return join_bars_with_indicators(bars, snapshots, indicator_requirements=requirements)


def _trend_fixture_bars(symbol: str) -> tuple[DailyBar, ...]:
    start_date = date(2024, 1, 1)
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=10.0 + index,
            high=11.0 + index,
            low=9.0 + index,
            close=10.0 + index,
            volume=1000,
        )
        for index in range(70)
    )


def _weakening_fixture_bars(symbol: str) -> tuple[DailyBar, ...]:
    start_date = date(2024, 1, 1)
    closes = [10.0 + index * 0.5 for index in range(65)]
    closes.extend([42.0 - index * 1.4 for index in range(25)])
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


def _baoma_rows(
    *,
    closes: tuple[float, ...],
    opens: tuple[float, ...],
    dea_values: tuple[float, ...],
    ma60_values: tuple[float, ...],
    ma25_values: tuple[float, ...] | None = None,
) -> tuple[MarketFeatureRow, ...]:
    symbol = "000001.SZ"
    start_date = date(2024, 1, 1)
    trade_dates = tuple(start_date + timedelta(days=index) for index in range(len(closes)))
    bars = tuple(
        DailyBar(
            symbol=symbol,
            trade_date=trade_date,
            open=open_price,
            high=max(open_price, close_price),
            low=min(open_price, close_price),
            close=close_price,
            volume=1000,
        )
        for trade_date, open_price, close_price in zip(trade_dates, opens, closes)
    )
    ma_by_key = {
        ("D", 60, trade_date): MAValue(period=60, value=ma_value)
        for trade_date, ma_value in zip(trade_dates, ma60_values)
    }
    if ma25_values is not None:
        ma_by_key.update(
            {
                ("D", 25, trade_date): MAValue(period=25, value=ma_value)
                for trade_date, ma_value in zip(trade_dates, ma25_values)
            }
        )
    frame = IndicatorFrame(
        symbol=symbol,
        macd_by_key={
            ("D", trade_date): MACDValue(line=dea, signal=dea, histogram=0.0)
            for trade_date, dea in zip(trade_dates, dea_values)
        },
        ma_by_key=ma_by_key,
    )
    requirements = (
        IndicatorRequirement("macd", "D"),
        IndicatorRequirement("ma25", "D"),
        IndicatorRequirement("ma60", "D"),
    )
    return tuple(
        MarketFeatureRow(
            symbol=symbol,
            trade_date=bar.trade_date,
            bar=bar,
            indicators=MarketIndicators(
                symbol=symbol,
                trade_date=bar.trade_date,
                frame=frame,
                requirements=requirements,
            ),
        )
        for bar in bars
    )
