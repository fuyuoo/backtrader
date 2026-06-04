from attbacktrader.analysis import evaluate_scenario_fit
from attbacktrader.reports import (
    BacktestReport,
    BenchmarkComparisonSummary,
    MarketRegimeSummary,
    ReturnSummary,
    RiskSummary,
    TradeQualitySummary,
)


def test_evaluate_scenario_fit_labels_fit_when_evidence_is_strong() -> None:
    report = _report(
        trade_count=5,
        cumulative_return=0.2,
        max_drawdown=0.06,
        win_rate=0.6,
        profit_loss_ratio=1.4,
        excess_return=0.03,
    )

    fit = evaluate_scenario_fit(report, min_trades=3)

    assert fit.label == "fit"
    assert fit.score == 5
    assert "positive cumulative return" in fit.reasons
    assert not any(reason.startswith("market regime is") for reason in fit.reasons)


def test_evaluate_scenario_fit_labels_not_fit_when_evidence_is_weak() -> None:
    report = _report(
        trade_count=4,
        cumulative_return=-0.03,
        max_drawdown=0.18,
        win_rate=0.25,
        profit_loss_ratio=0.7,
        excess_return=-0.02,
    )

    fit = evaluate_scenario_fit(report, min_trades=3)

    assert fit.label == "not_fit"
    assert fit.score == 0
    assert not any(warning.startswith("market regime is") for warning in fit.warnings)


def test_evaluate_scenario_fit_requires_minimum_trade_count() -> None:
    report = _report(
        trade_count=1,
        cumulative_return=0.2,
        max_drawdown=0.02,
        win_rate=1.0,
        profit_loss_ratio=None,
        excess_return=0.05,
    )

    fit = evaluate_scenario_fit(report, min_trades=3)

    assert fit.label == "insufficient_evidence"
    assert fit.score == 0
    assert fit.reasons == ()
    assert fit.warnings == ("trade_count 1 is below minimum 3",)


def _report(
    *,
    trade_count: int,
    cumulative_return: float,
    max_drawdown: float,
    win_rate: float | None,
    profit_loss_ratio: float | None,
    excess_return: float,
) -> BacktestReport:
    return BacktestReport(
        report_id="scenario-fit-test",
        returns=ReturnSummary(
            starting_equity=1.0,
            final_equity=1.0 + cumulative_return,
            cumulative_return=cumulative_return,
        ),
        risk=RiskSummary(max_drawdown=max_drawdown),
        trade_quality=TradeQualitySummary(
            trade_count=trade_count,
            win_count=int(trade_count * (win_rate or 0)),
            loss_count=trade_count - int(trade_count * (win_rate or 0)),
            win_rate=win_rate,
            average_win=0.1 if win_rate else None,
            average_loss=-0.05 if win_rate != 1.0 else None,
            profit_loss_ratio=profit_loss_ratio,
        ),
        benchmark_comparison=(
            BenchmarkComparisonSummary(
                benchmark_symbol="000001.SH",
                strategy_return=cumulative_return,
                benchmark_return=cumulative_return - excess_return,
                excess_return=excess_return,
            ),
        ),
        market_regime=MarketRegimeSummary(
            primary_label="input_only",
            windows=(),
            benchmark_symbols=("000001.SH",),
            industry_index_symbols=("801780.SI",),
            timeframes=("D",),
        ),
    )
