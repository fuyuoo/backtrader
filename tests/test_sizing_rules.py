from __future__ import annotations

from datetime import date

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.features import ATRValue, IndicatorFrame, IndicatorRequirement, MarketFeatureRow, MarketIndicators
from attbacktrader.sizing import EqualWeightSizing


def test_equal_weight_sizing_without_caps_preserves_fallback_stake() -> None:
    decision = EqualWeightSizing().size_entry(
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        price=10.0,
        cash=100000.0,
        total_value=100000.0,
        fallback_quantity=100,
    )

    assert decision.requested_quantity == 100
    assert decision.blocked_by is None
    assert decision.signal_values["fallback_quantity"] == 100


def test_equal_weight_sizing_blocks_when_max_holding_count_is_reached() -> None:
    decision = EqualWeightSizing(max_holding_count=1).size_entry(
        symbol="000002.SZ",
        trade_date=date(2024, 1, 2),
        price=10.0,
        cash=100000.0,
        total_value=100000.0,
        current_holding_count=1,
        fallback_quantity=100,
    )

    assert decision.requested_quantity == 0
    assert decision.blocked_by == "MAX_HOLDING_COUNT"


def test_equal_weight_sizing_applies_cash_reserve_and_position_cap() -> None:
    decision = EqualWeightSizing(
        max_position_percent=0.2,
        cash_reserve_percent=0.1,
    ).size_entry(
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        price=10.0,
        cash=15000.0,
        total_value=100000.0,
        fallback_quantity=10000,
    )

    assert decision.requested_quantity == 500
    assert decision.target_value == pytest.approx(20000.0)
    assert decision.available_cash == pytest.approx(5000.0)


def test_equal_weight_sizing_applies_atr_risk_cap_and_declares_indicator_requirement() -> None:
    sizing = EqualWeightSizing(atr_risk_percent=0.01, atr_multiple=2.0)
    decision = sizing.size_entry(
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        price=10.0,
        cash=100000.0,
        total_value=100000.0,
        fallback_quantity=10000,
        row=_feature_row(atr14=2.0),
    )

    assert sizing.required_indicators == frozenset({IndicatorRequirement("atr14", "D")})
    assert decision.requested_quantity == 250
    assert decision.risk_budget_value == pytest.approx(1000.0)
    assert decision.risk_per_share == pytest.approx(4.0)


def test_equal_weight_sizing_blocks_atr_risk_when_atr_is_unavailable() -> None:
    decision = EqualWeightSizing(atr_risk_percent=0.01).size_entry(
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        price=10.0,
        cash=100000.0,
        total_value=100000.0,
        fallback_quantity=100,
    )

    assert decision.requested_quantity == 0
    assert decision.blocked_by == "ATR_RISK_UNAVAILABLE"


def test_equal_weight_sizing_applies_total_exposure_cap() -> None:
    decision = EqualWeightSizing(max_total_exposure_percent=0.5).size_entry(
        symbol="000002.SZ",
        trade_date=date(2024, 1, 2),
        price=10.0,
        cash=100000.0,
        total_value=100000.0,
        fallback_quantity=10000,
        current_exposure_value=45000.0,
    )

    assert decision.requested_quantity == 500
    assert decision.max_total_exposure_value == pytest.approx(50000.0)


def test_equal_weight_sizing_applies_risk_group_exposure_cap() -> None:
    decision = EqualWeightSizing(max_risk_group_exposure_percent=0.3).size_entry(
        symbol="000002.SZ",
        trade_date=date(2024, 1, 2),
        price=10.0,
        cash=100000.0,
        total_value=100000.0,
        fallback_quantity=10000,
        current_risk_group_exposure_value=25000.0,
        risk_group="801780.SI",
    )

    assert decision.requested_quantity == 500
    assert decision.max_risk_group_exposure_value == pytest.approx(30000.0)
    assert decision.signal_values["risk_group"] == "801780.SI"


def test_equal_weight_sizing_applies_turnover_cap() -> None:
    decision = EqualWeightSizing(max_turnover_percent=0.1).size_entry(
        symbol="000002.SZ",
        trade_date=date(2024, 1, 2),
        price=10.0,
        cash=100000.0,
        total_value=100000.0,
        fallback_quantity=10000,
        current_turnover_value=8000.0,
    )

    assert decision.requested_quantity == 200
    assert decision.turnover_budget_value == pytest.approx(10000.0)


def test_equal_weight_sizing_blocks_before_rebalance_interval_elapses() -> None:
    decision = EqualWeightSizing(rebalance_min_interval_days=5).size_entry(
        symbol="000001.SZ",
        trade_date=date(2024, 1, 4),
        price=10.0,
        cash=100000.0,
        total_value=100000.0,
        fallback_quantity=100,
        last_rebalance_date=date(2024, 1, 2),
    )

    assert decision.requested_quantity == 0
    assert decision.blocked_by == "REBALANCE_INTERVAL"
    assert decision.signal_values["elapsed_days"] == 2


def _feature_row(*, atr14: float) -> MarketFeatureRow:
    trade_date = date(2024, 1, 2)
    bar = DailyBar("000001.SZ", trade_date, 10.0, 11.0, 9.0, 10.0, 1000.0)
    frame = IndicatorFrame(
        symbol="000001.SZ",
        atr_by_key={("D", 14, trade_date): ATRValue(14, atr14)},
    )
    return MarketFeatureRow(
        symbol="000001.SZ",
        trade_date=trade_date,
        bar=bar,
        indicators=MarketIndicators(
            symbol="000001.SZ",
            trade_date=trade_date,
            frame=frame,
            requirements=(IndicatorRequirement("atr14", "D"),),
        ),
    )
