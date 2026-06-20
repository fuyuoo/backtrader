from datetime import date

import pytest

from attbacktrader.engines.business import LifecycleExecutionEvent
from attbacktrader.features import IndicatorSnapshot
from attbacktrader.reports import build_scale_out_attribution_report


def test_scale_out_attribution_looks_up_sell_date_indicators_and_profit() -> None:
    event = LifecycleExecutionEvent(
        trade_date=date(2024, 1, 10),
        symbol="000001.SZ",
        side="sell",
        status="accepted",
        reason_code="BAOMA_SCALE_OUT_ATR_FIRST_TRIGGERED",
        requested_quantity=100,
        executed_quantity=100,
        price=11.0,
        scale_out_stage="FIVE_PERCENT",
        scale_out_mode="atr_multiple",
        entry_signal_date=date(2024, 1, 5),
        entry_signal_day_atr14=0.5,
        atr_multiple=1.0,
        scale_out_trigger_price=10.5,
        position_quantity_before=300,
        remaining_cost_value_before=3000.0,
        remaining_cost_basis_before=10.0,
        position_quantity_after=200,
        remaining_cost_value_after=1900.0,
        remaining_cost_basis_after=9.5,
    )
    snapshot = IndicatorSnapshot(
        symbol="000001.SZ",
        trade_date=date(2024, 1, 10),
        kdj_j=88.0,
        cci14=120.0,
        boll_up20_2=10.8,
    )

    report = build_scale_out_attribution_report(
        run_id="atr-test",
        lifecycle_events=(event,),
        indicator_snapshots_by_symbol={"000001.SZ": (snapshot,)},
        run_config={
            "execution": {
                "baoma": {
                    "scale_out_mode": "atr_multiple",
                    "first_scale_out_atr_multiple": 1.0,
                    "second_scale_out_atr_multiple": 2.0,
                }
            }
        },
    )

    sample = report["samples"][0]
    assert report["schema"] == "attbacktrader.scale_out_attribution.v1"
    assert report["atr_pair"] == "1_2atr"
    assert sample["scale_out_date"] == date(2024, 1, 10)
    assert sample["scale_out_stage"] == "first"
    assert sample["entry_signal_date"] == date(2024, 1, 5)
    assert sample["entry_signal_day_atr14"] == pytest.approx(0.5)
    assert sample["scale_out_return_pct_before_execution"] == pytest.approx(0.1)
    assert sample["scale_out_gross_pnl_before_execution"] == pytest.approx(100.0)
    assert sample["kdj_j"] == pytest.approx(88.0)
    assert sample["kdj_j_bucket"] == "gte_80"
    assert sample["kdj_j_fine_bucket"] == "80_100"
    assert sample["cci14"] == pytest.approx(120.0)
    assert sample["cci14_bucket"] == "gte_100"
    assert sample["cci14_fine_bucket"] == "100_150"
    assert sample["close_at_or_above_boll_up"] is True
    assert sample["boll_up_distance_pct"] == pytest.approx(11.0 / 10.8 - 1.0)
    assert sample["boll_up_distance_bucket"] == "0_3pct"
    assert report["summaries"]["overall"]["average_scale_out_return_pct_before_execution"] == pytest.approx(0.1)
    assert report["summaries"]["by_stage_kdj_cci_boll_fine"][0]["dimensions"] == {
        "scale_out_stage": "first",
        "kdj_j_fine_bucket": "80_100",
        "cci14_fine_bucket": "100_150",
        "boll_up_distance_bucket": "0_3pct",
    }


