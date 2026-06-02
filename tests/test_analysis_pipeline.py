from __future__ import annotations

from datetime import date

import pytest

from attbacktrader.analysis import AnalysisEvidence, enrich_backtest_report
from attbacktrader.config import RunPlan
from attbacktrader.data import IndexBar, StockIndustryMembership
from attbacktrader.engines import ExecutionAuditEvent
from attbacktrader.reports import build_report_from_closed_trades
from attbacktrader.strategies.templates import ClosedTrade, Position


def test_enrich_backtest_report_adds_configured_analysis_sections() -> None:
    closed_trades = (
        ClosedTrade("000001.SZ", date(2024, 1, 2), date(2024, 1, 3), 10.0, 12.0, "take_profit"),
        ClosedTrade("000001.SZ", date(2024, 1, 4), date(2024, 1, 5), 10.0, 11.0, "take_profit"),
        ClosedTrade("000001.SZ", date(2024, 1, 8), date(2024, 1, 9), 10.0, 10.5, "take_profit"),
    )
    base_report = build_report_from_closed_trades(closed_trades, report_id="analysis-pipeline-test")

    report = enrich_backtest_report(
        _run_plan(),
        base_report=base_report,
        closed_trades=closed_trades,
        evidence=AnalysisEvidence(
            benchmark_bars_by_symbol={"000001.SH": _index_bars("000001.SH")},
            industry_index_bars_by_symbol={"801780.SI": _index_bars("801780.SI")},
            memberships_by_symbol={"000001.SZ": (_membership(),)},
            open_positions=(Position("000001.SZ", date(2024, 1, 10), 11.0),),
            execution_audit=(
                ExecutionAuditEvent(
                    event_date=date(2024, 1, 2),
                    signal_date=date(2024, 1, 2),
                    symbol="000001.SZ",
                    side="buy",
                    event_type="completed",
                    status="Completed",
                    reason_code="KDJ_J_BELOW_13",
                    requested_quantity=100,
                    executable_quantity=100,
                    signal_price=10.0,
                    executed_quantity=100,
                    executed_price=10.01,
                    commission=1.0,
                    slippage=0.01,
                ),
            ),
            final_cash=250000.0,
            final_value=1000000.0,
        ),
    )

    assert len(report.benchmark_comparison) == 1
    assert report.benchmark_comparison[0].benchmark_symbol == "000001.SH"
    assert len(report.industry_attribution) == 3
    assert report.market_regime is not None
    assert report.market_regime.primary_label == "hot"
    assert report.scenario_fit is not None
    assert report.scenario_fit.label == "fit"
    assert report.scenario_fit.score >= 5
    assert report.portfolio_behavior is not None
    assert report.portfolio_behavior.open_position_count == 1
    assert report.portfolio_behavior.open_symbols == ("000001.SZ",)
    assert report.portfolio_behavior.cash_ratio == pytest.approx(0.25)
    assert report.execution_costs is not None
    assert report.execution_costs.completed_count == 1
    assert report.execution_costs.total_commission == pytest.approx(1.0)
    assert report.execution_costs.total_slippage_cost == pytest.approx(1.0)


def test_enrich_backtest_report_honors_analysis_switches() -> None:
    closed_trades = (
        ClosedTrade("000001.SZ", date(2024, 1, 2), date(2024, 1, 3), 10.0, 11.0, "take_profit"),
    )
    base_report = build_report_from_closed_trades(closed_trades, report_id="analysis-disabled-test")

    report = enrich_backtest_report(
        _run_plan(analysis_enabled=False),
        base_report=base_report,
        closed_trades=closed_trades,
        evidence=AnalysisEvidence(
            benchmark_bars_by_symbol={},
            industry_index_bars_by_symbol={},
            memberships_by_symbol={},
        ),
    )

    assert report.benchmark_comparison == ()
    assert report.industry_attribution == ()
    assert report.market_regime is None
    assert report.scenario_fit is None
    assert report.portfolio_behavior is not None
    assert report.portfolio_behavior.closed_symbol_count == 1
    assert report.execution_costs is not None
    assert report.execution_costs.order_count == 0


def _run_plan(*, analysis_enabled: bool = True) -> RunPlan:
    return RunPlan.from_mapping(
        {
            "run": {
                "id": "analysis-pipeline-test",
                "from_date": "2024-01-02",
                "to_date": "2024-01-11",
            },
            "data": {
                "snapshot_root": "data/snapshots",
                "refresh_snapshots": False,
                "symbols": ["000001.SZ"],
                "benchmark_series": {"indexes": ["000001.SH"]},
                "industry_series": {"source": "SW2021", "indexes": ["801780.SI"]},
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "kdj_oversold_entry",
                "profit_taking_method": "kdj_overheated_exit",
                "stop_loss_method": "fixed_percent_stop",
                "sizing_rule": "equal_weight",
            },
            "broker": {
                "initial_cash": 1000000,
                "commission_rate": 0.0003,
                "stamp_tax_rate": 0.001,
                "transfer_fee_rate": 0.00001,
                "slippage": {"type": "percent", "value": 0.0005},
            },
            "analysis": {
                "industry_attribution": {
                    "enabled": analysis_enabled,
                    "source": "SW2021",
                    "levels": [1, 2, 3],
                },
                "market_regime": {
                    "enabled": analysis_enabled,
                    "timeframes": ["D"],
                },
                "scenario_fit": {
                    "enabled": analysis_enabled,
                    "min_trades": 3,
                },
            },
        }
    )


def _index_bars(symbol: str) -> tuple[IndexBar, ...]:
    return (
        IndexBar(symbol, date(2024, 1, 2), 100.0, 101.0, 99.0, 100.0),
        IndexBar(symbol, date(2024, 1, 3), 111.0, 112.0, 110.0, 111.0),
        IndexBar(symbol, date(2024, 1, 4), 122.0, 123.0, 121.0, 122.0),
        IndexBar(symbol, date(2024, 1, 5), 133.0, 134.0, 132.0, 133.0),
    )


def _membership() -> StockIndustryMembership:
    return StockIndustryMembership(
        symbol="000001.SZ",
        stock_name="000001.SZ",
        level1_code="801780.SI",
        level1_name="银行",
        level2_code="801783.SI",
        level2_name="股份制银行Ⅱ",
        level3_code="857831.SI",
        level3_name="股份制银行Ⅲ",
        in_date=date(1990, 1, 1),
        out_date=None,
        is_new=True,
        source="SW2021",
    )
