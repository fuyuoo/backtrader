"""Rule-based scenario-fit scoring from report evidence."""

from __future__ import annotations

from statistics import fmean

from attbacktrader.reports.models import BacktestReport, ScenarioFitSummary


def evaluate_scenario_fit(report: BacktestReport, *, min_trades: int = 3) -> ScenarioFitSummary:
    if min_trades <= 0:
        raise ValueError("min_trades must be positive")

    trade_count = report.trade_quality.trade_count
    if trade_count < min_trades:
        return ScenarioFitSummary(
            label="insufficient_evidence",
            score=0,
            reasons=(),
            warnings=(f"trade_count {trade_count} is below minimum {min_trades}",),
        )

    score = 0
    reasons: list[str] = []
    warnings: list[str] = []

    if report.returns.cumulative_return > 0:
        score += 1
        reasons.append("positive cumulative return")
    else:
        warnings.append("non-positive cumulative return")

    if report.risk.max_drawdown <= 0.12:
        score += 1
        reasons.append("max drawdown within 12%")
    else:
        warnings.append("max drawdown above 12%")

    win_rate = report.trade_quality.win_rate
    if win_rate is not None and win_rate >= 0.5:
        score += 1
        reasons.append("win rate at least 50%")
    elif win_rate is not None:
        warnings.append("win rate below 50%")

    profit_loss_ratio = report.trade_quality.profit_loss_ratio
    if profit_loss_ratio is not None and profit_loss_ratio >= 1.0:
        score += 1
        reasons.append("profit/loss ratio at least 1")
    elif profit_loss_ratio is None:
        warnings.append("profit/loss ratio unavailable")
    else:
        warnings.append("profit/loss ratio below 1")

    average_excess_return = _average_excess_return(report)
    if average_excess_return is not None and average_excess_return > 0:
        score += 1
        reasons.append("positive average benchmark excess return")
    elif average_excess_return is None:
        warnings.append("benchmark comparison unavailable")
    else:
        warnings.append("average benchmark excess return is non-positive")

    return ScenarioFitSummary(
        label=_label_from_score(score),
        score=score,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def _average_excess_return(report: BacktestReport) -> float | None:
    if not report.benchmark_comparison:
        return None
    return fmean(comparison.excess_return for comparison in report.benchmark_comparison)


def _label_from_score(score: int) -> str:
    if score >= 5:
        return "fit"
    if score >= 3:
        return "conditional_fit"
    return "not_fit"
