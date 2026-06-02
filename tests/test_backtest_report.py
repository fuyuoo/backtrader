from datetime import date
from pathlib import Path

import pytest

from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.engines import EquityCurvePoint
from attbacktrader.reports import build_report_from_equity_curve, build_report_from_trend_result
from attbacktrader.strategies.templates import TrendTemplateV1


def test_build_report_from_single_stock_golden_backtest() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    result = TrendTemplateV1().run_single_symbol(bars)

    report = build_report_from_trend_result(result, report_id="single-stock-kdj")

    assert report.report_id == "single-stock-kdj"
    assert report.trade_quality.trade_count == 2
    assert report.trade_quality.win_count == 1
    assert report.trade_quality.loss_count == 1
    assert report.trade_quality.win_rate == pytest.approx(0.5)
    assert report.trade_quality.average_win == pytest.approx(14.0 / 7.5 - 1.0)
    assert report.trade_quality.average_loss == pytest.approx(-0.05)
    assert report.trade_quality.profit_loss_ratio == pytest.approx((14.0 / 7.5 - 1.0) / 0.05)

    expected_final_equity = 1.0 * (1.0 - 0.05) * (14.0 / 7.5)
    assert report.returns.starting_equity == 1.0
    assert report.returns.final_equity == pytest.approx(expected_final_equity)
    assert report.returns.cumulative_return == pytest.approx(expected_final_equity - 1.0)
    assert report.risk.max_drawdown == pytest.approx(0.05)


def test_report_rejects_non_positive_starting_equity() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    result = TrendTemplateV1().run_single_symbol(bars)

    with pytest.raises(ValueError, match="starting_equity"):
        build_report_from_trend_result(result, report_id="bad-equity", starting_equity=0.0)


def test_build_report_from_equity_curve_uses_account_value_for_returns_and_risk() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    result = TrendTemplateV1().run_single_symbol(bars)
    equity_curve = (
        EquityCurvePoint(date(2024, 1, 2), 1000.0, 0.0, 1000.0, 0.0, 0, 0.0),
        EquityCurvePoint(date(2024, 1, 3), 990.0, 0.0, 990.0, 0.01, 0, 0.0),
        EquityCurvePoint(date(2024, 1, 4), 1100.0, 0.0, 1100.0, 0.0, 0, 0.0),
    )

    report = build_report_from_equity_curve(
        equity_curve,
        closed_trades=result.closed_trades,
        report_id="equity-curve",
        starting_equity=1000.0,
    )

    assert report.returns.final_equity == pytest.approx(1100.0)
    assert report.returns.cumulative_return == pytest.approx(0.1)
    assert report.risk.max_drawdown == pytest.approx(0.01)
    assert report.trade_quality.trade_count == 2
