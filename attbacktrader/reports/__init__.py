"""Backtest report models and assembly helpers."""

from .assembly import build_report_from_closed_trades, build_report_from_equity_curve, build_report_from_trend_result
from .models import (
    BacktestReport,
    BenchmarkComparisonSummary,
    ExecutionCostSummary,
    ExecutionRejectionSummary,
    IndustryAttributionSummary,
    MarketRegimeSummary,
    MarketRegimeWindowSummary,
    PortfolioBehaviorSummary,
    ReturnSummary,
    RiskSummary,
    ScenarioFitSummary,
    SymbolContributionSummary,
    TradeQualitySummary,
)
from .writer import RunArtifactPaths, write_run_artifacts
from .writer import render_backtest_report_markdown

__all__ = [
    "BacktestReport",
    "BenchmarkComparisonSummary",
    "ExecutionCostSummary",
    "ExecutionRejectionSummary",
    "IndustryAttributionSummary",
    "MarketRegimeSummary",
    "MarketRegimeWindowSummary",
    "PortfolioBehaviorSummary",
    "ReturnSummary",
    "RiskSummary",
    "RunArtifactPaths",
    "ScenarioFitSummary",
    "SymbolContributionSummary",
    "TradeQualitySummary",
    "build_report_from_closed_trades",
    "build_report_from_equity_curve",
    "build_report_from_trend_result",
    "render_backtest_report_markdown",
    "write_run_artifacts",
]