def test_scale_out_attribution_records_fine_indicator_bucket_boundaries() -> None:
    first_event = LifecycleExecutionEvent(
        trade_date=date(2024, 1, 10),
        symbol="000001.SZ",
        side="sell",
        status="accepted",
        reason_code="BAOMA_SCALE_OUT_ATR_FIRST_TRIGGERED",
        requested_quantity=100,
        executed_quantity=100,
        price=10.0,
        scale_out_stage="FIVE_PERCENT",
        scale_out_mode="atr_multiple",
        position_quantity_before=300,
        remaining_cost_value_before=2700.0,
        remaining_cost_basis_before=9.0,
        position_quantity_after=200,
        remaining_cost_value_after=1700.0,
        remaining_cost_basis_after=8.5,
    )
    second_event = LifecycleExecutionEvent(
        trade_date=date(2024, 1, 11),
        symbol="000002.SZ",
        side="sell",
        status="accepted",
        reason_code="BAOMA_SCALE_OUT_ATR_SECOND_TRIGGERED",
        requested_quantity=100,
        executed_quantity=100,
        price=10.0,
        scale_out_stage="FIFTEEN_PERCENT",
        scale_out_mode="atr_multiple",
        position_quantity_before=200,
        remaining_cost_value_before=1800.0,
        remaining_cost_basis_before=9.0,
        position_quantity_after=100,
        remaining_cost_value_after=800.0,
        remaining_cost_basis_after=8.0,
        confirmation_required=True,
        confirmation_passed=True,
        confirmation_mode="kdj_cci_boll_up_distance",
        kdj_j=125.0,
        cci14=250.0,
        boll_up20_2=9.0,
        boll_up_distance_pct=10.0 / 9.0 - 1.0,
    )
    first_snapshot = IndicatorSnapshot(
        symbol="000001.SZ",
        trade_date=date(2024, 1, 10),
        kdj_j=105.0,
        cci14=175.0,
        boll_up20_2=9.6,
    )
    second_snapshot = IndicatorSnapshot(
        symbol="000002.SZ",
        trade_date=date(2024, 1, 11),
        kdj_j=125.0,
        cci14=250.0,
        boll_up20_2=9.0,
    )

    report = build_scale_out_attribution_report(
        run_id="fine-bucket-test",
        lifecycle_events=(first_event, second_event),
        indicator_snapshots_by_symbol={
            "000001.SZ": (first_snapshot,),
            "000002.SZ": (second_snapshot,),
        },
        run_config={
            "execution": {
                "baoma": {
                    "scale_out_mode": "atr_multiple",
                    "first_scale_out_atr_multiple": 2.0,
                    "second_scale_out_atr_multiple": 4.0,
                }
            }
        },
    )

    first_sample, second_sample = report["samples"]
    assert first_sample["kdj_j_fine_bucket"] == "100_120"
    assert first_sample["cci14_fine_bucket"] == "150_200"
    assert first_sample["boll_up_distance_pct"] == pytest.approx(10.0 / 9.6 - 1.0)
    assert first_sample["boll_up_distance_bucket"] == "3_7pct"
    assert second_sample["kdj_j_fine_bucket"] == "gte_120"
    assert second_sample["confirmation_required"] is True
    assert second_sample["confirmation_passed"] is True
    assert second_sample["confirmation_mode"] == "kdj_cci_boll_up_distance"
    assert second_sample["confirmation_kdj_j"] == pytest.approx(125.0)
    assert second_sample["confirmation_cci14"] == pytest.approx(250.0)
    assert second_sample["confirmation_boll_up20_2"] == pytest.approx(9.0)
    assert second_sample["confirmation_boll_up_distance_pct"] == pytest.approx(10.0 / 9.0 - 1.0)
    assert second_sample["cci14_fine_bucket"] == "200_300"
    assert second_sample["boll_up_distance_pct"] == pytest.approx(10.0 / 9.0 - 1.0)
    assert second_sample["boll_up_distance_bucket"] == "gte_7pct"
    assert report["missing_counts"]["boll_up_distance_pct"] == 0


def test_scale_out_attribution_labels_fixed_fifteen_percent_as_second_stage() -> None:
    event = LifecycleExecutionEvent(
        trade_date=date(2024, 1, 10),
        symbol="000001.SZ",
        side="sell",
        status="accepted",
        reason_code="BAOMA_SCALE_OUT_15_PERCENT_TRIGGERED",
        requested_quantity=100,
        executed_quantity=100,
        price=11.5,
        scale_out_stage="FIFTEEN_PERCENT",
        scale_out_mode="fixed_percent",
        position_quantity_before=200,
        remaining_cost_value_before=2000.0,
        remaining_cost_basis_before=10.0,
        position_quantity_after=100,
        remaining_cost_value_after=850.0,
        remaining_cost_basis_after=8.5,
    )

    report = build_scale_out_attribution_report(
        run_id="fixed-test",
        lifecycle_events=(event,),
        indicator_snapshots_by_symbol={},
        run_config={"execution": {"baoma": {"scale_out_mode": "fixed_percent"}}},
    )

    sample = report["samples"][0]
    assert sample["reason_code"] == "BAOMA_SCALE_OUT_15_PERCENT_TRIGGERED"
    assert sample["scale_out_stage"] == "second"
    assert report["summaries"]["by_stage"][0]["dimensions"] == {"scale_out_stage": "second"}
